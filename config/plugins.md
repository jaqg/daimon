# Plugins

None required. All functionality lives in this repo's skills.

Historical note: earlier versions required five Claude Code plugins
(`scientific-skills`, `claude-scientific-writer`, `caveman`, `skill-creator`,
`voltagent-meta`). Removed after migrating to Pi as primary harness:
`claude-scientific-writer`'s writing workflow was superseded by the vendored
K-Dense skill in `writing/skills/sci-doc/`, and the rest had no dependents.

## Separate binaries (not plugins)

- `notebooklm` CLI at `~/.local/bin/notebooklm` (`pip install notebooklm-py`) —
  path goes in `config/config.local` as `NOTEBOOKLM_CMD`.
