#!/usr/bin/env python3
"""Apply Claude's structured update JSON to project knowledge files.

Usage:
    python3 apply_updates.py \\
        --project-dir <path> \\
        --updates '<json>' \\
        [--dry-run]

Applies decisions, results, methods rows, and questions from Claude's JSON output
to the corresponding project files. Idempotent: skips entries that already exist
(matched on date + first 40 chars of content). Prints a unified diff on --dry-run.
"""

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


TODAY = datetime.today().strftime('%Y-%m-%d')


def _diff(original: str, modified: str, filename: str) -> list[str]:
    return list(difflib.unified_diff(
        original.splitlines(),
        modified.splitlines(),
        fromfile=f'a/{filename}',
        tofile=f'b/{filename}',
        lineterm='',
    ))


def _already_present(text: str, date: str, key: str) -> bool:
    return date in text and key[:40] in text


# ── decisions-log.md ──────────────────────────────────────────────────────────

def append_decisions(text: str, decisions: list[dict]) -> str:
    lines = text.rstrip('\n').split('\n')
    for d in decisions:
        date = d.get('date') or TODAY
        entry_text = d.get('text', '').strip()
        rationale = d.get('rationale', '').strip()
        if _already_present(text, date, entry_text):
            continue
        lines += ['', f'## {date} — {entry_text}', f'**Rationale:** {rationale}', '']
    return '\n'.join(lines) + '\n'


# ── results-log.md ────────────────────────────────────────────────────────────

def append_results(text: str, results: list[dict]) -> str:
    lines = text.rstrip('\n').split('\n')
    for r in results:
        date = r.get('date') or TODAY
        run = r.get('run', 'Unnamed run').strip()
        if _already_present(text, date, run):
            continue
        what = r.get("what") or r.get("result", "")
        lines += [
            '',
            f'## {date} — {run}',
            f'**What:** {what.strip()}',
            f'**Result:** {r.get("result", "").strip()}',
            f'**Interpretation:** {r.get("interpretation", "").strip()}',
            f'**Files:** {r.get("files", "TBD").strip()}',
            '',
        ]
    return '\n'.join(lines) + '\n'


# ── methods.md ────────────────────────────────────────────────────────────────

def append_methods_rows(text: str, methods_updates: list[dict]) -> str:
    if not methods_updates:
        return text
    lines = text.split('\n')
    # Find last line of first markdown table
    table_end = None
    in_table = False
    for i, line in enumerate(lines):
        if line.strip().startswith('|') and '|' in line.strip()[1:]:
            in_table = True
            table_end = i
        elif in_table:
            break
    if table_end is None:
        return text  # no table found; skip

    new_rows = []
    for m in methods_updates:
        date = m.get('date') or TODAY
        software = m.get('software', '').strip()
        if _already_present(text, date, software):
            continue
        row = (f"| {date} | {software} | {m.get('version', '—').strip()} "
               f"| {m.get('parameters', '').strip()} | {m.get('notes', '').strip()} |")
        new_rows.append(row)

    if not new_rows:
        return text
    result = lines[:table_end + 1] + new_rows + lines[table_end + 1:]
    return '\n'.join(result)


# ── open-questions.md ─────────────────────────────────────────────────────────

def update_questions(text: str, questions: list[dict]) -> str:
    lines = text.rstrip('\n').split('\n')
    for q in questions:
        status = q.get('status', 'OPEN').upper()
        qtext = q.get('text', '').strip()
        date = q.get('date') or TODAY
        answer = (q.get('answer') or '').strip()

        if status == 'OPEN':
            if qtext[:40] in text:
                continue
            lines += ['', f'## [OPEN] {qtext} (added {date})', '']
        elif status == 'CLOSED' and answer:
            # Replace matching [OPEN] header with [CLOSED]
            closed_line = f'## [CLOSED] {qtext} (resolved {date}) → {answer}'
            new_lines = []
            for line in lines:
                if '[OPEN]' in line and qtext[:30] in line:
                    new_lines.append(closed_line)
                else:
                    new_lines.append(line)
            lines = new_lines

    return '\n'.join(lines) + '\n'


# ── project-dashboard.md ──────────────────────────────────────────────────────

def update_dashboard_status(text: str, status_line: str) -> str:
    if not status_line:
        return text
    # Replace the blockquote line immediately after "## Current status"
    new_text = re.sub(
        r'(## Current status\n)(> [^\n]*)',
        lambda m: m.group(1) + '> ' + status_line.strip(),
        text, count=1,
    )
    return new_text


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-dir', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--updates', help='JSON string (avoid for unicode-heavy content)')
    group.add_argument('--updates-file', help='Path to JSON file (preferred; avoids shell quoting issues)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    try:
        if args.updates_file:
            updates = json.loads(Path(args.updates_file).read_text(encoding='utf-8'))
        else:
            updates = json.loads(args.updates)
    except json.JSONDecodeError as e:
        print(f'JSON parse error: {e}', file=sys.stderr)
        sys.exit(1)

    project_dir = Path(args.project_dir)
    all_diffs: list[str] = []
    write_ops: list[tuple[Path, str]] = []

    def process(filename: str, transform):
        path = project_dir / filename
        if not path.exists():
            return
        original = path.read_text(encoding='utf-8', errors='replace')
        modified = transform(original)
        if modified != original:
            all_diffs.extend(_diff(original, modified, filename))
            write_ops.append((path, modified))

    if updates.get('decisions'):
        process('decisions-log.md', lambda t: append_decisions(t, updates['decisions']))

    if updates.get('results'):
        process('results-log.md', lambda t: append_results(t, updates['results']))

    if updates.get('methods_updates'):
        process('methods.md', lambda t: append_methods_rows(t, updates['methods_updates']))

    if updates.get('questions'):
        process('open-questions.md', lambda t: update_questions(t, updates['questions']))

    if updates.get('dashboard_status_line'):
        process('project-dashboard.md',
                lambda t: update_dashboard_status(t, updates['dashboard_status_line']))

    galaxy = updates.get('galaxy_candidates', [])

    if args.dry_run:
        print('\n'.join(all_diffs) if all_diffs else '(no changes)')
        if galaxy:
            print('\nGalaxy note candidates (not written):')
            for c in galaxy:
                print(f'  - {c}')
        sys.exit(0)

    for path, content in write_ops:
        path.write_text(content, encoding='utf-8')

    if write_ops:
        print(f'Updated {len(write_ops)} file(s):')
        for path, _ in write_ops:
            print(f'  {path.name}')
    else:
        print('No changes.')

    if galaxy:
        print('\nGalaxy note candidates (not written — run /galaxy to create):')
        for c in galaxy:
            print(f'  - {c}')


if __name__ == '__main__':
    main()
