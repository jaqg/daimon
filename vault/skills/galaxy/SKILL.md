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
tools: Read, Write, Bash, Glob, Grep
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

### Step 1 — Find confirmed Galaxy links

Scan all `$VAULT_DIR/20-Sources/papers/*.md` for uncommented `[[concept]]` links.

A confirmed link: `[[concept-name]]` appearing in the note body (NOT preceded by `<!--`).
A commented suggestion: `<!--[[concept-name]]-->` — skip these, user has not confirmed them.

Extract concept names from all confirmed links. Normalize each:
- Strip `[[` and `]]`
- Lowercase
- Replace spaces with hyphens
- Remove characters not in `[a-z0-9-]`
- Collapse multiple hyphens

Example: `[[Electron Delocalization]]` → `electron-delocalization`

Treat normalized names as canonical. Collect the set of paper notes that link to each concept.

### Step 2 — Cross-check existing Galaxy notes

List all files in `$VAULT_DIR/30-Galaxy/`. Strip `.md` extension → existing concept slugs.

Partition confirmed concepts into:
- **Already exists** — skip, report as present
- **Missing** — draft skeleton

If all concepts already exist, report that and stop (nothing to draft).

### Step 3 — Draft skeletons

For each missing concept, read the paper notes that link to it. Use their `## Abstract (verbatim)`
and `## Summary` sections to infer a working definition and subject tags.

Draft the concept name as title-case of the slug (`electron-delocalization` → `Electron Delocalization`).

Skeleton format (match real vault style exactly):

```markdown
---
id: {slug}
aliases: []
tags: []
status: Seed
type: Concept
subject: [{TAG1}, {TAG2}]
---

# {Title Case Concept Name}

> [!note] Skeleton — complete after reading source papers
> Auto-drafted by /galaxy from: [[{paper1-key}]], [[{paper2-key}]]

## Core idea
[1–2 sentence working definition, inferred from paper abstracts. Be specific — no generic filler.]

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
- `subject:` — infer 2–4 tags from the paper abstracts (domain + concept type)
- `## Core idea` — one specific sentence, not a tautology ("X is the study of X")
- `## Sources` — list all paper notes that link to this concept, one line each
- Do NOT fill `## Key properties`, `## Connections`, `## Open questions` — leave for user
- Filename: `{slug}.md`

### Step 4 — Present for review

Print all drafted skeletons to the terminal, clearly separated. Then ask:

```
Drafted N skeleton(s):
  - electron-delocalization.md  (linked from: smith2021-mlpotentials, bader2022-topological)
  - interacting-quantum-atoms.md  (linked from: bader2022-topological)

Write to 30-Galaxy/? Options:
  all       write all
  none      skip (--dry-run equivalent)
  1,3,...   write specific ones by number
```

Wait for user response before writing anything.

If `--dry-run`: print skeletons, state clearly "dry run — nothing written", stop.

### Step 5 — Write approved skeletons

Write only the approved files to `$VAULT_DIR/30-Galaxy/{slug}.md`.

Do not overwrite existing files — if a file was created between step 2 and step 5, skip and warn.

### Step 6 — Report

```
Written: N concept notes to 30-Galaxy/
Skipped (already existed): M
User skipped: K

Next: open in Obsidian, read source papers, complete ## Key properties and ## Connections.
```

## --concept mode

When `--concept "name"` is given, skip scan. Draft one skeleton for the named concept.
Look up any paper notes in `20-Sources/papers/` that contain `[[name]]` (normalized match)
to populate `## Sources`. If none found, leave `## Sources` empty with a note.
Present single skeleton for approval, then write if approved.

## Security

- Never write to `30-Galaxy/` without explicit approval in the current session.
- Never overwrite an existing Galaxy note.
- Never invent paper note links — only reference notes that actually exist in `20-Sources/papers/`.
- `## Core idea` must be grounded in the linked paper abstracts, not general training knowledge alone.
