---
name: update-project
description: >
  Capture end-of-session knowledge into structured project files. Use this skill when the user says
  /update-project, "update my project notes", "capture today's work", "log my results",
  "update project files after this session", "save session insights", or wants to record
  decisions/results/methods/questions from a work session into the vault project folder.
  Reads session content (daily note or inline summary), extracts structured updates,
  and applies them to methods.md, results-log.md, decisions-log.md, and open-questions.md
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
- `project-dashboard.md` — status line update

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

## Step 1 — Locate scripts and vault

```bash
SKILL_DIR=$(dirname "$(readlink -f "$(find -L ~/.claude/skills/update-project -name SKILL.md 2>/dev/null | head -1)")")
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"
VAULT_DIR=$(grep '^VAULT_DIR=' "$CONFIG_LOCAL" | cut -d= -f2-)

READ_SCRIPT=$(find -L ~/.claude -path "*/update-project/scripts/read_project_state.py" -type f | head -1)
APPLY_SCRIPT=$(find -L ~/.claude -path "*/update-project/scripts/apply_updates.py" -type f | head -1)

PROJECT_DIR="$VAULT_DIR/10-Projects/<project-id>"
```

## Step 2 — Read session input

- If `--daily-note`: read `$VAULT_DIR/00-Inbox/$(date +%Y-%m-%d).md`. If file not found, warn and continue with empty input (user can supplement with `--session-summary`).
- If `--session-summary "text"`: use the provided text directly.
- If neither provided: ask user for a brief summary of what was done in this session.

## Step 3 — Read project state

```bash
python3 "$READ_SCRIPT" --project-dir "$PROJECT_DIR"
```

Output JSON with: recent methods rows, last 3 results entries, last 5 decisions, all OPEN questions, current dashboard status line. This tells Claude what already exists so it avoids duplication.

## Step 4 — Claude extraction pass (single call)

You are the Claude doing this step. Given the session input from Step 2 and project state from Step 3, extract all structured updates.

**Decision checklist before extraction:**
1. Is this a new decision, or does it just confirm something already in decisions-log?
2. Is this a new numerical result, or a reiteration of a known outcome?
3. Is this a new/changed parameter, or the same setup as before?
4. Is this a new open question, or one already in open-questions.md?

**What to extract:**

- **Decisions** — explicit choices made, with rationale. Example: "decided to use scaffold-aware split instead of random" with rationale "random split leaks stereo pairs (15.2% near-duplicates)".
- **Results** — numerical outcomes, convergence data, model scores, calculation outputs. Include the numbers. Example: "E_ads(BEA-PE) = −0.06 eV with PBE-D3" not just "ran the calculation".
- **Methods updates** — new software used, new parameters, changed settings. Only if genuinely new vs methods.md.
- **New open questions** — blockers, hypotheses, things to investigate that surfaced today.
- **Closed questions** — previously open questions that now have answers (include the answer).
- **Galaxy candidates** — new concepts or connections worth a `30-Galaxy/` concept note. List names only.
- **Dashboard status** — one-line summary of current project state.

**Output JSON:**
```json
{
  "decisions": [{"date": "YYYY-MM-DD", "text": "decision text", "rationale": "why"}],
  "results": [{"date": "YYYY-MM-DD", "run": "run name", "what": "action taken (what was run/done)", "result": "numerical outcome or concrete result", "interpretation": "what it means", "files": "path or TBD"}],
  "methods_updates": [{"date": "YYYY-MM-DD", "software": "name", "version": "—", "parameters": "key settings", "notes": "context"}],
  "questions": [{"status": "OPEN"|"CLOSED", "text": "question", "date": "YYYY-MM-DD", "answer": null|"answer text"}],
  "galaxy_candidates": ["concept name"],
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

python3 "$APPLY_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --updates-file "$UPDATES_FILE" \
  --dry-run
```

Show the diff to the user. Also list any Galaxy candidates separately. Ask for explicit confirmation before writing.

After approval:
```bash
python3 "$APPLY_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --updates-file "$UPDATES_FILE"
rm "$UPDATES_FILE"
```

**Approval gate:** always show diff first. Never write without explicit user confirmation ("yes", "go ahead", "looks good"). If Galaxy candidates exist, remind user to run `/galaxy` to create them.

## Edge cases

- **No input and no daily note:** ask user for a brief summary before proceeding
- **Daily note file missing:** warn, ask for `--session-summary` supplement
- **Nothing to extract:** tell user "No new decisions, results, or questions identified in this session"
- **methods.md has no table:** skip methods update, note it
- **Galaxy candidates:** list them but never create notes unilaterally
