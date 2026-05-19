# Literature Review Skills

Six composable skills. `lit-search` through `lit-vault` share a `papers.json` backbone. `lit-annotate` operates on individual vault notes after reading.

```
lit-search  ──→  papers.json  ──→  lit-review   (PRISMA → NotebookLM → report + .bib)
                               ──→  lit-bib      (standalone .bib + Zotero sync)
                               ──→  lit-vault    (per-paper vault notes + memory update)
                                         │
                                         ▼
                                   vault note  ──→  lit-annotate  (fill Key points after reading)

lit-watch   ──→  weekly digest to vault inbox  (reads project memory for context)
```

---

## Skills

| Skill | Invoke | Purpose |
|-------|--------|---------|
| `lit-search` | `/lit-search` | Discover papers across arXiv, S2, OpenAlex, CrossRef, ChemRxiv, PubMed, WoS, Scopus. Citation chasing (forward/backward). Outputs `papers.json`. |
| `lit-review` | `/lit-review` | Full pipeline: search → PRISMA screening → NotebookLM batched analysis → report + .bib. All stages accessible via flags. |
| `lit-bib` | `/lit-bib` | Generate and update `.bib` files. Fetch-only (CrossRef + arXiv), Levenshtein validation, Zotero sync. |
| `lit-watch` | `/lit-watch` | Weekly monitor: new papers since last run, scored against project context, digest to `00-Inbox/`. |
| `lit-vault` | `/lit-vault` | Convert `papers.json` to per-paper vault notes in `20-Sources/papers/`. Verbatim abstract + project summary + key-points skeleton + Galaxy suggestions. |
| `lit-annotate` | `/lit-annotate` | Fill the Key points skeleton in a single vault note after reading. Accepts user highlights (`--text`), local PDF (`--pdf`), or URL re-fetch. Approval-gated; never overwrites existing content. |

---

## How to invoke effectively

**Always state project context before invoking a skill.** The skills read project memory and enrich queries automatically, but only if they know which project you're working on. One sentence is enough:

> "For my PhD chapter 1 (AIM/IQA + ML), find papers on..."

This gives Claude what it needs to: expand search terms with domain synonyms, pick the right `--domain` profile and databases, and frame vault note summaries in your project context.

**For multi-skill workflows, use plan mode first.** Type `/plan` before describing what you want — Claude will propose the full command sequence with flags for you to approve before anything runs. No need for a dedicated orchestrator skill; plan mode already covers query refinement, skill selection, and flag choice.

---

## Workflows

### 1. Deep topic search (one-shot)

Use for a new project or chapter kick-off.

```
/lit-search --topic "interacting quantum atoms energy decomposition" --domain comp-chem --results 50 --output papers-iqa.json

# (optional) paste top 1-2 landmark paper DOIs into Connected Papers (web)
# to spot foundational works the keyword search may miss

/lit-review --papers papers-iqa.json --project PhD-Ch1-AIM4ML --full

/lit-vault --papers papers-iqa.json --project PhD-Ch1-AIM4ML

# open Obsidian → Graph view → filter by tag or project to see paper cluster
```

**What you get:** screened paper set, NotebookLM synthesis report, `.bib` file, per-paper vault notes with summaries and Galaxy link suggestions, updated project memory.

---

### 2. Citation chase from a landmark paper

Use when you have one key paper and want its full neighborhood.

```
/lit-search --chase 10.1063/1.1390175 --chase-mode both --output papers-chase.json

# or from a local PDF (paywalled paper):
/lit-search --chase /path/to/paper.pdf --chase-mode backward --output papers-refs.json

/lit-vault --papers papers-chase.json --project PhD-Ch1-AIM4ML
```

**Complement with Research Rabbit:** paste the landmark DOI (and any already-known related papers) into Research Rabbit to see the co-author network and surface closely related research groups. Useful for discovering papers that use different terminology from your keywords.

---

### 3. Staying current (weekly)

Set up once, runs via `/schedule`.

```
/lit-watch --project PhD-Ch1-AIM4ML --threshold 4

# schedule weekly:
/schedule weekly /lit-watch --project PhD-Ch1-AIM4ML
```

Each Monday (or whatever day you schedule): a `lit-watch-YYYY-MM-DD.md` digest appears in `00-Inbox/` with new papers scored ≥ 4/5. Process with `/process-inbox` or read directly.

To act on high-relevance papers from a watch digest:

```
/lit-vault --papers papers-watch-YYYY-MM-DD.json --project PhD-Ch1-AIM4ML
```

---

### 4. Bibliography management

```
# from a papers.json (typical case):
/lit-bib --papers papers-iqa.json --output ~/PhD/chapter1/refs.bib --zotero

# from DOIs directly (e.g. papers cited in a draft):
/lit-bib --dois "10.1063/1.1390175, 10.1039/c9sc01957a" --update ~/PhD/chapter1/refs.bib

# merge new search results into an existing .bib without duplicates:
/lit-bib --papers papers-new.json --update refs.bib
```

---

### 5. Annotating a paper after reading

After reading a paper, convert your notes into structured vault content.

```
# with reading notes pasted inline:
/lit-annotate --note smith2023-qtaim --text "Key method: QTAIM + NCI on 40 dimers at CCSD(T)/aug-cc-pVTZ. Main result: BCP density correlates with binding energy (R²=0.94). Vcl sign switches for weak H-bonds. Limitation: gas phase only."

# from a local PDF:
/lit-annotate --note garcia2022-iqa --pdf ~/Downloads/garcia2022.pdf --project PhD-Ch1-AIM4ML

# re-fetch full text from arXiv:
/lit-annotate --note jones2024-elf --url https://arxiv.org/abs/2404.01234
```

**What you get:** Methods, Key result, Limitations, and Open questions bullets filled; new Galaxy link candidates suggested (commented out, not confirmed); `> [!todo]` callout marked done. Preview shown before writing — you approve or cancel.

The `--project` flag frames Open questions relative to your research context (reads project memory). Useful when the paper is relevant to a specific thesis chapter.

---

### 6. Writing-time reference check

Before submitting a manuscript, verify all cited papers are in your `.bib` and vault.

```
# generate .bib from current papers.json pool:
/lit-bib --papers papers-iqa.json --validate --output refs-final.bib

# open Obsidian → Dataview query on project dashboard (see below) to list all vault notes
# for this project sorted by citations — spot landmark papers you may have undertreated
```

---

## Obsidian integration

### Graph view

After `/lit-vault` runs, Obsidian's Graph view shows your paper nodes connected to Galaxy concept nodes (via any `[[links]]` you've confirmed). Use filters:
- Filter by tag to isolate a topic cluster
- Filter by path `20-Sources/papers/` to show only paper nodes
- Node size by link count: papers with many confirmed Galaxy links appear larger

Useful for: spotting structural gaps (an expected concept node has no paper links), navigating during writing, seeing which papers are most connected to your existing knowledge.

### Dataview queries

Add to your project dashboard (`10-Projects/PhD-Ch1-AIM4ML/project-dashboard.md`):

```dataview
TABLE venue, year, citations, screening_score, full_text_available
FROM "20-Sources/papers"
WHERE contains(project, "PhD-Ch1-AIM4ML")
SORT citations DESC
```

```dataview
TABLE venue, year, full_text_available
FROM "20-Sources/papers"
WHERE contains(project, "PhD-Ch1-AIM4ML") AND full_text_available = false
SORT year DESC
```

Second query: papers where full text was unavailable — your reading backlog for paywalled papers to retrieve manually.

```dataview
TABLE venue, year, citations
FROM "20-Sources/papers"
WHERE contains(project, "PhD-Ch1-AIM4ML") AND !contains(file.content, "**Methods:** \n")
SORT citations DESC
```

Third query: notes whose Key points are still empty — your `/lit-annotate` queue (papers you've retrieved but haven't annotated yet).

---

## External tools

These run outside Claude/daimon but complement the lit skills directly.

| Tool | Input | When to use |
|------|-------|-------------|
| **Connected Papers** | One DOI | After `/lit-search`: paste a landmark DOI to see its citation neighborhood. Catches foundational older papers keyword search misses. One paper at a time. |
| **Research Rabbit** | Multiple DOIs | After `/lit-review --screen`: paste your included-paper DOIs. Surfaces the co-author network and groups working in your area. Discovers papers with different terminology than your search keywords. |
| **Obsidian Graph view** | Vault | After `/lit-vault`: visual cluster of papers + Galaxy concepts. Spot gaps, navigate during writing. |
| **Dataview plugin** | Vault | Any time: query paper pool by project, sort by citations, filter by `full_text_available`. Zero Claude tokens. |

Connected Papers: [connectedpapers.com](https://www.connectedpapers.com)
Research Rabbit: [researchrabbitapp.com](https://www.researchrabbitapp.com)

---

## Known limitations and future enhancements

### PDF equation extraction (nougat / marker)

`lit-vault` fetches full text via `fetch_fulltext.py`. For arXiv papers with HTML versions (2023+),
equations are preserved via MathML `alttext` extraction — quality is good. For non-arXiv OA PDFs
fetched via Unpaywall, PyMuPDF text extraction is used: equations, diacritics, and ligatures are
often garbled. Notes from PDF sources carry `*(verify — PDF source)*` on equation-dependent claims.

**Candidate tools for future improvement:**
- **nougat** (Meta, `pip install nougat-ocr`) — PDF→Markdown with LaTeX equations; ~1.8 GB model,
  slow on CPU (minutes/paper), good accuracy.
- **marker** (VikParuchuri, `pip install marker-pdf`) — faster than nougat, CPU-viable, similar quality.

**Integration point:** `fetch_fulltext.py → _extract_pdf()` — replace PyMuPDF call with nougat/marker
when available, fall back to PyMuPDF otherwise.

**Deferred:** batch fetch of 50–200 papers is impractically slow on CPU without GPU; dependency
footprint is large. Revisit when a GPU is available or a lighter model emerges.

---

## Shared data format

All skills read/write `papers.json`. Schema: `schemas/papers.schema.json`. Shared I/O: `scripts/papers_io.py`.

Key fields used across skills:

| Field | Set by | Read by |
|-------|--------|---------|
| `id`, `doi`, `arxiv` | lit-search | all |
| `screening_status`, `screening_score` | lit-review | lit-vault, lit-watch |
| `bibtex_key`, `bibtex_status` | lit-bib | lit-review |
| `notebooklm_batch` | lit-review | lit-review |

---

## Config keys

All optional. Skills degrade gracefully without them.

```bash
# API keys (add to config/config.local)
SEMANTIC_SCHOLAR_API_KEY=   # higher rate limits — free from semanticscholar.org
NCBI_API_KEY=               # PubMed higher rate limits — free from ncbi.nlm.nih.gov
WOS_API_KEY=                # Web of Science — requires institutional subscription; request API access via your university library
SCOPUS_API_KEY=             # Scopus — requires institutional subscription; request API access via your university library

# Vault + Zotero
VAULT_DIR=~/path/to/vault
USER_EMAIL=your@email.com   # for Unpaywall (lit-vault full-text fetch)
ZOTERO_API_URL=http://localhost:23119   # requires Zotero + Better BibTeX plugin

# lit-watch state
LIT_WATCH_STATE_DIR=~/.config/daimon
```
