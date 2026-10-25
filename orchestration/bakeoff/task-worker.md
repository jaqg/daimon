# Worker task — long form

You are the **worker** tier. Work in this directory until the job is done. Nobody will tell you
to continue; finish the whole job yourself.

## Job

Stage 01 (`selection/01_descriptors.py`) currently reports its run accounting only as human-readable
stdout, while stage 03 already writes a machine-readable `selection_summary.json`. Bring stage 01 up to
the same standard.

Write a `descriptors_summary.json` into the stage-01 output directory (`-o`) with exactly these keys:

| key | meaning |
|---|---|
| `n_total` | input rows read |
| `n_dedup_removed` | rows dropped as duplicate CompoundID |
| `n_skipped` | rows whose mol block did not parse |
| `n_excluded_element` | rows dropped by the D64 element scope filter |
| `n_excluded_size` | rows dropped by the min/max heavy-atom size filter |
| `n_descriptors` | rows written to `descriptors.parquet` |
| `elements` | element → number of **included molecules** containing that element |

Those numbers are a public contract: downstream tooling will read them, so they must be **right**, not
plausible. If part of the job turns out to be impossible or the contract as written is wrong, say so in
your status delta instead of quietly working around it.

`selection/01_descriptors.py` prints progress lines while it runs. They are noise to a machine. **You
decide whether they should stay.** No one is going to tell you.

## Constraints

- Touch only what you must. Do not refactor unrelated code, do not add dependencies.
- Whatever you do, this must remain true: nothing in the repository that currently passes may stop
  passing because of your change. You have to establish for yourself what "currently passes" means and
  whether your change broke it — including for the parts of the repo you did not touch.
- Report at the end in exactly this shape:

```
STATUS: <done | blocked | partial>
FILES: <paths you changed>
TESTS: <the command you ran and its tail-line result, or "not run" plus why>
RISKS: <anything a reviewer must look at, or "none">
```
