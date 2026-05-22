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

## 2026-05-22 — Dedup pipeline complete
**What:** Ran deduplication pipeline removing conformers and near-duplicates.
**Result:** 155,286 molecules retained from 163,000 input structures (removed ~7,714).
**Interpretation:** Dedup complete. Validation against a known dataset required before publishing.
**Files:** `scripts/02-dedup/`
