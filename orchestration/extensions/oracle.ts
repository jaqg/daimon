/**
 * oracle.ts — one-shot premium-model lane for pi.
 *
 * Why this exists: `advisor` (rpiv-advisor) makes its reviewer side-call without pi's
 * `x-opencode-session` header, and the OpenCode Go gateway rejects headerless requests:
 *     400 {"type":"MissingSessionID","message":"Request is missing x-opencode-session ..."}
 * So the escalation model cannot be reached from inside a session through that path.
 *
 * This extension reaches it through a child `pi --print` instead. That is a real pi session,
 * so it carries its own session header, and it costs the brain tier nothing extra: the answer
 * enters this context exactly ONCE, as a custom message, instead of being re-billed forever as
 * chat history.
 *
 * Usage:
 *   /oracle <question>                  → uses OPENCODE_GO_ORACLE_MODEL or opencode-go/glm-5.3
 *   /oracle --model opencode-go/kimi-k3 --thinking max <question>
 *
 * Budget rule (enforced by habit, not by code): one call per planning cycle. A call costs
 * ~12-30K premium-model input tokens (~$0.02-0.05) plus the answer's tokens in this context.
 */

import { spawnSync } from "node:child_process";

const DEFAULT_MODEL = process.env.OPENCODE_GO_ORACLE_MODEL || "opencode-go/glm-5.3";
const DEFAULT_THINKING = process.env.OPENCODE_GO_ORACLE_THINKING || "high";
const TIMEOUT_MS = Number(process.env.OPENCODE_GO_ORACLE_TIMEOUT || 600_000);

type Parsed = { model: string; thinking: string; question: string };

function parseArgs(args: string): Parsed | null {
	let model = DEFAULT_MODEL;
	let thinking = DEFAULT_THINKING;
	const tokens = args.trim().split(/\s+/);
	const rest: string[] = [];
	for (let i = 0; i < tokens.length; i++) {
		if (tokens[i] === "--model" && tokens[i + 1]) model = tokens[++i];
		else if (tokens[i] === "--thinking" && tokens[i + 1]) thinking = tokens[++i];
		else rest.push(tokens[i]);
	}
	const question = rest.join(" ").trim();
	if (!question) return null;
	return { model, thinking, question };
}

export default function (pi: any) {
	pi.registerCommand("oracle", {
		description: `One-shot ask to the premium lane (default ${DEFAULT_MODEL}:${DEFAULT_THINKING}). Escalate on repetition, not on effort.`,
		async handler(args: string, ctx: any) {
			const parsed = parseArgs(args || "");
			if (!parsed) {
				ctx.ui.notify("usage: /oracle [--model provider/id] [--thinking level] <question>", "warning");
				return;
			}
			const { model, thinking, question } = parsed;

			// No input array: the question arrives as the prompt argument, so nothing is echoed
			// back as a user turn. stdout is the reviewer's answer; stderr is diagnostics only.
			ctx.ui.notify(`oracle → ${model}:${thinking} …`, "info");
			const res = spawnSync("pi", ["--model", model, "--thinking", thinking, "--no-session", "--print", question], {
				encoding: "utf8",
				timeout: TIMEOUT_MS,
				maxBuffer: 32 * 1024 * 1024,
				env: { ...process.env, PI_ORACLE_CHILD: "1" },
			});

			if (res.error || res.status !== 0) {
				const detail = (res.stderr || res.error?.message || "").split("\n").filter(Boolean).slice(-3).join(" | ");
				ctx.ui.notify(`oracle failed (exit ${res.status}): ${detail.slice(0, 300)}`, "error");
				return;
			}

			const answer = (res.stdout || "").trim();
			if (!answer) {
				ctx.ui.notify("oracle returned an empty answer", "warning");
				return;
			}

			// Enter context on the next turn: the reviewer is advisory, it does not steer mid-flight.
			await pi.sendMessage(
				{
					customType: "oracle",
					content: `ORACLE (${model}:${thinking}) — one-shot escalation, not a participant in this session.\n\nQUESTION: ${question}\n\nANSWER:\n${answer}\n\nTreat this as external review: reconcile it against your plan before acting, and log any place you disagree.`,
					display: true,
					details: { model, thinking, question },
				},
				{ triggerTurn: false, deliverAs: "nextTurn" },
			);
			ctx.ui.notify(`oracle answered (${answer.length} chars) — enters context next turn`, "info");
		},
	});
}
