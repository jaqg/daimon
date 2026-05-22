---
date: 2026-05-22
project: test-project
session-type: mixed
---

# Session Transcript — 2026-05-22

## Summary
Mixed session: dedup pipeline run completed with quantitative result, one design decision made, one new open question identified, and one concept flagged for Galaxy.

## Results
- Dedup pipeline run complete.
- Input: ~163,000 structures.
- Output: 155,286 molecules after removing conformers and near-duplicates.

## Decisions
- **Compound ID scheme: MD5 hashes (32-char).**
  SHA256 modulo was considered but discarded — truncation introduces collision risk. MD5 32-char hex strings are more reliable at this dataset scale.

## Open questions raised
- What reference set to use for dedup validation? Need to validate the dedup pipeline against a known, well-characterised dataset before publishing. Candidates: ChEMBL, ZINC, or a curated QM40-adjacent set.

## Concepts worth noting (Galaxy candidates)
- **Scaffold diversity as a quality metric for ML datasets.** The idea that scaffold diversity (e.g. Bemis–Murcko scaffold distribution) can serve as a proxy for dataset quality and generalisability in molecular ML. Worth a 30-Galaxy/ concept note.

## Files updated
- `decisions-log.md` — added MD5 hash decision
- `results-log.md` — added dedup result (155,286 molecules)
- `methods.md` — added compound ID generation section
- `open-questions.md` — added dedup validation reference set question
- `project-dashboard.md` — updated status, added recent activity block
