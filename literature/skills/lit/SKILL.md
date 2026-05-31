---
name: lit
description: >
  Literature pipeline orchestrator. Parses natural language intent and routes to the
  right lit-* skills in the correct order. Use for any literature request:
  "/lit", "find papers on X", "lit review on X", "import papers to vault",
  "full pipeline for X", "watch for new papers on X", "annotate this paper",
  "chase citations of X", "bib file for X", "extract literature for X".
  Eliminates needing to choose or manually sequence lit-* skills.
  Also triggers for: "literature for my project", "set up lit monitoring",
  "I finished reading [paper]", "generate bibliography for X", "what cites [paper]",
  "import from bib", "process my .bib file", "add papers from bibliography", "bib to vault".
tools: Bash, Read, Write
---

# lit

Natural-language entry point for the daimon literature pipeline. Parses user intent,
asks only the questions needed to fill in important missing parameters, shows an
execution plan, gets approval, then invokes sub-skills in order.

## Intent taxonomy

| Intent | Trigger phrases | Sub-skills invoked |
|--------|----------------|--------------------|
| `search` | "find papers", "search for papers", "papers on X", "discover papers" | `lit-search` |
| `chase` | "chase citations", "what cites X", "references of X", "citation graph" | `lit-search` (--chase) |
| `vault_import` | "import to vault", "add to vault", "extract literature for X", "save papers to vault" | `lit-search` → `lit-vault` |
| `review` | "review literature", "lit review on X", "analyze papers", "systematic review" | `lit-review` |
| `full` | "full pipeline", "everything for X", "complete workflow", "review + vault" | `lit-review` → `lit-vault` |
| `bib` | "generate bib", "bibliography for X", ".bib file", "BibTeX" | `lit-search` → `lit-bib` |
| `watch` | "watch papers on X", "monitor literature", "weekly update", "track new papers" | `lit-watch` |
| `annotate` | "annotate this paper", "read and annotate", "fill in notes for", "I finished reading" | `lit-annotate` |
| `bib_import` | "import from bib", "process my .bib file", "add papers from bibliography", "I have a .bib file", "bib to vault" | bib2papers → `lit-vault` |
| `coverage` | "what do I have on X", "existing coverage of X", "do I already have papers on X", "what's in my vault on X", "what do I know about X", "summarize my notes on X", "tell me about X in my vault", "what's the state of X in my literature" | graphify query → synthesize answer → escalate if thin |

Ambiguous intent: lean toward the more comprehensive option (e.g., `vault_import` over `search`).
If `review` is detected, ask whether the user also wants vault notes (→ `full`).

## Scripts

```bash
COVERAGE_SCRIPT=$(find -L ~/.claude -path "*/lit/scripts/coverage_check.py" -type f | head -1)
FRESHNESS_SCRIPT=$(find -L ~/.claude -path "*/lit/scripts/graph_freshness.py" -type f | head -1)
UPDATE_SCRIPT=$(find -L ~/.claude -path "*/lit/scripts/update_graph.sh" -type f | head -1)

# Resolve VAULT_DIR (needed for direct graphify calls)
_CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$_CONFIG" ]] && source "$_CONFIG"
VAULT_DIR="${VAULT_DIR:-$HOME/vault}"
VAULT_DIR="${VAULT_DIR/#\~/$HOME}"
```

## Step 0: Parse what's clear

Extract from user message:
- **intent**: one of the 9 intents above
- **topic**: what to search for
- **paper**: DOI / arXiv ID / URL / local path (for chase/annotate)
- **papers_path**: existing papers.json path if user mentions one
- **bib_path**: .bib file path (for bib_import)
- **local_pdf_dir**: base dir for local PDFs (e.g. Zotero storage; for bib_import / vault_import with full-text)
- **project**: project ID if mentioned
- **scope**: results count, domain, date range if stated

Map domain from topic language:
- "DFT", "QM", "QTAIM", "IQA", "computational chemistry", "zeolite" → `comp-chem`
- "ML", "neural network", "deep learning", "machine learning" → `ml`
- "biology", "enzyme", "protein", "biochemistry" → `bio`
- "physics", "condensed matter", "quantum physics" → `physics`
- otherwise → `general`

## Step 0b: Mini-intake

Ask only for what's actually needed and not already provided. Bundle all questions for
the intent into ONE message — do not ask one question at a time.

### Per-intent questions

**search:**
- (optional) "Associate with a project? (for memory/context, or skip)"
- Mention defaults: "Will search for 20 papers, sorted by impact. Adjust?"

**chase:**
- If direction not stated: "Forward citations, backward references, or both? (default: both)"

**vault_import:**
- If project not stated: "Which project should these notes be linked to? (or skip for no project)"
- "Full-text fetch or abstract-only? Full-text = slower but better notes; abstract-only = fast."
- If full-text chosen: "Do you have local PDFs (e.g. Zotero storage at ~/.local/share/Zotero/storage/)? If yes, provide the base directory — matching PDFs will be pre-cached to skip re-download."
- If full-text and no local PDFs: "Save downloaded PDFs anywhere? (provide path, or skip to discard after import)"
- If papers_path not provided: "Do you already have a papers.json from a previous search? (provide path, or skip to run a new search)"

**bib_import:**
- If bib_path not provided: "Path to the .bib file?" (required)
- If project not stated: "Which project should these notes be linked to? (or skip for no project)"
- "Full-text fetch or abstract-only? Full text = slower but better notes; abstract-only = fast."
- If full-text chosen: "Do you have local PDFs (e.g. Zotero storage)? If yes, provide the base directory — they will be pre-cached by DOI/key match before running lit-vault."
- If full-text and no local PDFs: "Save downloaded PDFs anywhere? (provide path, or skip)"
- "Want NotebookLM analysis after import? (yes = lit-review NLM stage on imported papers; no = vault notes only)"

**review:**
- "What should be included / excluded? (e.g. 'include only papers using DFT, exclude review articles') — or skip for default PRISMA scoring"
- "Also want vault notes after the review? (yes → full pipeline)"
- If project not stated: "Project context? (improves screening relevance)"
- "NotebookLM analysis included? (yes = full review with NLM; no = screening + .bib only)"

**full:**
- "Screening criteria? (include/exclude rules — or skip for default)"
- If project not stated: "Project? (required for vault notes to be project-linked)"
- "Full-text fetch for vault notes? (slower but better notes)"
- If full-text: "Save PDFs? (provide path or skip)"

**bib:**
- "Update an existing .bib file or create new? (if update, provide path)"
- "Output path for the .bib? (default: refs.bib in current directory)"
- If papers_path not provided: "Do you have an existing papers.json? (or run new search)"

**watch:**
- If neither project nor topics stated: "Monitor by project (reads project memory) or by explicit topics? Which project / what topics?"
- If project not stated and intent is watch: project OR topics is required — must ask.

**annotate:**
- If note not identified: "Which paper note? (filename, author+year prefix, or fuzzy name)"
- "Source material: paste your reading notes, provide a PDF path, a URL, or re-fetch? (or skip to annotate from abstract only)"

### Intake rules
- If a parameter is already clear from the message, do NOT ask for it again.
- Keep questions brief and offer clear options with defaults marked.
- For optional questions (project on search, PDF storage), make it easy to skip.
- After intake, proceed immediately to Step 0c — no further questions before showing the plan.

## Step 0c: Graph check (skip for `watch`, `bib`, `annotate`)

Run freshness check and coverage check before building the plan. These are read-only and fast.

```bash
FRESHNESS=$(python3 "$FRESHNESS_SCRIPT")
# FRESHNESS: {"fresh": bool, "stale_notes": N, "graph_json": PATH|null}
```

If `graph_json` is null: skip graph check silently — no graph built yet.

If `fresh` is false and `stale_notes` > 0: warn once:
> Graph is stale — `stale_notes` note(s) modified since last build. Coverage results may miss
> recent imports. Rebuild with: `/graphify VAULT_DIR`

Then run coverage regardless (stale results still useful as a lower bound):

```bash
COVERAGE=$(python3 "$COVERAGE_SCRIPT" "TOPIC")
# COVERAGE: {"node_count": N, "papers": [...], "galaxy_concepts": [...]}
```

Synthesize a one-line summary to show the user in the plan:
- `papers` list → existing paper notes in vault for this topic
- `galaxy_concepts` list → your distilled concept notes relevant to this topic

Display as part of Step 1 plan header:
```
Vault coverage: N papers, M Galaxy concepts already on '[topic]'.
```

Use coverage to inform plan defaults:
- If `len(papers) >= 10`: suggest "Search for gaps only?" — offer to pass `--append` to existing papers.json
- If `len(papers) == 0` and intent is `vault_import`: no shortcut available; proceed with full search.
- For `annotate`: pass `galaxy_concepts` as suggested `[[links]]` to lit-annotate (see Step 2).

For `coverage` intent: skip Step 1 plan. Proceed directly to Step 2 coverage block — do NOT jump to Step 3 yet; the full graphify query in Step 2 is required before synthesis.

## Step 1: Show plan and get approval

Display:

```
Plan: [paraphrased intent in one line]

  Step N: [skill-name] — [what it will do]
           Flags: [key flags, including scope defaults so user sees what's happening]
  Step N+1: [skill-name] — [what it will do]
           Flags: [key flags]

Tip: [one optional enhancement, e.g. "Add --expand 3 to also search related topics" or
     "Add --adaptive to lit-review for deeper gap analysis"]

Proceed? Enter y to run, or describe what to change.
```

Always show defaults explicitly in flags (e.g. `--results 20 --sort impact`).
The "Tip" line is optional — only include when a flag would meaningfully improve results.

Wait for explicit confirmation (y / yes / ok / go) or change request.
If user requests changes: update the plan and show again. Do not run until confirmed.

## Step 2: Execute

Invoke sub-skills in order using the Skill tool. Pass file paths between steps.

### Per-intent invocation

**search:**
```
lit-search: --topic TOPIC --results N --sort impact [--domain D] [date flags]
            [--min-citations N if stated] [--expand N if stated]
```

**chase:**
```
lit-search: --chase PAPER --mode MODE --results N
```
MODE defaults to `both` unless user specified forward/backward.

**vault_import:**
```
lit-search: --topic TOPIC --results N --sort impact [--domain D] [date flags]
            (skip if papers_path provided)
lit-vault:  --papers PATH [--project PROJECT] [--no-full-text if chosen]
            [--output-dir if non-default] [--overwrite if re-importing]
```
After lit-vault completes, update the graph:
```bash
bash "$UPDATE_SCRIPT"   # graphify --update on vault; keeps coverage check current
```

**review:**
```
lit-review: --topic TOPIC --results N [--domain D] [--project PROJECT]
            [--criteria "TEXT"] [--no-notebooklm if chosen] [--expand N if stated]
            [--adaptive if stated]
```
lit-review runs its own search internally — do NOT run lit-search separately.
NLM analysis (Stage 3) is handled by lit-review's `--notebooklm` flag (on by default). **Never invoke the notebooklm skill directly** for literature analysis — lit-review's Stage 3 adds sources in priority order (local PDF → arXiv → Unpaywall → DOI URL) and runs structured multi-question analysis that the standalone notebooklm skill lacks.

**full:**
```
lit-review: --topic TOPIC --results N [--domain D] [--project PROJECT]
            [--criteria "TEXT"] [--expand N if stated]
lit-vault:  --papers <screened papers output from lit-review>
            [--project PROJECT] [--no-full-text if chosen]
```
NLM analysis (if wanted) is lit-review Stage 3 — already included unless `--no-notebooklm` is passed. **Never invoke notebooklm skill directly.**
After lit-vault completes:
```bash
bash "$UPDATE_SCRIPT"
```

**bib:**
```
lit-search: --topic TOPIC --results N [--domain D]
            (skip if papers_path provided; also accepts --dois / --arxiv lists)
lit-bib:    --papers PATH [--output OUT.bib | --update EXISTING.bib]
            [--style phys] [--zotero | --no-zotero]
```

**watch:**
```
lit-watch:  [--project PROJECT | --topics "X, Y"] [--threshold 4]
            [--since DATE if override needed]
```

**annotate:**

Run coverage check using the paper title or topic as query:
```bash
COVERAGE=$(python3 "$COVERAGE_SCRIPT" "PAPER_TITLE_OR_TOPIC" 400)
```
Extract `galaxy_concepts` from the JSON. Pass them to lit-annotate as suggested links:
```
lit-annotate: --note NOTE_IDENTIFIER [--text "..." | --pdf PATH | --url URL]
              [--project PROJECT if set]
              Suggest linking to these Galaxy concepts found via graphify: [[concept1]], [[concept2]], ...
```
Only suggest concepts where `source_file` starts with `30-Galaxy/` — those are your notes, not auto-extracted nodes.

**coverage:**
```bash
FRESHNESS=$(python3 "$FRESHNESS_SCRIPT")
COVERAGE=$(python3 "$COVERAGE_SCRIPT" "TOPIC")
# Full graphify context for synthesis (larger budget = more note chunks retrieved):
GRAPHIFY_CTX=$(cd "$VAULT_DIR" && graphify query "TOPIC" --budget 1500 2>/dev/null)
```
No sub-skills. Skip Step 1. After running the three commands above, go to Step 3.

**CRITICAL**: Do NOT use the Read tool to inspect paper notes individually. Graphify is
the only retrieval mechanism for vault knowledge. `GRAPHIFY_CTX` contains actual excerpts
from paper notes and Galaxy concept notes — use it as the RAG context for synthesis.
If graphify is not installed or graph.json doesn't exist, report this to the user and stop;
do not attempt to read notes manually as a fallback.

Synthesis: use `GRAPHIFY_CTX` to compose a prose answer to the user's actual question.
Cite paper notes by short key (e.g. `rogers2010-ecfp`) and Galaxy concepts by name.

**bib_import:**

Requires `bib2papers.py` — locate with:
```bash
BIB2PAPERS=$(find -L ~/.claude -path "*/lit/scripts/bib2papers.py" -type f | head -1)
```
If not found, warn the user: "bib2papers.py not yet in daimon — conversion step must be done manually (see note below)."

Step 1 — convert .bib → papers.json (DOI enrichment via Semantic Scholar + abstract extraction):
```bash
python3 "$BIB2PAPERS" --bib BIB_PATH --output papers.json
```

Step 2 (optional) — pre-cache local PDFs if `local_pdf_dir` was provided. This populates
`~/.cache/daimon/lit-vault/fulltext-cache.json` with extracted text keyed by paper ID so
lit-vault skips re-downloading already-local files. Run inline:
```python
# Pre-cache local PDFs from Zotero (or any flat/nested PDF directory)
import json, hashlib, subprocess
from pathlib import Path

cache_path = Path("~/.cache/daimon/lit-vault/fulltext-cache.json").expanduser()
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

papers = json.loads(Path("papers.json").read_text())
pdf_base = Path("LOCAL_PDF_DIR")

for p in papers:
    pid = p.get("paperId") or p.get("doi") or p.get("externalIds", {}).get("DOI")
    if not pid or pid in cache:
        continue
    # Find PDF by DOI/key match in filename or Zotero storage subdir
    matches = list(pdf_base.rglob("*.pdf"))
    doi_slug = str(pid).replace("/", "_").lower()
    hit = next((f for f in matches if doi_slug in f.name.lower() or doi_slug in str(f.parent).lower()), None)
    if hit:
        result = subprocess.run(["python3", "-c",
            f"import fitz; d=fitz.open('{hit}'); print('\\n'.join(p.get_text() for p in d))"],
            capture_output=True, text=True)
        if result.stdout.strip():
            cache[pid] = result.stdout.strip()

cache_path.parent.mkdir(parents=True, exist_ok=True)
cache_path.write_text(json.dumps(cache, indent=2))
print(f"Pre-cached {sum(1 for p in papers if (p.get('paperId') or p.get('doi')) in cache)} PDFs")
```
Note: requires `pymupdf` (`pip install pymupdf`). If not installed, skip and let lit-vault fetch normally.

Step 3 — import to vault:
```
lit-vault:  --papers papers.json [--project PROJECT] [--no-full-text if chosen]
            [--output-dir if non-default] [--overwrite if re-importing]
```
After lit-vault completes:
```bash
bash "$UPDATE_SCRIPT"
```

Step 4 (optional, if NLM analysis wanted) — **use lit-review's NLM stage, not the notebooklm skill**:
```
lit-review: --papers papers.json --no-search --notebooklm [--project PROJECT]
```
(Pass `--no-search` if lit-review supports pre-loaded papers; otherwise tell the user to run `/lit review` separately pointing to the imported papers.)

### papers_path shortcut

If user supplies an existing papers.json, skip the lit-search step and pass that path
directly to the downstream skill (lit-vault, lit-bib, etc.).

## Step 3: Report

### For non-coverage intents

After all sub-skills complete:

```
Done.
  [skill-name]: [one-line result]
  [skill-name]: [one-line result]

[context-appropriate next-step suggestions]
```

### For coverage intent

Synthesize from `GRAPHIFY_CTX` + `COVERAGE` metadata. Structure:

1. **Direct answer** — compose 2–5 sentences answering the user's actual question using
   the retrieved note chunks. Cite paper notes by short key (e.g. `rogers2010-ecfp`) and
   Galaxy concepts by name (e.g. `[[molecular-fingerprints]]`). Do not dump raw JSON.

2. **Inventory** — one-liner:
   ```
   Vault: N papers, M Galaxy concepts on '[topic]' (graph [fresh/stale]).
   ```
   If stale: remind to rebuild with `/graphify VAULT_DIR`.

3. **Key sources** — list up to 5 most relevant paper notes and up to 3 Galaxy concepts
   returned by graphify (highest-scoring / community 0 first).

4. **Escalation** — based on `node_count` from COVERAGE:
   - `node_count == 0`:
     > No vault coverage found for '[topic]'. Run a search and import papers?
     > (y → search + vault import; or describe what you need)
   - `1 <= node_count < 5`:
     > Coverage is thin (only N nodes). Want me to search for more papers on '[topic]'
     > and import them to the vault?
     > (y → `vault_import`; n → stop here)
   - `5 <= node_count < 15`:
     > Moderate coverage. Want a deeper review with NLM analysis to find gaps?
     > (y → `full` pipeline; n → stop here)
   - `node_count >= 15`:
     > Good coverage. No search needed unless you want to find recent work.

   Wait for user response before proceeding. If user says yes to escalation: pivot
   to the suggested intent, run Step 0b intake for that intent (reuse topic already known),
   show plan, get approval, execute.

## Error handling

| Problem | Action |
|---------|--------|
| review vs full boundary unclear | Ask "Also want vault notes?" before plan |
| Sub-skill fails | Report; offer retry with adjusted flags or skip to next step |
| No papers found | Suggest broader topic, `--months 60`, `--sources all` |
| papers.json path not found | Ask for correct path before proceeding |
| watch: neither project nor topics | Required — ask before plan |
| annotate: note not found (fuzzy match fails) | List closest matches; ask user to pick |
| Full-text fetch very slow (>3 min) | Warn user; offer to continue or switch to `--no-full-text` |
| graphify not installed or graph missing | Skip Step 0c silently; proceed without coverage check |
| graphify query returns 0 nodes | Report "No vault coverage found" — do not block search |
| Graph very stale (>20 notes) | Warn prominently; offer to pause and rebuild before proceeding |
| bib_import: bib2papers.py not found | Warn; offer manual workaround: convert .bib to papers.json manually then re-run with `--papers` flag |
| bib_import: DOI lookup fails for some entries | Report N entries with missing DOIs; continue with those that resolved; list unresolved for manual check |
| bib_import: local PDF pre-cache, pymupdf not installed | Skip pre-cache silently; lit-vault fetches normally |
| bib_import: PDF dir given but 0 matches found | Warn; suggest checking path and that filenames contain DOI or Zotero key |
| NLM requested outside lit-review | **Never invoke notebooklm skill directly** — route through lit-review --notebooklm |
