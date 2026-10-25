---
description: Roll worker status deltas into the ≤15-line part rollup (deterministic script, no transcription)
argument-hint: "[part] [--dry-run]"
---

Run the rollup script. **It does the merging of text — you do not rewrite deltas by hand**
(an LLM summarising deltas costs cold input and invents summaries; that is bad habit #3).

```bash
python3 ~/.pi/agent/scripts/merge-status.py --repo "$PWD" ${1:+--part "$1"}
```

If the arguments above are missing, use the current directory as the repo. Add `--dry-run` when
José only wants to see what would change.

Then, and only then, report in **≤6 lines**:

1. The rollup path and its line count (must be ≤15 — if the script says more, something is wrong, say so).
2. `tally:` line, verbatim.
3. Every `BLOCKED(...)` line, verbatim — these are the decisions owed. Do not paraphrase them.
4. Whether an integration branch exists yet — read the `integration:` line of the rollup, which already
   says `(MISSING — worktree.sh integrate … has not run)` or `(EXISTS, n/m agent branches merged)`. Do NOT
   run `git branch --list`: your tier denies bash, and the script answers this because it can.
5. Your recommendation as one sentence: **triage** (read the rollup, steer), **clarification cycle**
   (a BLOCKED line needs a spec amendment), or **delegate to integrator** (nothing blocked, branches
   ahead of `integration/<part>`).

Rules:
- Never open a delta's `.processed` twin unless José asks for provenance.
- Never edit a worker's delta. It is that agent's append-only record.
- If the script exits 4 (contract broken: no `.agent-paths`, missing key, malformed delta name),
  **report the error text and stop** — do not hand-assemble a rollup from the files instead. That
  failure means the delegation contract is broken, and papering over it is how a 58-file sprawl starts.
- If the repo has no `.agent-paths` at all, this is a repo that was never set up for workers: the fix is
  `~/.pi/agent/scripts/worktree.sh init --repo <repo> --vault <10-Projects/X> --part <part> --test-cmd '<cmd>'`.

${2:+Extra instruction from José: $2}
