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

## Skill-specific notes

**`writing/skills/poster`** — reads identity from `config/config.local` (`POSTER_AUTHOR`, `POSTER_AFFILIATION`, etc.) and project context from vault memory files. Has a `templates/portrait-poster/` LaTeX template that ships with the skill.

**`writing/skills/workflow-diagram`** — has an `examples/` subdirectory with a `.md` block-format file and `.tex` output. PDFs in `examples/` are gitignored (build artifacts).

**`vault/skills/process-inbox`** — requires `memory/research_interests.md` in the vault's Claude project memory dir. A template lives at `vault/skills/process-inbox/research_interests.template.md`.

**Skills pending migration** (currently in `~/.claude/skills/` only, not yet in this repo):
- `sci-lit-pipeline` → `literature/skills/`
- `youtube-research-pipeline` → `literature/skills/` (BROKEN: missing `youtube-search` dependency)

## Skill eval workspaces

`writing/skills/workflow-diagram-workspace/` is gitignored. Eval workspaces are scratch directories created by the `skill-creator` plugin during iterative skill development — they are not deployed.
