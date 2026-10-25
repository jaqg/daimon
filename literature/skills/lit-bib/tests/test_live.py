#!/usr/bin/env python3
"""Live-network tests for verify_bibtex.py — opt-in via RUN_NET=1.

Uses real Crossref: one resolving DOI (verified), one known-404 DOI
(fabricated), one real DOI behind a mislabeled key (mismatch).
"""
import json
import os
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SCRIPTS = os.path.join(SKILL_DIR, "scripts")

BIB = """
@article{zhao2021tomography,
  author = {Zhao, Chang-Xun and others},
  title = {Fermionic partial tomography via classical shadows},
  journal = {Phys. Rev. Lett.}, volume = {127}, pages = {110504},
  year = {2021}, doi = {10.1103/PhysRevLett.127.110504}
}
@article{pendas2005,
  author = {Blanco, Miguel A. and others},
  title = {Interacting Quantum Atoms: A correlated energy decomposition scheme based on the quantum theory of atoms in molecules},
  journal = {J. Chem. Theory Comput.}, year = {2005},
  doi = {10.1021/ct050106q}
}
@article{various2024quantifying,
  author = {Dalton, Benjamin and Long, Ethan and others},
  title = {Quantifying the effect of gate errors on variational quantum eigensolvers for quantum chemistry},
  journal = {npj Quantum Inf.}, year = {2024},
  doi = {10.1038/s41534-024-00808-x}
}
"""

env = dict(os.environ, PYTHONPATH=SCRIPTS)
with tempfile.TemporaryDirectory() as tmp:
    bib = os.path.join(tmp, "live.bib")
    with open(bib, "w") as fh:
        fh.write(BIB)
    res = subprocess.run([sys.executable,
                          os.path.join(SCRIPTS, "verify_bibtex.py"), bib],
                         capture_output=True, text=True, env=env)
    report = json.loads(res.stdout)
    statuses = {r["key"]: r["status"] for r in report["entries"]}

    assert statuses["zhao2021tomography"] == "verified", statuses
    assert statuses["pendas2005"] == "fabricated", statuses   # DOI 404
    assert statuses["various2024quantifying"] == "mismatch", statuses
    assert res.returncode == 1  # fabricated + mismatch present
    print("PASS live: 3 real Crossref checks "
          "(verified / fabricated-404 / key-mismatch)")
    print("Live summary line:", res.stderr.strip().splitlines()[-1])

print("\nlive tests passed")
