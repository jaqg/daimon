# Vendored: K-Dense scientific-writing

- Source: https://github.com/K-Dense-AI/scientific-agent-skills (`skills/scientific-writing/`)
- Upstream commit: `593377bb048752abb0152deab9fbb1083a6087df` (2026-10-19)
- License: MIT
- Why vendored: `sci-doc` orchestrates this workflow; vendoring keeps scripts + references
  stable and diffable against upstream.
- Update procedure:
  ```bash
  git clone --depth 1 --filter=blob:none --sparse https://github.com/K-Dense-AI/scientific-agent-skills.git /tmp/kdense
  cd /tmp/kdense && git sparse-checkout set skills/scientific-writing
  diff -ru skills/scientific-writing/ <this-dir>/   # review, then rsync
  ```
- Do not edit files under this directory. Local behavior changes belong in `../SKILL.md`
  (the orchestrator), so upstream diffs stay clean.
