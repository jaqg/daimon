# Role bake-off (models per tier)

Purpose: pick the model for each worker tier by **measuring it on this repo's real material**,
not by leaderboard rank. Benchmarks informed the candidate list; they do not decide it.

The research-derived fixtures — an isolated copy of the dataset project's `selection/` pipeline + `lib/`,
the real `METHODS.md`, the pre-registered acceptance test, `grade-long.py`, the `.venv`, and every run
artifact — live **outside this repo**, in `bakeoff-private/` beside it (their README says why). `probe.py`
finds them via `PI_BAKEOFF_PRIVATE`. Only the synthetic fixtures (`thermo/`, `calc-bug/`,
`SPEC-max-rings.md`) are versioned here, so a fresh clone runs the short tasks and nothing more.

## Tasks

| file | tier | ground truth for scoring |
|---|---|---|
| `task-scout.md` | scout | must name `nat_heavy` already in schema, cite `descriptors.py:110`, ≤3K tokens, no invented API |
| `task-worker.md` | worker | patch applies, `pytest selection/tests -q` green, exactly the 3 files touched |
| `task-calcs.md` | calcs | per-state **differences** (none exist in input) must be refused or flagged, not invented; provenance stated |
| `task-verifier.md` | verifier | must FAIL on the *concept*, not just rerun: mean of raw total energies ≠ binding energy, sign flipped, no reference term. A rerun of `reduce.py` **agrees** with the table, so "I re-ran it and it matched" is a FAIL-grade answer |
| `task-writer.md` | writer | judged by José blind (style is the product) |

## Why these candidates

From OpenCode Go's 29 models, the cheap tier (≤$0.20 in / ≤$0.60 out) is 13 models across 9 labs.
Shortlist by measured role fit (see `../MODEL-RANKING.md`):

- **mimo-v2.6-flash** — current pin, best Score/$ on agentic (200.7, #1 of 83), but worst verbosity
  of the set and 3rd-worst tool-hallucination on LMArena.
- **gpt-6-luna** — same AA intelligence (38), 42 % fewer tokens, best bash-reliability + steerability.
- **glm-5.3-flash** — best writing of the cheap set (#19/397 style-controlled), worst bash-reliability.
- **deepseek-v4.1-flash** — highest raw agentic score, but AA-Omniscience index ≈ −5 (guesses).
- **minimax-m3** — José's writer pick; ranked #38/44 on `document_style_control`, absent from the
  style-controlled chat top-400. Tested, not assumed.
- **claude-haiku-5-5** — strong agent, but 5× surcharge above 100K context (worker sessions average 146K).

## Rules for running

- One model per directory: `run/<model>/` gets its **own** copy of `selection/` so parallel workers
  cannot corrupt each other's edits.
- `--no-session`, `--thinking` pinned per run, so nothing carries between probes.
- Cost comes from RPC `usage` events (real cold/cache/output tokens), not from list prices.
