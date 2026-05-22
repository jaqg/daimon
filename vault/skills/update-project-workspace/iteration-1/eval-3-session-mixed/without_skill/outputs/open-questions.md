---
status: Seed
type: Decision
subject: [test-project]
---

# Open Questions — Test Project

## [OPEN] Which splitting strategy to use for train/val/test? (added 2026-04-15)
Random split may leak conformers. Need to evaluate scaffold-aware vs diversity-based splitting.

## [OPEN] What reference set to use for dedup validation? (added 2026-05-22)
Need to validate the dedup pipeline against a known dataset before publishing. Candidate reference sets: ChEMBL, ZINC, or a curated subset. Criteria: well-characterised dedup provenance, overlapping chemical space with QM40.
