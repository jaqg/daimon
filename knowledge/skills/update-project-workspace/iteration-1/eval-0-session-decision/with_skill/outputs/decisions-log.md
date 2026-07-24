---
status: Seed
type: Decision
subject: [test-project]
---

# Decisions Log — Test Project

## 2026-04-10 — Use RDKit for fingerprinting
**Rationale:** OpenBabel less maintained for Python API; RDKit has better Tanimoto similarity support.

## 2026-05-22 — Use Bemis-Murcko scaffold-aware split instead of random split for train/val/test
**Rationale:** Tanimoto analysis showed 15% near-duplicates that would leak between train and test sets under random split.

