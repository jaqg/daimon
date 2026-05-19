---
name: lit-annotate
description: >
  Fills the Key points skeleton in an existing vault paper note after the user has read the paper.
  Accepts user reading notes / highlights (pasted text), a local PDF, or re-fetches the full text.
  Generates Methods, Key result, Limitations, and Open questions entries; optionally expands the
  Summary section; suggests new Galaxy concept links (commented out). Never overwrites user-written
  content. Always shows a preview and asks for confirmation before writing.
  Trigger for: "/lit-annotate", "annotate this paper", "fill in key points for [paper]",
  "I've read [paper]", "complete the notes for [paper]", "fill the skeleton", "process my reading
  notes", "I finished reading", "update the paper note". Use whenever the user has just read a paper
  and wants to convert their notes into structured vault content.
tools: Bash, Read, Write, Edit, Glob, Grep
---

# lit-annotate

Fill the `## Key points` skeleton in an existing vault paper note after the user has read the paper.
Works with notes created by `lit-vault` or any note that follows the vault naming convention.

## Config

```bash
CONFIG=$(find -L ~/.claude -path "*/daimon/config/config.local" -type f | head -1)
[ -f "$CONFIG" ] && source "$CONFIG"
```

Key used: `VAULT_DIR` (required).

## Flags

```
--note PATH|FILENAME   vault note to annotate (required). Accept: absolute path, filename with
                       or without .md, or first-author-year prefix (fuzzy match in 20-Sources/papers/)
--text "..."           paste user's reading highlights/notes inline as the annotation source
--pdf PATH             local PDF — extract text via PyMuPDF; use as annotation source
--url URL              re-fetch full text from this URL (arXiv HTML or OA PDF)
--project PROJECT_ID   read project memory for context framing of open questions
--dry-run              show diff without writing
```

At least one of `--text`, `--pdf`, or `--url` is required unless the note already has a Summary
from a full-text fetch (checked in Step 1).

## Workflow

### Step 1: Locate and read the note

Resolve `--note` to an absolute path:
1. If it's a valid absolute path: use directly.
2. If it's a filename (with or without `.md`): look in `$VAULT_DIR/20-Sources/papers/`.
3. If no exact match: fuzzy-match by prefix (`startswith`). If multiple matches: list them and ask
   the user to pick one.

Read the note. Parse:
- Frontmatter: extract `doi`, `arxiv`, `full_text_available`, `project`.
- Existing `## Key points` content: check each bullet (`Methods`, `Key result`, `Limitations`,
  `Open questions`) for existing content. Record which bullets are already filled by the user
  (non-empty text after the label).
- Existing `## Connections` block: extract current commented suggestions so you don't duplicate them.
- Existing `> [!todo]` callout items.

If note is missing a `## Key points` section entirely: report "Note has no Key points section.
Run `/lit-vault` first to create the structured skeleton, then re-run `/lit-annotate`." Stop.

### Step 2: Collect source material

Build `source_text` from the inputs provided, in priority order (use all that are available):

1. **`--text`**: use as-is. This is the primary source — the user's own reading notes carry the
   most signal.

2. **`--pdf`**: extract with PyMuPDF if available.
   ```python
   import fitz
   doc = fitz.open(pdf_path)
   text = "\n".join(page.get_text() for page in doc)
   ```
   If PyMuPDF not installed: warn and skip this source.

3. **`--url`**: fetch. If arXiv HTML (`arxiv.org/html/`): use `requests` + strip HTML tags.
   If PDF URL: download to `/tmp/` → PyMuPDF extract → delete.

4. **Existing abstract in note**: always included as baseline context.

If no source material beyond the abstract: warn "No reading notes or full text provided. Key points
will be drafted from abstract only — may be shallow." Continue (user can edit after).

### Step 3: Load project context (if --project or frontmatter project field)

```bash
MEMORY_DIR=$(find ~/.claude/projects -name "MEMORY.md" | head -1 | xargs dirname)
```

Find `$MEMORY_DIR/project_*.md` whose filename matches PROJECT_ID. Read open questions and
methodology keywords. Use to frame the `Open questions` bullet in Step 4.

If `--project` not given but `project:` frontmatter field exists: use that value.

### Step 4: Generate annotations

For each **empty** Key points bullet, generate content from `source_text`. Do not touch bullets
that already contain user-written text.

```
- **Methods:** [Specific techniques, tools, datasets. Not generic — name the method. E.g.:
  "DFT-D3/VASP on amorphous silica model; Bader charge analysis" not "DFT methods were used".]

- **Key result:** [The single most important finding. Quantitative where possible. E.g.:
  "All five P-bearing molecules show exothermic adsorption; IR spectra confirm chemisorption
  via characteristic peaks at 1253–2313 cm⁻¹."]

- **Limitations:** [Scope or method constraints that bound where the result applies. E.g.:
  "Amorphous silica model may not capture full surface heterogeneity; no temperature effects."]

- **Open questions:** [What's still unknown or what this raises for the reader's own project.
  If project context loaded: frame as "How does X relate to PROJECT_ID?" where X is a
  result from the paper and PROJECT_ID is the research context.]
```

**Summary expansion (optional):** If `full_text_available: false` in frontmatter AND `--text` or
`--pdf` is provided: offer to expand the existing Summary section. Show the existing summary and
the proposed expansion. Only update if the user agrees (in Step 5 approval).

**Additional Galaxy link candidates:** Tokenize `source_text` (lowercase, drop stopwords). Score
each existing Galaxy concept filename (from `ls $VAULT_DIR/30-Galaxy/*.md`) by token overlap.
Return top 3 candidates NOT already listed in the note's Connections block. Format as:
`<!--[[concept-name]]-->  <!-- suggested by /lit-annotate from full text -->`

Do NOT add Galaxy links that are already in the note (commented or confirmed).

### Step 5: Preview and approval

Print a diff-style preview showing:
```
## Key points  (changes only)
- **Methods:**    [empty → new text]
- **Key result:** [empty → new text]
...

## Connections  (new suggestions)
<!--[[new-concept]]-->

(No changes to Summary)   OR   ## Summary  (proposed expansion)
[existing text]
---PROPOSED ADDITION---
[expansion]
```

Then ask:
```
Write these changes to {note_filename}?
  [y] yes — apply all
  [n] no — discard
  [k] key points only — skip Summary and Galaxy suggestions
  [s] summary expansion only
```

Wait for user input. Proceed based on response.

### Step 6: Write

Apply only the approved changes:
- **Key points**: use `Edit` to replace only the empty bullet lines within `## Key points`. Never
  touch filled bullets.
- **Summary expansion**: append to existing `## Summary` content after a blank line; do NOT replace.
- **Galaxy suggestions**: append new `<!--[[...]]-->` lines to the `## Connections` block. If no
  Connections block exists: add it before the `---` footer line.
- **Todo callout**: if `- [ ] Read paper, fill key points section` exists in the callout: mark it
  done (`- [x] Read paper...`).

Never write anywhere outside the single note file.

### Step 7: Report

```
Annotated: {note_filename}
  Key points filled: Methods, Key result, Limitations, Open questions  (or list which)
  Summary:           [expanded | unchanged]
  Galaxy suggestions added: N  (concept-a, concept-b)
  Source used:       --text | PDF: {path} | URL: {url} | abstract only
```

## Security

1. Only write to the single note file specified by `--note`. No other files.
2. Never overwrite a bullet that already has user-written content after the label.
3. Galaxy suggestions always added as `<!--[[...]]-->` — never as confirmed links.
4. PDFs downloaded to `/tmp/` only; delete after extraction.
5. `--dry-run` prints the diff from Step 5 without proceeding to Step 6.
6. If the note is outside `VAULT_DIR`: warn and ask for explicit confirmation before writing.
