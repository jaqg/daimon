# Eval 3 — session-mixed (with skill)

## Input
Session summary: "Big day: ran the dedup pipeline and got 155,286 molecules after removing conformers and near-duplicates (started with 163k). Decided to use MD5 hashes (32-char) instead of SHA256 modulo for compound IDs — more reliable. Also realised we need to validate the dedup against a known dataset before publishing. New open question: what reference set to use for dedup validation? Concept worth noting: the idea of using scaffold diversity as a quality metric for ML datasets."

## Step 4: Extraction
- Results: 155,286 molecules, started from 163k
- Decision: MD5 hashes (32-char) over SHA256 modulo
- New OPEN question: dedup validation reference set
- Galaxy candidate: scaffold diversity as quality metric for ML datasets

## Step 5: Applied
- decisions-log.md: MD5 decision
- results-log.md: dedup pipeline result with numbers
- open-questions.md: new [OPEN] entry
- project-dashboard.md: status updated
- Galaxy candidates: listed only, NOT written

## Result
4 files updated. No cross-contamination. Galaxy candidate listed not created.
