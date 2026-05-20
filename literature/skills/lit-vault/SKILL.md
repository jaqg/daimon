---
name: lit-vault
description: >
  Creates per-paper Obsidian vault notes from a papers.json file (output of lit-search or lit-review).
  Each note includes verbatim abstract, Claude-generated project-situated summary, structured key-points
  skeleton, Galaxy link suggestions (commented out for user confirmation), and a read-and-annotate task.
  Builds a searchable paper wiki in the vault. Updates project memory with paper pool metadata.
  Trigger for: "/lit-vault", "import papers to vault", "create vault notes", "save papers to vault",
  "add papers to my reading list", "create a paper wiki", "make reading notes from search results",
  "build a literature wiki". Part of the daimon literature skill suite.
tools: Bash, Read, Write, Edit, Glob, Grep
---

# lit-vault

Convert `papers.json` (from `lit-search` or `lit-review`) into per-paper Obsidian vault notes
stored in `VAULT_DIR/20-Sources/papers/`. Attempts full-text fetch (arXiv HTML or Unpaywall OA PDF)
before falling back to abstract. Situates each summary in project context when `--project` is given.
Updates the project memory file with a cumulative paper-pool summary.

## Config keys (from config.local)

```bash
VAULT_DIR              # required — path to Obsidian vault root
USER_EMAIL             # optional — improves Unpaywall rate limits (any email works)
LIT_VAULT_CACHE_DIR    # optional — cache fetched full text; default: ~/.cache/daimon/lit-vault/
LIT_VAULT_PDF_DIR      # optional — persist downloaded PDFs to this dir (omit to skip saving)
ELSEVIER_API_KEY       # optional — ScienceDirect full text for 10.1016/* DOIs; register at dev.elsevier.com; institutional IP/VPN required at runtime
WILEY_TDM_TOKEN        # optional — Wiley TDM PDF for 10.1002/*, 10.1111/* DOIs; get via ORCID at Wiley TDM portal; library must hold TDM agreement
```

Source config:
```bash
CONFIG=$(find -L ~/.claude -path "*/daimon/config/config.local" -type f | head -1)
[ -f "$CONFIG" ] && source "$CONFIG"
```

## Flags

```
--papers PATH          source papers.json (required)
--project PROJECT_ID   project tag for frontmatter; reads project memory for context framing
--threshold N          min screening_score to import (default: 3)
--status included|all  import screening_status=included papers only, or all (default: included)
--output-dir PATH      override output dir (default: $VAULT_DIR/20-Sources/papers/)
--dry-run              print notes to stdout without writing files
--no-full-text         skip full text fetch; abstract only (faster)
--overwrite            replace already-existing notes (default: skip with warning)
```

## Workflow

### Step 0: Load config and select papers

Source config.local. If `VAULT_DIR` not set, ask user before proceeding.

Load `--papers` file. Filter:
- Default: `screening_status = "included"` AND `screening_score >= threshold`
- If no screening fields present (raw lit-search output without screening): import all papers

Report: "N papers selected for import."

### Step 1: Load project context (if --project)

```bash
MEMORY_DIR=$(find ~/.claude/projects -name "MEMORY.md" | head -1 | xargs dirname)
```

Find `$MEMORY_DIR/project_*.md` whose filename contains PROJECT_ID (case-insensitive; treat `-`
and `_` as equivalent). Read it. Extract: research questions, methodology keywords, known concepts,
open questions. This context shapes the Summary section of every note.

If no matching file: proceed without project context; omit project-framing from summaries.

### Step 2: Fetch full text (skip if --no-full-text)

```bash
FETCH_SCRIPT=$(find -L ~/.claude -path "*/lit-vault/scripts/fetch_fulltext.py" -type f | head -1)
FULLTEXT_OUT="/tmp/lit-vault-fulltext-$(date +%s).json"
CACHE_DIR="${LIT_VAULT_CACHE_DIR:-$HOME/.cache/daimon/lit-vault}"
python3 "$FETCH_SCRIPT" \
  --papers "$FILTERED_PAPERS_JSON" \
  --output "$FULLTEXT_OUT" \
  --email "${USER_EMAIL:-anonymous@example.com}" \
  --cache-dir "$CACHE_DIR" \
  ${LIT_VAULT_PDF_DIR:+--pdf-dir "$LIT_VAULT_PDF_DIR"} \
  ${ELSEVIER_API_KEY:+--elsevier-key "$ELSEVIER_API_KEY"} \
  ${WILEY_TDM_TOKEN:+--wiley-token "$WILEY_TDM_TOKEN"}
```

The script tries per paper, in priority order — stops at first success:
1. **arXiv HTML** — `https://arxiv.org/html/{id}` if `arxiv` field present
2. **arXiv PDF** — fallback when no HTML version exists
3. **Unpaywall** — all OA PDF URLs then all OA HTML URLs from `oa_locations`
4. **Europe PMC** — full text XML via PMC ID (if DOI is indexed)
5. **Elsevier ScienceDirect** — XML then PDF via TDM API for `10.1016/*` DOIs (requires `ELSEVIER_API_KEY` + institutional IP/VPN)
6. **Wiley TDM** — PDF via TDM API for `10.1002/*`, `10.1111/*` DOIs (requires `WILEY_TDM_TOKEN` + library TDM agreement)
7. **Fallback** — abstract only; `full_text_available: false` in output

Output: single JSON `{paper_id: {full_text, source, full_text_available, fetch_reason, publisher}, ...}`.
Cache written to `$CACHE_DIR/fulltext-cache.json` — subsequent runs skip already-fetched papers.
PDFs saved to `LIT_VAULT_PDF_DIR` if set; otherwise downloaded to `/tmp/` and discarded.

**Manual download manifest**: script always writes `<output>-to-download.tsv` listing papers that fell back to abstract-only. Organized by publisher with download URLs and expected PDF filenames. Drop downloaded PDFs into `--pdf-dir` and re-run to pick them up.

After the script completes, load the JSON and map each paper ID to its full text and fetch source. Report the manifest path to the user if it contains any entries.

### Step 3: Locate Galaxy suggestion script

```bash
SUGGEST_SCRIPT=$(find -L ~/.claude -path "*/lit-vault/scripts/suggest_galaxy.py" -type f | head -1)
```

Used per-paper in Step 4c to score concept overlap. If not found, skip Galaxy suggestions and omit `## Connections` block.

### Step 4: Generate and write notes

Process each paper sequentially.

**4a. Derive filename:**
`{firstauthorlastname}{year}-{keyword}.md`
- First author last name: lowercase, ASCII-normalize (strip diacritics: é→e, ü→u, ñ→n)
- Year: 4-digit
- Keyword: first meaningful noun from title. Skip stopwords: a, an, the, of, in, on, for, with,
  by, to, from, and, or, is, are, was, new, novel, study, investigation, analysis, approach, method
- Example: `smith2023-iqatransferability.md`

If file already exists in output-dir:
- Without `--overwrite`: skip, add to skipped list, continue
- With `--overwrite`: proceed

**4b. Extract subject tags:**
Combine: paper `keywords` field (if present) + venue name tokens + abstract noun phrases.
Keep 3–5 tags, lowercase, hyphenated. Example: `density-functional-theory`, `qtaim`, `basis-sets`.

**4c. Galaxy link candidates:**

```bash
python3 "$SUGGEST_SCRIPT" \
  --vault-dir "$VAULT_DIR" \
  --text "PAPER_TITLE PAPER_ABSTRACT" \
  --top 5
```

Output: JSON array of slugs (e.g. `["qtaim", "iqa-energy-decomposition", ...]`). Use these directly as the `<!--[[slug]]-->` lines in `## Connections`. If `SUGGEST_SCRIPT` is empty or script returns `[]`, omit `## Connections` block.

**4d. Generate note** using the template below. Then write to file. If `--dry-run`, print only the target filename (not the note content) — never print full notes to terminal.

---

## Note template

Use this exact structure. Every section in the order shown.

```markdown
---
status: Seed
type: Paper
subject: [TAG1, TAG2, TAG3]
project: [PROJECT_ID]
doi: 10.xxxx/xxxxx
arxiv: XXXX.XXXXX
year: YYYY
venue: Journal Name
citations: N
screening_score: N
full_text_available: true
---

# FirstAuthorLastname YEAR — Short keyword phrase from title

**Authors:** Author1, Author2, Author3 et al.
**Venue:** Journal Name | **Year:** YYYY | **Citations:** N
**Why included:** [Copy screening_reason from papers.json. If absent: "Manually imported."]

> [!todo]
> - [ ] Read paper, verify and expand drafted key points, confirm Galaxy links

---

## Abstract (verbatim)
[Paste abstract from papers.json exactly — no edits, no paraphrasing, no ellipsis]

## Summary
[3–5 sentences. If full text available: draw from methods + results, not just abstract.
If project context loaded: open with "This paper is relevant to PROJECT_ID because..."
then summarize the core contribution.
If abstract-only: close with: *(Full text unavailable — summary from abstract only)*]

## Key points *(drafted — verify after reading)*
- **Methods:** [1–2 sentences on the approach, algorithm, or experimental design. Source: full text
  if available, otherwise abstract. If genuinely not inferable, write "Not clear from abstract."]
- **Key result:** [The single most important finding or contribution. Prefer a concrete claim over
  a vague description — e.g. "FPS with ECFP4 outperforms random selection by 15% on coverage" not
  "the method performs well". If not inferable, write "Not clear from abstract."]
- **Limitations:** [Known weaknesses, scope restrictions, or caveats stated or implied in the paper.
  If none inferable, write "Not stated."]
- **Relevance to project:** [What does this paper contribute to PROJECT_ID specifically? One
  sentence connecting the paper's contribution to the project's research questions. If no --project
  given, omit this bullet entirely.]

## Open questions *(from paper)*
[Bullet list of open problems, future directions, and unresolved issues stated by the authors,
drawn from conclusions and future work sections. These are the authors' own words/claims, not
your interpretation. If full text unavailable, infer from abstract if possible.
Format each as a standalone question or problem statement so it can be read out of context.
If none found: write "None stated explicitly." — never omit this section.]
- 

## Connections *(suggested — uncomment to confirm)*
<!--[[galaxy-concept-1]]-->
<!--[[galaxy-concept-2]]-->
<!--[[galaxy-concept-3]]-->

---
*Imported: YYYY-MM-DD | Full text: arxiv|unpaywall|abstract-only | lit-vault*
```

**Template rules:**
- Omit `project:` frontmatter line if no `--project` given
- Omit `doi:` if paper has no DOI; omit `arxiv:` if no arXiv ID
- Omit `screening_score:` if paper has no screening data
- Omit `## Connections` block entirely if no Galaxy candidates found (all scores = 0)
- Omit `Relevance to project:` bullet in Key points if no `--project` given
- Always include `## Abstract (verbatim)` — never shorten or paraphrase
- Always include `## Key points` — always draft content, never leave bullets blank
- Always include `## Open questions` — never omit even if empty; write "None stated explicitly."
- Prefer full text over abstract for key points and open questions; flag abstract-only sourcing as *(from abstract)*
- If `source` is `arxiv-pdf` or `unpaywall-pdf`: full text is PyMuPDF-extracted from PDF — equations and numerical values may be garbled. Use the abstract for all quantitative claims (specific numbers, equations, error bars). Narrative text (methods description, conclusions) from PDF is reliable. Flag equation-dependent key results as *(verify — PDF source)*.
- `> [!todo]` renders as Obsidian callout; keep it exactly as shown

### Step 5: Report

Before reporting, verify actual files on disk — do not count papers attempted:
```bash
# confirm each expected file exists before including in report
for expected_path in $WRITTEN_PATHS; do
    [ -f "$expected_path" ] && echo "$expected_path"
done
```

Only list notes whose file path was confirmed to exist. If a write was attempted but the file does not exist, log it as a write failure, not as imported.

```
Imported:  N notes → VAULT_DIR/20-Sources/papers/
  [list each confirmed filename, one per line]
Skipped:   M files (already exist — use --overwrite to replace)
Failed:    F writes (attempted but file not found — check permissions/path)
Full text: K papers (arXiv: J | Unpaywall: L | abstract-only: P)
```

If `--dry-run`: "Dry run — no files written. N notes would be created."

### Step 6: Update project memory (if --project)

Re-locate the project memory file (same logic as Step 1).

Find or create a `## Paper pool` section. Update fields in-place — do not duplicate the section:

```markdown
## Paper pool

Last updated: YYYY-MM-DD
Total imported for this project: N
Latest batch: YYYY-MM-DD — N papers added
Topics covered: tag1, tag2, tag3, tag4
Top venues: Journal1, Journal2, Journal3
```

Rules:
- `Total imported` = existing count (read from file) + newly imported count
- `Topics covered` = union of subject tags across all newly imported notes
- `Top venues` = top 3 venues by frequency from newly imported papers
- If `## Paper pool` absent: append at end of file
- If memory file absent: create a minimal stub and warn the user
- Do not modify any other section of the memory file

## Security

1. Only write to `VAULT_DIR/20-Sources/papers/` (or explicit `--output-dir`). No writes elsewhere.
2. Never delete vault files.
3. `--overwrite` required to replace existing notes.
4. PDFs downloaded to `/tmp/` only — never persisted to disk beyond the session.
5. Unpaywall and arXiv requests: 0.5 s delay between fetches; back off on HTTP 429.
6. Memory update modifies only the `## Paper pool` section.

