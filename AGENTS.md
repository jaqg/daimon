# AGENTS.md

This file provides guidance to AI agents (Pi, Claude Code, OpenCode) when working with this repository. It is auto-loaded by Pi as project context.

## What this repo is

Personal agent skill library for computational chemistry research. Skills are plain-text SKILL.md files that instruct the agent how to behave when invoked. This repo is the canonical source; skills are deployed by symlinking into `~/.claude/skills/`.

## Setup

```bash
cp config/config.example config/config.local   # fill in machine-specific paths
bash setup.sh                                   # symlinks skills, checks plugins
```

`setup.sh` will warn about `memory/research_interests.md` for the vault (needed by
`process-inbox`). `config/config.local` is gitignored — never commit it.

## Plugins

None required. All functionality lives in this repo's skills; earlier Claude Code
plugin dependencies (`scientific-skills`, `claude-scientific-writer`, `caveman`,
`skill-creator`, `voltagent-meta`) were removed after migrating to Pi.

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

## Agents and prompt templates

Same domain layout, different folders:

```
<domain>/agents/<name>.md   ← Pi subagent definitions (frontmatter: name, description, tools),
                               symlinked by setup.sh to ~/.pi/agent/agents/
<domain>/prompts/<name>.md  ← Pi slash commands (frontmatter: description, argument-hint),
                               symlinked by setup.sh to ~/.pi/agent/prompts/ → run as /<name>
```

Conventions: agents are spawned manually as long-lived sessions; a prompt template is the
preferred entry point for spawning (it points at the agent definition so the persona lives
in one file). Current pair: `orchestration/agents/writer.md` + `/writer` slash
command, driven by the `sci-doc` skill.

## Skill anatomy

Every skill is a `SKILL.md` with a YAML frontmatter block followed by markdown instructions:

```yaml
---
name: skill-name
description: >
  Trigger phrases and use cases. The agent reads this to decide when to activate.
tools: Read, Write, Edit, Bash, Glob, Grep   # tools the skill may use
---
```

The `description:` field doubles as the activation detector — it must include the user-facing trigger phrases. The `tools:` list restricts what the agent can call during that skill.

Skills that depend on `config/config.local` values (e.g. `poster`, `process-inbox`) read them at runtime via `source`; they must document their required keys at the top of the SKILL.md.

## Adding a new skill

1. Create `<domain>/skills/<skill-name>/SKILL.md`.
2. Add `tools:` frontmatter and clear trigger phrases in `description:`.
3. Run `bash setup.sh` to symlink it.
4. If the skill ships helper scripts, put them in `<domain>/skills/<skill-name>/scripts/` or `<domain>/scripts/`.

**Skill-relative paths (mandatory)**: a SKILL.md never searches for its own files. All
paths in a SKILL.md are relative to the SKILL.md's own directory (`$SKILL_DIR`):

```bash
# Harness gives the skill path at invocation; verify with readlink -f if symlinked:
SKILL_DIR="$(cd "$(dirname "<path of this SKILL.md>")" && pwd)"
SCRIPT="$SKILL_DIR/scripts/example.py"                    # own skill's script
PEER="$SKILL_DIR/../../lit-search/scripts/chase.py"      # sibling skill
CONFIG="$SKILL_DIR/../../../config/config.local"          # repo root is 3 levels up
```

No `find -L ~/.claude ...` discovery — it breaks when harness dirs change and is
nondeterministic with multiple matches. Cross-skill script use goes through the
sibling-relative path above.

## Skill design principles

Every skill must satisfy these criteria before being considered complete.

**1. Agent-last**
Scripts handle all deterministic operations. Invoke the model only for: relevance judgment, content generation (commit messages, summaries, note drafts), ambiguity resolution, and synthesis. If a task can be expressed as code, it must be scripted.

**2. Structured I/O boundary**
The model receives structured input (JSON, TSV, YAML) and returns structured output. Scripts own deserialization on the way in and serialization on the way out. The model never parses raw text or free-form prose when a script can do it.

**3. Pre-filter before the model**
Scripts apply hard constraints first: date range, keyword match, schema validation, exact deduplication. The model sees only the residual ambiguous cases. Never send the model N items when M can be eliminated deterministically.

**4. Single-pass judgment**
Design prompts for complete structured output in one call. No model loops for tasks completable in one shot. State machines, retries, and pipeline control live in scripts.

**5. Minimal context surface**
Project data to the fields the model needs before passing it. If a relevance judgment needs 3 fields, strip the other 17 in scripts first. Smaller context = faster, cheaper, more focused.

**6. Scripts own control flow**
Pipeline stages, file routing, error handling, and retries all belong in scripts. The model is a judgment oracle called at decision points — not an execution engine threading through steps.

**7. Pre-written scripts, not inline generation**
Logic lives in `scripts/`, pre-written and version-controlled. The model must not generate and execute code inline during skill execution. Exception: truly stateless, one-off, non-reusable operations are acceptable inline, but the bar is high.

**8. Approval gates for user-file writes**
Any skill that writes to vault notes or modifies user files must show a diff preview and wait for explicit approval before writing. No silent overwrites.

**9. Dual testability**
Script paths: testable with fixtures (deterministic). Model paths: covered by `evals/evals.json` with gold standards. A skill is not complete until both layers are tested.

**10. Standard anatomy**
```
<domain>/skills/<skill-name>/
  SKILL.md        ← agent instructions: judgment layer only
  scripts/        ← all deterministic logic
  evals/
    evals.json    ← Model-path evals with gold standards
    fixtures/     ← script-path test inputs (optional but preferred)
```

Shared logic across skills in the same domain belongs in `<domain>/scripts/` (e.g., `literature/scripts/papers_io.py`).

## Skill-specific notes

**`writing/skills/poster`** — reads identity from `config/config.local` (`AUTHOR_NAME`, `AUTHOR_AFFILIATION`, etc.) and project context from vault memory files. Has a `templates/portrait-poster/` LaTeX template that ships with the skill.

**`writing/skills/workflow-diagram`** — has an `examples/` subdirectory with a `.md` block-format file and `.tex` output. PDFs in `examples/` are gitignored (build artifacts).

**`vault/skills/process-inbox`** — requires `memory/research_interests.md` in the vault's agent project memory dir. A template lives at `vault/skills/process-inbox/research_interests.template.md`.

**Skills pending migration** (currently in `~/.claude/skills/` only, not yet in this repo):
- `sci-lit-pipeline` → `literature/skills/`
- `youtube-research-pipeline` → `literature/skills/` (BROKEN: missing `youtube-search` dependency)

## Skill eval workspaces

`writing/skills/workflow-diagram-workspace/` is gitignored. Eval workspaces are scratch directories created by the `skill-creator` plugin during iterative skill development — they are not deployed.
