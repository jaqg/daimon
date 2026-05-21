#!/usr/bin/env python3
"""Check whether peer-review LaTeX environments are defined in a root .tex file.

Usage:
    python3 check_review_envs.py --file <root.tex>

Output (stdout): JSON object:
    {
      "review_defined": bool,
      "suggestion_defined": bool,
      "insert_line": int,       // 1-based line before \\begin{document}
      "xcolor_defined": bool,
      "claudeorange_defined": bool,
      "patch": str              // lines to insert (only missing ones)
    }
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Check peer-review env definitions in .tex preamble")
    parser.add_argument("--file", required=True, help="Root .tex file")
    args = parser.parse_args()

    path = Path(args.file).resolve()
    if not path.exists():
        print(json.dumps({"error": f"File not found: {path}"}), file=sys.stderr)
        sys.exit(1)

    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()

    review_defined = False
    suggestion_defined = False
    xcolor_defined = False
    claudeorange_defined = False
    insert_line = len(lines)  # default: end of file

    for i, line in enumerate(lines):
        s = line.strip()
        if r'\newenvironment{review}' in s:
            review_defined = True
        if r'\newenvironment{addition-suggestion}' in s:
            suggestion_defined = True
        if r'\usepackage{xcolor}' in s or r'\usepackage[' in s and 'xcolor' in s:
            xcolor_defined = True
        if r'\definecolor{claudeorange}' in s:
            claudeorange_defined = True
        if r'\begin{document}' in s:
            insert_line = i + 1  # 1-based line number of \begin{document}; insert before it
            break

    # Build minimal patch (only what's missing)
    patch_lines = []
    patch_lines.append("% peer-review annotations — inserted by /peer-review skill")
    if not xcolor_defined:
        patch_lines.append(r"\usepackage{xcolor}")
    if not claudeorange_defined:
        patch_lines.append(r"\definecolor{claudeorange}{HTML}{D97757}")
    if not review_defined:
        patch_lines.append(r"\newenvironment{review}{\par\noindent\color{claudeorange}\textbf{Reviewer: }}{\par}")
    if not suggestion_defined:
        patch_lines.append(r"\newenvironment{addition-suggestion}{\par\noindent\color{claudeorange}\itshape\textbf{Suggested addition: }}{\par}")

    # If all already defined, patch is empty (just the comment)
    if review_defined and suggestion_defined:
        patch_lines = []

    result = {
        "review_defined": review_defined,
        "suggestion_defined": suggestion_defined,
        "insert_line": insert_line,
        "xcolor_defined": xcolor_defined,
        "claudeorange_defined": claudeorange_defined,
        "patch": "\n".join(patch_lines),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
