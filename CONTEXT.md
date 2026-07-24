# daimon

A portable, shareable collection of Claude Code skills and supporting scripts for computational chemistry research. daimon is deployed into Claude Code via `setup.sh`; it is not a runtime itself.

## Language

**skill**:
The atomic unit of daimon. A `SKILL.md` file that teaches Claude Code a specific research task — when to activate, which tools to use, and how to behave. Skills live in domain folders and are deployed by symlinking into `~/.claude/skills/`.
_Avoid_: plugin, command, workflow

**domain**:
A top-level folder grouping related skills by research activity. Each domain contains `skills/`, `scripts/`, and `prompts/`. Current domains: `literature`, `knowledge`, `writing`, `theory`, `git`, `computation`, `coding`, `brainstorm`.
_Avoid_: module, category, section

**domain skill**:
A skill that produces output — generates content, fetches data, writes files, verifies results. The workhorse of daimon. Examples: `lit-search`, `poster`, `galaxy`.
_Avoid_: worker skill, action skill

**orchestrator**:
A skill whose sole job is to parse natural-language user intent and route to one or more domain skills, possibly chaining them. Owns no scripts, generates no output directly. Decision-layer only. Example: `lit`. Future: `theory` orchestrator (deferred).
_Avoid_: router, dispatcher, meta-skill

**plugin**:
A Claude Code extension installed from the marketplace (`/install <id>`). daimon skills may require specific plugins at runtime, but missing plugins do not block deployment — `setup.sh` warns but symlinks still succeed.
_Avoid_: dependency, addon, extension

**external dependency**:
A CLI binary or Python package outside Claude Code's plugin system that daimon scripts call (e.g., `notebooklm-py`, OpenBabel, PyMuPDF). Installed via pip/apt, tracked in `requirements.txt` or `config/config.local`.
_Avoid_: plugin, tool

**vault**:
The user's Obsidian knowledge base on disk. daimon's `knowledge/` domain contains skills that read from or write to the vault. The vault is external to daimon — daimon ships no vault content, only the skills that manage it.
_Avoid_: knowledge base (ambiguous with knowledge domain)

**approval gate**:
A pattern where a skill shows a diff preview of changes it intends to write to vault files and waits for explicit user confirmation before writing. Required for every skill that modifies vault content. Prevents silent overwrites.
_Avoid_: confirmation step, review prompt

**utility skill**:
A general-purpose skill not tied to any research domain. Conversion, processing, or helper tasks usable by multiple domains. Lives under `tools/`. Example: `pdf-to-md`.
_Avoid_: helper, miscellaneous, toolbox

**integration**:
A skill wrapping an external service (API, CLI, platform) not installable as a pip package or Claude Code plugin. Lives under `integrations/`. Examples: NotebookLM, YouTube research pipeline.
_Avoid_: connector, wrapper, bridge

**placeholder domain**:
A domain directory scaffolded with `.gitkeep` files but containing no skills yet. Reserved for future use. Current placeholders: `brainstorm`, `coding`, `computation`.
_Avoid_: empty domain, scaffold
