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
  --output "$OUTPUT_DIR/papers-raw.json"
```

Display coverage statement and paper count. Proceed even if fewer than 5 papers (warn user).

## Stage 2: PRISMA Screening (if not --notebooklm or --report)

Apply PRISMA methodology (from K-Dense literature-review plugin):

### Phase order
1. **Identification**: total papers from search
2. **Title screening**: exclude clearly irrelevant (score 1–2) on title alone
3. **Abstract screening**: score remaining 1–5 on title + abstract
4. **Full inclusion**: papers scoring ≥ 3 are included (or score ≥ threshold from --criteria)
5. **PRISMA flowchart**: print ASCII counts at each stage

Scoring rubric (domain-agnostic):
- **5**: directly answers the review question / addresses core methodology
- **4**: clearly relevant, likely key reference
- **3**: relevant but peripheral; include unless abundant papers
- **2**: shares topic but different scope or approach; exclude if papers abundant
- **1**: not relevant; exclude

**Citation-count impact thresholds** (from K-Dense):
- Highly cited (>100 for >5yr paper, >20 for <3yr): default include even at score 3
- Never exclude a paper solely on low citations

**Venue tier** (informative, not decisive):
- Tier 1: Nature, Science, Cell, JACS, PRL, Angew. Chem., NeurIPS/ICML/ICLR/JMLR
- Tier 2: domain-leading journals (JCTC, PCCP, JCP, PRB for comp-chem; similar for other domains)

**Criteria logging**: store `--criteria` text in output JSON for reproducibility.

**Screening audit**: after exclusion, randomly re-examine 5% of excluded papers.
Flag any that appear to have been wrongly excluded.

**Abstract requirement**: flag papers without abstracts (cannot screen properly).

Print PRISMA flowchart:
```
Records identified: N
After title screening: N (excluded: N)
After abstract screening: N (excluded: N)
After criteria filter: N (excluded: N)
Included for analysis: N
```

Save screened `papers.json` with `screening_status` and `screening_score` filled in.

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

For each paper in batch, add URL as source:
```bash
$NLM source add "URL" --notebook NOTEBOOK_ID --json
```

Priority: arXiv abstract URL > open-access PDF > DOI URL.
If source add fails: log failure, continue. Note in report.

Wait for sources to process:
```bash
$NLM source wait SOURCE_ID --notebook NOTEBOOK_ID --timeout 120
```

### Analysis per batch

Default question (when no --goal):
> "Based on these papers about [TOPIC], provide: (1) **State of the field** — key results,
> open problems, recent trends, most promising approaches; (2) **Methodological comparison** —
> how do these papers differ in technique, framework, computational approach? Where do they agree
> or contradict? Be specific: cite papers by author and year. Note limitations and gaps."

If `--goal`: use that question instead.

```bash
$NLM ask "QUESTION" --notebook NOTEBOOK_ID --json
```

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

### Deliverable (if requested)

```bash
$NLM generate TYPE --notebook NOTEBOOK_ID
$NLM download TYPE output.FILE --notebook NOTEBOOK_ID
```

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
[NLM response]

## Synthesis [if multiple batches]
[merged synthesis]

## Hallucination check
Papers cited in analysis that appear in papers.json: N/M (N%)
[Flagged citations if any]

## Bibliography
refs.bib: N entries | Manual-needed: N (see list below)
[Manual-needed list]

## Zotero
[Sync result or "not synced"]

## Deliverable
[file path and type, or "none requested"]

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
