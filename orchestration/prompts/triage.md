---
description: Read-only project triage — reconstruct where a project stands and name 2-3 candidate next parts
argument-hint: "[project name under 10-Projects/ (e.g. a-collab-project, the-dataset-project, Collabs/a-collab-project)]"
---

Adopt the **brain** role: read `~/.pi/agent/agents/brain.md` now and follow it for this session.
This is a **triage cycle** — recon and recommendation only. No planning, no file writing, no delegation.
Project: `${1:-ask José which project, then continue}`

## 1. Deterministic recon first (zero tokens per fact, run it before reading anything)

```bash
bash ~/.pi/agent/scripts/triage.sh <project> [--vault <path>]
```

That script is on your allow-list; everything else in `bash` is denied. It resolves the vault (flag,
then `VAULT_ROOT`, then `~/.config/pi/vault-root`), finds the project under `10-Projects/` (exact, then
unique case-insensitive match; ambiguous or absent exits 4 rather than guessing), and prints `VAULT=`,
`PROJECT=`, `REL=`, `STATE=`, `STRUCTURE`, `DOC=` paths with line counts, recent `history.md` headings,
open-question count, `ROLLUP=` lines, `REPOS` with branch/dirty/last-commit, and `STRUCTURE DEBT` with
the exact `next-command[operator]:` line that clears it. Exit 4 means the name was not resolvable —
report it, do not widen the search by hand.

It prints pointers and counts, not bodies. Never substitute a listing for a `read` of a file you intend
to summarise: read the two or three files it names, after it.

## 2. Then read, in this order, and stop when you can answer

1. `memory/project_*.md` if the pointer exists (current state + constraints).
2. `project-dashboard.md` (status + 30-day work log) — **this is the real state file for most projects.**
3. The newest 2–4 sections of `history.md`, or `handoffs/next-session-context.md` if present.
4. `plans/*.md` if present (planned-but-unstarted parts).

If a project has no `memory/project_*.md`, say so and use the dashboard — do not create a state file,
and do not invent a path. Missing directory ≠ missing knowledge.

## 3. Report in ≤20 lines, exactly these four blocks

**WHERE IT STANDS** — 3–5 lines: last landed thing, what's mid-flight, what's blocked, date of the newest evidence.

**STRUCTURE DEBT** — one line per generation-old element, with the fix being *always* the same script, never you:
```
plans/ missing → the `next-command[operator]:` line that triage.sh already printed   (José runs it — your bash is denied for it)
no memory/project_*.md pointer in AGENTS.md → same script
```
You cannot `mkdir`: the gate denies it. Reporting the debt is your whole job for this block.

**CANDIDATE NEXT PARTS** — 2–3, each as `<part-name>: one sentence of what lands — <N> worker panes, model tier, rough cost`.
Recommend the cheapest one that unblocks the most. Part names become branches, so lowercase, hyphenated,
no verbs (`selection-pipeline`, not `do-selection`).

**ASK** — one question that only José can answer. If the answer is obvious, there is nothing to triage;
say "run `/brain <part>`" and stop.

Do not paste file bodies into chat, do not draft specs, do not open a scout. Triage ends when José picks a part.
