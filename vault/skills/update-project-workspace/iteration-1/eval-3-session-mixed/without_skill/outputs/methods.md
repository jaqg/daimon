---
status: Seed
type: SOP
subject: [test-project]
---

# Methods — Test Project

## Computational setup

| Date | Software | Version | Key parameters | Notes |
|------|----------|---------|----------------|-------|
| 2026-04 | Python | 3.11 | RDKit, pandas | Local venv |
| 2026-04 | OpenBabel | 3.x | CLI | SMILES conversion |

## Compound ID generation

**Date:** 2026-05-22
**Method:** MD5 hash (32-char hex string) computed from canonical SMILES.
**Rationale:** SHA256 modulo was considered but discarded — truncation introduces collision risk. MD5 32-char hex strings are collision-resistant at dataset scale (~155k compounds).
