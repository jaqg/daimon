---
name: lit-bib
description: >
  Bibliography management: generate and update .bib files from papers.json, DOI lists, or arXiv IDs,
  with optional Zotero desktop sync. Trigger for: "/lit-bib", "generate bib", "make a bib file",
  "update my bibliography", "add to .bib", "add to bibliography", "sync with Zotero",
  "import to Zotero", "create refs.bib", "fetch BibTeX for these papers".
  Never generates or guesses BibTeX fields — only fetches from CrossRef/arXiv.
tools: Bash, Read, Write
---

# lit-bib

Fetches verified BibTeX entries from CrossRef and arXiv. Validates titles via Levenshtein
similarity (≥85%) to prevent hallucinated fields. Optionally syncs to Zotero desktop.

## Config keys (sourced from config.local)

```bash
ZOTERO_API_URL=http://localhost:23119   # default; requires Better BibTeX plugin
```

## Flags

```
--papers PATH          source papers.json (from lit-search)
--dois "10.x/y, ..."   manual DOI list (comma-separated)
--arxiv "2301.x, ..."  manual arXiv ID list
--output PATH          target .bib (default: refs.bib in cwd)
--update PATH          merge into existing .bib (dedup by DOI/citekey)
--style phys|acs|apa|ieee   citekey format (default: phys = author+year+keyword)
--zotero               sync to Zotero desktop (default: auto-detect)
--no-zotero            skip Zotero
--validate             HEAD-check every DOI before writing
```

## Step 0: Parse inputs

Determine paper source:
- `--papers`: load papers.json, use all papers with `screening_status != "excluded"` (or all if unscreened)
- `--dois`: parse comma-separated DOI list
- `--arxiv`: parse comma-separated arXiv ID list

Source config.local:
```bash
CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$CONFIG" ]] && source "$CONFIG"
```

## Step 1: Locate scripts

```bash
FETCH_SCRIPT=$(find -L ~/.claude -path "*/lit-bib/scripts/fetch_bibtex.py" -type f | head -1)
ZOTERO_SCRIPT=$(find -L ~/.claude -path "*/lit-bib/scripts/zotero_sync.py" -type f | head -1)
```

## Step 2: Fetch BibTeX

```bash
python3 "$FETCH_SCRIPT" \
  --papers <papers.json or synthesized list> \
  --style phys \
  [--validate]
```

The script:
1. For each paper: tries CrossRef first (via DOI), then arXiv API (via arXiv ID)
2. Validates fetched title against known title (Levenshtein ≥85%)
3. Generates citekey in requested style
4. Reports: N fetched, N failed (no DOI/ID), N manual-needed (title mismatch / DOI won't resolve)

**Never generates or guesses BibTeX fields.** If fetch fails → paper goes to manual-needed list.

## Step 3: Write .bib file

**If `--update`**: load existing .bib, merge new entries, deduplicate by DOI and citekey.
Report: N new entries added, N duplicates skipped, N conflicts (same DOI, different citekey).

**If `--output`** (or default `refs.bib`): write new file.

Show the user:
- Output path
- Summary: X entries written, Y failed (see manual-needed list), Z skipped (duplicate)
- List of manual-needed papers (title + reason)

## Step 4: Zotero sync (unless --no-zotero)

```bash
python3 "$ZOTERO_SCRIPT" --bibtex <output.bib>
```

The script:
1. Checks if Zotero is running at `ZOTERO_API_URL` (default: `http://localhost:23119`)
2. If not running: prints one-line warning and skips — does NOT abort
3. For each entry: checks for existing DOI before importing
4. Reports: N new, N updated, N skipped (already in Zotero), N failed

## Step 5: Report

```
Bibliography complete:
  .bib: refs.bib (N entries)
  Zotero: N new, N skipped | [or: skipped (Zotero not running)]

Manual entry needed (N papers):
  - Smith 2023: "Title" — DOI does not resolve
  - Jones 2022: "Title" — title mismatch (fetched: "Different Title")
```

## Security: what this skill guarantees

1. No hallucinated BibTeX — only fetches from CrossRef/arXiv; never generates fields.
2. Title validation — rejects entries where fetched title differs >15% from known title.
3. DOI resolution — verifies DOI resolves (HEAD check) when `--validate` is set.
4. Cannot-fetch list — papers without DOI or arXiv ID go to manual-needed, not silently dropped.
5. Duplicate report — same DOI with different citekeys flagged as conflict.
6. Zotero pre-check — duplicate check before every import (no duplicate items).

## Error handling

| Problem | Action |
|---------|--------|
| CrossRef fetch fails | Fallback to arXiv; if both fail → manual-needed |
| Title mismatch | Manual-needed (never silently accept wrong entry) |
| Zotero not running | One-line warning; continue writing .bib |
| DOI won't resolve | Manual-needed when --validate is set |
| Duplicate citekey | Append suffix (`key2`, `key3`) and report conflict |
