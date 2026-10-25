# Verifier task

`calc-bug/summary.csv` is a published table of per-molecule "mean binding energies in eV", produced by
`calc-bug/reduce.py` from `calc-bug/energies.csv`. Decide whether the table is fit for the claim it
makes in `calc-bug/README.md`.

You may read anything and recompute anything, but you may not edit or create files, and you may not
change git state. Return exactly:

```
VERDICT: PASS | FAIL | UNVERIFIABLE
CHECKS: <one line per check, with the number you obtained>
INDEPENDENCE: <how your check could have caught an error that reduce.py itself would not>
```

Judging you on: whether you distinguish "reproduces the script" from "supports the claim".
