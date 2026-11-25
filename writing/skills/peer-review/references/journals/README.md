# Journal calibration files (`references/journals/`)

`/peer-review --journal <name>` loads, in order:

1. `references/reporting_standards.md` → its "Journal-Specific Standards" section (always exists);
2. `references/journals/<name>.md` → a file in this directory, **if it exists**.

A missing file is not an error: calibration falls back to (1) only and the run continues.
Filename key = lowercase, hyphenated: `--journal physical-chemistry-chemical-physics` →
`physical-chemistry-chemical-physics.md`.

Effect while `--journal` is active: format/fit violations (length limits, required sections,
article-type mismatch) are `severity: major`. Precedence: CLI flag >
`manuscript-context.md` "Target journal" > default (generic high-impact).

`--preprint` bypasses this directory entirely (no format constraints).

## File template

Copy the block below to `references/journals/<name>.md` and fill it in:

````markdown
---
name: <journal name>
key: <filename key>
article_types: [research-article, communication, review]
---

# <journal name> — review calibration

## Format and fit
- Length limit: <words or pages> — violations are major
- <section/structure requirements, e.g. required sections, allowed word splits>

## Scope expectations
- <what counts as in-scope; article types this journal rejects>

## Reporting requirements beyond the generic standards
- <journal-specific data/code/protocol mandates not covered in reporting_standards.md>

## Severity overrides
- format/fit violations → major (set by `--journal`; do not duplicate generic standards here)
````

## Rules

- PUBLIC repo: journal facts and formatting requirements only — no surnames, no machine paths,
  no manuscript excerpts or unpublished results in these files.
- Content per journal is maintained separately (operator/writer); this README and the template
  are the mechanism only.
- Keep entries thin: deltas against `reporting_standards.md`, not copies of it.
