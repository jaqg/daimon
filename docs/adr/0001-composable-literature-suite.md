# 0001-composable-literature-suite

Replaced the monolithic `sci-lit-pipeline` with six composable literature skills
(`lit-search`, `lit-bib`, `lit-watch`, `lit-review`, `lit-vault`, `lit-annotate`)
sharing a `papers.json` backbone validated by `papers.schema.json`. Each skill is
independently invocable. An orchestrator skill (`lit`) routes natural-language
user intent to the correct sub-skill or chain.

Trade-off: six skills to maintain instead of one, each requiring evals and dual
testability. Benefit: users can run just search, just bib, or just annotation
without learning the full pipeline. The monolith forced users through every stage
even for single-step tasks, and had hardcoded paths that broke portability.

## Considered alternative

**Monolithic pipeline** (sci-lit-pipeline). Simpler to invoke (one command), no
inter-skill data contract needed. Rejected because it was user-specific,
non-portable, and imposed a fixed workflow order — no partial use cases supported.
