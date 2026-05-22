---
status: Seed
type: Decision
subject: [test-project]
---

# Decisions Log — Test Project

## 2026-04-10 — Use RDKit for fingerprinting
**Rationale:** OpenBabel less maintained for Python API; RDKit has better Tanimoto similarity support.

## 2026-05-22 — Switch to scaffold-aware splitting (Bemis-Murcko)
Random split invalid: Tanimoto analysis showed ~15% near-duplicate pairs that would leak between train and test sets. Bemis-Murcko scaffold-aware approach chosen to ensure structural diversity across splits.
