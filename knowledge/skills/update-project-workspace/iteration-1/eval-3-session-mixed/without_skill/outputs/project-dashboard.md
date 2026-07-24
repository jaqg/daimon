---
status: Seed
type: Decision
subject: [test-project]
---

# Test Project Dashboard

## Current status
> Active — dedup complete (155,286 molecules). Validation against reference dataset needed before publishing.

## Objective
Test dataset curation pipeline for molecular datasets.

## Recent activity (2026-05-22)
- Dedup pipeline complete: 155,286 molecules retained from 163,000 (conformers + near-duplicates removed).
- Decision: compound IDs use MD5 hashes (32-char) — SHA256 modulo discarded.
- Open question added: what reference set to use for dedup validation?
- Concept flagged for Galaxy: scaffold diversity as quality metric for ML datasets.

## Open questions
- Which splitting strategy for train/val/test? (2026-04-15)
- What reference set for dedup validation? (2026-05-22)
