---
name: process-inbox
disable-model-invocation: true
description: >
  Processes the vault's 00-Inbox/ folder. Invoke whenever the user says "process inbox",
  "process my inbox", "process emails", "clear the inbox", or any similar phrasing. Also invoke
  when the user says "process email" followed by a filename, or asks to handle pending inbox items.
  Categorises loose notes, routes email files by type, proposes Galaxy concept skeletons,
  and logs everything to 40-Meta/ai-changes.md.
tools: Bash, Read, Write, Edit
---

## Vault layout (reference)

```
00-Inbox/          ← scan here; email-*.md files live here
  processed/       ← destination for processed email files
10-Projects/       ← one subfolder per project; each has decisions-log.md
20-Sources/
  papers/          ← one note per paper: firstauthor+year+keyword.md
  datasets/        ← one note per dataset
30-Galaxy/         ← flat Zettelkasten, one concept per note
40-Meta/
  ai-changes.md    ← append a log entry after every run
  events.md        ← conference tracker table
```

---

## Execution steps

### 1. Scan (script)

```bash
# $SKILL_DIR = directory of this SKILL.md (symlink-verify: readlink -f "$SKILL_MD")
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
CONFIG="$SKILL_DIR/../../../config/config.local"
[ -f "$CONFIG" ] && source "$CONFIG"

SCAN="$SKILL_DIR/scripts/scan_inbox.py"
python3 "$SCAN" --vault-dir "$VAULT_DIR"
```

Output JSON: `{"emails": [...], "loose_notes": [...], "daily_notes": [...], "stats": {...}}`.

- **Emails**: `email-*.md` — full content included.
- **Loose notes**: everything else except daily notes (`YYYY-MM-DD.md`) — frontmatter + 200-char preview.
- **Daily notes**: frontmatter only.

Report pre-scan stats: `N total → emails: E | loose notes: L | daily notes: D`

### 2. Process email files

For each item in `scan_output["emails"]`, apply the matching rule for `email_type`:

**conference**
Extract from the email: conference name, abstract submission deadline, registration deadline, event dates, location, cost, all URLs (homepage, registration, abstract submission, etc.), and any notes (satellite events, funding, seat limits, etc.). Then:

1. **Append a table row** to the table in `40-Meta/events.md` with columns: Conference, Relevance, Abstract deadline, Registration deadline, Dates, Location, Cost. Write `—` for missing fields. For Relevance, assign `High` / `Medium` / `Low` using the rubric in `memory/research_interests.md` — read that file if not already in context; it covers all active projects and defines the scoring criteria. If the file does not exist, check `[skill-dir]/research_interests.template.md` for the expected format, warn the user it is missing, and infer relevance from available memory and AGENTS.md context as a fallback.

2. **Append a summary block** to the `## Event Summaries` section at the bottom of `40-Meta/events.md` using this exact format:
   ```
   ### [Short name] — [Full name]
   - **Dates:** YYYY-MM-DD – DD
   - **Location:** city, country
   - **Homepage:** <url or —>
   - **Registration:** <url or —>
   - **Abstract submission:** <url or —> (omit line if not applicable)
   - **Relevance:** one sentence on relevance to QCT / ML / computational chemistry PhD research
   - **Notes:** satellite meetings, funding, seat limits, deadlines already passed, etc. Write — if none.
   ```

3. **Re-sort the entire table** after every update: ascending by earliest upcoming registration deadline; events with no deadline or past-only deadlines go last.

**tutor**
Summarise the email content in 3–5 bullet points. Extract: explicit decisions, guidance, and action items. Promote each decision to the relevant project's `10-Projects/[project]/decisions-log.md` (infer the project from the `project:` frontmatter field or from context). Flag action items explicitly to the user at the end of the run — do not silently drop them.

**software**
Summarise the update in 2–3 sentences. If a relevant project note exists (e.g., the software is used in a specific project), append the summary there. Otherwise, the processed file in `00-Inbox/processed/` is sufficient.

**other**
Summarise and route to the most appropriate location. If no clear home exists, leave it in `00-Inbox/processed/`.

**unknown email-type**
If `email-type` is missing or unrecognised, treat as `other` and note the missing/unknown type in the final report.

After processing each email file, move it to `00-Inbox/processed/`. Never delete email files unless the user explicitly asks.

### 3. Process loose notes

For each item in `scan_output["loose_notes"]`:
- If it looks like a **source note** (about a paper, dataset, or external resource): move to the appropriate subfolder under `20-Sources/`.
- If it contains a **distilled, standalone idea** (concept with a clear definition, not just a reference or task): **draft a skeleton** for a Galaxy note and notify the user — do not write the permanent note. The user reviews and writes the final version. Threshold: the concept should be usable outside the context of a single paper or project.
- If it belongs to a project: summarise any decisions and route them to the relevant `10-Projects/[project]/decisions-log.md`.

### 4. Log to ai-changes.md

Append a dated entry to `40-Meta/ai-changes.md` listing every action taken: files moved, rows appended, decisions promoted, skeletons drafted.

### 5. Report to user

End the run with a compact summary:
- Emails processed (one line each: filename → action taken)
- Loose notes moved or flagged
- Galaxy skeletons proposed (list them)
- Action items extracted from tutor emails (flagged clearly)
- Anything skipped and why

If the inbox is empty, say so briefly.

---

## Event ingest (single email)

Input mode B: one conference email passed as a **file path** or as **pasted content** — no inbox scan. If the content is not event-like (newsletter, generic mail, personal note), do **zero writes** and tell the user to run `/process-inbox` normally.

Pipeline (scripts own control flow; exactly one Claude fill pass, plus an optional second gap-only pass):

```
raw email → event_stage.py → ONE Claude pass (fill schema) → gaps + candidate link?
    yes → event_enrich.py → 2nd Claude pass (missing fields ONLY)
        → event_write.py (upsert + summary + re-sort)
    no  → event_write.py
```

### B1. Stage (script)

```bash
# $SKILL_DIR = directory of this SKILL.md (symlink-verify: readlink -f "$SKILL_MD")
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
CONFIG="$SKILL_DIR/../../../config/config.local"
[ -f "$CONFIG" ] && source "$CONFIG"

# file input:
python3 "$SKILL_DIR/scripts/event_stage.py" --input "/path/to/email.md"
# pasted content:
printf '%s\n' "$PASTED_EMAIL" | python3 "$SKILL_DIR/scripts/event_stage.py" --stdin
```

Output: the extraction schema skeleton (all content fields null) plus `source_email`, `candidates` (every URL with its anchor text, ISO date candidates pre-filtered from the body), and `missing_fields` = nulls ∩ {cost, registration_deadline, abstract_deadline, dates, location}.

### B2. Fill the schema (ONE Claude pass)

Fill every null field **from the email only** — never invent values. Use `candidates` for `urls` (homepage / registration / abstracts / other) and dates. Assign `relevance` High/Medium/Low + a one-sentence `relevance_reason` with the same rubric as mode A: read `memory/research_interests.md`; if missing, use `[skill-dir]/research_interests.template.md`, warn the user, and infer from AGENTS.md context. Leave fields the email does not state as `null`. Save the JSON to a temp file, then recompute gaps:

```bash
python3 "$SKILL_DIR/scripts/event_stage.py" --refresh-missing "$SCHEMA" > "$SCHEMA.tmp" && mv "$SCHEMA.tmp" "$SCHEMA"
```

### B3. Enrich gaps (only if `missing_fields` non-empty AND a candidate link exists)

```bash
python3 "$SKILL_DIR/scripts/event_enrich.py" --schema "$SCHEMA"
```

Fetches ≤3 pages with urllib (UA `daimon research tool`, 0.5 s between requests, 10 s timeout), picking links whose anchor or URL mentions registration/fee/cost/prices/travel-grant. Emits a **gap-only JSON payload** (`missing_fields`, `links`, `pages[].lines` pre-filtered to gap-relevant text); it writes nothing itself. Dead links become `ok: false` entries — fail-soft, never a crash; with no network the payload just carries errors and the `—` cells stand.

**Second Claude pass (only fields in `missing_fields`)**: fill those from `pages[].lines`. Never touch a field the email already supplied — email-derived values are never overwritten. Re-run `event_stage.py --refresh-missing` after filling.

### B4. Write (script)

```bash
python3 "$SKILL_DIR/scripts/event_write.py" --schema "$SCHEMA" --events "$VAULT_DIR/40-Meta/events.md"
```

Upserts the table row (dedupe on normalised `event_name`), appends or updates the `### ...` block under `## Event Summaries`, and re-sorts the whole table: ascending by earliest upcoming registration deadline; no-deadline and past-only rows last (stable). `—` for missing fields. Duplicate pass → `action=no_change`, zero diff. `event_name: null` → `action=refused` with a "not an event" message and **no writes**.

### B5. Log and report

On a successful write, append the action to `40-Meta/ai-changes.md` and report what was written (row + summary) like mode A. On refusal: no log entry, just the message.

### Deterministic checks (script path)

```bash
# exit 0 = all fixtures green; zero network, synthetic fixtures only
bash "$SKILL_DIR/evals/run_evals.sh"
```
