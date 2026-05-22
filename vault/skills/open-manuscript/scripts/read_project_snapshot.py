#!/usr/bin/env python3
"""Read a concise snapshot of a project's methods and results for manuscript context.

Usage:
    python3 read_project_snapshot.py --project-dir <path>

Outputs JSON with:
  - methods_rows: last 5 table rows from methods.md (header + rows)
  - results_recent: last 5 entries from results-log.md
  - open_questions: all [OPEN] entries from open-questions.md
"""

import argparse
import json
import re
from pathlib import Path

MAX_METHODS_ROWS = 5
MAX_RESULTS = 5


def strip_frontmatter(text: str) -> str:
    if not text.startswith('---'):
        return text
    end = text.find('\n---', 3)
    return text[end + 4:].lstrip('\n') if end != -1 else text


def methods_table_rows(text: str, n: int) -> str:
    """Return header + last n data rows of first markdown table."""
    body = strip_frontmatter(text)
    lines = body.split('\n')
    table_lines = [l for l in lines if l.strip().startswith('|')]
    if len(table_lines) < 2:
        return ''
    header = table_lines[0]
    separator = table_lines[1] if table_lines[1].strip().startswith('|--') else ''
    data_rows = [l for l in table_lines[2:] if l.strip().startswith('|')]
    recent = data_rows[-n:]
    parts = [header]
    if separator:
        parts.append(separator)
    parts.extend(recent)
    return '\n'.join(parts)


def results_recent(text: str, n: int) -> list[str]:
    """Return last n ## sections from results-log."""
    body = strip_frontmatter(text)
    sections = re.split(r'(?=^## )', body, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip().startswith('## ')]
    return sections[-n:]


def open_questions(text: str) -> list[str]:
    body = strip_frontmatter(text)
    sections = re.split(r'(?=^## )', body, flags=re.MULTILINE)
    return [s.strip() for s in sections if s.strip().startswith('## [OPEN]')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-dir', required=True)
    args = parser.parse_args()

    project_dir = Path(args.project_dir)

    def read_file(name: str) -> str:
        path = project_dir / name
        if not path.exists():
            return ''
        return path.read_text(encoding='utf-8', errors='replace')

    methods_text = read_file('methods.md')
    results_text = read_file('results-log.md')
    questions_text = read_file('open-questions.md')

    output = {
        'methods_rows': methods_table_rows(methods_text, MAX_METHODS_ROWS) if methods_text else '',
        'results_recent': results_recent(results_text, MAX_RESULTS) if results_text else [],
        'open_questions': open_questions(questions_text) if questions_text else [],
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
