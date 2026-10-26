---
name: update-project
disable-model-invocation: true
description: >
  Capture end-of-session knowledge into structured project files. Use this skill when the user says
  /update-project, "update my project notes", "capture today's work", "log my results",
  "update project files after this session", "save session insights", or wants to record
  decisions/results/methods/questions from a work session into the vault project folder.
  Reads session content (daily note or inline summary), extracts structured updates,
  and applies them to methods.md, results-log.md, decisions-log.md, open-questions.md,
  history.md, project-dashboard.md, and the memory/project file CURRENT section
  with a diff preview and approval gate before writing.
  Always invoke after a productive session when the user asks to save, capture, or record work.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# update-project

Capture a work session's scientific content into the project folder's structured knowledge files:
- `decisions-log.md` — decisions and rationale
- `results-log.md` — calculation results with interpretation
- `methods.md` — new software/parameters used
- `open-questions.md` — new or resolved questions/hypotheses
- `history.md` — dated session-log section (narrative detail that would bloat the files above)
- `project-dashboard.md` — status line update
- `memory/project_*.md` — CURRENT bullets refresh + new CONSTRAINTS (this skill owns these; /update-memory never touches them — see `AGENTS.md § Memory contract`)
- `status/<part>.md` — ≤15-line part rollup (CURRENT / NEXT / BLOCKED / DEBT), fed by worker deltas in `<repo>/.agent/status/`; this is the file the brain reads directly

## Invocation

```
/update-project --project <id> [--daily-note] [--session-summary "text"]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--project <id>` | required | Project folder name under `10-Projects/` |
| `--daily-note` | off | Read today's `00-Inbox/YYYY-MM-DD.md` as session input |
| `--session-summary "text"` | — | Inline session description (alternative to `--daily-note`) |

Both `--daily-note` and `--session-summary` may be combined: the daily note plus a brief inline addendum.

## Step 0 — Role guard: only an operator pane may apply

This skill reconciles project-wide state and edits files that already exist. Most tiers are missing one of
those two abilities, and the failure is **silent**: with `bash` denied the script calls below cannot run,
so the session degrades into hand-editing the dashboard — which bypasses every cap `apply_updates.py`
enforces (CURRENT ≤5 bullets, file length, replace-not-delta semantics). A hand-transcribed rollup looks
right and then drifts, which is the same class of bug as a status file frozen at its last consumption.

Detect before touching anything. `Read` is the one tool every tier keeps, so the check works even in the
brain pane where `bash` does not exist:

1. `Read` `./.pi-role`, then each parent up to the vault root (`../.pi-role`, `../../.pi-role`, …, 8 hops).
2. Any file found and non-empty ⇒ this is a gated tier ⇒ **STOP**. Write nothing, edit nothing.
3. Secondary signal: if any `Bash` call returns a role-gate refusal (`bash-deny`, or the allow-list note),
   stop for the same reason even if no `.pi-role` was found.

| Role found | What that pane does instead |
|---|---|
| none / empty | continue to Step 1 — this is an operator pane |
| `worker`, `calcs` | write `current:` (≤4 date-stamped bullets) and `next:` (≤3) lines in your `.agent/status/` delta — Step 4 reads those. Never edit `history.md`, `results-log.md`, or anything under `memory/`: `role-gate` denies `memory/` writes for your tier, so a refusal there means this table, not a bug |
| `scout`, `verifier`, `integrator` | you have no write tools by design; put the state change in your report/delta and let an operator apply it |
| `brain` | you may draft candidate CURRENT bullets into `10-Projects/<X>/plans/`, but `bash` is denied so `apply_updates.py` cannot run here. Emit the hand-off line below |
| `reporter` (the writer tier) | prose for humans only; project state is not yours to reconcile |

Print the hand-off verbatim, so nobody has to remember the syntax:

```
next-command[operator]: cd "$VAULT_DIR" && pi   # unroled pane, then /update-project --project <id>
```

Unroled means **operator**: no `.pi-role` anywhere up the tree ⇒ `role-gate` fails open ⇒ full tools. It is
the human's own pane, not an agent file — see `USAGE.md § 1`.

## Step 1 — Locate scripts and vault

```bash
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"
VAULT_DIR=$(grep '^VAULT_DIR=' "$CONFIG_LOCAL" | cut -d= -f2- | sed "s|~|$HOME|")

READ_SCRIPT="$SKILL_DIR/scripts/read_project_state.py"
APPLY_SCRIPT="$SKILL_DIR/scripts/apply_updates.py"

PROJECT_DIR="$VAULT_DIR/10-Projects/<project-id>"
```

If `VAULT_DIR` is unset/template in config.local → stop, tell user to fill `config/config.local` (machine-local, gitignored).

Memory file: find the project's memory file via `$VAULT_DIR/memory/MEMORY.md` index (e.g. project `PhD-AIM4ML` → `memory/project_aim4ml.md`). Not 1:1 derivable — always look it up.

Worker deltas (raw input for the status rollup): read `$PROJECT_DIR/status/repos.txt` → each line
`repo: <path>`; pending deltas are `<path>/.agent/status/*.md` (files ending `.processed` are
already rolled up). If repos.txt or deltas exist, run this skill **before** the brain clears
context — otherwise the only copy of the worker's account dies with the worktree.

## Step 2 — Read session input

- If `--daily-note`: read `$VAULT_DIR/00-Inbox/$(date +%Y-%m-%d).md`. If file not found, warn and continue with empty input (user can supplement with `--session-summary`).
- If `--session-summary "text"`: use the provided text directly.
- If neither provided: ask user for a brief summary of what was done in this session.

## Step 3 — Read project state

```bash
python3 "$READ_SCRIPT" --project-dir "$PROJECT_DIR" --memory-file "$VAULT_DIR/memory/<project_memory_file>.md"
```

Output JSON with: recent methods rows, last 3 results entries, last 5 decisions, all OPEN questions, current dashboard status line, last 2 history sections, current memory CURRENT bullets. This tells Claude what already exists so it avoids duplication.

## Step 4 — Claude extraction pass (single call)

You are the Claude doing this step. Given the session input from Step 2 and project state from Step 3, extract all structured updates.

**Decision checklist before extraction:**
1. Is this a new decision, or does it just confirm something already in decisions-log?
2. Is this a new numerical result, or a reiteration of a known outcome?
3. Is this a new/changed parameter, or the same setup as before?
4. Is this a new open question, or one already in open-questions.md?
5. Is this durable state change (→ memory CURRENT) or dated narrative (→ history.md)? Never both.

**Routing (memory contract — `AGENTS.md § Memory contract`):**

| Content | Destination |
|---|---|
| Decisions + rationale | `decisions-log.md` |
| Numerical results | `results-log.md` |
| Parameter/software changes | `methods.md` |
| Open/closed questions | `open-questions.md` |
| Dated session narrative, implementation detail | `history.md` section |
| ≤5 date-stamped state changes ("what is true now") | memory CURRENT bullets (replace set) |
| New durable rule (Why + How to apply) | memory CONSTRAINTS |
| Work-log one-liner | dashboard status line (30-day window rule applies to work-log section) |
| Worker delta rollup for part <X> | `status/<X>.md` (≤15 lines, replace semantics) |

**What to extract:**

- **Decisions** — explicit choices made, with rationale. Example: "decided to use scaffold-aware split instead of random" with rationale "random split leaks stereo pairs (15.2% near-duplicates)".
- **Results** — numerical outcomes, convergence data, model scores, calculation outputs. Include the numbers. Example: "E_ads(BEA-PE) = −0.06 eV with PBE-D3" not just "ran the calculation".
- **Methods updates** — new software used, new parameters, changed settings. Only if genuinely new vs methods.md.
- **New open questions** — blockers, hypotheses, things to investigate that surfaced today.
- **Closed questions** — previously open questions that now have answers (include the answer).
- **History section** — one `## date — title` section with markdown body: what was done, how, what broke, what was learned. This is the overflow valve — anything too dated/narrative for the other files goes here. Cap body ~40 lines; split sections by topic if a session touched multiple threads.
- **Memory current bullets** — the FULL desired ≤5-bullet set (replace semantics, not delta). Each bullet: date + state change. Example: "2026-10-01 — Kr₂ cross-driver diff verified, 17 wfns".
- **Memory constraints** — new durable rules only (append semantics, idempotent). Example: "Cluster builds require `make qtcovi` — bare `make` links system GSL, exit 127 on compute nodes".
- **Galaxy candidates** — new concepts or connections worth a `30-Galaxy/` concept note. List names only.
- **Dashboard status** — one-line summary of current project state.
- **Status rollups** (`status_rollups`) — one object per part touched this session, distilled from
  the pending `.agent/status/*.md` deltas: `current` (≤4 bullets, date-stamped), `next` (≤3),
  `blocked` (≤3, each `who: what, since`), `debt` (≤3 known compromises). Total file ≤15 lines —
  the brain reads it directly, so detail belongs in `history.md`, not here.

**Output JSON:**
```json
{
  "decisions": [{"date": "YYYY-MM-DD", "text": "decision text", "rationale": "why"}],
  "results": [{"date": "YYYY-MM-DD", "run": "run name", "what": "action taken (what was run/done)", "result": "numerical outcome or concrete result", "interpretation": "what it means", "files": "path or TBD"}],
  "methods_updates": [{"date": "YYYY-MM-DD", "software": "name", "version": "—", "parameters": "key settings", "notes": "context"}],
  "questions": [{"status": "OPEN"|"CLOSED", "text": "question", "date": "YYYY-MM-DD", "answer": null|"answer text"}],
  "history": [{"date": "YYYY-MM-DD", "title": "short section title", "body": "markdown narrative, ~≤40 lines"}],
  "memory_current": ["2026-10-01 — state bullet 1", "…≤5 bullets total, FULL set"],
  "constraints": ["new durable rule with implicit Why/How"],
  "galaxy_candidates": ["concept name"],
  "status_rollups": [{"part": "A", "date": "YYYY-MM-DD", "current": ["…"], "next": ["…"], "blocked": ["…"], "debt": ["…"]}],
  "dashboard_status_line": "one-line current status"
}
```

Use `[]` for any field with nothing to report. Today's date if date is not specified in the session content.

## Step 5 — Preview and apply

Write the JSON to a temp file first (avoids shell quoting issues with unicode characters):
```bash
UPDATES_FILE=$(mktemp /tmp/update-project-XXXX.json)
cat > "$UPDATES_FILE" << 'ENDJSON'
<JSON from Step 4>
ENDJSON

# REPO = first path from $PROJECT_DIR/status/repos.txt ("repo: <path>"), if any
REPO="$(sed -n 's/^.*[[:space:]]\(~\?\/[[:print:]]*\)[[:space:]]*$/\1/p' "$PROJECT_DIR/status/repos.txt" 2>/dev/null | head -1)"

python3 "$APPLY_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --memory-file "$VAULT_DIR/memory/<project_memory_file>.md" \
  --updates-file "$UPDATES_FILE" \
  --agent-scratch "$REPO/.agent/status" \
  --dry-run
```

Show the diff to the user. Also list any Galaxy candidates separately. Ask for explicit confirmation before writing.

After approval:
```bash
python3 "$APPLY_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --memory-file "$VAULT_DIR/memory/<project_memory_file>.md" \
  --updates-file "$UPDATES_FILE" \
  --agent-scratch "$REPO/.agent/status"   # renames consumed deltas *.processed
rm "$UPDATES_FILE"
```

Script-side enforcement: CURRENT capped at 5 bullets (truncates with warning); memory file capped
at 80 lines (warns — move dated detail to history.md); idempotent on date + first-40-chars
(re-runs skip duplicates); `status/<part>.md` written whole and warns above 15 lines; with
`--agent-scratch` and a real (non-dry) apply, consumed worker deltas are renamed `*.processed`
— that is what makes `<repo>/.agent/` safe to delete.

**Approval gate:** always show diff first. Never write without explicit user confirmation ("yes", "go ahead", "looks good"). If Galaxy candidates exist, remind user to run `/galaxy` to create them.

## Step 6 — Hygiene check (post-apply, always)

After a real (non-dry-run) apply:

```bash
HYGIENE="$SKILL_DIR/../vault-hygiene/scripts/vault_hygiene.py"
python3 "$HYGIENE" --vault-dir "$VAULT_DIR" --check --project <id>
```

Append any violations to your report (e.g. decisions-log over cap → suggest `/vault-hygiene --archive`). Prune-at-write already handles decisions-log splits automatically during apply — residual violations are memory-file size, work-log dates, frontmatter. Full vault pass = `/vault-hygiene`.

**Feedback/user-type insights** ("Claude got X wrong, user prefers Y") → those belong to `/update-memory` (owns `feedback_*.md`, `user_*.md`). Don't write them here; mention in your report so the user can run it.

## Edge cases

- **No input and no daily note:** ask user for a brief summary before proceeding
- **Daily note file missing:** warn, ask for `--session-summary` supplement
- **Nothing to extract:** tell user "No new decisions, results, or questions identified in this session"
- **methods.md has no table:** skip methods update, note it
- **history.md missing:** script skips silently (file must exist with its title header — create it from template if absent: `# <Project> — History`)
- **memory file not found:** script warns; continue with project-dir updates only
- **Galaxy candidates:** list them but never create notes unilaterally
