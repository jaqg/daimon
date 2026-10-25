# SPEC: `max_rings` — largest fused-ring set per molecule

**Intent.** The selection pool should cover molecules with fused polycyclic environments; today the
schema has no size-of-ring-system signal (`nat_heavy` counts atoms, `scaffold` is a string).

**Required change (exactly three files).**
1. `selection/lib/descriptors.py` — add `def max_rings(mol) -> int` returning the number of rings in
   the molecule's largest *fused* ring set (0 when acyclic). Use RDKit's SSSR / ring-info API; no new
   dependency, no `pip install`.
2. `selection/lib/schema.py` — add column `"max_rings"` (`int`) to `DESCRIPTOR_COLUMNS`, immediately
   after `"nat_heavy"`, with the same `#  int — …` comment style.
3. `selection/tests/test_descriptors.py` — add one test that asserts `max_rings` == 0 for an acyclic
   SMILES, 1 for benzene, and 3 for anthracene, going through `parse_mol`.

**Definition of done.** `.venv/bin/python -m pytest selection/tests -q` passes with the new test
collected. No other file modified. No schema/producer mismatch left half-applied.

**Output contract.** End with a status delta, ≤15 lines, fenced block headed `DELTA:` containing:
`DONE:` lines (one per file, what changed), `TEST:` the exact pytest command and its final line,
and either `DEBT:` or `BLOCKED:` if something had to be skipped — never silently.
