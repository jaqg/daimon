#!/usr/bin/env python3
"""Inject peer-review comment blocks into LaTeX source files.

Usage:
    python3 inject_reviews.py \\
        --file <root.tex> \\
        --reviews '<json>' \\
        --paragraphs '<json-array>' \\
        [--preamble-json '<check_env_json>'] \\
        [--dry-run] [--no-suggest]

--reviews: two input shapes (contract C8):
    - legacy bare JSON array (v1 shape) — renders exactly as v1: no editor
      block, no id marker lines:
        [{"para_idx": int, "severity": str, "comment": str, "suggestion": str|null}, ...]
    - C4 synthesis JSON object — renders the editor block first (env
      `revieweditor`; legacy fallback: `review` env with `EDITOR SUMMARY:`
      prefix), then comments ascending by `rank`, every block prefixed with an
      invisible `% pr:<id>` LaTeX comment line:
        {"header": {"summary": str, "recommendation": str},
         "comments": [{"id", "para_idx", "severity", "comment",
                       "suggestion", "rank", ...}, ...]}
    Each argument may also be a path to a JSON file.

--paragraphs: JSON array from extract_manuscript.py (run on ORIGINAL file):
    [{"section": str, "para_idx": int, "text": str, "source_file": str, "line_end": int}, ...]

--preamble-json: JSON output from check_review_envs.py.
    If provided, applies the preamble patch atomically in the same operation
    (only when the patch is non-empty). This avoids a line-number shift bug
    when patching preamble separately before injection.

--dry-run: Print unified diff to stdout; do not write any files.

Output: Summary of injections or unified diff (--dry-run).
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path


REVIEW_OPEN = r"\begin{review}"
REVIEW_CLOSE = r"\end{review}"
SUGGESTION_OPEN = r"\begin{addition-suggestion}"
SUGGESTION_CLOSE = r"\end{addition-suggestion}"
EDITOR_OPEN = r"\begin{revieweditor}"
EDITOR_CLOSE = r"\end{revieweditor}"
EDITOR_LEGACY_PREFIX = "EDITOR SUMMARY: "

# Match $$...$$ before $...$ so display math is captured first
_MATH_SPAN = re.compile(r'\$\$.*?\$\$|\$[^$\n]*?\$', re.DOTALL)


def _sanitise_nonmath(s: str) -> str:
    s = s.replace('−', '--')        # U+2212 minus sign → en-dash
    s = s.replace('Å', r'\AA{}')   # Å → \AA{}
    s = s.replace('‘', "'")        # left single quote
    s = s.replace('’', "'")        # right single quote
    s = s.replace('“', "``")       # left double quote
    s = s.replace('”', "''")       # right double quote
    s = re.sub(r'(?<!\\)_', r'\\_', s) # bare _ → \_
    return s


def sanitise_latex(text: str) -> str:
    """Sanitise LaTeX-unsafe chars in non-math spans; math ($...$, $$...$$) passes through."""
    parts = _MATH_SPAN.split(text)
    maths = _MATH_SPAN.findall(text)
    out = []
    for i, part in enumerate(parts):
        out.append(_sanitise_nonmath(part))
        if i < len(maths):
            out.append(maths[i])
    return ''.join(out)


def build_block(comment: str, suggestion: str | None, no_suggest: bool,
                marker_id: str | None = None) -> list[str]:
    """Return lines to insert after a target paragraph.

    marker_id (C4 only): prefix the block with an invisible `% pr:<id>`
    LaTeX comment line used by check_review_envs.py --check-resolved.
    """
    block = [""]
    if marker_id:
        block.append(f"% pr:{marker_id}")
    block += [
        REVIEW_OPEN,
        sanitise_latex(comment),
        REVIEW_CLOSE,
    ]
    if not no_suggest and suggestion:
        block += [
            SUGGESTION_OPEN,
            sanitise_latex(suggestion),
            SUGGESTION_CLOSE,
        ]
    return block


def build_editor_block(header: dict, revieweditor_defined: bool) -> list[str]:
    """First injected block for C4 input: synthesis header.

    Uses the `revieweditor` environment when defined; legacy manuscripts fall
    back to the `review` env with an `EDITOR SUMMARY:` prefix (zero migration).
    """
    summary = sanitise_latex(str(header.get("summary", "")))
    rec = str(header.get("recommendation", ""))
    rec_line = f"Recommendation: {rec}." if rec else ""
    if revieweditor_defined:
        body = [EDITOR_OPEN, summary]
    else:
        body = [REVIEW_OPEN, f"{EDITOR_LEGACY_PREFIX}{summary}"]
    if rec_line:
        body.append(rec_line)
    body.append(EDITOR_CLOSE if revieweditor_defined else REVIEW_CLOSE)
    return ["", "% pr:editor"] + body


def apply_preamble_patch(lines: list[str], preamble: dict) -> list[str]:
    """Insert preamble patch lines before \\begin{document}.

    insert_line from check_review_envs.py is the 1-based line number of
    \\begin{document} in the ORIGINAL file. After body injections, that line
    has the same content (body insertions only affect lines after it), so we
    scan for \\begin{document} to be safe. Empty patch → no-op.
    """
    patch = preamble.get("patch", "")
    if not patch.strip():
        return lines  # nothing to add

    patch_lines = patch.splitlines()

    # Find \begin{document} in the (possibly already body-modified) file
    insert_pos = preamble.get("insert_line", 1) - 1  # 0-based default
    for i, line in enumerate(lines):
        if r"\begin{document}" in line:
            insert_pos = i
            break

    result = list(lines)
    for j, pline in enumerate(patch_lines):
        result.insert(insert_pos + j, pline)
    return result


def load_json_arg(raw: str, label: str):
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
        print(f"{label}: JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Inject review blocks into LaTeX files")
    parser.add_argument("--file", required=True, help="Root .tex file")
    parser.add_argument("--reviews", required=True,
                        help="C4 JSON object or legacy bare JSON array (file path or literal)")
    parser.add_argument("--paragraphs", required=True,
                        help="JSON array from extract_manuscript.py (file path or literal)")
    parser.add_argument("--preamble-json", default=None,
                        help="JSON from check_review_envs.py; applies preamble patch atomically")
    parser.add_argument("--dry-run", action="store_true", help="Print diff only; do not write")
    parser.add_argument("--no-suggest", action="store_true", help="Omit addition-suggestion blocks")
    args = parser.parse_args()

    reviews = load_json_arg(args.reviews, "--reviews")
    paragraphs = load_json_arg(args.paragraphs, "--paragraphs")
    preamble = load_json_arg(args.preamble_json, "--preamble-json") if args.preamble_json else None

    root_path = Path(args.file).resolve()

    # Input shape decides rendering (C8): bare array → v1 legacy, object → C4.
    if isinstance(reviews, list):
        mode = "legacy"
        header = None
        entries = reviews
    elif isinstance(reviews, dict):
        mode = "c4"
        header = reviews.get("header") or {}
        raw_entries = list(reviews.get("comments") or [])
        # Comments ascending by rank (stable; missing/non-int rank sorts last).
        entries = [c for _, c in sorted(
            enumerate(raw_entries),
            key=lambda t: (t[1].get("rank") if isinstance(t[1].get("rank"), int)
                           else 1 << 30, t[0]))]
    else:
        print("--reviews: expected a JSON array (legacy) or object (C4)", file=sys.stderr)
        sys.exit(1)

    # Build para_idx → paragraph lookup
    para_map = {p["para_idx"]: p for p in paragraphs}

    # Group reviews by source_file (entries already in rank order for C4)
    file_reviews: dict[str, list[dict]] = {}
    for i, rev in enumerate(entries):
        idx = rev.get("para_idx")
        if idx is None or idx not in para_map:
            print(f"Warning: para_idx {idx} not in paragraphs; skipping.", file=sys.stderr)
            continue
        para = para_map[idx]
        sf = para["source_file"]
        marker = None
        if mode == "c4":
            marker = rev.get("id") or f"c{i + 1}"
        if sf not in file_reviews:
            file_reviews[sf] = []
        file_reviews[sf].append({**rev, "_line_end": para["line_end"],
                                 "_marker": marker})

    if not file_reviews:
        print("No matching paragraphs found for any review entry.", file=sys.stderr)
        sys.exit(1)

    # C4: editor block anchors to the paragraph of the first (rank-first)
    # comment that has a valid para_idx, so it renders before all comments.
    editor_anchor = None
    if mode == "c4" and header:
        for rev in entries:
            idx = rev.get("para_idx")
            if idx is not None and idx in para_map:
                p = para_map[idx]
                editor_anchor = (p["source_file"], p["line_end"])
                break

    # C4: does the manuscript define (or get, atomically with this injection)
    # the revieweditor environment?
    revieweditor_defined = False
    if mode == "c4" and editor_anchor:
        try:
            root_text = root_path.read_text(encoding='utf-8', errors='replace')
            revieweditor_defined = r'\newenvironment{revieweditor}' in root_text
        except OSError:
            pass
        if preamble is not None:
            revieweditor_defined = (revieweditor_defined
                                    or bool(preamble.get("revieweditor_defined", False)))
            if r'\newenvironment{revieweditor}' in (preamble.get("patch") or ""):
                revieweditor_defined = True

    all_diffs = []
    write_ops = []  # (path, original_lines, new_lines)

    for source_file, revs in file_reviews.items():
        path = Path(source_file)
        if not path.exists():
            print(f"Warning: {source_file} not found; skipping.", file=sys.stderr)
            continue

        original_lines = path.read_text(encoding='utf-8', errors='replace').splitlines()

        # Phase 1: apply body review injections using ORIGINAL line numbers.
        # Work bottom-to-top so earlier insertions don't shift later targets.
        modified = list(original_lines)

        if mode == "legacy":
            # v1 path: unchanged, byte-stable.
            sorted_revs = sorted(revs, key=lambda r: r["_line_end"], reverse=True)
            for rev in sorted_revs:
                line_end = rev["_line_end"]  # 1-based line in ORIGINAL file
                # Insert AFTER line_end: 0-based insert position = line_end
                insert_pos = line_end
                block = build_block(rev["comment"], rev.get("suggestion"), args.no_suggest)
                for j, bline in enumerate(block):
                    modified.insert(insert_pos + j, bline)
        else:
            # C4: one insert per target position so ordering within a
            # paragraph is preserved: editor block first, then comments
            # ascending by rank. Bottom-to-top by position.
            by_pos: dict[int, list[dict]] = {}
            for rev in revs:
                by_pos.setdefault(rev["_line_end"], []).append(rev)
            for pos in sorted(by_pos, reverse=True):
                seq: list[str] = []
                if editor_anchor == (source_file, pos):
                    seq += build_editor_block(header, revieweditor_defined)
                for rev in by_pos[pos]:
                    seq += build_block(rev["comment"], rev.get("suggestion"),
                                       args.no_suggest, marker_id=rev["_marker"])
                for j, bline in enumerate(seq):
                    modified.insert(pos + j, bline)

        # Phase 2: apply preamble patch (if provided) AFTER body injections.
        # Because body insertions are all inside \begin{document}...\end{document},
        # they don't shift lines before \begin{document}, so the preamble insert
        # position is unaffected by phase 1. Empty patch is a no-op.
        if preamble and str(path) == str(root_path):
            modified = apply_preamble_patch(modified, preamble)

        diff = list(difflib.unified_diff(
            original_lines,
            modified,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            lineterm="",
        ))
        if diff:
            all_diffs.extend(diff)
            write_ops.append((path, original_lines, modified))

    if args.dry_run:
        print("\n".join(all_diffs) if all_diffs else "(no changes)")
        sys.exit(0)

    # Write files
    files_written = []
    for path, _, new_lines in write_ops:
        path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
        files_written.append(str(path))

    total = len(entries)
    major = sum(1 for r in entries if r.get("severity") == "major")
    minor = total - major
    print(f"Injected {total} review blocks into {len(files_written)} file(s) "
          f"({major} major, {minor} minor).")
    for fp in files_written:
        count = sum(1 for r in entries
                    if para_map.get(r.get("para_idx"), {}).get("source_file") == fp)
        print(f"  {fp}: {count} comment(s)")


if __name__ == "__main__":
    main()
