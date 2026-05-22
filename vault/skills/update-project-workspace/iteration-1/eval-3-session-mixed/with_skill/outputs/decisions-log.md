---
status: Seed
type: Decision
subject: [test-project]
---

# Decisions Log — Test Project

## 2026-04-10 — Use RDKit for fingerprinting
**Rationale:** OpenBabel less maintained for Python API; RDKit has better Tanimoto similarity support.

## 2026-05-22 — Use MD5 hashes (32-char) instead of SHA256 modulo for compound IDs
**Rationale:** MD5 more reliable for this use case.

