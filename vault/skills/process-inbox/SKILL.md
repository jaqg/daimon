---
name: process-inbox
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
CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[ -f "$CONFIG" ] && source "$CONFIG"

SCAN=$(find -L ~/.claude -path "*/process-inbox/scripts/scan_inbox.py" -type f | head -1)
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

1. **Append a table row** to the table in `40-Meta/events.md` with columns: Conference, Relevance, Abstract deadline, Registration deadline, Dates, Location, Cost. Write `—` for missing fields. For Relevance, assign `High` / `Medium` / `Low` using the rubric in `memory/research_interests.md` — read that file if not already in context; it covers all active projects and defines the scoring criteria. If the file does not exist, check `[skill-dir]/research_interests.template.md` for the expected format, warn the user it is missing, and infer relevance from available memory and CLAUDE.md context as a fallback.

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
