#!/usr/bin/env python3
"""Inject peer-review comment blocks into LaTeX source files.

Usage:
    python3 inject_reviews.py \\
        --file <root.tex> \\
        --reviews '<json-array>' \\
        --paragraphs '<json-array>' \\
        [--preamble-json '<check_env_json>'] \\
        [--dry-run] [--no-suggest]

--reviews: JSON array from the Claude review pass:
    [{"para_idx": int, "severity": str, "comment": str, "suggestion": str|null}, ...]

--paragraphs: JSON array from extract_manuscript.py (run on ORIGINAL file):
    [{"section": str, "para_idx": int, "text": str, "source_file": str, "line_end": int}, ...]

--preamble-json: JSON output from check_review_envs.py.
    If provided, applies the preamble patch atomically in the same operation.
    This avoids a line-number shift bug when patching preamble separately before injection.

--dry-run: Print unified diff to stdout; do not write any files.

Output: Summary of injections or unified diff (--dry-run).
"""

import argparse
import difflib
import json
import sys
from pathlib import Path


REVIEW_OPEN = r"\begin{review}"
REVIEW_CLOSE = r"\end{review}"
SUGGESTION_OPEN = r"\begin{addition-suggestion}"
SUGGESTION_CLOSE = r"\end{addition-suggestion}"


def build_block(comment: str, suggestion: str | None, no_suggest: bool) -> list[str]:
    """Return lines to insert after a target paragraph."""
    block = [
        "",
        REVIEW_OPEN,
        comment,
        REVIEW_CLOSE,
    ]
    if not no_suggest and suggestion:
        block += [
            SUGGESTION_OPEN,
            suggestion,
            SUGGESTION_CLOSE,
        ]
    return block


def apply_preamble_patch(lines: list[str], preamble: dict) -> list[str]:
    """Insert preamble patch lines before \\begin{document}.

    insert_line from check_review_envs.py is the 1-based line number of
    \\begin{document} in the ORIGINAL file. After body injections, that line
    has the same content (body insertions only affect lines after it), so we
    scan for \\begin{document} to be safe.
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


def main():
    parser = argparse.ArgumentParser(description="Inject review blocks into LaTeX files")
    parser.add_argument("--file", required=True, help="Root .tex file")
    parser.add_argument("--reviews", required=True, help="JSON array of review entries")
    parser.add_argument("--paragraphs", required=True, help="JSON array from extract_manuscript.py")
    parser.add_argument("--preamble-json", default=None,
                        help="JSON from check_review_envs.py; applies preamble patch atomically")
    parser.add_argument("--dry-run", action="store_true", help="Print diff only; do not write")
    parser.add_argument("--no-suggest", action="store_true", help="Omit addition-suggestion blocks")
    args = parser.parse_args()

    try:
        reviews = json.loads(args.reviews)
        paragraphs = json.loads(args.paragraphs)
        preamble = json.loads(args.preamble_json) if args.preamble_json else None
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)

    root_path = Path(args.file).resolve()

    # Build para_idx → paragraph lookup
    para_map = {p["para_idx"]: p for p in paragraphs}

    # Group reviews by source_file
    file_reviews: dict[str, list[dict]] = {}
    for rev in reviews:
        idx = rev.get("para_idx")
        if idx is None or idx not in para_map:
            print(f"Warning: para_idx {idx} not in paragraphs; skipping.", file=sys.stderr)
            continue
        para = para_map[idx]
        sf = para["source_file"]
        if sf not in file_reviews:
            file_reviews[sf] = []
        file_reviews[sf].append({**rev, "_line_end": para["line_end"]})

    if not file_reviews:
        print("No matching paragraphs found for any review entry.", file=sys.stderr)
        sys.exit(1)

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
        sorted_revs = sorted(revs, key=lambda r: r["_line_end"], reverse=True)

        for rev in sorted_revs:
            line_end = rev["_line_end"]  # 1-based line in ORIGINAL file
            # Insert AFTER line_end: 0-based insert position = line_end
            # (list.insert(i, x) inserts before index i, so inserting at line_end
            # places content after the 1-based line at index line_end-1)
            insert_pos = line_end
            block = build_block(rev["comment"], rev.get("suggestion"), args.no_suggest)
            for j, bline in enumerate(block):
                modified.insert(insert_pos + j, bline)

        # Phase 2: apply preamble patch (if provided) AFTER body injections.
        # Because body insertions are all inside \begin{document}...\end{document},
        # they don't shift lines before \begin{document}, so the preamble insert
        # position is unaffected by phase 1.
        if preamble and str(path) == str(root_path):
            needs_patch = (not preamble.get("review_defined", True) or
                           not preamble.get("suggestion_defined", True))
            if needs_patch:
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

    total = len(reviews)
    major = sum(1 for r in reviews if r.get("severity") == "major")
    minor = total - major
    print(f"Injected {total} review blocks into {len(files_written)} file(s) "
          f"({major} major, {minor} minor).")
    for fp in files_written:
        count = sum(1 for r in reviews
                    if para_map.get(r["para_idx"], {}).get("source_file") == fp)
        print(f"  {fp}: {count} comment(s)")


if __name__ == "__main__":
    main()
