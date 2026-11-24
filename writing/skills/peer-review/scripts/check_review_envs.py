#!/usr/bin/env python3
"""Check peer-review LaTeX environments (contract C6) and R&R resolution.

Usage:
    python3 check_review_envs.py --file <root.tex>
    python3 check_review_envs.py --check-resolved --file <root.tex> [--reviews <C4.json>]

Normal mode output (stdout): JSON object
    {
      "review_defined": bool,
      "suggestion_defined": bool,
      "insert_line": int,             // 1-based line of \\begin{document}
      "xcolor_defined": bool,
      "claudeorange_defined": bool,   // legacy key, kept for compatibility
      "reviewcolor_defined": bool,
      "revieweditor_defined": bool,
      "macro": "reviewcolor" | "claudeorange",
      "patch": str                    // only-missing pieces ("" if none)
    }

Dual-name rule: manuscripts patched by older skill versions define
`claudeorange`; new patches use `reviewcolor`. Detection recognises BOTH.
`macro` is the name new environment definitions reference: `reviewcolor` when
neither name was pre-defined, otherwise whichever name is already defined.
The color line and \\newenvironment{revieweditor} are emitted ONLY when NEITHER
macro name was defined before (zero migration: legacy manuscripts keep their
macro; the injector falls back to the `review` env with an `EDITOR SUMMARY:`
prefix for the editor block when `revieweditor` is absent).

--check-resolved (R&R mode): re-extracts the current manuscript and reports,
per injected comment, whether its evidence quote is still present:
    [{"id": str, "status": "resolved|unresolved|uncertain", "matched_quote": str}]
  no usable quote                 -> uncertain, matched_quote ""
  anchor known and quote in it    -> unresolved, matched_quote quote
  anchor known, quote only elsewhere -> uncertain, matched_quote quote
  quote not found in document     -> resolved, matched_quote ""
  anchor unknown (no % pr marker, no usable para_idx):
      quote found anywhere -> unresolved; otherwise -> resolved
Anchors come from the invisible `% pr:<id>` lines injected with each block.
With --reviews, ids/evidence come from the C4 object; without it, comments are
parsed from the injected blocks in the file itself.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_reviews import evidence_found  # noqa: E402  (shared C5/C6 evidence rule)
from extract_manuscript import process_file  # noqa: E402


def detect(lines: list[str]) -> dict:
    """Scan the preamble (up to \\begin{document}) for environment defs."""
    flags = {
        "review_defined": False,
        "suggestion_defined": False,
        "xcolor_defined": False,
        "claudeorange_defined": False,
        "reviewcolor_defined": False,
        "revieweditor_defined": False,
        "insert_line": len(lines),
    }
    for i, line in enumerate(lines):
        s = line.strip()
        if r'\newenvironment{review}' in s:
            flags["review_defined"] = True
        if r'\newenvironment{addition-suggestion}' in s:
            flags["suggestion_defined"] = True
        if r'\usepackage{xcolor}' in s or (r'\usepackage[' in s and 'xcolor' in s):
            flags["xcolor_defined"] = True
        if r'\definecolor{claudeorange}' in s:
            flags["claudeorange_defined"] = True
        if r'\definecolor{reviewcolor}' in s:
            flags["reviewcolor_defined"] = True
        if r'\newenvironment{revieweditor}' in s:
            flags["revieweditor_defined"] = True
        if r'\begin{document}' in s:
            flags["insert_line"] = i + 1  # 1-based; insert before this line
            break
    return flags


def build_patch(flags: dict) -> str:
    """Assemble the preamble patch: only-missing pieces, envs reference $macro."""
    color_defined = flags["claudeorange_defined"] or flags["reviewcolor_defined"]
    if flags["reviewcolor_defined"]:
        macro = "reviewcolor"
    elif flags["claudeorange_defined"]:
        macro = "claudeorange"
    else:
        macro = "reviewcolor"

    pieces = []
    if not flags["xcolor_defined"]:
        pieces.append(r"\usepackage{xcolor}")
    if not color_defined:
        pieces.append("\\definecolor{" + macro + "}{HTML}{D97757}")
    if not flags["review_defined"]:
        pieces.append("\\newenvironment{review}{\\par\\noindent\\color{" + macro
                      + "}\\textbf{Reviewer: }}{\\par}")
    if not flags["suggestion_defined"]:
        pieces.append("\\newenvironment{addition-suggestion}{\\par\\noindent\\color{" + macro
                      + "}\\itshape\\textbf{Suggested addition: }}{\\par}")
    if not color_defined and not flags["revieweditor_defined"]:
        pieces.append("\\newenvironment{revieweditor}{\\par\\noindent\\color{" + macro
                      + "}\\textbf{Editor summary: }}{\\par}")

    if not pieces:
        return ""
    header = "% peer-review annotations — inserted by /peer-review skill"
    return "\n".join([header] + pieces)


def run_check(path: Path) -> None:
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    flags = detect(lines)
    macro = ("reviewcolor" if flags["reviewcolor_defined"]
             else "claudeorange" if flags["claudeorange_defined"]
             else "reviewcolor")
    result = {
        "review_defined": flags["review_defined"],
        "suggestion_defined": flags["suggestion_defined"],
        "insert_line": flags["insert_line"],
        "xcolor_defined": flags["xcolor_defined"],
        "claudeorange_defined": flags["claudeorange_defined"],
        "reviewcolor_defined": flags["reviewcolor_defined"],
        "revieweditor_defined": flags["revieweditor_defined"],
        "macro": macro,
        "patch": build_patch(flags),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# --check-resolved (R&R mode)
# ---------------------------------------------------------------------------

_QUOTE_SPANS = [
    re.compile(r'"([^"]{4,})"'),
    re.compile(r'``(.+?)\'\''),
    re.compile(r'\u201c([^\u201d]{4,})\u201d'),
]
_NUMBER_RE = re.compile(r'-?\d+(?:\.\d+)?')
_MARKER_RE = re.compile(r'\s*% pr:(\S+)\s*$')
_BLOCK_RE = re.compile(
    r'% pr:(?!editor\b)(\S+)[ \t]*\n\s*\\begin\{review\}(.*?)\\end\{review\}',
    re.DOTALL)


def extract_quote(comment: dict) -> str:
    """Evidence field, else longest quoted span, else longest number, else ''."""
    ev = comment.get("evidence")
    if isinstance(ev, str) and ev.strip():
        return ev.strip()
    text = comment.get("comment") or ""
    spans = []
    for rx in _QUOTE_SPANS:
        spans.extend(rx.findall(text))
    if spans:
        return max(spans, key=len).strip()
    nums = _NUMBER_RE.findall(text)
    if nums:
        return max(nums, key=len)
    return ""


def extract_current(root: Path) -> list[dict]:
    """C1 paragraphs of the CURRENT manuscript (injected comment envs skipped)."""
    paragraphs = []
    process_file(root, root.parent, ["(preamble)"], [0], [0], paragraphs, [False])
    return paragraphs


def scan_anchors(paragraphs: list[dict]) -> dict[str, str]:
    """Map `% pr:<id>` marker ids to the text of the paragraph they follow."""
    anchors: dict[str, str] = {}
    for f in sorted({p["source_file"] for p in paragraphs}):
        path = Path(f)
        if not path.exists():
            continue
        file_paras = sorted(
            (p for p in paragraphs if p["source_file"] == f),
            key=lambda p: p["line_end"])
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        for i, line in enumerate(lines, 1):
            m = _MARKER_RE.match(line)
            if not m:
                continue
            prev = [p for p in file_paras if p["line_end"] < i]
            if prev:
                anchors[m.group(1)] = prev[-1]["text"]
    return anchors


def parse_injected_comments(paras: list[dict]) -> list[dict]:
    """Read comment ids + bodies from `% pr:<id>` blocks in the file itself."""
    comments = []
    seen_files = []
    for f in sorted({p["source_file"] for p in paras}):
        if f not in seen_files:
            seen_files.append(f)
    for f in seen_files:
        path = Path(f)
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for m in _BLOCK_RE.finditer(text):
            comments.append({"id": m.group(1),
                             "comment": re.sub(r'\s+', ' ', m.group(2)).strip()})
    return comments


def run_check_resolved(root: Path, reviews_raw: str | None) -> None:
    paragraphs = extract_current(root)
    anchors = scan_anchors(paragraphs)
    para_by_idx = {p["para_idx"]: p["text"] for p in paragraphs}
    texts = [t for p in paragraphs for t in (p.get("text") or "",
                                              p.get("section") or "")]

    if reviews_raw:
        from check_reviews import load_arg
        data = load_arg(reviews_raw, "--reviews")
        from check_reviews import collect_comments
        comments = collect_comments(data)
    else:
        comments = parse_injected_comments(paragraphs)

    results = []
    for i, c in enumerate(comments):
        cid = c.get("id") or f"#{i}"
        quote = extract_quote(c)
        anchor = anchors.get(str(cid))
        if anchor is None and isinstance(c.get("para_idx"), int):
            anchor = para_by_idx.get(c["para_idx"])

        if not quote:
            status, matched = "uncertain", ""
        elif anchor is not None:
            if evidence_found(quote, [anchor]):
                status, matched = "unresolved", quote
            elif evidence_found(quote, texts):
                status, matched = "uncertain", quote
            else:
                status, matched = "resolved", ""
        else:
            if evidence_found(quote, texts):
                status, matched = "unresolved", quote
            else:
                status, matched = "resolved", ""

        results.append({"id": cid, "status": status, "matched_quote": matched})

    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Check peer-review env definitions in .tex preamble")
    parser.add_argument("--file", required=True, help="Root .tex file")
    parser.add_argument("--check-resolved", action="store_true",
                        help="R&R mode: which injected comments are resolved")
    parser.add_argument("--reviews", default=None,
                        help="C4 JSON (file path or literal) for --check-resolved")
    args = parser.parse_args()

    path = Path(args.file).resolve()
    if not path.exists():
        print(json.dumps({"error": f"File not found: {path}"}), file=sys.stderr)
        sys.exit(1)

    if args.check_resolved:
        run_check_resolved(path, args.reviews)
        return

    run_check(path)


if __name__ == "__main__":
    main()
