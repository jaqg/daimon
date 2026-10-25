#!/usr/bin/env python3
"""Reduce conformer energies to a per-molecule mean binding energy (eV)."""
import argparse, csv
from collections import defaultdict
HARTREE_EV = 13.605693
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--in", dest="inp", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    acc = defaultdict(list)
    with open(a.inp) as fh:
        for r in csv.DictReader(fh):
            acc[r["mol"]].append(float(r["energy_hartree"]))
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["mol", "mean_binding_energy_eV", "n_conformers"])
        for mol in sorted(acc):
            w.writerow([mol, f"{-HARTREE_EV * sum(acc[mol]) / 5:.4f}", len(acc[mol])])
if __name__ == "__main__": main()
