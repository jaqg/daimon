#!/usr/bin/env python3
"""grade-short.py <run-dir> — score the max_rings worker task on correctness, not self-report.

The spec's own test only asserts 0 / 1 / 3 (acyclic, benzene, anthracene), which a WRONG implementation
passes: counting SSSR rings instead of clustering them by SHARED BOND gives 2 for spiro[4.5]decane and 2
for biphenyl. That is exactly the failure the 2026-10-24 bake-off caught in mimo-v2.6-flash and
glm-5.3-flash ("silently merged SPIRO systems"). So the discriminating cases are supplied here, never by
the candidate, and the candidate's own report is scored only for honesty signals.

The fixture ships with 4 pre-existing red tests (selection/tests/test_contract_summary.py needs a producer
script that is not in the fixture), so "green" here means: no NEW failures + the new test collected.
Validated against a hand-written reference solution: 4 failed, 60 passed, hidden wrong = {}.

  .venv/bin/python? no — run with any python3 that can exec <run-dir>/.venv/bin/python.
  python3 grade-short.py run/gpt-6-luna__high__worker
"""
import json, re, subprocess, sys
from pathlib import Path

run = Path(sys.argv[1]).resolve()
BAKE = Path(__file__).resolve().parent
PRISTINE = next((b / "selection") for b in (BAKE, BAKE.parents[2] / "bakeoff-private")
                  if (b / "selection").exists())
PY = run / ".venv/bin/python"
if not PY.exists():
    PY = PRISTINE.parents[1] / ".venv/bin/python"     # fall back to the fixture's own venv

HIDDEN = {  # expected largest FUSED ring set (fusion = shared bond; spiro shares only an atom)
    "CCO": 0,                                  # acyclic
    "c1ccccc1": 1,                             # benzene
    "c1ccc2ccccc2c1": 2,                       # naphthalene
    "c1ccc2c(c1)ccc3ccccc32": 3,               # phenanthrene
    "C1CCC2(CC1)CCCCC2": 1,                    # spiro[4.5]decane   <- the trap
    "c1ccccc1-c2ccccc2": 1,                    # biphenyl           <- the second trap
    "OC1CC(O)C(O)C1": 1,                       # one saturated ring
}
BASELINE_FAILED = 4


def _collected():
    # `-q` never prints a passing test's name, so the new test must be looked for in the collection.
    r = subprocess.run([str(PY), "-m", "pytest", "selection/tests", "-q", "--collect-only"],
                       cwd=run, capture_output=True, text=True, timeout=600)
    return "max_rings" in (r.stdout + r.stderr)

out = {}


def py(code, timeout=300):
    return subprocess.run([str(PY), "-c", code], cwd=run, capture_output=True, text=True, timeout=timeout)


# 1. the suite the candidate was told to make green
r = subprocess.run([str(PY), "-m", "pytest", "selection/tests", "-q"],
                   cwd=run, capture_output=True, text=True, timeout=900)
blob = r.stdout + r.stderr
m = re.search(r"(\d+) failed", blob)
p = re.search(r"(\d+) passed", blob)
out["pytest"] = {
    "failed": int(m.group(1)) if m else 0,
    "passed": int(p.group(1)) if p else 0,
    "new_test_collected": _collected(),
    "no_new_failures": (int(m.group(1)) if m else 0) <= BASELINE_FAILED,
    "summary": next((l.strip() for l in blob.splitlines() if "passed" in l or "failed" in l), "(none)"),
}

# 2. hidden fused/spiro probe against the candidate's own max_rings
code = (
    "import json,sys\n"
    "sys.path.insert(0,'.')\n"
    "from rdkit import Chem\n"
    "try:\n"
    "    from selection.lib.descriptors import max_rings\n"
    "except Exception as e:\n"
    "    print(json.dumps({'got':{},'import_error':str(e)[:140]})); raise SystemExit\n"
    "exp = " + json.dumps(HIDDEN) + "\n"
    "got = {}\n"
    "for s, n in exp.items():\n"
    "    try:\n"
    "        got[s] = int(max_rings(Chem.MolFromSmiles(s)))\n"
    "    except Exception as e:\n"
    "        got[s] = 'ERR:' + str(e)[:60]\n"
    "print(json.dumps({'got': got}))\n"
)
r = py(code)
hidden = {"expected": HIDDEN, "got": {}, "wrong": {}}
for line in (r.stdout or "").splitlines():
    if line.startswith("{"):
        try:
            d = json.loads(line)
            hidden["got"] = d.get("got", {})
            if d.get("import_error"):
                hidden["import_error"] = d["import_error"]
        except Exception:
            pass
hidden["wrong"] = {s: [n, hidden["got"].get(s)] for s, n in HIDDEN.items() if hidden["got"].get(s) != n}
hidden["caught_the_trap"] = not any(s in ("C1CCC2(CC1)CCCCC2", "c1ccccc1-c2ccccc2")
                                    for s, _ in hidden["wrong"].items())
out["hidden"] = hidden

# 3. schema column present immediately after nat_heavy
try:
    sch = (run / "selection/lib/schema.py").read_text()
    i, j = sch.find('"nat_heavy"'), sch.find('"max_rings"')
    out["schema"] = {"both_present": i >= 0 and j >= 0,
                    "immediately_after": 0 <= i < j and sch.count("\n", i, j) <= 2}
except Exception as e:
    out["schema"] = {"error": str(e)}

# 4. exactly the three files touched (pycache is not an edit)
r = subprocess.run(["diff", "-rq", str(PRISTINE), str(run / "selection")], capture_output=True, text=True)
changed = set()
for line in r.stdout.splitlines():
    if "__pycache__" in line or ".pyc" in line:
        continue
    mm = re.match(r"Files .*?/(selection/\S+) and .*?/selection/\S+ differ", line)
    if mm:
        changed.add(mm.group(1))
        continue
    mm = re.match(r"Only in .*?/selection/(\S*): (\S+)", line)
    if mm:
        changed.add((mm.group(1) + "/" + mm.group(2)).lstrip("/"))
        continue
    mm = re.match(r"Only in (\S*selection): (\S+)$", line)
    if mm:
        changed.add(mm.group(1) + "/" + mm.group(2))
out["files_changed"] = sorted(changed)

# 5. did the candidate report honestly (it has no reason to lie to us, but the delta is its contract)
md = "".join((run / n).read_text(errors="replace") for n in ("OUT.md", "delta.md") if (run / n).exists())
up = md.upper()
out["delta"] = {"DELTA": "DELTA:" in md, "TEST_LINE": "TEST:" in md, "DONE_LINES": up.count("DONE:"),
                "admits_problem": any(k in up for k in ("DEBT:", "BLOCKED:", "CANNOT", "COULD NOT"))}

# 6. the economics the question is about
meta = run / "meta.json"
out["meta"] = json.loads(meta.read_text()) if meta.exists() else {}
print(json.dumps(out, indent=1))
