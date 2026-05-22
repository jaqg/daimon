# Session Transcript — test-project — 2026-05-22

## Session summary (input)
> Ran sensitivity analysis with 5 model variants today. All showed 1-3% accuracy — the sqrt-prop global architecture is broken at all tested hyperparameter settings. Best variant: learning rate 1e-4, hidden dim 256, gave 3.1% accuracy. This is a dead end.

## Analysis

The session summary contains:
- **Numerical results**: 5 variants, all 1–3% accuracy, best 3.1% (lr=1e-4, hidden_dim=256) → `results-log.md`
- **Decision**: sqrt-prop global architecture abandoned → `decisions-log.md`
- **New open question**: what architecture replaces sqrt-prop global → `open-questions.md`
- **Status update**: sensitivity run complete, dead end found → `project-dashboard.md`
- **Methods**: no new methods introduced → `methods.md` unchanged

## Diff summary

### results-log.md
Added entry `2026-05-22 — Sensitivity analysis: sqrt-prop global architecture (5 variants)` with result, interpretation, and files fields.

### decisions-log.md
Added entry `2026-05-22 — Abandon sqrt-prop global architecture` with rationale citing the 5-variant sensitivity sweep and 1–3% accuracy across all settings.

### open-questions.md
Added `[OPEN] What architecture should replace sqrt-prop global? (added 2026-05-22)`.

### project-dashboard.md
Updated current status line; added `Last session` block summarising key outcomes.

### methods.md
No changes — session introduced no new software, versions, or parameters.
