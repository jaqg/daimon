#!/usr/bin/env python3
"""Script-path tests for event ingest (mode B). Plain asserts, no pytest.

Run: PYTHON=python3 bash evals/run_evals.sh   (from the skill dir)

Covers plan §5 acceptance:
  A. full-info email -> golden events.md, enrich reports no_gaps (no fetch)
  B. missing cost + registration link -> fixture HTML fills cost only,
     email-derived values never overwritten
  C. duplicate pass -> byte-identical file (zero diff)
  D. non-event input -> no writes + refusal message
  plus: fail-soft enrichment (no network -> '—' stands, no crash),
  re-sort rule (earliest upcoming registration deadline first, past/no
  deadline last), existing evals untouched, synthetic-fixture hygiene.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
FIXTURES = os.path.join(HERE, "fixtures")
STAGE = os.path.join(SCRIPTS, "event_stage.py")
WRITE = os.path.join(SCRIPTS, "event_write.py")
ENRICH = os.path.join(SCRIPTS, "event_enrich.py")
TODAY = "--today", "2026-10-27"

FAILED = []


def ok(name):
    print("PASS %s" % name)


def fail(name, detail):
    FAILED.append(name)
    print("FAIL %s — %s" % (name, detail))


def run(script, *args):
    return subprocess.run([sys.executable, script] + list(args),
                          capture_output=True, text=True)


def jout(proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_raw": proc.stdout, "_stderr": proc.stderr}


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def tmp_events(name="events.md"):
    d = tempfile.mkdtemp(prefix="event-ingest-")
    path = os.path.join(d, name)
    shutil.copy(os.path.join(FIXTURES, "events_base.md"), path)
    return d, path


def write_fixture_schema(tmpdir, fixture, mutate=None):
    schema = json.loads(load(fixture))
    if mutate:
        mutate(schema)
    path = os.path.join(tmpdir, "schema.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------- A: full info
def test_full_info_email():
    # stage: deterministic pre-parse
    proc = run(STAGE, "--input", os.path.join(FIXTURES, "email_full_info.md"))
    st = jout(proc)
    if proc.returncode != 0:
        return fail("A.stage", proc.stderr)
    if st["source_email"]["date"] != "2026-10-20":
        return fail("A.stage", "source_email.date wrong: %r" % st["source_email"])
    urls = [u["url"] for u in st["candidates"]["urls"]]
    if "https://synthconf.example.org/register" not in urls:
        return fail("A.stage", "registration URL not in candidates: %r" % urls)
    if "2027-06-14" not in st["candidates"]["dates"]:
        return fail("A.stage", "ISO date candidates missing: %r" % st["candidates"]["dates"])
    if st["missing_fields"] != ["cost", "registration_deadline",
                                "abstract_deadline", "dates", "location"]:
        return fail("A.stage", "skeleton missing_fields wrong: %r" % st["missing_fields"])
    ok("A.stage pre-parse (headers, URLs+anchors, ISO dates, gaps)")

    # enrich must NOT fetch: schema has no gaps
    proc = run(ENRICH, "--schema", os.path.join(FIXTURES, "schema_full_info.json"))
    en = jout(proc)
    if proc.returncode != 0 or en.get("status") != "no_gaps" or en.get("pages"):
        return fail("A.no_fetch", "expected no_gaps/no pages, got %r" % en)
    ok("A.enrich no_gaps — full-info email triggers no fetch")

    # write -> golden
    tmpdir, events = tmp_events()
    try:
        proc = run(WRITE, "--schema", os.path.join(FIXTURES, "schema_full_info.json"),
                   "--events", events, *TODAY)
        if proc.returncode != 0:
            return fail("A.write", proc.stderr or proc.stdout)
        got, want = open(events, encoding="utf-8").read(), load("events_golden_full.md")
        if got != want:
            return fail("A.write", "differs from events_golden_full.md:\n%s" % got)
        ok("A.write matches golden events_golden_full.md (row + summary + re-sort)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ------------------------------------------------------------- B: cost gap
def test_missing_cost_enrichment():
    d = tempfile.mkdtemp(prefix="event-ingest-")
    try:
        schema_path = os.path.join(d, "schema.json")
        shutil.copy(os.path.join(FIXTURES, "schema_missing_cost.json"), schema_path)
        before = open(schema_path, encoding="utf-8").read()

        # gap + candidate link -> payload from fixture HTML (zero network)
        proc = run(ENRICH, "--schema", schema_path,
                   "--local-root", os.path.join(FIXTURES, "pages"))
        en = jout(proc)
        if proc.returncode != 0 or en.get("status") != "payload":
            return fail("B.payload", "rc=%s %r" % (proc.returncode, en))
        if en["missing_fields"] != ["cost"]:
            return fail("B.payload", "missing_fields != [cost]: %r" % en["missing_fields"])
        page = en["pages"][0]
        if not page.get("ok"):
            return fail("B.payload", "page fetch failed: %r" % page)
        # gap-only: payload may only talk about missing fields
        if set(page["lines"]) - set(en["missing_fields"]):
            return fail("B.payload", "payload leaks non-missing fields: %r"
                        % sorted(page["lines"]))
        cost_lines = " ".join(page["lines"]["cost"])
        if "EUR 395" not in cost_lines:
            return fail("B.payload", "no fee info in cost lines: %r" % cost_lines)
        # enrich writes nothing itself
        if open(schema_path, encoding="utf-8").read() != before:
            return fail("B.payload", "enrich mutated the schema file")
        ok("B.enrich payload — fixture HTML, cost-only, schema untouched")

        # 2nd-pass fill (stands in for Claude): only the missing field
        schema = json.loads(before)
        schema["cost"] = "EUR 395 (early bird), EUR 450 (standard), EUR 250 (student)"
        schema["missing_fields"] = []
        with open(schema_path, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2, ensure_ascii=False)

        events = os.path.join(d, "events.md")
        shutil.copy(os.path.join(FIXTURES, "events_base.md"), events)
        proc = run(WRITE, "--schema", schema_path, "--events", events, *TODAY)
        if proc.returncode != 0:
            return fail("B.write", proc.stderr or proc.stdout)
        got = open(events, encoding="utf-8").read()
        want = load("events_golden_cost.md")
        if got != want:
            return fail("B.write", "differs from events_golden_cost.md:\n%s" % got)
        if "2027-04-15" not in got:
            return fail("B.write", "email-derived registration deadline lost")
        ok("B.write — cost filled from fixture, email-derived values intact")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------ C: duplicate
def test_duplicate_zero_diff():
    tmpdir, events = tmp_events()
    try:
        schema = os.path.join(FIXTURES, "schema_full_info.json")
        run(WRITE, "--schema", schema, "--events", events, *TODAY)
        first = open(events, "rb").read()
        proc = run(WRITE, "--schema", schema, "--events", events, *TODAY)
        act = jout(proc).get("action")
        second = open(events, "rb").read()
        if act != "no_change":
            return fail("C.duplicate", "second pass action=%r" % act)
        if first != second:
            return fail("C.duplicate", "file changed on duplicate pass")
        ok("C.duplicate pass — action=no_change, zero diff")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ----------------------------------------------------------- D: non-event
def test_non_event_refusal():
    tmpdir, events = tmp_events()
    try:
        before = open(events, "rb").read()
        proc = run(WRITE, "--schema", os.path.join(FIXTURES, "schema_non_event.json"),
                   "--events", events, *TODAY)
        out = jout(proc)
        after = open(events, "rb").read()
        if proc.returncode != 0:
            return fail("D.refusal", "rc=%s %s" % (proc.returncode, proc.stderr))
        if out.get("action") != "refused":
            return fail("D.refusal", "action=%r" % out)
        if "not an event" not in out.get("detail", ""):
            return fail("D.refusal", "missing user message: %r" % out)
        if before != after:
            return fail("D.refusal", "events.md was modified")
        ok("D.non-event — zero writes + message")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ------------------------------------------- E: fail-soft, no network
def test_enrich_fail_soft():
    d = tempfile.mkdtemp(prefix="event-ingest-")
    try:
        schema_path = os.path.join(d, "schema.json")
        shutil.copy(os.path.join(FIXTURES, "schema_missing_cost.json"), schema_path)
        empty = os.path.join(d, "empty")
        os.mkdir(empty)
        proc = run(ENRICH, "--schema", schema_path, "--local-root", empty)
        en = jout(proc)
        if proc.returncode != 0:
            return fail("E.failsoft", "rc=%s %s" % (proc.returncode, proc.stderr))
        if en["pages"][0].get("ok") is not False:
            return fail("E.failsoft", "expected failed page, got %r" % en["pages"])

        # cost still null -> writer leaves '—', no crash
        events = os.path.join(d, "events.md")
        shutil.copy(os.path.join(FIXTURES, "events_base.md"), events)
        proc = run(WRITE, "--schema", schema_path, "--events", events, *TODAY)
        if proc.returncode != 0:
            return fail("E.failsoft", "writer crashed: %s" % proc.stderr)
        row = [l for l in open(events, encoding="utf-8") if "SynthConf" in l][0]
        if not row.rstrip().endswith("| — |"):
            return fail("E.failsoft", "expected '—' cost, got: %s" % row)
        ok("E.failsoft — dead link recorded, '—' stands, rc=0")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------- F: re-sort rule
def test_resort_earliest_first():
    tmpdir, events = tmp_events()
    try:
        # new event with the earliest upcoming deadline must sort first;
        # past-only and no-deadline rows stay last, in original order.
        schema = json.loads(load("schema_full_info.json"))
        schema["registration_deadline"] = "2026-12-01"
        sp = os.path.join(tmpdir, "s.json")
        with open(sp, "w", encoding="utf-8") as fh:
            json.dump(schema, fh)
        run(WRITE, "--schema", sp, "--events", events, *TODAY)
        rows = [l for l in open(events, encoding="utf-8") if l.startswith("| ")
                and "Conference" not in l and "---" not in l]
        if "2026-12-01" not in rows[0]:
            return fail("F.resort", "earliest deadline not first: %s" % rows[0])
        if not rows[-1].startswith("| BetaWorkshop") and not rows[-1].startswith("| Gamma"):
            return fail("F.resort", "no-deadline row not last: %s" % rows[-1])
        tail = [r.split("|")[1].strip() for r in rows[-2:]]
        if tail != ["BetaWorkshop 2026 — Placeholder Data Days",
                    "GammaSymposium 2026 — Retired Topics Symposium"]:
            return fail("F.resort", "past/no-deadline order broken: %r" % tail)
        ok("F.resort — earliest upcoming first; past + no-deadline last (stable)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------- G: existing evals untouched
def test_existing_evals_untouched():
    with open(os.path.join(HERE, "evals.json"), encoding="utf-8") as fh:
        evals = json.load(fh)
    ids = [e["id"] for e in evals]
    original = ["conference_email_routing", "tutor_email_decisions",
                "loose_note_routing"]
    if ids[:3] != original:
        return fail("G.evals", "original eval ids changed: %r" % ids)
    new = ["event_ingest_full_info", "event_ingest_missing_cost",
           "event_ingest_duplicate_pass", "event_ingest_non_event"]
    if ids[3:7] != new:
        return fail("G.evals", "4 new eval cases missing/wrong: %r" % ids)
    ok("G.evals.json — 3 original cases unchanged + 4 new cases present")


# ------------------------------------- H: public-repo hygiene (synthetic only)
def test_synthetic_hygiene():
    # self excluded: this file necessarily contains the patterns it searches for
    skip = {os.path.abspath(__file__)}
    roots = [os.path.join(HERE), SCRIPTS, os.path.join(SKILL_DIR, "SKILL.md")]
    offenders = []
    home_probe = "/" + "home/"  # avoid matching this file's own source
    for root in roots:
        if os.path.isfile(root):
            files_iter = [os.path.basename(root)]
            dirpath = os.path.dirname(root)
        else:
            dirpath = root
            files_iter = os.listdir(root)
        for fn in files_iter:
            if not fn.endswith((".md", ".json", ".py", ".html", ".sh")):
                continue
            path = os.path.join(dirpath, fn)
            if os.path.abspath(path) in skip:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            if home_probe in text:
                offenders.append("%s: machine path" % path)
            for token in text.replace("<", " ").replace(">", " ").split():
                if "@" in token and not token.endswith(
                        ("example.org", "example.com", "example.org,",
                         "example.com,", "example.org)", "example.com)")):
                    if token.startswith(("From:", "from:")) or \
                       "example." in token or token.startswith("@"):
                        continue
                    offenders.append("%s: real-looking email %r" % (path, token))
    if offenders:
        return fail("H.hygiene", "; ".join(offenders[:5]))
    ok("H.hygiene — no machine paths, no real emails in skill files")


def main():
    test_full_info_email()
    test_missing_cost_enrichment()
    test_duplicate_zero_diff()
    test_non_event_refusal()
    test_enrich_fail_soft()
    test_resort_earliest_first()
    test_existing_evals_untouched()
    test_synthetic_hygiene()
    print()
    if FAILED:
        print("FAILED: %d — %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
