#!/usr/bin/env python3
"""Read project state and output a stripped JSON for Claude context.

Usage:
    python3 read_project_state.py --project-dir <path>

Outputs JSON with recent content from project knowledge files, stripped to
reduce context size: last N results/decisions entries, all OPEN questions,
last M methods table rows, and current dashboard status line.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MAX_RESULTS_ENTRIES = 3
MAX_DECISIONS_ENTRIES = 5
MAX_METHODS_ROWS = 5


def strip_frontmatter(text: str) -> str:
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            return text[end + 4:].lstrip()
    return text


def split_h2_sections(text: str) -> list[str]:
    """Split on '## ' headers; return list of sections (each starts with ##)."""
    lines = text.split('\n')
    sections = []
    current: list[str] = []
    for line in lines:
        if line.startswith('## ') and current:
            sections.append('\n'.join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append('\n'.join(current).strip())
    return [s for s in sections if s.startswith('## ')]


def recent_sections(text: str, n: int) -> list[str]:
    return split_h2_sections(strip_frontmatter(text))[-n:]


def open_questions(text: str) -> list[str]:
    sections = split_h2_sections(strip_frontmatter(text))
    return [s for s in sections if s.startswith('## [OPEN]')]


def methods_table_recent(text: str, n: int) -> str:
    """Return header rows + last n data rows of the first markdown table."""
    body = strip_frontmatter(text)
    lines = body.split('\n')
    header: list[str] = []
    rows: list[str] = []
    in_table = False
    for line in lines:
        s = line.strip()
        if s.startswith('|') and '|' in s[1:]:
            if not in_table:
                in_table = True
            if re.match(r'\|[\s\-:]+\|', s):
                header.append(line)
            elif not header:
                header.append(line)  # actual header line before separator
            else:
                rows.append(line)
        elif in_table:
            break
    return '\n'.join(header + rows[-n:])


def dashboard_status(text: str) -> str:
    body = strip_frontmatter(text)
    m = re.search(r'## Current status\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
    if m:
        return m.group(1).strip()[:300]
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-dir', required=True)
    args = parser.parse_args()

    d = Path(args.project_dir)

    def read(name: str) -> str:
        p = d / name
        return p.read_text(encoding='utf-8', errors='replace') if p.exists() else ''

    state = {
        'methods_recent': methods_table_recent(read('methods.md'), MAX_METHODS_ROWS),
        'results_recent': recent_sections(read('results-log.md'), MAX_RESULTS_ENTRIES),
        'decisions_recent': recent_sections(read('decisions-log.md'), MAX_DECISIONS_ENTRIES),
        'open_questions': open_questions(read('open-questions.md')),
        'dashboard_status': dashboard_status(read('project-dashboard.md')),
    }

    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
