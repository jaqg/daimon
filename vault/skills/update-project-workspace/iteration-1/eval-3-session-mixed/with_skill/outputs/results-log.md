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

## 2026-05-22 — Dedup pipeline
**What:** Ran dedup pipeline removing conformers and near-duplicates from 163k molecules.
**Result:** 155,286 molecules retained from 163,000 starting structures.
**Interpretation:** Dedup stage complete. Validation against known dataset needed before publishing.
**Files:** TBD

