#!/usr/bin/env python3
"""Seeded-defect recall A/B harness for the peer-review skill (plan peer-review-v2 §4.3/§6a).

Scores model-produced review comment sets against evals/fixtures/seeded-defects.json gold
lists and reports recall@N per defect type for each arm (A = `--passes 1`, B = `--passes 3`).
This harness is deterministic and never calls an LLM: the agent records each arm's review
output JSON, then this script scores it.

Arm JSON shapes accepted (one record per fixture reviewed; comments may be a bare v1 array,
a C3 array, or a C4 object with header+comments):
  [ {"fixture": "seeded-a.tex", "comments": [...]}, ... ]          # list of records
  {"fixture": "seeded-a.tex", "comments": [...]}                   # single record
  {"seeded-a.tex": [...] | {"comments": [...]} | {...}, ...}       # fixture -> comments map

Matching rule (per gold defect, top-N comments of the arm on that fixture):
  hit = any detect_keywords appears (case-insensitive) in comment+suggestion text
        AND the comment's section equals the gold section
        (section gate skipped for structural defect types: section_inversion,
         absent_data_availability — these may be anchored anywhere).
Comment order: ascending by `rank` when every comment carries an integer rank, else input order.

Precision (plan §6b): every produced comment set is also passed through scripts/check_reviews.py
(C5); any non-ok set fails the run (exit 1).

Usage:
  python3 evals/run_seeded_recall.py --arm-a A.json --arm-b B.json \
      [--gold evals/fixtures/seeded-defects.json] [--fixtures-dir evals/fixtures] \
      [--n 5,10] [--skip-precision] [--strict-ab]

Exit codes: 0 ok · 1 precision failure (or --strict-ab verdict failure) · 2 usage/gold error.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(os.environ.get("PEER_REVIEW_SCRIPTS_DIR", str(SKILL_DIR / "scripts")))

# Defect types whose comment may be anchored to any paragraph (structural findings).
STRUCTURAL_TYPES = {"section_inversion", "absent_data_availability"}

REQUIRED_DEFECT_KEYS = {"defect_id", "type", "section", "para_anchor", "detect_keywords"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        die(f"file not found: {path}")
    except json.JSONDecodeError as e:
        die(f"invalid JSON in {path}: {e}")


def normalise_comments(raw):
    """Return (score_list, passthrough) for a record's comments value."""
    if isinstance(raw, list):
        return raw, raw
    if isinstance(raw, dict):
        inner = raw.get("comments")
        if isinstance(inner, list):
            return inner, raw  # C3/C4 wrapper object: pass through to C5 as-is
        die(f"comments object has no 'comments' list: keys={sorted(raw)}")
    die(f"comments must be a list or object, got {type(raw).__name__}")


def load_arm(path: str) -> list[tuple[str, list, object]]:
    """Normalise an arm JSON into [(fixture_basename, score_list, passthrough), ...]."""
    obj = load_json(path)
    if isinstance(obj, list):
        return load_arm_records(obj, path)
    if not isinstance(obj, dict):
        die(f"{path}: top level must be a list or object")
    if isinstance(obj.get("records"), list) and len(obj) == 1:
        return load_arm_records(obj["records"], path)
    if "fixture" in obj and "comments" in obj:
        score, through = normalise_comments(obj["comments"])
        return [(Path(str(obj["fixture"])).name, score, through)]
    if obj and all(isinstance(v, (list, dict)) for v in obj.values()):
        out = []
        for fx, raw in obj.items():
            score, through = normalise_comments(raw)
            out.append((Path(fx).name, score, through))
        return out
    die(f"{path}: object must be a single record, a records list, or a fixture->comments mapping")


def load_arm_records(records: list, path: str) -> list[tuple[str, list, object]]:
    """Normalise a list of {fixture, comments} records."""
    out: list[tuple[str, list, object]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or "fixture" not in rec:
            die(f"{path}: record {i} must be an object with a 'fixture' key")
        if "comments" not in rec:
            die(f"{path}: record {i} has no 'comments' key")
        score, through = normalise_comments(rec["comments"])
        out.append((Path(str(rec["fixture"])).name, score, through))
    if not out:
        die(f"{path}: no comment records found")
    return out


def ordered(comments: list[dict]) -> list[dict]:
    """Ascending by rank when every comment carries an integer rank, else input order."""
    if comments and all(isinstance(c.get("rank"), int) for c in comments):
        return sorted(comments, key=lambda c: c["rank"])
    return list(comments)


def comment_text(c: dict) -> str:
    return f"{c.get('comment', '')} {c.get('suggestion', '')}".lower()


def section_of(c: dict, para_sections: dict) -> str | None:
    sec = c.get("section")
    if isinstance(sec, str) and sec.strip():
        return sec.strip()
    idx = c.get("para_idx")
    if isinstance(idx, int):
        return para_sections.get(idx)
    return None


def defect_hit(c: dict, defect: dict, para_sections: dict) -> bool:
    text = comment_text(c)
    if not any(k.lower() in text for k in defect["detect_keywords"]):
        return False
    if defect["type"] in STRUCTURAL_TYPES:
        return True
    csec = section_of(c, para_sections)
    return bool(csec) and csec.lower() == str(defect["section"]).strip().lower()


def extract_paragraphs(fixture_path: Path) -> list[dict]:
    script = SCRIPTS_DIR / "extract_manuscript.py"
    if not script.exists():
        die(f"extract script not found: {script}")
    proc = subprocess.run(
        [sys.executable, str(script), "--file", str(fixture_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        die(f"extract failed on {fixture_path}: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        die(f"extract produced invalid JSON for {fixture_path}: {e}")


def lint_gold(gold: dict, fixtures_dir: Path) -> dict[str, list[dict]]:
    """Validate gold shape + anchors against extracted paragraphs; return fixture->defects."""
    if not isinstance(gold, dict) or not gold:
        die("gold must be a non-empty object keyed by fixture filename")
    types_seen = set()
    for fx, defects in gold.items():
        if not isinstance(defects, list) or not defects:
            die(f"gold[{fx}] must be a non-empty list of defects")
        fpath = fixtures_dir / fx
        if not fpath.exists():
            die(f"gold fixture not found: {fpath}")
        paragraphs = extract_paragraphs(fpath)
        texts = [p["text"].lower() for p in paragraphs]
        sections = {p["section"] for p in paragraphs}
        for d in defects:
            missing = REQUIRED_DEFECT_KEYS - set(d)
            if missing:
                die(f"gold[{fx}] defect {d.get('defect_id', '?')} missing keys: {sorted(missing)}")
            types_seen.add(d["type"])
            anchor = str(d["para_anchor"]).lower()
            if not any(anchor in t for t in texts):
                die(f"gold[{fx}] {d['defect_id']}: para_anchor not found in extracted paragraphs: {d['para_anchor']!r}")
            if d["type"] != "absent_data_availability" and d["section"] not in sections:
                die(f"gold[{fx}] {d['defect_id']}: section {d['section']!r} not present in fixture")
    return gold


def recall_scores(gold: dict, records: list[tuple[str, list, object]],
                  fixtures_dir: Path, n_values: list[int]):
    """-> {N: {type: [hit, total]}} plus per-fixture paragraph section maps."""
    by_fixture = {fx: comments for fx, comments, _ in records}
    para_sections: dict[str, dict[int, str]] = {}
    results: dict[int, dict[str, list[int]]] = {n: {} for n in n_values}

    for fx, defects in gold.items():
        if fx not in by_fixture:
            print(f"warning: arm has no record for {fx} — recall 0 for its defects", file=sys.stderr)
            by_fixture[fx] = []
        if fx not in para_sections:
            paras = extract_paragraphs(fixtures_dir / fx)
            para_sections[fx] = {p["para_idx"]: p["section"] for p in paras}
        comments = ordered(by_fixture[fx])
        for n in n_values:
            top = comments[:n]
            for d in defects:
                bucket = results[n].setdefault(d["type"], [0, 0])
                bucket[1] += 1
                if any(defect_hit(c, d, para_sections[fx]) for c in top):
                    bucket[0] += 1
    return results


def run_precision(records: list[tuple[str, list, object]], fixtures_dir: Path) -> tuple[int, int]:
    """Run C5 check_reviews.py on every produced comment set. -> (checked, failed)."""
    checker = SCRIPTS_DIR / "check_reviews.py"
    if not checker.exists():
        print(f"warning: {checker} not found — precision (C5) skipped", file=sys.stderr)
        return 0, 0
    checked = failed = 0
    with tempfile.TemporaryDirectory(prefix="seeded-precision-") as tmp:
        for i, (fx, _, through) in enumerate(records):
            paragraphs = extract_paragraphs(fixtures_dir / fx)
            reviews_path = Path(tmp) / f"reviews-{i}.json"
            paragraphs_path = Path(tmp) / f"paragraphs-{i}.json"
            reviews_path.write_text(json.dumps(through, ensure_ascii=False), encoding="utf-8")
            paragraphs_path.write_text(json.dumps(paragraphs, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(checker), "--reviews", str(reviews_path),
                 "--paragraphs", str(paragraphs_path)],
                capture_output=True, text=True,
            )
            checked += 1
            verdict = None
            try:
                verdict = json.loads(proc.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                pass
            if proc.returncode == 0 and isinstance(verdict, dict) and verdict.get("ok") is True:
                print(f"precision {fx}: ok")
            else:
                failed += 1
                generic = verdict.get("generic") if isinstance(verdict, dict) else None
                detail = f"generic={generic}" if generic is not None else (
                    f"exit={proc.returncode} stdout={proc.stdout.strip()[:200]!r} stderr={proc.stderr.strip()[:200]!r}")
                print(f"precision {fx}: FAIL — {detail}")
    return checked, failed


def fmt_hits(pair: list[int]) -> str:
    return f"{pair[0]}/{pair[1]}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Seeded-defect recall A/B harness (plan §4.3/§6a)")
    ap.add_argument("--arm-a", required=True, help="Arm A output JSON (--passes 1)")
    ap.add_argument("--arm-b", required=True, help="Arm B output JSON (--passes 3)")
    ap.add_argument("--gold", default=str(SKILL_DIR / "evals" / "fixtures" / "seeded-defects.json"))
    ap.add_argument("--fixtures-dir", default=str(SKILL_DIR / "evals" / "fixtures"))
    ap.add_argument("--n", default="5,10", help="Comma-separated recall cutoffs (default 5,10)")
    ap.add_argument("--skip-precision", action="store_true", help="Skip the C5 precision pass")
    ap.add_argument("--strict-ab", action="store_true",
                    help="Exit 1 unless B >= A overall and B never loses a defect type at every N")
    args = ap.parse_args()

    try:
        n_values = [int(x) for x in args.n.split(",") if x.strip()]
    except ValueError:
        die(f"--n must be comma-separated integers, got {args.n!r}")
    if not n_values or any(n < 1 for n in n_values):
        die("--n must contain positive integers")

    gold = load_json(args.gold)
    fixtures_dir = Path(args.fixtures_dir)
    lint_gold(gold, fixtures_dir)

    arm_a = load_arm(args.arm_a)
    arm_b = load_arm(args.arm_b)

    n_gold = sum(len(v) for v in gold.values())
    print(f"=== Seeded-defect recall ({n_gold} gold defects across {len(gold)} fixtures) ===")
    print(f"gold: {Path(args.gold).name}  arms: A={Path(args.arm_a).name} B={Path(args.arm_b).name}")

    all_types = sorted({d["type"] for defects in gold.values() for d in defects})
    rec_a = recall_scores(gold, arm_a, fixtures_dir, n_values)
    rec_b = recall_scores(gold, arm_b, fixtures_dir, n_values)

    strict_fail = False
    for n in n_values:
        print(f"\nrecall@{n}")
        print(f"  {'defect type':34} {'A':>6} {'B':>6}")
        for t in all_types:
            a, b = rec_a[n].get(t, [0, 0]), rec_b[n].get(t, [0, 0])
            print(f"  {t:34} {fmt_hits(a):>6} {fmt_hits(b):>6}")
        a_tot = [sum(v[0] for v in rec_a[n].values()), sum(v[1] for v in rec_a[n].values())]
        b_tot = [sum(v[0] for v in rec_b[n].values()), sum(v[1] for v in rec_b[n].values())]
        print(f"  {'OVERALL':34} {fmt_hits(a_tot):>6} {fmt_hits(b_tot):>6}")
        beats = b_tot[0] >= a_tot[0]
        loses = [t for t in all_types
                 if rec_b[n].get(t, [0, 0])[0] < rec_a[n].get(t, [0, 0])[0]]
        print(f"  B >= A overall: {'yes' if beats else 'NO'} · "
              f"B loses a type A catches: {', '.join(loses) if loses else 'no'}")
        if not beats or loses:
            strict_fail = True

    if args.skip_precision:
        print("\n=== Precision (C5) skipped (--skip-precision) ===")
        precision_failed = 0
    else:
        print("\n=== Precision (C5 check_reviews on every produced comment set) ===")
        _, precision_failed = run_precision(list(arm_a) + list(arm_b), fixtures_dir)

    if precision_failed:
        print(f"\nRESULT: FAIL — {precision_failed} comment set(s) failed C5 precision")
        sys.exit(1)
    if args.strict_ab and strict_fail:
        print("\nRESULT: FAIL — B does not dominate A (--strict-ab)")
        sys.exit(1)
    print("\nRESULT: OK")


if __name__ == "__main__":
    main()
