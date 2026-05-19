---
name: lit-search
description: >
  Multi-database paper discovery and citation chasing. Use when the user wants to find papers:
  "/lit-search", "search papers on X", "find papers about X", "search the literature for X",
  "find recent papers on X", "chase citations of [paper/DOI/arXiv]", "what cites [paper]",
  "references of [paper]", "chase this PDF", "forward citations of [DOI]",
  "backward references of [paper]". Also handles "--chase" flag for citation graph expansion.
  Output: papers.json file usable by lit-review, lit-bib, lit-watch.
tools: Bash, Read, Write
---

# lit-search

Discovers papers across multiple academic databases and outputs a structured `papers.json`
file for downstream use by `lit-review`, `lit-bib`, and `lit-watch`.

## Config keys (all optional — sourced from config.local)

```bash
SEMANTIC_SCHOLAR_API_KEY   # higher rate limits (free, get from semanticscholar.org)
NCBI_API_KEY               # PubMed higher rate limits (free from NCBI)
WOS_API_KEY                # Web of Science (institutional)
SCOPUS_API_KEY             # Scopus (institutional)
```

Skill prints a coverage statement after every run listing which databases were searched
and which were skipped (no key or not requested).

## Flags

```
--topic QUERY          keyword search (default mode)
--chase PAPER          citation graph from paper: DOI / arXiv ID / URL / local PDF path
  --chase-mode forward|backward|both   (default: both; forward=papers citing this; backward=references)
--results N            papers to return (default: 20)
--domain general|comp-chem|ml|physics|bio   (default: general)
--sources arxiv,semantic_scholar,...         override DB selection
--months M             date window: papers from last M months
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--sort impact|citations|recency|relevance    (default: impact = citations/year)
--min-citations N
--append PATH          merge results into existing papers.json (dedup by DOI/arXiv ID)
--output PATH          save papers.json (default: papers-QUERY-DATE.json in cwd)
```

## Step 0: Gather inputs

Parse the user request to extract:
- **Mode**: `--topic` (keyword search) or `--chase` (citation graph)
- **Query / paper**: what to search for, or which paper to chase
- **Options**: domain, date range, result count, sort, min-citations
- **Output path**: default `papers-<slug>-<date>.json` in cwd if not specified

Source config.local for API keys:
```bash
CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$CONFIG" ]] && source "$CONFIG"
```

## Step 1: Locate scripts

```bash
SEARCH_SCRIPT=$(find -L ~/.claude -path "*/lit-search/scripts/search.py" -type f | head -1)
CHASE_SCRIPT=$(find -L ~/.claude -path "*/lit-search/scripts/chase.py" -type f | head -1)
```

## Step 2: Run search

### Keyword search (--topic mode)

```bash
python3 "$SEARCH_SCRIPT" "QUERY" \
  --results N \
  [--domain comp-chem|ml|physics|bio|general] \
  [--months M | --from-date YYYY-MM-DD [--to-date YYYY-MM-DD]] \
  [--sort impact|citations|recency|relevance] \
  [--min-citations N] \
  [--sources arxiv,semantic_scholar,openalex,chemrxiv,pubmed] \
  [--append existing.json] \
  --output papers-QUERY-DATE.json
```

Set `SEMANTIC_SCHOLAR_API_KEY`, `NCBI_API_KEY`, etc. in the environment before running
(already loaded from config.local in Step 0).

### Citation chase (--chase mode)

```bash
python3 "$CHASE_SCRIPT" "DOI_OR_ARXIV_OR_PDF" \
  --mode forward|backward|both \
  --results N \
  [--append existing.json] \
  --output papers-chase-DATE.json
```

For local PDF: pass the absolute path. PyMuPDF must be installed (`pip install pymupdf`).

## Step 3: Report results

Capture stderr (coverage statement + warnings) and display to user.

Parse and display the papers.json summary:
- Number of papers found, databases searched, databases skipped
- Any warnings (source diversity, recency bias)
- For --chase: how many resolved vs manual-check
- Top 5 papers by impact score (title, authors, year, citations, venue)

Always show the coverage statement:
> Searched: arxiv, semantic_scholar, openalex | Not searched (no key): wos, scopus

## Step 4: Suggest next steps

After reporting results, offer:
```
papers.json saved to: <path>
Next steps:
  - Screen and analyze:  /lit-review --papers <path>
  - Generate .bib only:  /lit-bib --papers <path>
  - Append more papers:  /lit-search --topic "X" --append <path>
```

## Security: what this skill guarantees

1. Every paper in papers.json has a DOI or arXiv ID — no orphan entries.
2. Coverage statement always printed (stderr + shown to user).
3. Source diversity warning if >80% from one DB.
4. Recency bias warning if >70% of results are <2 years old and no date filter set.
5. Chase verification: source paper resolved before expanding citations.
6. Rate limit safety: exponential backoff, never exceeds free API limits.

## Error handling

| Problem | Action |
|---------|--------|
| No output file specified | Default to `papers-<slugified-query>-<YYYY-MM-DD>.json` in cwd |
| Fewer than 3 papers | Suggest `--months 60`, broader query, or `--sources all` |
| PyMuPDF missing for PDF chase | Print install command; offer to proceed with DOI/URL only |
| S2 / OpenAlex API down | Continue with remaining sources; note in coverage statement |
| PDF: <20% refs resolved | Warn; list all unresolved for manual check |
