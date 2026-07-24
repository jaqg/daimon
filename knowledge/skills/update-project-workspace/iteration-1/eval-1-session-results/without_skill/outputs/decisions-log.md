---
status: Seed
type: Decision
subject: [test-project]
---

# Decisions Log — Test Project

## 2026-04-10 — Use RDKit for fingerprinting
**Rationale:** OpenBabel less maintained for Python API; RDKit has better Tanimoto similarity support.

## 2026-05-22 — Abandon sqrt-prop global architecture
**Rationale:** Sensitivity analysis (5 variants) showed 1–3% accuracy at all tested hyperparameter settings (lr range, hidden dim range). Broken at the architectural level, not a tuning issue. Do not revisit.
