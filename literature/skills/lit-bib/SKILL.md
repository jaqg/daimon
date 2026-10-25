---
name: lit-bib
disable-model-invocation: true
description: >
  Bibliography management: generate and update .bib files from papers.json, DOI lists, or arXiv IDs,
  with optional Zotero desktop sync; plus QC verification of .bib entries against Crossref/arXiv.
  Trigger for: "/lit-bib", "/lit-bib verify", "generate bib", "make a bib file",
  "update my bibliography", "add to .bib", "add to bibliography", "sync with Zotero",
  "import to Zotero", "create refs.bib", "fetch BibTeX for these papers",
  "verify bib", "audit bibliography", "check refs", "validate references".
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
# $SKILL_DIR = directory of this SKILL.md (symlink-verify: readlink -f "$SKILL_MD")
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
CONFIG="$SKILL_DIR/../../../config/config.local"
[[ -n "$CONFIG" ]] && source "$CONFIG"
```

## Step 1: Locate scripts

```bash
FETCH_SCRIPT="$SKILL_DIR/scripts/fetch_bibtex.py"
ZOTERO_SCRIPT="$SKILL_DIR/scripts/zotero_sync.py"
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
3. **Author-set verification** — rejects entries whose fetched first-author family
   name differs from the record's, or where <50% of expected family names appear
   among fetched authors. Rationale (observed failure 2026-10-21): a WRONG-author
   entry pointing at a REAL DOI passes both resolution and — if the title is close
   enough — title validation. Title-approximate misattributions (paraphrased title,
   right first author, wrong coauthors) are only caught by author-set comparison.
   Checks pass vacuously when the input record carries no authors (manual DOI/arXiv
   lists) — for those, `--validate` (DOI resolution) is the only guard.
4. DOI resolution — verifies DOI resolves (HEAD check) when `--validate` is set.
5. Cannot-fetch list — papers without DOI or arXiv ID go to manual-needed, not silently dropped; manual-needed reasons print to stderr.
6. Duplicate report — same DOI with different citekeys flagged as conflict.
7. Zotero pre-check — duplicate check before every import (no duplicate items).

## Known fetch artifacts (curator overrides, document each override in the .bib comment)

- **Online-first vs volume year**: Crossref often returns the online-first year
  (e.g. QST vol. 8 / 2023 returned as 2022-11). Citekey and `year` follow the
  record; override to the volume year when the journal-ref is verified, and
  leave a `%` comment stating the basis.
- **`author = {Various, ...}` in the source record** now trips the author-set
  check (by design) — replace placeholder authors with the real set before fetching.

## Error handling

| Problem | Action |
|---------|--------|
| CrossRef fetch fails | Fallback to arXiv; if both fail → manual-needed |
| Title mismatch | Manual-needed (never silently accept wrong entry) |
| Zotero not running | One-line warning; continue writing .bib |
| DOI won't resolve | Manual-needed when --validate is set |
| Duplicate citekey | Append suffix (`key2`, `key3`) and report conflict |

---

# Mode: verify (`/lit-bib verify`)

QC verification of an existing .bib against Crossref/arXiv. Built after the
2026-10-21 citation audit (phantom DOIs, mislabeled keys, 14/21 bad entries).

## CLI

```bash
VERIFY_SCRIPT="$SKILL_DIR/scripts/verify_bibtex.py"
python3 "$VERIFY_SCRIPT" PATH [--strict]
```

`PATH` = one .bib file, a directory (all `*.bib`), or `-` (stdin).

## Flags

```
--strict        exit 1 on unverified entries too (default: only fabricated|mismatch)
--key-check on|off   verify citekey contains resolved surname+year (default on;
                     off = metadata-only verification for legacy bibs)
```

## I/O contract (deterministic, no model judgment)

- **stdout** = structured JSON only:

```json
{"entries": [{"key": "pendas2005", "status": "fabricated",
               "provenance": "crossref",
               "details": {"reason": "identifier did not resolve via crossref ...",
                            "reasons": ["..."], "doi": "10.1021/ct050106q"}}],
 "summary": {"verified": N, "fabricated": N, "mismatch": N, "unverified": N}}
```

- **stderr** = one human summary line (fetch-header shape):
  `Verified: N | Fabricated: N | Mismatch: N | Unverified: N`
  plus `Duplicate keys: k1, k2` when the same key is used by >1 real entry.
- **exit**: 1 if any fabricated, mismatch, or duplicate key (verified/
  unverified-only = 0).
- Parser skips whole-line `%` comments between entries (a `%` line quoting
  `@misc{key}` verbatim is not an entry); `%` inside entry values is literal.
  Real duplicate keys remain a hard, exit-blocking finding.

## Classification table (script-owned)

| Condition | status |
|-----------|--------|
| DOI/eprint does not resolve (404) | fabricated |
| title Levenshtein sim < 0.5 vs resolved record | fabricated |
| title sim 0.5–0.85 | mismatch |
| first-author surname or year (>±1) disagreement | mismatch |
| key lacks resolved first-author surname (strict) | mismatch |
| key lacks resolved year (±1 tolerated) | mismatch |
| title sim ≥ 0.85 AND author+year match | verified |
| no DOI and no eprint | unverified |

DOI present → Crossref; eprint present with no DOI → arXiv API. Key check runs
whenever metadata resolves (disable with `--key-check off`): key must contain
resolved first-author surname (STRICT — method-name keys like `pendas2005` are
flagged, editorial: rename or justify) AND resolved year with ±1 tolerance
(online-first vs issue year; catches `various2024quantifying`,
`dipaola2023dipole`).

## Trigger phrases

"verify bib", "audit bibliography", "check refs", "validate references",
"/lit-bib verify <path>".

## Judgment layer rules (agent)

1. **Report only, never fix.** Run the script, pass the JSON report back to the
   user / project gate verbatim (per-entry status + reasons). The model NEVER
   edits, deletes, or regenerates entries itself — fabricated/mismatch entries
   are flagged for the user or gate to act on.
2. **Interpret statuses** (`details.reasons` names the real resolved title,
   expected surname/year): fabricated = paper does not exist / DOI is fake;
   mismatch = real paper but fields or key wrong; unverified = no identifier —
   ask the user for DOI/arXiv ID or mark as manual.
3. **Gate action proposal** (suggest only): delete fabricated, correct-or-replace
   mismatch entries with the resolved metadata quoted in `details.resolved`,
   supply identifiers for unverified.
4. Exit 1 is EXPECTED when problems were found — not a tooling error.
   Duplicate keys (`report.duplicates`) are exit-blocking too — flag both
   entries for the user/gate.
5. Network note: Crossref polite pool uses `CROSSREF_MAILTO` from config.local
   when present (else generic UA); retries/backoff live in `fetch()`.
