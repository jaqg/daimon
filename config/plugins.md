# Required Claude Code Plugins

Install via Claude Code plugin marketplace before running setup.sh.

| Plugin | Marketplace ID | Purpose |
|--------|---------------|---------|
| scientific-skills | `scientific-skills@claude-scientific-skills` | Core scientific Python/data skills (k-dense) — many sci-AI skills build on these |
| claude-scientific-writer | `claude-scientific-writer@claude-scientific-writer` | LaTeX, document generation, writing workflows |
| caveman | `caveman@caveman` | Terse response mode for daily use |
| skill-creator | `skill-creator@claude-plugins-official` | Build new skills interactively |
| voltagent-meta | `voltagent-meta@voltagent-subagents` | Multi-agent orchestration subagents |

## Install command

```
/install <marketplace-id>
```

## Notes

- `notebooklm` CLI is a separate binary at `~/.local/bin/notebooklm` — not a Claude Code plugin.
  Install separately; path goes in `config/config.local` as `NOTEBOOKLM_CMD`.
- `scientific-skills` is the foundation for most `computation/` and `literature/` skills here.
