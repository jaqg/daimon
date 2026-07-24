---
name: open-manuscript
description: >
  Create or update manuscript-context.md for a project before writing a paper.
  Use when the user says /open-manuscript, "prepare for writing", "create manuscript context",
  "set up manuscript file", "start writing the paper for project X", "I'm starting to write
  the paper", or wants to configure the peer-review --expert mode with manuscript-specific context.
  Reads existing methods.md and results-log.md to pre-populate computational details and key
  results. Asks user for: target journal, working title, key claims, anticipated reviewer concerns.
  Writes manuscript-context.md with approval gate.
  Also invoke proactively when /peer-review --expert is run and no manuscript-context.md exists.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# open-manuscript

Create `manuscript-context.md` — the primary context source for `/peer-review --expert`.

This file tells the reviewer agent which journal's standards apply, what the paper claims,
what the methods are (as used, not from memory), and what weaknesses the user anticipates.
It is written once before paper-writing begins and updated as the manuscript evolves.

## Invocation

```
/open-manuscript --project <id> [--update]
```

| Flag | Meaning |
|------|---------|
| `--project <id>` | Project ID (folder under `10-Projects/`) |
| `--update` | Update an existing manuscript-context.md (add/change fields without full rewrite) |

## Step 1 — Locate project and read snapshot

```bash
SKILL_DIR=$(dirname "$(readlink -f "$(find -L ~/.claude/skills/open-manuscript -name SKILL.md 2>/dev/null | head -1)")")
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"
VAULT_DIR=$(grep '^VAULT_DIR=' "$CONFIG_LOCAL" | cut -d= -f2-)

SNAPSHOT_SCRIPT=$(find -L ~/.claude -path "*/open-manuscript/scripts/read_project_snapshot.py" -type f | head -1)

PROJECT_DIR="$VAULT_DIR/10-Projects/<project-id>"
python3 "$SNAPSHOT_SCRIPT" --project-dir "$PROJECT_DIR"
```

The snapshot gives you the last 5 methods rows and last 10 results entries — enough to pre-populate computational details without loading the full files.

## Step 2 — Ask user for manuscript details

Ask these questions (in a single message if possible):

1. **Target journal** — which journal is this submission aimed at?
2. **Working title** — what is the current title (can be a placeholder)?
3. **Key claims** — what are the 3-5 main scientific claims the paper makes? (ask for bullet points)
4. **Anticipated reviewer concerns** — what weaknesses or objections do you expect reviewers to raise?

If `--update`: read the existing `manuscript-context.md` first, show the user what's there, and ask which fields to update. Only change what the user confirms.

## Step 3 — Draft manuscript-context.md

Using the user's answers (Step 2) + project snapshot (Step 1), draft:

```markdown
---
status: Active
type: SOP
subject: [<project-id>]
---

# Manuscript Context — <project-id>

## Target journal
<journal name and relevant standards>

## Working title
<title>

## Key claims
- <claim 1>
- <claim 2>
- <claim 3>

## Computational methods (as used)
| Software | Version | Key parameters | Role |
|----------|---------|----------------|------|
<rows from methods.md snapshot>

## Key results
<last 3-5 result entries summarised as bullets with numbers>

## Known weaknesses / anticipated reviewer concerns
- <concern 1>
- <concern 2>

## Open questions
<OPEN entries from open-questions.md if present>
```

Pre-populate **Computational methods** and **Key results** from the snapshot.
The user fills in claims, journal, concerns — don't invent these.

## Step 4 — Show diff and write with approval gate

Show the draft (or a diff if `--update`). Ask for explicit confirmation.
Write to `<PROJECT_DIR>/manuscript-context.md` after approval.

After writing:
- Remind user to run `/peer-review --expert --project <id>` to use this context.
- If significant open questions exist, suggest addressing them before submission.

## Edge cases

- **methods.md missing or empty:** note "No methods.md found — add methods section manually"
- **results-log.md missing:** note "No results-log.md found — add key results manually"
- **`--update` but no existing file:** proceed as fresh creation
- **User declines to answer a question:** leave that field as a placeholder `[TODO]`
