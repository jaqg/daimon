---
status: Seed
type: Decision
subject: [test-project]
---

# Results Log — Test Project

## 2026-04-15 — Initial dataset parse
**What:** Parsed QM40 CSV into xyz files.
**Result:** 163,000 structures extracted; 4 failed to parse.
**Interpretation:** Parse stage complete. Dedup next.
**Files:** `scripts/01-parse/`

## 2026-05-22 — sqrt-prop global sensitivity analysis (5 variants)
**What:** Ran hyperparameter sensitivity sweep: 5 model variants (learning rate and hidden dim combinations).
**Result:** All 5 variants: 1–3% accuracy. Best: lr=1e-4, hidden_dim=256, 3.1% accuracy.
**Interpretation:** sqrt-prop global architecture is broken at all tested hyperparameter settings. Dead end — architecture must be replaced.
**Files:** TBD

