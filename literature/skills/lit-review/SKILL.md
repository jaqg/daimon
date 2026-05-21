---
name: lit-review
description: >
  Full literature review pipeline: search → PRISMA screening → NotebookLM analysis → report + .bib.
  Use when user wants a structured literature review: "/lit-review", "run a literature review on X",
  "full lit review on X", "review these papers", "screen my paper list", "analyze papers on X",
  "lit review for my project", "literature review --screen", "review --notebooklm",
  "comprehensive review of X", "systematic review of X".
  Orchestrates lit-search, lit-bib, and NotebookLM. All stages accessible via flags.
tools: Bash, Read, Write
---

# lit-review

Full pipeline from topic/paper list to knowledge artifact. Each stage is accessible independently
via flags. Default (`--full`) runs all stages.

## Config keys (sourced from config.local)

```bash
NOTEBOOKLM_CMD         # notebooklm CLI (default: notebooklm)
SEMANTIC_SCHOLAR_API_KEY
NCBI_API_KEY
ZOTERO_API_URL
```

## Flags

```
-- Input (one required) --
--topic QUERY          run lit-search first, then proceed
--papers PATH          use existing papers.json (skip search)
--project PROJECT_ID   read vault memory for search context and screening keywords

-- Stage flags (default: --full) --
--screen               screen only (PRISMA; stop after screening)
--notebooklm           NotebookLM stages only (assumes papers already screened)
--report               generate report only (assumes notebooks exist)
--bib                  generate .bib only (skips NLM)
--full                 all stages (default)
--no-notebooklm        search + screen + bib, skip NLM entirely

-- Search options (passed to lit-search when --topic used) --
--domain general|comp-chem|ml|physics|bio
--months M / --from-date / --to-date
--results N

-- Analysis --
--goal "TEXT"          custom NotebookLM question (default: state-of-field + methodology comparison)
--criteria "TEXT"      PRISMA inclusion/exclusion criteria (stated before screening)
--deliverable TYPE     podcast|flashcards|study-guide|quiz
--output DIR           output directory (default: lit-review-TOPIC-DATE/ in cwd)

-- Pipeline enhancements --
--expand [N]           pass through to lit-search query expansion (N derived queries, default 3)
--adaptive             adaptive NLM follow-up questions per batch (identify gaps, ask targeted follow-ups)
--adaptive-depth N     max follow-up questions per batch (default 2; raise for deeper research)
--web                  web search pass for grey literature (added as NLM URL sources only)
```

## Step 0: Setup

Source config.local:
```bash
CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$CONFIG" ]] && source "$CONFIG"
NLM="${NOTEBOOKLM_CMD:-notebooklm}"
```

Determine output dir: `lit-review-<slugified-topic>-<YYYY-MM-DD>/` (create it).

If `--project`: read vault memory file for project keywords to use in screening.
```bash
MEMORY_DIR=$(find ~/.claude/projects -name "MEMORY.md" | head -1 | xargs dirname)
# read $MEMORY_DIR/project_<PROJECT_ID>.md
```

## Stage 1: Search (if --topic)

Locate search script:
```bash
SEARCH_SCRIPT=$(find -L ~/.claude -path "*/lit-search/scripts/search.py" -type f | head -1)
```

```bash
python3 "$SEARCH_SCRIPT" "TOPIC" \
  --results $N --domain $DOMAIN \
  [date flags] \
  ${EXPAND:+--expand $EXPAND} \
  --output "$OUTPUT_DIR/papers-raw.json"
```

If `--expand N` was passed to lit-review, set `EXPAND=N` and pass it through. The search script
will append expansion results into papers-raw.json before returning. See lit-search Step 2b.

Display coverage statement and paper count. Proceed even if fewer than 5 papers (warn user).

## Stage 2: PRISMA Screening (if not --notebooklm or --report)

### Phase 2a: Deterministic pre-filter (script)

Run before Claude sees any abstracts:

```bash
PREFILTER=$(find -L ~/.claude -path "*/lit-review/scripts/prisma_prefilter.py" -type f | head -1)
python3 "$PREFILTER" \
  --papers "$OUTPUT_DIR/papers-raw.json" \
  [--keywords "K1,K2,..."] \
  [--exclude-terms "T1,T2,..."]
```

Extract keywords from `--criteria` text or project memory (the nouns and domain terms).
Extract exclude-terms from `--criteria` exclusion clauses (e.g. "Exclude: biology, MD simulations").

Output: `{"auto_excluded": [...], "auto_included": [...], "for_claude": [...], "stats": {...}}`.

Report pre-filter results:
```
Pre-filter: N total → auto-excluded: A (no keyword match) | auto-included: B (high citations) | for Claude: C (reduction_pct%)
```

### Phase 2b: Abstract screening (Claude — for_claude set only)

Apply PRISMA methodology to `for_claude` papers only:

1. **Title screening**: exclude clearly irrelevant (score 1–2) on title alone
2. **Abstract screening**: score remaining 1–5 on title + abstract
3. **Full inclusion**: papers scoring ≥ 3 included (or ≥ threshold from --criteria)

Scoring rubric (domain-agnostic):
- **5**: directly answers the review question / addresses core methodology
- **4**: clearly relevant, likely key reference
- **3**: relevant but peripheral; include unless abundant papers
- **2**: shares topic but different scope or approach; exclude if papers abundant
- **1**: not relevant; exclude

**Venue tier** (informative, not decisive):
- Tier 1: Nature, Science, Cell, JACS, PRL, Angew. Chem., NeurIPS/ICML/ICLR/JMLR
- Tier 2: domain-leading journals (JCTC, PCCP, JCP, PRB for comp-chem; similar for other domains)

**Criteria logging**: store `--criteria` text in output JSON for reproducibility.

**Screening audit**: after exclusion, randomly re-examine 5% of excluded papers (from for_claude set).
Flag any that appear to have been wrongly excluded.

**Abstract requirement**: flag papers without abstracts (cannot screen properly).

### Phase 2c: Merge and PRISMA flowchart

Merge all three groups. Print:
```
Records identified: N
  Auto-excluded (pre-filter): A
  Auto-included (high-citation): B
After title screening: N (excluded: N)
After abstract screening: N (excluded: N)
After criteria filter: N (excluded: N)
Included for analysis: N
```

Save screened `papers.json` with `screening_status` and `screening_score` filled in for all papers.

## Phase 2.7: Web fallback (if --web)

Extract top 3–5 keyphrases from included paper titles (most frequent domain terms — skip
stopwords and short words <4 chars).

For each keyphrase, run WebSearch (Claude's WebSearch tool):
- `"{keyphrase} preprint 2024 2025"`
- `"{keyphrase} technical report grey literature"`

Collect unique URLs not already represented in papers-screened.json (match by URL substring
against doi and oa_locations fields). Target: preprint servers, agency reports, conference
proceedings not indexed by CrossRef.

Web sources are added to the NLM notebook in Stage 3 source-add — NOT added to papers.json
(no structured metadata; NLM processes them as additional context only).

Save collected URLs to `$OUTPUT_DIR/web-sources.txt` (one per line). Report:
"Web sources collected: N URLs → will be added to NLM notebook"

## Stage 3: NotebookLM Analysis (if not --screen, --bib, --no-notebooklm)

### Auth check
```bash
$NLM status
```
If fails: run `$NLM login`; ask user to re-authenticate.

### Batch logic (≤50 papers per notebook)

**If ≤50 included papers**: single notebook
```bash
$NLM create "Lit Review: TOPIC (YYYY-MM-DD)" --json
```

**If >50 included papers**: split into batches of 50
```bash
$NLM create "Lit Review: TOPIC — Batch 1/M (YYYY-MM-DD)" --json
$NLM create "Lit Review: TOPIC — Batch 2/M (YYYY-MM-DD)" --json
# ...
```
Assign each paper to a batch (`notebooklm_batch` field in papers.json).

### Add sources

For each paper in batch, add source in priority order — stop at first success:

1. **Local PDF** (if `--pdf-dir` given and file exists for this paper ID):
   ```bash
   $NLM source add "PATH/paperId.pdf" --type file --mime-type application/pdf --notebook NOTEBOOK_ID --json
   ```
2. **arXiv PDF URL** (if paper has `arxiv` field):
   ```bash
   $NLM source add "https://arxiv.org/pdf/{arxiv_id}" --notebook NOTEBOOK_ID --json
   ```
3. **Unpaywall OA PDF URL** (from `oa_locations` where `url_for_pdf` is set):
   ```bash
   $NLM source add "OA_PDF_URL" --notebook NOTEBOOK_ID --json
   ```
4. **DOI URL** (last resort — likely abstract only):
   ```bash
   $NLM source add "https://doi.org/{doi}" --notebook NOTEBOOK_ID --json
   ```

Do NOT use arXiv abstract URL (`arxiv.org/abs/...`) — NLM gets abstract only. arXiv PDF URL (`arxiv.org/pdf/...`) gives full paper.

If source add fails at all levels: log failure, continue. Note in report.

**Web sources (if --web):** After all paper sources are added, also add each URL from
`$OUTPUT_DIR/web-sources.txt`:
```bash
$NLM source add "URL" --notebook NOTEBOOK_ID --json
```
Log failures; web source failures are non-fatal.

Wait for sources to process:
```bash
$NLM source wait SOURCE_ID --notebook NOTEBOOK_ID --timeout 120
```

### Analysis per batch

**Construct question before calling `$NLM ask`:**

If `--goal`: use that question verbatim (skip question construction below).

Otherwise, build a structured question in two parts:

**Part 1 — General analysis (always included):**
```
Based on these papers about [TOPIC], provide:
(1) **State of the field** — key results, open problems, recent trends, most promising approaches.
(2) **Methodological comparison** — how do these papers differ in technique, framework, or computational approach? Where do they agree or contradict?
Be specific: cite papers by author and year. Note limitations and gaps.
```

**Part 2 — Project-specific analysis (only if `--project`):**

Read the project memory file (same logic as Step 1 of lit-vault: find `$MEMORY_DIR/project_*.md`
matching PROJECT_ID). Extract:
- Research questions (lines under "research questions", "open questions", or "goals" headings)
- Methodology keywords (domain terms, method names, computational approaches)
- Known gaps (lines under "gaps", "missing", "unknown", or "limitations" headings)

Append to the question:
```
(3) **Project-specific analysis** — For the [PROJECT_ID] project, address the following:
[List extracted research questions as sub-bullets, e.g.:
  - What mechanisms explain X?
  - Which methods best address Y?
  - What are known limitations of Z?]
Focus on: [comma-separated methodology keywords].
Flag any papers that directly address known gaps: [list extracted gaps].
```

If project memory file not found or yields no extractable questions/gaps: omit Part 2 entirely, log warning "No project context found for PROJECT_ID — using general question only."

```bash
$NLM ask "QUESTION" --notebook NOTEBOOK_ID --json
```

### Adaptive follow-up (if --adaptive)

After first ask response, read it and identify:
- Gaps explicitly flagged ("further research needed", "no studies found on…", "remains unclear")
- Topics mentioned in passing but not elaborated on
- Contradictions between cited papers that remain unresolved

Rank identified gaps by importance. For `i` in `1..adaptive_depth` (default 2):
1. Formulate a targeted follow-up question addressing the i-th most important gap.
2. `$NLM ask "FOLLOW_UP_i" --notebook NOTEBOOK_ID --json`
3. Save response.
4. If response reveals no new gaps or information: stop early (do not exhaust `--adaptive-depth`).

Include all follow-up responses in report under `## Adaptive Follow-up (i/adaptive_depth questions used)`.

### Cross-batch synthesis (if multiple batches)

Run synthesis query on **each notebook separately**, then on a synthesis notebook:
> "Compare and synthesize findings from all batches below. Ensure all sub-topics
> are covered. Identify consensus findings, contradictions, and gaps across the full paper set."

Provide each batch summary as context in the synthesis query.

### Hallucination guard

After NLM analysis: verify that ≥50% of papers cited by name/year in the NLM response
exist in papers.json. Flag any citations that don't match.

### Cross-batch coverage

Synthesis response must explicitly reference content from all N batches.
If any batch is absent from synthesis: run targeted follow-up question.

### Deliverable (default: briefing-doc; override with --deliverable)

Always generate a briefing-doc report after analysis. If `--deliverable` is specified, generate that type instead (or in addition).

Always pass `--append` with topic context so NLM focuses the briefing on the correct subject — without it, NLM may default to whatever source it considers most prominent.

```bash
# Build BRIEFING_CONTEXT: if --goal given, use that; otherwise use TOPIC string
BRIEFING_CONTEXT="${GOAL:-$TOPIC}"

$NLM generate report \
  --format briefing-doc \
  --notebook NOTEBOOK_ID \
  --append "$BRIEFING_CONTEXT" \
  --wait --json

$NLM download report "$OUTPUT_DIR/nlm-briefing-YYYY-MM-DD.md" \
  --notebook NOTEBOOK_ID --latest --force
```

**Topic validation after download**: read the briefing-doc and verify its content is about TOPIC (not a random paper). Check: does the title/first paragraph match the review subject?

- If content matches: proceed.
- If content is off-topic (NLM defaulted to wrong subject): re-run `generate report` once with a more explicit `--append "Provide a comprehensive briefing on TOPIC based on all sources in this notebook."` then re-download.
- If still off-topic after retry: **stop and report error to user** — do not embed wrong-topic content in the report. Do not fall back to existing report files.

Read the downloaded markdown file and embed its full content verbatim in the report under `## NLM Deliverable`. Do not summarize or rewrite it.

## Stage 4: Generate .bib (if --bib or --full)

```bash
FETCH_SCRIPT=$(find -L ~/.claude -path "*/lit-bib/scripts/fetch_bibtex.py" -type f | head -1)
ZOTERO_SCRIPT=$(find -L ~/.claude -path "*/lit-bib/scripts/zotero_sync.py" -type f | head -1)

python3 "$FETCH_SCRIPT" --papers "$OUTPUT_DIR/papers-screened.json" --style phys \
  > "$OUTPUT_DIR/refs.bib"

python3 "$ZOTERO_SCRIPT" --bibtex "$OUTPUT_DIR/refs.bib"
```

Report: N entries fetched, N manual-needed, Zotero sync result.

## Stage 5: Assemble report

Save to `$OUTPUT_DIR/lit-review-report-YYYY-MM-DD.md`:

```markdown
# Literature Review: TOPIC
**Date:** YYYY-MM-DD
**Goal:** [user goal or "State of field + methodological comparison (default)"]
**Criteria:** [screening criteria or "default PRISMA scoring ≥3"]
**Project:** [if --project]

---
## Coverage
Searched: [...] | Not searched (no key): [...]
Papers identified: N → screened: N → included: N

## PRISMA Flowchart
[ASCII flowchart]

## Screening Summary
[PRISMA phase table]

## Analysis — [Batch 1/M or single]
[verbatim NLM ask response]

## Synthesis [if multiple batches]
[merged synthesis]

## Adaptive Follow-up [if --adaptive; omit section if not used]
Questions asked: i/adaptive_depth
[verbatim follow-up responses, one subsection per question]

## Web sources [if --web; omit section if not used]
URLs added as NLM sources: N

## Hallucination check
Papers cited in analysis that appear in papers.json: N/M (N%)
[Flagged citations if any]

## Bibliography
refs.bib: N entries | Manual-needed: N (see list below)
[Manual-needed list]

## Zotero
[Sync result or "not synced"]

## NLM Deliverable
**Format:** briefing-doc (or type if --deliverable override)
**File:** nlm-briefing-YYYY-MM-DD.md
**Sources loaded:** N/M (note any paywalled failures)

[verbatim content of downloaded briefing-doc markdown]

## Notebook IDs
[list all notebook IDs so user can open in NotebookLM]

## Pipeline metadata
[dates, sources, sort, threshold, etc.]
```

## Security: what this skill guarantees

1. **Screening audit**: 5% random re-examination of excluded papers.
2. **Hallucination guard**: ≥50% of NLM-cited papers must exist in papers.json.
3. **Cross-batch coverage**: synthesis must reference all batches; follow-up if not.
4. **Abstract requirement**: papers without abstracts flagged (cannot screen properly).
5. **Criteria logging**: `--criteria` stored in papers.json for reproducibility.
6. **Citation sanity**: if <5 citations across all included papers for a broad topic, warn.
7. **DOI/arXiv ID required**: inherited from lit-search — no orphan papers.

## Error handling

| Problem | Action |
|---------|--------|
| NLM auth failure | `$NLM login`; ask user to re-auth |
| <5 papers found | Warn; suggest broadening search |
| Source add fails | Log failure; note in report; continue |
| Paywalled URL | Expected; arXiv fallback already preferred |
| NLM response too vague | One follow-up question before giving up |
| Synthesis missing a batch | Targeted follow-up for the missing batch |
| --screen only | Stop after Stage 2; save screened papers.json |
| --no-notebooklm | Skip Stages 3; run 1+2+4+5 |
