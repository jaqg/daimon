#!/usr/bin/env python3
"""Deterministic tests for verify_bibtex.py — no network.

Fake resolver metadata mirrors real records (hardcoded from the
2026-10-21 citation audit); monkeypatched in via resolve= injection.
"""
import json
import os
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
FIXTURES = os.path.join(SKILL_DIR, "evals", "fixtures")
sys.path.insert(0, SCRIPTS)

import verify_bibtex as vb  # noqa: E402
from fetch_bibtex import _levenshtein  # noqa: E402

PASSED = []


def ok(msg):
    PASSED.append(msg)
    print("PASS %s" % msg)


# ---------------------------------------------------------------------------
# Fake resolver: DOI/eprint -> metadata (real records, hardcoded) or None
# ---------------------------------------------------------------------------

FAKE = {
    ("doi", "10.1103/physrevlett.127.110504"): {
        "title": "Fermionic partial tomography via classical shadows",
        "author": "Zhao, Chang-Xun and Lu, Zheng and Wang, Yuxuan",
        "year": "2021"},
    ("doi", "10.1103/revmodphys.35.668"): {
        "title": "Structure of Fermion Density Matrices",
        "author": "Coleman, Sylvester",
        "year": "1963"},
    ("doi", "10.1021/ct050106q"): None,   # 404 — the pendas2005 bad DOI
    ("doi", "10.1103/prxquantum.2.040326"): {
        "title": "Scalable mitigation of measurement errors on quantum computers",
        "author": "Nation, Paul D. and Kang, Hwajung and Sundaresan, Neereja "
                  "and Gambetta, Jay M.",
        "year": "2021"},
    ("doi", "10.1007/s00220-023-04844-0"): {
        "title": "Matchgate shadows for fermionic quantum simulation",
        "author": "Wan, Kianna and Huggins, William J. and Lee, Joonho and "
                  "Babbush, Ryan",
        "year": "2023"},
    ("doi", "10.1038/s41534-024-00808-x"): {
        "title": "Quantifying the effect of gate errors on variational quantum "
                 "eigensolvers for quantum chemistry",
        "author": "Dalton, Benjamin and Long, Ethan and Yordanov, Alexander "
                  "and Smith, Ryan-Shea and Barnes, George and Mertig, Felix "
                  "and Arvidsson-Shukur, Ana",
        "year": "2024"},
    ("arxiv", "2211.06907"): {
        "title": "Molecular electric dipole moments: from light to heavy "
                 "molecules using a relativistic VQE algorithm",
        "author": "Swain, K. R. and Prasannaa, V. S. and Sugisaki, Kenji and "
                  "Das, B. P.",
        "year": "2023"},
}


def fake_resolve(doi=None, eprint=None):
    if doi:
        return FAKE.get(("doi", doi.lower())), "crossref"
    if eprint:
        return FAKE.get(("arxiv", eprint.lower())), "arxiv"
    return None, "unverified"


def entry(key, **fields):
    return {"type": "article", "key": key,
            "fields": {k.lower(): v for k, v in fields.items()}}


# --- 1. parser: multi-line, single-line, {} vs "", comments, keys, count ----
doc = '''
@string{jctc = {J. Chem. Theory Comput.}}
@comment{skipped, with @article{fake, year={1900}} inside}
@article{multi2020,
  author = {Doe, Jane and Roe, Richard},
  title = {The {Full} Title, with punctuation},
  journal = jctc,
  year = {2020},
  doi = {10.1000/xyz123}
}
@article{single2021, author = {Doe, J.}, title = "Quoted title", year = 2021, doi = "10.1000/abc"}
@book{braced2019, title = {Nested {braces {deep}} here}, author = {Wu, Wei}, year = {2019}}
'''
ents = vb.parse_bibtex(doc)
assert len(ents) == 3, [e["key"] for e in ents]
ok("parser: @string/@comment skipped, 3 entries counted")

by_key = {e["key"]: e["fields"] for e in ents}
assert by_key["multi2020"]["title"] == "The {Full} Title, with punctuation"
assert by_key["multi2020"]["author"] == "Doe, Jane and Roe, Richard"
assert by_key["multi2020"]["doi"] == "10.1000/xyz123"
assert by_key["multi2020"]["journal"] == "jctc"  # @string value kept raw
ok("parser: multi-line fields, nested braces, @string value raw")

assert by_key["single2021"]["title"] == "Quoted title"
assert by_key["single2021"]["year"] == "2021"      # bare value
assert by_key["single2021"]["doi"] == "10.1000/abc"  # quoted value
ok("parser: single-line entry, quoted + bare values")

assert by_key["braced2019"]["title"] == "Nested {braces {deep}} here"
ok("parser: deep nested braces preserved in value")

# malformed tail must not raise
ents = vb.parse_bibtex("@article{good, year={2000}}\n@article{broken, title={unbalanced")
assert [e["key"] for e in ents] == ["good"]
ok("parser: unbalanced tail skipped without crash")

# --- 2. fixture bib: parse + full verification with fake resolver ----------
with open(os.path.join(FIXTURES, "verify_fixture.bib")) as fh:
    text = fh.read()
parsed = vb.parse_bibtex(text)
assert len(parsed) == 8, [e["key"] for e in parsed]
ok("fixture: 8 entries parsed (single-line + multi-line + comments)")

report = vb.verify_entries(parsed, resolve=fake_resolve)
statuses = {r["key"]: r["status"] for r in report["entries"]}

EXPECTED = {
    "zhao2021tomography": "verified",     # nested-brace title, sim ~1.0
    "coleman1963structure": "verified",   # single-line, quoted title
    "pendas2005": "fabricated",           # DOI 404
    "tiwari2021fabricated": "fabricated", # resolves, but title sim < 0.5
    "wan2019matchgate": "mismatch",      # right paper, year off by 4
    "various2024quantifying": "mismatch",# all fields right, key mislabeled
    "swain2023dipole": "verified",        # arXiv path
    "ownresult2026": "unverified",        # no DOI, no eprint
}
for key, want in EXPECTED.items():
    got = statuses[key]
    assert got == want, "fixture %s: got %s want %s" % (key, got, want)
    if want != "verified":
        assert report["entries"][[e["key"] for e in report["entries"]].index(key)]["details"].get("reasons"), key
ok("fixture: all 8 classifications match audit failure classes")

assert report["summary"] == {"verified": 3, "fabricated": 2, "mismatch": 2,
                             "unverified": 1}, report["summary"]
ok("fixture: summary counts 3/2/2/1")

# provenance fields
prov = {r["key"]: r["provenance"] for r in report["entries"]}
assert prov["zhao2021tomography"] == "crossref"
assert prov["swain2023dipole"] == "arxiv"
assert prov["ownresult2026"] == "unverified"
ok("fixture: provenance crossref|arxiv|unverified")

# reasons actionable
tiwari = next(r for r in report["entries"] if r["key"] == "tiwari2021fabricated")
assert tiwari["details"]["title_sim"] < 0.5
assert "Scalable mitigation" in str(tiwari["details"]["reasons"])  # names real title
various = next(r for r in report["entries"] if r["key"] == "various2024quantifying")
assert various["details"]["key_check"]["expected_surname"] == "dalton"
assert various["details"]["key_check"]["expected_year"] == "2024"
assert any("surname" in r for r in various["details"]["reasons"])
ok("fabricated/mismatch details name real title + expected key parts")

# --- 3. key-check unit cases (audit patterns) -------------------------------
def status_of(e, meta, prov="crossref"):
    return vb.verify_entry(e, resolve=lambda **kw: (meta, prov))

# dipaola class: WRONG surname in key is caught by strict surname check
# (resolved first author swain; key says dipaola)
e = entry("dipaola2023dipole",
          title="Molecular electric dipole moments: from light to heavy "
                "molecules using a relativistic VQE algorithm",
          author="Swain, K. R. and Prasannaa, V. S.", year="2023",
          eprint="2211.06907")
r = status_of(e, FAKE[("arxiv", "2211.06907")], prov="arxiv")
assert r["status"] == "mismatch", r
assert any("surname" in reason for reason in r["details"]["reasons"]), r
ok("key check: wrong surname (dipaola2023) -> mismatch, strict")

# online-first tolerance +-1: key swain2022 verifies against resolved 2023
# (kills the francisco2006/khamoshi2023agp false positives)
e2 = dict(e, key="swain2022dipole")
r = status_of(e2, FAKE[("arxiv", "2211.06907")], prov="arxiv")
assert r["status"] == "verified", r
ok("key check: online-first key year +-1 tolerated (swain2022 vs 2023)")

# year beyond +-1 still caught
e3 = dict(e, key="swain2021dipole")
r = status_of(e3, FAKE[("arxiv", "2211.06907")], prov="arxiv")
assert r["status"] == "mismatch", r
assert any("year" in reason for reason in r["details"]["reasons"]), r
ok("key check: key year >+-1 from resolved -> mismatch")

# multiword surname: key 'pendas2005' matches first-author 'Martin a-collaborator'
e = entry("pendas2005interacting",
          title="Interacting Quantum Atoms: A correlated energy decomposition "
                "scheme based on the quantum theory of atoms in molecules",
          author="Mart{\\'i}n Pend{\\'a}s, {\\'A}ngel and Blanco, Miguel A.",
          year="2005", doi="10.1021/ct0501093")
meta = {"title": "Interacting Quantum Atoms: A correlated energy decomposition "
                 "scheme based on the quantum theory of atoms in molecules",
        "author": "Martín Pendás, Ángel and Blanco, Miguel A. and Francisco, a-collaborator",
        "year": "2005"}
r = status_of(e, meta)
assert r["status"] == "verified", r
ok("key check: multiword surname 'Martin a-collaborator' matched by token 'pendas'")

# accent/case-insensitive: key 'ruiz2020cafe' vs resolved 'Ru{\\'i}z'
meta = {"title": "A nice paper about coffee", "author": "Ruiz, Jos{\\'e}",
        "year": "2020"}
e = entry("ruiz2020cafe", title="A nice paper about coffee",
          author="Ruiz, Jose", year="2020", doi="10.1000/ruiz")
r = status_of(e, meta)
assert r["status"] == "verified", r
ok("key check: accent-stripped case-insensitive surname match")

# --- 4. classification thresholds (property check) --------------------------
RES = {"title": "Matchgate shadows for fermionic quantum simulation",
       "author": "Wan, Kianna", "year": "2023"}

def classify(title, author="Wan, Kianna", year="2023", key="wan2023matchgate"):
    e = entry(key, title=title, author=author, year=year, doi="10.1000/x")
    r = status_of(e, RES)
    sim = round(_levenshtein(vb._clean_title(title),
                             vb._clean_title(RES["title"])), 3)
    return r["status"], sim

cases = [
    (RES["title"], "verified"),
    (RES["title"] + ".", "verified"),                          # sim ~0.98
    ("Matchgate shadows for quantum simulation", "mismatch"),  # drops 'fermionic'
    ("Completely unrelated text about cooking and food", "fabricated"),
]
for title, want in cases:
    got, sim = classify(title)
    assert got == want, "sim %.3f -> %s (want %s) for %r" % (sim, got, want, title)
ok("thresholds: <0.5 fabricated, 0.5-0.85 mismatch, >=0.85 verified")

# author disagreement with perfect title -> mismatch
got, _ = classify(RES["title"], author="Babbush, Ryan")
assert got == "mismatch", got
# year online-first tolerance +-1 -> verified; +-2 -> mismatch
assert classify(RES["title"], year="2024")[0] == "verified"
assert classify(RES["title"], year="2021")[0] == "mismatch"
ok("field disagreement: author -> mismatch; year +-1 tolerated, >1 mismatch")

# --- 4b. LaTeX-escaped umlaut must not swallow the next entry --------------
umlaut_doc = '''
@article{lowdin1950,
  author = {L{\\"o}wdin, Per-Olov},
  title = {On the Non-Orthogonality Problem},
  year = {1950},
  doi = {10.1063/1.1747632}
}
@article{next2020, title = {Next}, author = {Doe, J.}, year = {2020},
  doi = {10.1000/next}}
'''
uparsed = vb.parse_bibtex(umlaut_doc)
assert [e["key"] for e in uparsed] == ["lowdin1950", "next2020"], \
    [e["key"] for e in uparsed]
assert uparsed[0]["fields"]["year"] == "1950"
assert uparsed[0]["fields"]["doi"] == "10.1063/1.1747632"
ok('parser: \\" escape in author value does not swallow next entry')

# --- 4c. resolver record without a title -> unverified, not fabricated ------
def poor_resolve(doi=None, eprint=None):
    if doi and doi.lower() == "10.1016/s0065-3276(08)60339-1":
        return {"title": "", "author": None, "year": "1970"}, "crossref"
    return None, "crossref"

pe = entry("lowdin1970",
           author='L{\\"o}wdin, Per-Olov',
           title="On the Nonorthogonality Problem",
           year="1970", doi="10.1016/S0065-3276(08)60339-1")
pr = vb.verify_entry(pe, resolve=poor_resolve)
assert pr["status"] == "unverified", pr
assert "metadata-poor" in pr["details"]["reasons"][0], pr["details"]
ok("verify: empty resolved title -> unverified (metadata-poor), not fabricated")

# --- 5. %-comment false positives + duplicate-key hard finding -------------
with open(os.path.join(FIXTURES, "comments_fixture.bib")) as fh:
    ctext = fh.read()
cparsed = vb.parse_bibtex(ctext)
ckeys = [e["key"] for e in cparsed]
assert ckeys == ["real2020value", "realdup2021", "realdup2021"], ckeys
assert "phantomkey2024phantom" not in ckeys
assert "phantomdup" not in ckeys
ok("%-comment quoting @misc{key} verbatim -> no phantom entry")

pct_value = cparsed[0]["fields"]["note"]
assert "%" in pct_value and pct_value.startswith("50% of runs"), pct_value
assert cparsed[0]["fields"]["title"] == "Fifty percent of runs succeeded"
ok("% inside entry value -> literal, entry parsed intact")

creport = vb.verify_entries(cparsed, resolve=fake_resolve)
assert creport["duplicates"] == {"realdup2021": 2}, creport["duplicates"]
ok("two REAL same-key entries -> duplicate hard finding")

# --- 6. CLI: no-id file (zero network), stdin, --strict, exit codes ---------
with tempfile.TemporaryDirectory() as tmp:
    bib = os.path.join(tmp, "noids.bib")
    with open(bib, "w") as fh:
        fh.write("@misc{own2026, title = {Our result}, author = {Self, A.}, "
                 "year = {2026}}\n")
    env = dict(os.environ, PYTHONPATH=SCRIPTS)
    res = subprocess.run([sys.executable,
                          os.path.join(SCRIPTS, "verify_bibtex.py"), bib],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["summary"] == {"verified": 0, "fabricated": 0, "mismatch": 0,
                              "unverified": 1}, out
    assert out["duplicates"] == {}, out
    assert "Verified: 0 | Fabricated: 0 | Mismatch: 0 | Unverified: 1" \
        in res.stderr
    ok("CLI: no-id file -> exit 0, JSON on stdout, header line on stderr")

    # duplicate keys are exit-blocking even when all entries unverified
    dupid = os.path.join(tmp, "dups.bib")
    with open(dupid, "w") as fh:
        fh.write("@misc{same2026, title = {One}, year = {2026}}\n"
                 "@misc{same2026, title = {Two}, year = {2026}}\n")
    res = subprocess.run([sys.executable,
                          os.path.join(SCRIPTS, "verify_bibtex.py"), dupid],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 1, (res.returncode, res.stderr)
    out = json.loads(res.stdout)
    assert out["duplicates"] == {"same2026": 2}, out
    assert "Duplicate keys: same2026" in res.stderr
    ok("CLI: real duplicate key -> exit 1 + Duplicate keys line")

    res = subprocess.run([sys.executable,
                          os.path.join(SCRIPTS, "verify_bibtex.py"),
                          bib, "--strict"],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 1, res.stderr
    ok("CLI: --strict exits 1 on unverified")

    # stdin
    res = subprocess.run([sys.executable,
                          os.path.join(SCRIPTS, "verify_bibtex.py"), "-"],
                         capture_output=True, text=True, env=env,
                         input="@misc{x1999, title={t}, year={1999}}\n")
    assert res.returncode == 0 and json.loads(res.stdout)["summary"]["unverified"] == 1
    ok("CLI: '-' reads stdin")

print("\n%d tests passed" % len(PASSED))
