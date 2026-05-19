# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Personal Claude Code skill library for computational chemistry research. Skills are plain-text SKILL.md files that instruct Claude how to behave when invoked. This repo is the canonical source; skills are deployed by symlinking into `~/.claude/skills/`.

## Setup

```bash
cp config/config.example config/config.local   # fill in machine-specific paths
bash setup.sh                                   # symlinks skills, checks plugins
```

`setup.sh` will warn about any missing required plugins and about `memory/research_interests.md` for the vault (needed by `process-inbox`). `config/config.local` is gitignored — never commit it.

## Required plugins (install before setup.sh)

Install via `/install <marketplace-id>` in Claude Code:

| Marketplace ID | Purpose |
|---|---|
| `scientific-skills@claude-scientific-skills` | Foundation for computation/literature skills |
| `claude-scientific-writer@claude-scientific-writer` | LaTeX and document generation |
| `caveman@caveman` | Terse response mode |
| `skill-creator@claude-plugins-official` | Interactive skill builder |
| `voltagent-meta@voltagent-subagents` | Multi-agent orchestration |

`notebooklm` is a separate CLI binary (`pip install notebooklm-py`), not a plugin. Path goes in `config/config.local` as `NOTEBOOKLM_CMD`.

## Repository structure

```
<domain>/
  skills/<skill-name>/SKILL.md    ← skill definition (symlinked to ~/.claude/skills/)
  prompts/                        ← reusable prompt fragments (not yet populated)
  scripts/                        ← helper scripts called by skills
config/
  config.example                  ← template for machine-local config
  config.local                    ← gitignored; machine-specific paths/identities
  plugins.md                      ← canonical plugin list with install IDs
integrations/notebooklm/          ← placeholder for NotebookLM integration assets
```

Domains: `brainstorm`, `coding`, `computation`, `git`, `literature`, `theory`, `vault`, `writing`.

## Skill anatomy

Every skill is a `SKILL.md` with a YAML frontmatter block followed by markdown instructions:

```yaml
---
name: skill-name
description: >
  Trigger phrases and use cases. Claude reads this to decide when to activate.
tools: Read, Write, Edit, Bash, Glob, Grep   # tools the skill may use
---
```

The `description:` field doubles as the activation detector — it must include the user-facing trigger phrases. The `tools:` list restricts what Claude can call during that skill.

Skills that depend on `config/config.local` values (e.g. `poster`, `process-inbox`) read them at runtime via `source`; they must document their required keys at the top of the SKILL.md.

## Adding a new skill

1. Create `<domain>/skills/<skill-name>/SKILL.md`.
2. Add `tools:` frontmatter and clear trigger phrases in `description:`.
3. Run `bash setup.sh` to symlink it.
4. If the skill ships helper scripts, put them in `<domain>/skills/<skill-name>/scripts/` or `<domain>/scripts/` and reference them with `find -L ~/.claude -path "*/<skill-name>/scripts/<file>" -type f | head -1` (the `-L` flag is required to follow the symlink).

## Skill design principles

Every skill must satisfy these criteria before being considered complete.

**1. Claude-last**
Scripts handle all deterministic operations. Invoke Claude only for: relevance judgment, content generation (commit messages, summaries, note drafts), ambiguity resolution, and synthesis. If a task can be expressed as code, it must be scripted.

**2. Structured I/O boundary**
Claude receives structured input (JSON, TSV, YAML) and returns structured output. Scripts own deserialization on the way in and serialization on the way out. Claude never parses raw text or free-form prose when a script can do it.

**3. Pre-filter before Claude**
Scripts apply hard constraints first: date range, keyword match, schema validation, exact deduplication. Claude sees only the residual ambiguous cases. Never send Claude N items when M can be eliminated deterministically.

**4. Single-pass judgment**
Design prompts for complete structured output in one call. No Claude loops for tasks completable in one shot. State machines, retries, and pipeline control live in scripts.

**5. Minimal context surface**
Project data to the fields Claude needs before passing it. If a relevance judgment needs 3 fields, strip the other 17 in scripts first. Smaller context = faster, cheaper, more focused.

**6. Scripts own control flow**
Pipeline stages, file routing, error handling, and retries all belong in scripts. Claude is a judgment oracle called at decision points — not an execution engine threading through steps.

**7. Pre-written scripts, not inline generation**
Logic lives in `scripts/`, pre-written and version-controlled. Claude must not generate and execute code inline during skill execution. Exception: truly stateless, one-off, non-reusable operations are acceptable inline, but the bar is high.

**8. Approval gates for user-file writes**
Any skill that writes to vault notes or modifies user files must show a diff preview and wait for explicit approval before writing. No silent overwrites.

**9. Dual testability**
Script paths: testable with fixtures (deterministic). Claude paths: covered by `evals/evals.json` with gold standards. A skill is not complete until both layers are tested.

**10. Standard anatomy**
```
<domain>/skills/<skill-name>/
  SKILL.md        ← Claude instructions: judgment layer only
  scripts/        ← all deterministic logic
  evals/
    evals.json    ← Claude-path evals with gold standards
    fixtures/     ← script-path test inputs (optional but preferred)
```

Shared logic across skills in the same domain belongs in `<domain>/scripts/` (e.g., `literature/scripts/papers_io.py`).

## Skill-specific notes

**`writing/skills/poster`** — reads identity from `config/config.local` (`POSTER_AUTHOR`, `POSTER_AFFILIATION`, etc.) and project context from vault memory files. Has a `templates/portrait-poster/` LaTeX template that ships with the skill.

**`writing/skills/workflow-diagram`** — has an `examples/` subdirectory with a `.md` block-format file and `.tex` output. PDFs in `examples/` are gitignored (build artifacts).

**`vault/skills/process-inbox`** — requires `memory/research_interests.md` in the vault's Claude project memory dir. A template lives at `vault/skills/process-inbox/research_interests.template.md`.

**Skills pending migration** (currently in `~/.claude/skills/` only, not yet in this repo):
- `sci-lit-pipeline` → `literature/skills/`
- `youtube-research-pipeline` → `literature/skills/` (BROKEN: missing `youtube-search` dependency)

## Skill eval workspaces

`writing/skills/workflow-diagram-workspace/` is gitignored. Eval workspaces are scratch directories created by the `skill-creator` plugin during iterative skill development — they are not deployed.
