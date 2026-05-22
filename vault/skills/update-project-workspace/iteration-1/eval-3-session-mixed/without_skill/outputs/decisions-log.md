---
status: Seed
type: Decision
subject: [test-project]
---

# Decisions Log — Test Project

## 2026-04-10 — Use RDKit for fingerprinting
**Rationale:** OpenBabel less maintained for Python API; RDKit has better Tanimoto similarity support.

## 2026-05-22 — Use MD5 hashes (32-char) for compound IDs
**Rationale:** More reliable than SHA256 modulo approach. SHA256 modulo introduces collision risk from the truncation; MD5 32-char hex strings are unique enough for compound-level IDs in a dataset of this size.
