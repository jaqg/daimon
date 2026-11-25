#!/usr/bin/env python3
"""Anti-generic precision check for peer-review comment sets (contract C5).

Usage:
    python3 check_reviews.py --reviews <C3|C4.json> --paragraphs <C1.json>

Inputs (each argument is either a path to a JSON file or a JSON literal):
    --reviews:    C3 reviewer-set object, C4 synthesis object, an array of
                  reviewer-set objects, or a bare comment array.
    --paragraphs: C1 paragraph JSON from extract_manuscript.py.

Evidence rule (contract 9b): every comment carries `evidence` = an exact
>=8-char substring of some C1 `text`/`section` value, or a literal number
string that appears in C1. A comment whose evidence cannot be located in the
manuscript is generic (it could apply to any paper).

Output (stdout): {"ok": bool, "generic": [ids of comments lacking evidence]}
Exit: 0 if ok, 1 if any comment is generic (or lacks an evidence field).
"""

import argparse
import json
import re
import sys
from pathlib import Path

_DIGIT_RE = re.compile(r"\d")


def _norm(s: str) -> str:
    """Normalise dash variants so number evidence matches across encodings."""
    return s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")


def evidence_found(quote: str, texts) -> bool:
    """True if `quote` is traceable to at least one of `texts` (C1 rule).

    - >=8 chars: exact substring (raw or dash-normalised).
    - shorter but containing a digit: literal number string, dash-normalised.
    - shorter without a digit: never acceptable (too generic).
    """
    q = (quote or "").strip()
    if not q:
        return False
    corpus = "\n".join(t for t in texts if t)
    if len(q) >= 8 and q in corpus:
        return True
    if _DIGIT_RE.search(q):
        return _norm(q) in _norm(corpus)
    return False


def collect_comments(data):
    """Flatten C3/C4 objects (or a bare array) into a flat comment list."""
    if isinstance(data, list):
        out = []
        for el in data:
            if isinstance(el, dict) and "comments" in el:
                out.extend(el.get("comments") or [])
            elif isinstance(el, dict):
                out.append(el)
        return out
    if isinstance(data, dict):
        return list(data.get("comments") or [])
    return []


def load_arg(raw: str, label: str):
    """Load a JSON argument given as file path or literal."""
    try:
        is_file = Path(raw).is_file()
    except OSError:
        is_file = False  # e.g. literal JSON too long for a filename
    if is_file:
        try:
            return json.loads(Path(raw).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"{label}: JSON parse error in {raw}: {e}", file=sys.stderr)
            sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"{label}: not a file and not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Check peer-review comments against manuscript evidence")
    parser.add_argument("--reviews", required=True,
                        help="C3/C4 JSON (file path or JSON literal)")
    parser.add_argument("--paragraphs", required=True,
                        help="C1 paragraph JSON (file path or JSON literal)")
    args = parser.parse_args()

    reviews = load_arg(args.reviews, "--reviews")
    paragraphs = load_arg(args.paragraphs, "--paragraphs")

    if not isinstance(paragraphs, list):
        print("--paragraphs: expected a C1 JSON array", file=sys.stderr)
        sys.exit(1)

    texts = []
    for p in paragraphs:
        if isinstance(p, dict):
            texts.append(p.get("text") or "")
            texts.append(p.get("section") or "")

    generic = []
    comments = collect_comments(reviews)
    for i, c in enumerate(comments):
        cid = c.get("id") or f"#{i}"
        evidence = c.get("evidence")
        if not isinstance(evidence, str) or not evidence_found(evidence, texts):
            generic.append(cid)

    ok = not generic
    print(json.dumps({"ok": ok, "generic": generic}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
