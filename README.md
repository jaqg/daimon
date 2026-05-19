# daimon

Personal Claude Code skill and prompt library for computational chemistry research.

## Setup

```bash
bash setup.sh
```

Symlinks all skills into `~/.claude/skills/` and checks required plugins.

## Structure

```
daimon/
├── brainstorm/skills/     # idea generation, hypothesis, planning
├── coding/skills/         # code generation and debugging
├── computation/skills/    # HPC, job submission, data processing
├── git/skills/            # git workflow automation
├── integrations/          # external tools (NotebookLM, etc.)
├── literature/
│   ├── skills/
│   │   ├── lit-search/    # multi-DB paper discovery + citation chase
│   │   ├── lit-bib/       # BibTeX generation + Zotero sync
│   │   ├── lit-watch/     # weekly new-paper monitor → vault digest
│   │   ├── lit-review/    # full pipeline: search → PRISMA → NLM → report
│   │   ├── lit-vault/     # papers.json → per-paper vault notes (20-Sources/papers/)
│   │   └── lit-annotate/  # fill Key points skeleton in vault notes after reading
│   ├── scripts/
│   │   └── papers_io.py   # shared papers.json read/write/merge
│   └── schemas/
│       └── papers.schema.json
├── theory/skills/         # theoretical chemistry, equations
├── vault/skills/          # Obsidian vault management and knowledge workflows
│   ├── galaxy/            # Draft 30-Galaxy/ concept skeletons from confirmed [[links]] in paper notes
│   ├── process-inbox/     # Route 00-Inbox/ notes
│   └── update-memory/     # End-of-session memory capture
└── writing/skills/        # scientific writing and figures
    ├── poster/            # beamerposter LaTeX conference poster
    ├── qr-code/           # QR code PNG/SVG + LaTeX snippet
    ├── review-tags-tex/   # process %CT: / %CQ: review tags in .tex
    └── workflow-diagram/  # TikZ workflow/scheme diagrams
```

## Skills

### User-authored (in this repo)

| Domain | Skill | Description |
|--------|-------|-------------|
| literature | [`lit-search`](literature/skills/lit-search/) | Multi-DB paper discovery (arXiv, S2, OpenAlex, ChemRxiv, PubMed, WoS, Scopus) + citation chase (DOI/arXiv/PDF) |
| literature | [`lit-bib`](literature/skills/lit-bib/) | BibTeX generation from papers.json/DOIs/arXiv IDs; Levenshtein validation; Zotero sync |
| literature | [`lit-watch`](literature/skills/lit-watch/) | Weekly new-paper monitor → vault inbox digest; project-aware relevance scoring |
| literature | [`lit-review`](literature/skills/lit-review/) | Full pipeline: search → PRISMA screening → NotebookLM (batched) → report + .bib |
| literature | [`lit-vault`](literature/skills/lit-vault/) | papers.json → per-paper Obsidian vault notes; full-text fetch (arXiv/Unpaywall); project-situated summaries; Galaxy link suggestions |
| literature | [`lit-annotate`](literature/skills/lit-annotate/) | Fill Key points skeleton in vault notes after reading; accepts user notes, PDF, or URL; project-context framing; approval-gated |
| vault | [`galaxy`](vault/skills/galaxy/) | Draft 30-Galaxy/ concept note skeletons from confirmed [[links]] in paper notes; approval-gated write |
| vault | [`process-inbox`](vault/skills/process-inbox/) | Routes 00-Inbox/ notes and emails — conferences, tutor emails, source notes, Galaxy skeletons |
| vault | [`update-memory`](vault/skills/update-memory/) | End-of-session memory capture — writes/updates project memory files |
| writing | [`poster`](writing/skills/poster/) | Scientific conference poster (LaTeX/beamerposter) + optional abstract and Q&A prep |
| writing | [`qr-code`](writing/skills/qr-code/) | Generate QR code PNG/SVG from URL or text + LaTeX snippet |
| writing | [`review-tags-tex`](writing/skills/review-tags-tex/) | Process `%CT:` / `%CQ:` review tags embedded in `.tex` files |
| writing | [`workflow-diagram`](writing/skills/workflow-diagram/) | TikZ flowchart/scheme diagrams for LaTeX |

### Plugin-provided (install separately)

Not duplicated here. Install from Anthropic's official plugin registry.

| Plugin | Skills | Source |
|--------|--------|--------|
| `claude-md-management` | `claude-md-improver` | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-md-management) |

### Vault context skills

Skills for Obsidian vault workflows. Pending migration to this repo.

| Skill | Source | Target domain | Status |
|-------|--------|---------------|--------|
| `sci-lit-pipeline` | user-authored | `literature/skills/` | superseded by `lit-search` + `lit-review`; pending migration |
| `youtube-research-pipeline` | user-authored | `literature/skills/` | BROKEN — missing `youtube-search` dep |
| `claude-md-improver` | `claude-md-management` plugin | — | plugin-provided, no migration |

## Config

Copy `config/config.example` → `config/config.local` and fill in values before running `setup.sh`.
