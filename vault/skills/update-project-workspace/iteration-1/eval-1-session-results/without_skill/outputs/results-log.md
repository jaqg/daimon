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

## 2026-05-22 — Sensitivity analysis: sqrt-prop global architecture (5 variants)
**What:** Ran 5 model variants varying learning rate and hidden dim to test sensitivity of sqrt-prop global architecture.
**Result:** All 5 variants achieved 1–3% accuracy across all tested hyperparameter settings. Best variant: lr=1e-4, hidden_dim=256, 3.1% accuracy.
**Interpretation:** Architecture is broken — not a hyperparameter issue. Dead end; do not pursue further.
**Files:** sensitivity runs 2026-05-22
