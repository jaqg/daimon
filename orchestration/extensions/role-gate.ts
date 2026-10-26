/**
 * Role Gate Extension
 * ------------------
 * Mechanical enforcement of the agent-tier rules in
 * Design rationale: the bad-habits note in the operator's private vault memory (not published).
 *
 * A "role" is declared by a `.pi-role` file containing a single word
 * (brain | worker | calcs | scout | verifier | integrator | reporter). Pi searches upward from
 * cwd, so a role workspace applies to every session launched inside it.
 *
 * Why a gate instead of a rule in Markdown: a rule is a suggestion, an
 * undeclared tool does not exist, and a truncated tool result cannot be
 * re-read into the premium context. This makes "the brain does not ingest raw
 * files" physically true rather than aspirational.
 *
 * Fail-open by design: no `.pi-role` file => no behavior change.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";
import { spawnSync } from "node:child_process";

type Profile = {
	/** Max bytes of a single text block a tool may return to this tier. */
	toolResultCap: number;
	/** Max bytes of an intercom message this tier may SEND. */
	intercomSendCap: number;
	/** Tools removed from the model's reach for this tier. */
	deny: string[];
	/**
	 * Substrings that disqualify a write/edit target for this tier (e.g. `"/src/"` for `calcs`).
	 * Matched as a normalised path **component**, not a substring, so `../other/src/x.f90` matches
	 * and `a/src-x/evil.f90` or `a/src/../../evil` do not.
	 */
	pathDeny?: string[];
	/**
	 * Substrings that RE-ALLOW a tool the tier's `deny` list would otherwise block, for a specific
	 * destination. `scout` denies `write` outright but the `lit-*` pipeline must be able to drop
	 * `papers-*.json` into `queries/` — that is what this is for. Checked before `deny`.
	 */
	pathAllow?: string[];
	/** Regexes matched against `input.command` for bash-capable tiers (git hygiene, ssh, rm -rf). */
	bashDeny?: RegExp[];
	/**
	 * The one exception to a `bash` deny-list: a tier may run EXACTLY these scripts and nothing else.
	 * The brain has no shell because shell = raw ingestion, but it still has to create worktrees and
	 * roll up deltas, and those are deterministic scripts with no raw output. Guarded by
	 * `SHELL_SMUGGLE_RE`, so `python3 …/merge-status.py; cat big.log` is not an escape hatch.
	 */
	bashAllow?: RegExp[];
	/**
	 * Merge lock for the integrator: `git merge`/`rebase` is allowed ONLY while the session's cwd sits on
	 * a branch with this prefix (checked mechanically with `git rev-parse --abbrev-ref HEAD`). The prompt
	 * can be ignored; the branch name cannot. Fails closed — an unreadable HEAD means no merge.
	 */
	mergeOnlyOnBranchPrefix?: string;
	note: string;
};

// Anything that turns "run this one script" into "run a shell": command chaining, substitution,
// redirection, pipes, or a here-doc. A allowlisted script name plus any of these is refused.
const SHELL_SMUGGLE_RE = /[;&|`<>\n]|\$\(|\|\|/;

// The brain's entire shell: three deterministic scripts, named exactly. `/triage` used to instruct
// bash one-liners this role cannot run, so the recon it needed became a script instead (2026-10-26).
const BRAIN_SCRIPT_RE =
	/^\s*(?:(?:python3?(?:\.\d+)?|bash|sh|zsh)\s+)?(?:~|\$HOME|\/[A-Za-z0-9._@/-]*)\/\.pi\/agent\/scripts\/(?:worktree\.sh|merge-status\.py|triage\.sh)(?![\w.-])/;

const BRAIN_PROFILE: Profile = {
	toolResultCap: 12_000, // ~3K tokens
	intercomSendCap: 400,
	deny: ["bash", "grep", "find", "ls", "codemode"],
	bashAllow: [BRAIN_SCRIPT_RE],
	// Vault memory is reconciled by /update-memory and /update-project, which need bash to run their
	// applier scripts. The brain keeps write/edit (it owns plans/ and status rollups), so without this it
	// could hand-edit memory/ and skip the caps those scripts enforce.
	pathDeny: ["/memory/"],
	note: "brain tier: digests only. Route raw reading to a scout (subagent). bash is denied except for the three named scripts under ~/.pi/agent/scripts (worktree.sh, merge-status.py, triage.sh).",
};

const PROFILES: Record<string, Profile> = {
	// The brain plans. It does not inspect, shell, or swallow raw files.
	brain: BRAIN_PROFILE,
	// No `operator` profile ON PURPOSE (2026-10-26). The operator tier is José's own pane, defined by the
	// absence of a `.pi-role`: `findRole` returns null and nothing is denied. Documented in
	// `agents/operator.md`, because `merge-status.py` and both vault skills print
	// `next-command[operator]: …` and a name in machine output that is defined nowhere gets reinvented by
	// every session that reads it. Adding a permissive profile here would be equivalent but would hide the
	// fact that the tier is an absence rather than a policy.
	// Retired tiers (bad habit #4, confirmed by José 2026-10-23): the old sub-brain / `-main` router
	// panes were either brains or workers. Aliasing them to the BRAIN profile means a leftover pane
	// gets the strictest gate instead of a dead profile name or no gate at all.
	main: BRAIN_PROFILE,
	planner: BRAIN_PROFILE,
	submain: BRAIN_PROFILE,
	worker: {
		toolResultCap: 200_000,
		intercomSendCap: 800,
		// Leaf tier: no delegation (a session inside a session defeats restart-hygiene), and no
		// codemode, whose script can shell out and write anywhere, bypassing pathDeny/bashDeny.
		deny: ["subagent", "codemode"],
		// "Never merge, never push" is in the agent file, which is a suggestion. Landing is the
		// integrator's and José's decision, so the leaf tiers lose the verbs entirely.
		// Durable knowledge is the operator's, written by /update-memory; a leaf that records a rule keeps
		// it in its own context while its siblings and the next planning cycle never see it.
		pathDeny: ["/memory/"],
		bashDeny: [
			// Read-only ancestry plumbing stays reachable. `\b` matches at a hyphen, so this pattern used to
			// block `git merge-base` — the exact command a checker needs, and a real verifier worked around it
			// with `git rev-list HEAD | grep` to prove ancestry at a detached HEAD.
			/\bgit\s+(push|rebase)\b|\bgit\s+merge(?!-(?:base|tree))\b/,
			/\bgit\s+(checkout|switch)\s+(main|master)\b/,
			/\bgit\s+reset\s+--hard\b/,
			/\bgit\s+branch\s+-[dD]\b/,
		],
		note: "worker tier: one spec, one branch, one status delta. Never merge, never push.",
	},
	calcs: {
		toolResultCap: 200_000,
		intercomSendCap: 800,
		deny: ["subagent", "codemode"],
		// Production code is a worker job with a spec; calcs live in calculations/, scripts/,
		// canonical tables/, and .agent/scratch/.
		pathDeny: ["/src/", "/memory/"],
		// José is the cluster hands (2-hop). The agent's deliverable is a ready-to-run script.
		// Same landing ban as the worker: a calculation branch is reviewed, not merged by its author.
		bashDeny: [
			/\bssh\b/,
			/\bscp\b/,
			/\brsync\b/,
			/\bsshpass\b/,
			// Read-only ancestry plumbing stays reachable. `\b` matches at a hyphen, so this pattern used to
			// block `git merge-base` — the exact command a checker needs, and a real verifier worked around it
			// with `git rev-list HEAD | grep` to prove ancestry at a detached HEAD.
			/\bgit\s+(push|rebase)\b|\bgit\s+merge(?!-(?:base|tree))\b/,
			/\bgit\s+(checkout|switch)\s+(main|master)\b/,
		],
		note: "calcs tier: numbers + provenance, never src/, never ssh. Report circularity, don't fix code.",
	},
	verifier: {
		toolResultCap: 120_000,
		intercomSendCap: 0, // verdicts travel as return values, not as messages
		deny: ["write", "edit", "subagent", "codemode", "intercom"],
		// A verifier that repairs what it verifies is a second producer.
		// Mutation verbs only. `merge-base` and `merge-tree` are read-only plumbing and the checker's best
		// proof of ancestry, so they are excluded by lookahead: `\b` matches at a hyphen, and the flat
		// alternation used to deny `git merge-base` outright (the `structure` verifier had to fall back to
		// `git rev-list HEAD | grep` and said so in its Method section).
		bashDeny: [/\bgit\s+(checkout|switch|restore|reset|clean|revert|rebase|push)\b|\bgit\s+merge(?!-(?:base|tree))\b/],
		note: "verifier tier: read + recompute only. PASS/FAIL/UNVERIFIABLE plus an independence argument.",
	},
	integrator: {
		toolResultCap: 200_000,
		intercomSendCap: 800,
		deny: ["write", "edit", "subagent", "codemode"],
		// Prepare-only. `git push` and destructive branch ops stay banned outright; `git merge`/`rebase`
		// is allowed but only on the integration branch (see mergeOnlyOnBranchPrefix) — the integrator
		// cannot be ON main while merging into main unless it first checks out main, which is denied.
		bashDeny: [
			/\bgit\s+push\b/,
			/\bgit\s+(checkout|switch)\s+(main|master)\b/,
			/\bgit\s+reset\s+--hard\b/,
			/\bgit\s+branch\s+-[dD]\b/,
		],
		mergeOnlyOnBranchPrefix: "integration/",
		note: "integrator tier: prepares integration/<part>, tests the merged tree, reports conflicts. Never lands on main, never pushes.",
	},
	// Scouts are the ones ALLOWED to read raw. Their output is what gets capped.
	scout: {
		toolResultCap: 400_000,
		intercomSendCap: 3_000,
		deny: ["edit", "write", "codemode"],
		pathAllow: ["/queries/", "/lit-reviews/", "/.agent/digests/", "/ai-out/"],
		bashDeny: [/\brm\s+-[rf]/, /\bgit\s+(push|rebase|reset\s+--hard)\b|\bgit\s+merge(?!-(?:base|tree))\b/, /\b(make|cmake|meson|cargo\s+build|npm\s+run\s+build)\b/],
		note: "scout tier: read anything, return a digest <= 3K tokens. No builds, no deletes; lit-* scripts write queries/, lit-reviews/ via --output.",
	},
	reporter: {
		toolResultCap: 120_000,
		intercomSendCap: 1_200,
		deny: [],
		// The writer tier drafts prose for humans. Project state and durable memory are reconciled by the
		// operator's /update-project and /update-memory, whose scripts enforce the file caps this tier
		// would otherwise paraphrase.
		pathDeny: ["/memory/"],
		note: "reporter tier: draft section-sized; never re-read the whole .tex cold.",
	},
};

// ---------------------------------------------------------------------------
// Doom-loop guard.
// Some OpenCode Go-hosted models have a *vendor-acknowledged* tool-call repetition defect: Xiaomi's
// own post-mortem ("Diagnosing and Mitigating Tool-Call Repetition in MiMo-V2.6", mimo.xiaomi.com)
// states response-level repetition exceeded 0.05% for MiMo-V2.6, and upstream issues report
// mimo-v2.6-flash spamming the same Glob/Grep/bash call in a loop (anomalyco/opencode#50678,
// XiaomiMiMo/MiMo-Code#2497). One report repeated a single successful bash command ~1/sec until the
// account returned HTTP 402 — the loop itself drained the monthly quota. pi has no repetition guard,
// so the gate counts: a tool signature seen `limit` times inside the last `window` calls is blocked.
// This turns a quota-burning stall into one readable refusal the model can act on.
// ---------------------------------------------------------------------------
const LOOP_WINDOW = 24;
const LOOP_LIMIT = 3; // leaf tiers
const LOOP_LIMIT_BRAIN = 5; // the brain re-reads files on purpose while steering an interactive session
const recentCalls = new Map<string, string[]>();

function callSignature(toolName: string, input: unknown): string {
	let payload: string;
	try {
		payload = JSON.stringify(input ?? {});
	} catch {
		payload = String(input);
	}
	// Collapse whitespace so {"command":"ls -la"} and {"command": "ls  -la"} count as one loop.
	return `${toolName}:${payload.replace(/\s+/g, " ").trim()}`;
}

/** Record a call and report whether it has now repeated enough to be a loop. */
function loopCheck(key: string, sig: string, limit: number): { n: number; blocked: boolean } {
	const hist = recentCalls.get(key) ?? [];
	hist.push(sig);
	if (hist.length > LOOP_WINDOW) hist.shift();
	recentCalls.set(key, hist);
	const n = hist.filter((s) => s === sig).length;
	return { n, blocked: n >= limit };
}

// ---------------------------------------------------------------------------
// Merge lock: what branch is this session actually standing on?
// Deliberately pessimistic: any failure to read HEAD returns "" and the caller blocks the command,
// because "I could not tell" must never be treated as "it was safe".
// ---------------------------------------------------------------------------
function currentBranch(cwd: string): string {
	try {
		const r = spawnSync("git", ["-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"], {
			encoding: "utf8",
			timeout: 3000,
		});
		return r.status === 0 ? String(r.stdout).trim() : "";
	} catch {
		return "";
	}
}

const MERGE_RE = /\bgit\s+(merge|rebase|cherry-pick)\b/;

const ROLE_FILE = ".pi-role";

function canonicalRole(raw: string, profile: Profile): string {
	// Retired names alias to another tier's profile; report the tier, not the label.
	return profile === BRAIN_PROFILE && raw !== "brain" ? "brain" : raw;
}

/**
 * A `subagent` child is NOT spawned with `--agent`. pi runs
 * `--mode json -p --no-session --model X --tools a,b,c --append-system-prompt
 * /tmp/pi-subagent-XXXX/prompt-<name>.md` (pi-matt-pocock-skills/src/subagent/index.ts:294-327), so the
 * child's only gate would be the PARENT's `.pi-role`: measured 2026-10-25, a scout delegated from a brain
 * pane inherited the brain's bash ban and could not run `git branch --list`, and a worker subagent would
 * inherit the brain's raw-reading ban. The prompt argument is the single place the intended tier survives
 * the spawn, so it outranks the directory when both speak. Trust boundary: this reads a file generated
 * from an agent definition we already trust with `model:` and `tools:` — it cannot raise a tier above what
 * its own definition declares, and with no marker it falls back to the filename, then to the directory.
 */
function subagentRole(): { role: string; profile: Profile; source: string } | null {
	const argv = process.argv;
	let file = "";
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (a === "--append-system-prompt") file = argv[i + 1] ?? "";
		else if (a.startsWith("--append-system-prompt=")) file = a.slice("--append-system-prompt=".length);
	}
	if (!file) return null;

	// 1. The marker we own: a `Tier: `<name>`` line in the agent definition body.
	let body = "";
	try {
		body = fs.readFileSync(file, "utf8").slice(0, 64_000);
	} catch {
		/* unreadable prompt: the filename route still applies */
	}
	const m = body.match(/^Tier:\s*`?([a-z0-9_-]+)`?/m);
	if (m && PROFILES[m[1]]) {
		const p = PROFILES[m[1]];
		return { role: canonicalRole(m[1], p), profile: p, source: "subagent:Tier" };
	}

	// 2. Upstream's filename convention, prompt-<name>.md. Not ours to rely on alone, hence the marker.
	const f = path.basename(file).match(/^prompt-([a-z0-9_-]+)\.md$/);
	if (f && PROFILES[f[1]]) {
		const p = PROFILES[f[1]];
		return { role: canonicalRole(f[1], p), profile: p, source: "subagent:filename" };
	}
	return null;
}

function findRole(cwd: string): { role: string; profile: Profile; source: string } | null {
	const sa = subagentRole();
	if (sa) return sa; // a spawned child is its agent, whatever directory it landed in
	let dir = path.resolve(cwd);
	for (let hops = 0; hops < 8; hops++) {
		const f = path.join(dir, ROLE_FILE);
		try {
			const raw = fs.readFileSync(f, "utf8").trim().toLowerCase();
			const profile = PROFILES[raw];
			if (profile) {
				return { role: canonicalRole(raw, profile), profile, source: "dir" };
			}
			if (raw) return null; // explicit but unknown role: fail open, no surprises
		} catch {
			/* keep walking up */
		}
		const parent = path.dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}

const charLen = (c: unknown): number => {
	if (typeof c === "string") return c.length;
	if (Array.isArray(c)) return c.reduce((n: number, p: any) => n + (p?.type === "text" ? String(p.text ?? "").length : 0), 0);
	if (c && typeof c === "object") {
		const o = c as any;
		if (o.type === "text") return String(o.text ?? "").length;
		if (o.content) return charLen(o.content);
	}
	return 0;
};

/**
 * Does `absPath` sit under `seg` as a genuine path *component*? Deliberately NOT a substring
 * test: `a/queries/../../evil.f90` contains "/queries/" but resolves outside it, and `/my-src-x/`
 * contains "/src/" but is not a src dir. The path is normalised first, so `..` cannot smuggle a
 * write out of an allowed root (or a `src` deny past its own guard).
 */
function underComponent(absPath: string, seg: string): boolean {
	const norm = path.normalize(absPath);
	const needle = seg.replace(/^\/+|\/+$/g, ""); // "queries" from "/queries/" or "queries/"
	if (!needle) return false;
	const parts = norm.split(path.sep);
	return parts.includes(needle) || norm === needle || norm.endsWith(path.sep + needle);
}

/**
 * Resolve the file a content tool is aiming at, from whichever key that tool happens to use.
 * Returns null when the tool has no path argument (then path rules simply do not apply).
 */
function pathTarget(toolName: string, input: unknown, cwd: string): string | null {
	if (toolName !== "write" && toolName !== "edit") return null;
	const o = (input ?? {}) as any;
	const p = o.path ?? o.file ?? o.filePath ?? o.file_path ?? null;
	if (typeof p !== "string" || !p.trim()) return null;
	let abs = p;
	if (p === "~" || p.startsWith("~/")) abs = path.join(process.env.HOME ?? "", p.slice(2));
	else if (!path.isAbsolute(p)) abs = path.resolve(cwd, p);
	abs = path.normalize(abs);
	try {
		// Normalise symlinked dirs so `/src/` still matches through a link.
		abs = path.normalize(fs.realpathSync(abs));
	} catch {
		/* target may not exist yet (write of a new file) — the normalised string is fine */
	}
	return abs;
}

export default function (pi: ExtensionAPI) {
	let gate: ReturnType<typeof findRole> | null = null;
	let resolvedFor: string | null = null;

	const resolve = (cwd: string) => {
		if (resolvedFor !== cwd) {
			gate = findRole(cwd);
			resolvedFor = cwd;
		}
		return gate;
	};

	pi.on("session_start", async (_e, ctx) => {
		const g = resolve(ctx.cwd);
		if (g) ctx.ui.notify(`role=${g.role} [${g.source}] (gate active: ${g.profile.note})`, "info");
	});

	// 1. Hard tool deny-list for the tier.
	pi.on("tool_call", async (event, ctx) => {
		const g = resolve(ctx.cwd);
		if (!g) return undefined;

		// Runs before every other rule: a looping model does not get to spend quota on the next call.
		const sig = callSignature(event.toolName, event.input);
		const limit = g.role === "brain" ? LOOP_LIMIT_BRAIN : LOOP_LIMIT;
		const loop = loopCheck(`${ctx.cwd}|${g.role}`, sig, limit);
		if (loop.blocked) {
			return {
				block: true,
				reason:
					`[${g.role} tier] doom-loop guard: identical ${event.toolName} call is attempt ${loop.n} ` +
					`within the last ${LOOP_WINDOW}. Re-running it will not change the result. Do not retry: ` +
					`either aim at a different tool/path, or end your turn and report the blocker in your status ` +
					`delta. Repeated identical tool calls are a known defect of some Go-hosted models and they ` +
					`drain the monthly quota.
`,
			};
		}

		// Narrow script allowlist: lets a bash-less tier run its own machinery, and only that.
		if (event.toolName === "bash" && g.profile.bashAllow?.length) {
			const cmd = String((event.input as any).command ?? "");
			const allowed = g.profile.bashAllow.some((r) => r.test(cmd));
			if (allowed && !SHELL_SMUGGLE_RE.test(cmd)) return undefined;
			if (allowed) {
				return {
					block: true,
					reason:
						`[${g.role} tier] "${cmd.slice(0, 80)}" — the allowlisted script may be run, but shell ` +
						`composition (; && | $( ) backticks, redirection) is what makes a shell dangerous, so the ` +
						`allowlist covers the bare command only. Run the script alone and read its own output.`,
				};
			}
		}
		// The advisor lane is decision support, so it belongs to the tiers that decide. Two reasons a leaf
		// must not reach for it: (1) escalating instead of executing a spec means the spec is wrong, and the
		// fix belongs in the plan, not in a second model's opinion; (2) rpiv-advisor sends its request
		// without x-opencode-session, so on OpenCode Go it can only ever return a 400 (UPSTREAM.md #1) —
		// every leaf call is a wasted round trip, and this worker proved it by retrying into the doom-loop
		// guard. /oracle is the lane that actually works; it gates itself the same way (see oracle.ts).
		if (event.toolName === "advisor" && g.role && !["brain", "integrator"].includes(g.role)) {
			return {
				block: true,
				reason:
					`[${g.role} tier] tool "advisor" is denied: the premium lane is for tiers that decide (brain, integrator), ` +
					`not tiers that execute. On OpenCode Go it is also broken by a missing session header (UPSTREAM.md #1), so it ` +
					`cannot answer you at all. If the spec is unclear, write \`blocked: <the exact ambiguity>\` in your status ` +
					`delta and continue with what you can — that is how the ambiguity reaches the brain, which is where the fix belongs.`,
			};
		}

		if (g.profile.deny.includes(event.toolName)) {
			// Path-scoped re-allow: a denied tool may still be legal for a declared destination
			// (scout writing papers-*.json into queries/). Only content tools get this exemption —
			// bash/codemode can write anywhere, so they stay denied outright.
			const target = pathTarget(event.toolName, event.input, ctx.cwd);
			const reallowed =
				target !== null &&
				(event.toolName === "write" || event.toolName === "edit") &&
				(g.profile.pathAllow ?? []).some((s) => underComponent(target, s));
			if (!reallowed) {
				return {
					block: true,
					reason:
						`[${g.role} tier] tool "${event.toolName}" is denied. Bounded file? Call read with its full path and read it WHOLE (allowed, cheap) — do not extract sections with shell tools. ` +
						(g.profile.deny?.includes("subagent")
							// Leaf tiers cannot delegate: telling a worker to "spawn a scout" is advice it
							// physically cannot follow, and it burns a turn discovering that.
							? `Unbounded/raw material? You are a leaf tier and cannot delegate — write \`blocked: needs <fact>\` in your status delta and keep going on what you can. `
							: `Unbounded/raw material? subagent(scout). `) +
						(g.profile.pathAllow?.length
							? `Allowed destinations for this tier: ${g.profile.pathAllow.join(", ")}. `
							: "") +
						g.profile.note,
				};
			}
		}
		// Path-scoped deny for tiers that MAY write (calcs must not touch src/).
		if (g.profile.pathDeny?.length && (event.toolName === "write" || event.toolName === "edit")) {
			const target = pathTarget(event.toolName, event.input, ctx.cwd);
			const hit = target && g.profile.pathDeny.find((s) => underComponent(target, s));
			if (hit) {
				return {
					block: true,
					reason:
						`[${g.role} tier] "${event.toolName}" targets ${target}, which contains "${hit}" — off-limits for this tier. ` +
						`${g.profile.note} Production-code changes are a worker job with a spec: write DEBT/BLOCKED in your status delta instead.`,
				};
			}
		}
		// Command-scoped deny for bash-capable tiers (ssh hygiene, git landing, destructive rm).
		if (g.profile.bashDeny?.length && event.toolName === "bash") {
			const cmd = String((event.input as any).command ?? "");
			const re = g.profile.bashDeny.find((r) => r.test(cmd));
			if (re) {
				return {
					block: true,
					reason:
						`[${g.role} tier] command blocked by pattern ${re}. ${g.profile.note} ` +
						`If this is genuinely needed, put it in your status delta as a handoff line for José.`,
				};
			}
		}
		// Merge lock: for the integrator a merge is legal only while it stands on the integration branch.
		if (g.profile.mergeOnlyOnBranchPrefix && event.toolName === "bash") {
			const cmd = String((event.input as any).command ?? "");
			if (MERGE_RE.test(cmd)) {
				const branch = currentBranch(ctx.cwd);
				if (!branch.startsWith(g.profile.mergeOnlyOnBranchPrefix)) {
					return {
						block: true,
						reason:
							`[${g.role} tier] merge lock: HEAD is "${branch || "unreadable"}" and this tier may only merge into ` +
							`"${g.profile.mergeOnlyOnBranchPrefix}*" (the \`integration_branch:\` key of .agent-paths). ` +
							`Get the integration worktree with \`worktree.sh integrate --part <p>\`, or report the conflict instead of ` +
							`resolving it. Promoting to main is José's call, never yours.`,
					};
				}
			}
		}
		// Cap what a tier can push at another tier over intercom.
		if (event.toolName === "intercom") {
			const msg = String((event.input as any).message ?? "");
			if (msg.length > g.profile.intercomSendCap) {
				return {
					block: true,
					reason: `[${g.role} tier] intercom payload is ${msg.length} chars (cap ${g.profile.intercomSendCap}). ` +
						`Write the content to a file and send the path plus a one-line delta instead (bad habit #3).`,
				};
			}
		}
		return undefined;
	});

	// 2. Cap what lands in this tier's context from any tool result.
	pi.on("tool_result", async (event, ctx) => {
		const g = resolve(ctx.cwd);
		if (!g) return undefined;
		// The advisor is the escalation channel: its answer IS the deliverable (a plan, a
		// correction, or a stop signal). Truncating it defeats the ~$0.04 we just paid for it.
		// Spam is prevented by the one-call-per-cycle rule in agents/brain.md, not by the cap.
		if ((event as any).toolName === "advisor") return undefined;
		const cap = g.profile.toolResultCap;
		if (charLen(event.content) <= cap) return undefined;

		const kept: any[] = [];
		let budget = cap;
		for (const part of event.content as any[]) {
			if (part?.type !== "text") {
				kept.push(part);
				continue;
			}
			const text = String(part.text ?? "");
			if (text.length <= budget) {
				kept.push({ ...part, text });
				budget -= text.length;
			} else {
				kept.push({
					...part,
					text:
						text.slice(0, Math.max(0, budget)) +
						`\n\n[TRUNCATED by role gate: ${g.role} tier accepts <=${cap} chars per tool result. ` +
						`The remaining ${text.length - budget} chars are NOT in your context. ${g.profile.note}]`,
				});
				budget = 0;
			}
		}
		return { content: kept, structuredContent: null };
	});

	// 3. Inspection command.
	pi.registerCommand("role", {
		description: "Show the active role gate (or set one: /role brain)",
		handler: async (args, ctx) => {
			const req = args.trim().toLowerCase();
			if (req) {
				if (!PROFILES[req]) {
					ctx.ui.notify(`unknown role "${req}" — known: ${Object.keys(PROFILES).join(", ")}`, "warning");
					return;
				}
				const target = path.join(ctx.cwd, ROLE_FILE);
				fs.writeFileSync(target, `${req}\n`);
				ctx.ui.notify(
					`Wrote ${target}. Tool restrictions apply on the NEXT session (/new or restart); the size gate applies now.`,
					"info",
				);
				return;
			}
			const g = resolve(ctx.cwd);
			ctx.ui.notify(
				g
					? `role=${g.role} | tool-result cap ${g.profile.toolResultCap} chars | intercom send cap ${g.profile.intercomSendCap} | denied: ${g.profile.deny.join(", ") || "none"}${
							g.profile.pathDeny?.length ? ` | path-deny: ${g.profile.pathDeny.join(", ")}` : ""
						}${g.profile.pathAllow?.length ? ` | writes only: ${g.profile.pathAllow.join(", ")}` : ""}${
							g.profile.bashDeny?.length ? ` | ${g.profile.bashDeny.length} bash pattern(s) blocked` : ""
						}${g.profile.mergeOnlyOnBranchPrefix ? ` | MERGE LOCK: merges only into ${g.profile.mergeOnlyOnBranchPrefix}*` : ""}`
					: "no role gate active (no .pi-role found from cwd upward)",
				"info",
			);
		},
	});
}
