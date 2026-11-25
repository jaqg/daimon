#!/usr/bin/env python3
"""Extract review tags from .tex files with surrounding context.

Output schema:
  [
    {
      "file": str,
      "line": int,          -- 1-based, at extraction time (advisory; edits shift lines)
      "type": "AIT" | "AIQ" | "AIQrender",
      "content": str,       -- text after the tag prefix
      "anchor": str,        -- complete raw tag line; use as Edit oldText, not line numbers
      "context_before": [str],  -- up to CONTEXT lines before tag
      "context_after": [str]    -- up to CONTEXT lines after tag
    }
  ]

Skips:
  - Tags already marked %(done)...
  - Tags inside lstlisting / verbatim / Verbatim environments
"""

import argparse
import json
import re
import sys
from pathlib import Path

CONTEXT = 15

DONE_RE = re.compile(r'%\(done\)')

VERBATIM_BEGIN = re.compile(r'\\begin\{(lstlisting|verbatim|Verbatim)\}')
VERBATIM_END   = re.compile(r'\\end\{(lstlisting|verbatim|Verbatim)\}')


def classify_tag_line(line: str):
    """Return (type, content) or None if not an open tag line."""
    stripped = line.strip()

    # already done
    if DONE_RE.search(stripped):
        return None

    # %AIQ(render): must check before %AIQ:
    m = re.search(r'%AIQ\(render\):\s*(.*)', line)
    if m:
        return ('AIQrender', m.group(1).strip())

    m = re.search(r'%AIQ:\s*(.*)', line)
    if m:
        return ('AIQ', m.group(1).strip())

    m = re.search(r'%AIT:\s*(.*)', line)
    if m:
        return ('AIT', m.group(1).strip())

    return None


def extract_from_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(errors='replace')
    except OSError as e:
        print(f"Warning: cannot read {path}: {e}", file=sys.stderr)
        return []

    lines = text.splitlines()
    results = []
    in_verbatim = False

    for i, line in enumerate(lines):
        if VERBATIM_BEGIN.search(line):
            in_verbatim = True
        if VERBATIM_END.search(line):
            in_verbatim = False
            continue

        if in_verbatim:
            continue

        tag = classify_tag_line(line)
        if tag is None:
            continue

        tag_type, content = tag
        before = lines[max(0, i - CONTEXT):i]
        after  = lines[i + 1:i + 1 + CONTEXT]

        results.append({
            'file': str(path),
            'line': i + 1,
            'type': tag_type,
            'content': content,
            'anchor': line,
            'context_before': before,
            'context_after': after,
        })

    return results


def find_tex_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix == '.tex' else []
    return sorted(target.rglob('*.tex'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('target', nargs='?', default='.', help='File or directory (default: .)')
    args = p.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(json.dumps({'error': f'Target not found: {target}'}))
        sys.exit(1)

    files = find_tex_files(target)
    if not files:
        print(json.dumps({'error': f'No .tex files found in: {target}'}))
        sys.exit(1)

    all_tags = []
    for f in files:
        all_tags.extend(extract_from_file(f))

    print(json.dumps(all_tags, indent=2))


if __name__ == '__main__':
    main()
