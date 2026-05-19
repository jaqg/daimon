---
name: galaxy
description: >
  Drafts Obsidian Galaxy (30-Galaxy/) concept note skeletons from confirmed [[links]] in vault paper
  notes (20-Sources/papers/). Scans for uncommented [[concept]] links, cross-checks against existing
  30-Galaxy/ files, drafts skeletons for missing concepts (inferred from linked paper abstracts and
  summaries), and presents them for user review before writing. Never writes without explicit approval.
  Trigger for: "/galaxy", "create Galaxy notes", "draft Galaxy skeletons", "update Galaxy",
  "what Galaxy notes are missing", "fill Galaxy links", "generate Galaxy skeletons",
  "which concepts need Galaxy notes", "missing Galaxy notes". Also trigger when user confirms
  Galaxy links in a paper note and asks to create the corresponding Galaxy file.
tools: Write, Bash
---

# galaxy

Closes the `lit-vault` → `30-Galaxy/` gap: paper notes link to Galaxy concepts, this skill
creates the missing concept note skeletons for the user to complete.

**Core constraint:** never write to `30-Galaxy/` without explicit user approval. Always show
all drafted skeletons first.

## Config

```bash
CONFIG=$(find -L ~/.claude -path "*/daimon/config/config.local" -type f | head -1)
VAULT_DIR=$(grep '^VAULT_DIR=' "$CONFIG" 2>/dev/null | cut -d= -f2- | sed 's|~|'"$HOME"'|')
```

If `config.local` not found, ask user for `VAULT_DIR`.

## Flags

```
--scan PATH       vault root to scan (default: VAULT_DIR from config)
--concept "name"  draft skeleton for a specific concept, skip scan
--dry-run         show skeletons without writing (always safe to share output)
```

Without `--dry-run`, the skill still shows skeletons and asks for approval before writing.

## Workflow

### Step 1 — Scan for missing concepts

```bash
SCRIPT=$(find -L ~/.claude -path "*/galaxy/scripts/scan_links.py" -type f | head -1)
python3 "$SCRIPT" --vault-dir "$VAULT_DIR"
```

The script outputs JSON with:
- `missing[]` — concepts with no Galaxy note; each entry has `slug`, `title_case`, and
  `source_papers[]` with `key`, `abstract_excerpt`, `summary_excerpt`
- `already_exists[]` — concepts already covered in `30-Galaxy/`
- `total_papers_scanned`, `total_confirmed_links`

If `missing` is empty: report all concepts covered, state `already_exists` list, stop.

Report scan summary:
```
Scanned N papers. Found M confirmed [[links]].
Already in Galaxy: K  |  Missing: J
```

### --concept mode

When `--concept "name"` is given, skip the scan. Run:
```bash
python3 "$SCRIPT" --vault-dir "$VAULT_DIR" --concept "name"
```
The script returns a single-entry `missing[]` for that concept with source paper excerpts.

### Step 2 — Draft skeletons

For each entry in `missing[]`, draft a skeleton using the `abstract_excerpt` and
`summary_excerpt` from `source_papers[]` to infer a working definition and subject tags.
Do NOT read any vault files directly — all needed excerpts are in the JSON.

Skeleton format (match vault style exactly):

```markdown
---
id: {slug}
aliases: []
tags: []
status: Seed
type: Concept
subject: [{TAG1}, {TAG2}]
---

# {title_case}

> [!note] Skeleton — complete after reading source papers
> Auto-drafted by /galaxy from: [[{paper1-key}]], [[{paper2-key}]]

## Core idea
[1–2 sentence working definition inferred from paper abstracts. Be specific — no generic filler.]

## Key properties
- 

## Connections
- 

## Open questions / to expand
- [ ] 

## Sources
- [[{paper1-key}]] — [one-line: why this paper discusses this concept]
- [[{paper2-key}]] — [one-line: why this paper discusses this concept]

---
*Galaxy skeleton — expand after reading source papers | /galaxy {date}*
```

Rules:
- `subject:` — infer 2–4 tags from paper abstracts (domain + concept type)
- `## Core idea` — one specific sentence, not a tautology ("X is the study of X")
- `## Sources` — all papers from `source_papers[]` that have non-empty excerpts
- Do NOT fill `## Key properties`, `## Connections`, `## Open questions` — leave for user
- Filename: `{slug}.md`

### Step 3 — Present for review

Print all drafted skeletons, clearly separated. Then ask:

```
Drafted N skeleton(s):
  - electron-delocalization.md  (from: smith2021-mlpotentials, bader2022-topological)
  - interacting-quantum-atoms.md  (from: bader2022-topological)

Write to 30-Galaxy/? Options:
  all       write all
  none      skip (dry-run equivalent)
  1,3,...   write specific ones by number
```

Wait for user response before writing anything.

If `--dry-run`: print skeletons, state "dry run — nothing written", stop.

### Step 4 — Write approved skeletons

Write only approved files to `$VAULT_DIR/30-Galaxy/{slug}.md`.

Do not overwrite existing files — if a file appeared between step 1 and step 4, skip and warn.

### Step 5 — Report

```
Written: N concept notes to 30-Galaxy/
Skipped (already existed): M
User skipped: K

Next: open in Obsidian, read source papers, complete ## Key properties and ## Connections.
```

## Security

- Never write to `30-Galaxy/` without explicit approval in the current session.
- Never overwrite an existing Galaxy note.
- Never invent paper note links — only reference papers listed in `source_papers[]` from the script.
- `## Core idea` must be grounded in the linked paper excerpts, not general training knowledge alone.
