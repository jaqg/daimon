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

MAX_CURRENT_BULLETS = 5
MAX_MEMORY_LINES = 80
DECISIONS_CAP_LINES = 400   # prune-at-write threshold (AGENTS.md § Memory contract)
DECISIONS_KEEP_SECTIONS = 30


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


def _prune_decisions(text: str) -> tuple[str, str | None]:
    """Prune-at-write: if decisions-log exceeds cap, move oldest sections to
    archive payload. Returns (main_text, archive_payload_or_None).
    D-numbers are never reused — archived sections keep their numbers."""
    if len(text.splitlines()) <= DECISIONS_CAP_LINES:
        return text, None
    parts = re.split(r'(?m)^(?=## )', text)
    head = parts[0]
    sections = [p for p in parts[1:] if p.strip()]
    if len(sections) <= DECISIONS_KEEP_SECTIONS:
        return text, None
    keep, arch = sections[-DECISIONS_KEEP_SECTIONS:], sections[:-DECISIONS_KEEP_SECTIONS]
    nums = [int(n) for s in arch for n in re.findall(r'^## D(\d+)', s, re.M)]
    rng = f'D{min(nums):02d}–D{max(nums):02d}' if nums else f'{len(arch)} older entries'
    pointer = (f'\n> Archived {len(arch)} older entries ({rng}) → '
               f'`decisions-log-archive.md`. D-numbers final, never reused.\n\n')
    new_text = head.rstrip('\n') + '\n' + pointer + ''.join(keep)
    return new_text, ''.join(s.rstrip('\n') + '\n\n' for s in arch)


# ── decisions-log.md ──────────────────────────────────────────────────────────

def append_decisions(text: str, decisions: list[dict]) -> str:
    lines = text.rstrip('\n').split('\n')
    for d in decisions:
        date = d.get('date') or TODAY
        entry_text = d.get('text', '').strip()
        rationale = d.get('rationale', '').strip()
        if _already_present(text, date, entry_text):
            continue
        lines += ['', f'## {date} — {entry_text}', f'**Rationale:** {rationale}']
    return '\n'.join(lines).rstrip('\n') + '\n'


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
        ]
    return '\n'.join(lines).rstrip('\n') + '\n'


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
            lines += ['', f'## [OPEN] {qtext} (added {date})']
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

    return '\n'.join(lines).rstrip('\n') + '\n'


# ── history.md ────────────────────────────────────────────────────────────────

def append_history(text: str, entries: list[dict]) -> str:
    """Append dated session-log sections. Idempotent on date + title[:40]."""
    lines = text.rstrip('\n').split('\n')
    for h in entries:
        date = h.get('date') or TODAY
        title = h.get('title', '').strip()
        body = h.get('body', '').strip()
        if _already_present(text, date, title):
            continue
        lines += ['', f'## {date} — {title}', '', body]
    return '\n'.join(lines).rstrip('\n') + '\n'


# ── memory/project_*.md (CURRENT + CONSTRAINTS only) ──────────────────────────

def replace_current(text: str, bullets: list[str]) -> str:
    """Replace ## CURRENT section body with the given bullets (max 5).

    Replace semantics: caller supplies the FULL desired bullet set, not a delta.
    """
    if not bullets:
        return text
    if len(bullets) > MAX_CURRENT_BULLETS:
        print(f'warning: memory_current has {len(bullets)} bullets; '
              f'keeping first {MAX_CURRENT_BULLETS}', file=sys.stderr)
        bullets = bullets[:MAX_CURRENT_BULLETS]
    body = '\n'.join(f'- {b.strip()}' for b in bullets)
    pattern = r'(## CURRENT[^\n]*\n)(.*?)(?=\n## |\Z)'
    m = re.search(pattern, text, flags=re.DOTALL)
    if m:
        return text[:m.start(2)] + body + '\n' + text[m.end(2):]
    # No CURRENT section — insert after frontmatter (or at top)
    anchor = 0
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            anchor = text.find('\n', end + 4) + 1
    return text[:anchor] + '\n## CURRENT\n' + body + '\n' + text[anchor:]


def append_constraints(text: str, constraints: list[str]) -> str:
    """Append bullets into ## CONSTRAINTS section (idempotent on first 40 chars)."""
    new = [c.strip() for c in constraints if c.strip() and c.strip()[:40] not in text]
    if not new:
        return text
    body = '\n'.join(f'- {c}' for c in new)
    pattern = r'(## CONSTRAINTS[^\n]*\n)(.*?)(?=\n## |\Z)'
    m = re.search(pattern, text, flags=re.DOTALL)
    if m:
        section_body = m.group(2).rstrip('\n')
        replacement = (section_body + '\n' if section_body else '') + body + '\n'
        return text[:m.start(2)] + replacement + text[m.end(2):]
    return text.rstrip('\n') + '\n\n## CONSTRAINTS\n' + body + '\n'


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

# ── status/ rollups (brain reads these directly, so they stay tiny) ───────────

STATUS_CAP_LINES = 15


def render_status(r: dict) -> tuple[str, str]:
    """Return (relative path, content) for one part's status rollup."""
    part = r['part']
    date = r.get('date') or datetime.today().strftime('%Y-%m-%d')

    def sec(name: str, items: list[str]) -> str:
        body = '\n'.join(f'- {i}' for i in (items or [])) or '- (none)'
        return f'## {name}\n{body}\n'

    text = (f'---\npart: {part} · updated: {date} · by: update-project\n---\n\n'
            + sec('CURRENT', r.get('current', [])) + '\n'
            + sec('NEXT', r.get('next', [])) + '\n'
            + sec('BLOCKED', r.get('blocked', [])) + '\n'
            + sec('DEBT', r.get('debt', [])))
    n = len(text.splitlines())
    if n > STATUS_CAP_LINES:
        print(f'warning: status/{part}.md is {n} lines (cap {STATUS_CAP_LINES}) — '
              f'move detail to history.md', file=sys.stderr)
    return f'status/{part}.md', text.rstrip('\n') + '\n'


def collect_agent_deltas(scratch: Path) -> list[str]:
    """Worker deltas are the raw input to the rollup; read them, return paths."""
    if not scratch.is_dir():
        return []
    return sorted(str(p) for p in scratch.rglob('*.md') if p.is_file())


def mark_deltas_processed(scratch: Path) -> int:
    n = 0
    for p in scratch.rglob('*.md'):
        if p.is_file():
            p.rename(p.with_suffix(p.suffix + '.processed'))
            n += 1
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-dir', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--updates', help='JSON string (avoid for unicode-heavy content)')
    group.add_argument('--updates-file', help='Path to JSON file (preferred; avoids shell quoting issues)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--memory-file',
                        help='Path to memory/project_*.md (enables history + memory_current + constraints updates)')
    parser.add_argument('--agent-scratch',
                        help='Repo .agent/status dir whose worker deltas fed the rollup; '
                             'files are renamed *.processed after a real apply (never with --dry-run)')
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

    def process(filename: str, transform, create: bool = False):
        path = project_dir / filename
        if not path.exists() and not create:
            return
        original = (path.read_text(encoding='utf-8', errors='replace')
                    if path.exists() else '')
        modified = transform(original)
        if modified != original:
            all_diffs.extend(_diff(original, modified, filename))
            write_ops.append((path, modified))

    if updates.get('decisions'):
        dec_path = project_dir / 'decisions-log.md'
        if dec_path.exists():
            original = dec_path.read_text(encoding='utf-8', errors='replace')
            modified = append_decisions(original, updates['decisions'])
            modified, archived = _prune_decisions(modified)
            if modified != original:
                all_diffs.extend(_diff(original, modified, 'decisions-log.md'))
                write_ops.append((dec_path, modified))
            if archived:
                apath = project_dir / 'decisions-log-archive.md'
                existing = (apath.read_text(encoding='utf-8', errors='replace')
                            if apath.exists() else '')
                combined = (existing.rstrip('\n') + '\n\n' if existing else '') + archived
                if not existing:
                    name = project_dir.name.replace('-', ' ')
                    combined = (f'# {name} — Decisions Archive\n\n'
                                f'Superseded decision entries, auto-archived by '
                                f'update-project (>{DECISIONS_CAP_LINES} lines, keep last '
                                f'{DECISIONS_KEEP_SECTIONS}).\n'
                                f'D-numbers here are final — never reused.\n\n---\n\n') + archived
                all_diffs.extend(_diff(existing, combined, 'decisions-log-archive.md'))
                write_ops.append((apath, combined))

    if updates.get('results'):
        process('results-log.md', lambda t: append_results(t, updates['results']))

    if updates.get('methods_updates'):
        process('methods.md', lambda t: append_methods_rows(t, updates['methods_updates']))

    if updates.get('questions'):
        process('open-questions.md', lambda t: update_questions(t, updates['questions']))

    if updates.get('dashboard_status_line'):
        process('project-dashboard.md',
                lambda t: update_dashboard_status(t, updates['dashboard_status_line']))

    if updates.get('history'):
        def history_transform(t: str) -> str:
            if not t:
                # Create from template: title header + purpose line
                name = project_dir.name.replace('-', ' ')
                t = (f'# {name} — History\n\n'
                     f'Dated session logs and implementation narratives.\n'
                     f'Current state: `memory/` project file. Canonical decisions: `decisions-log.md`.\n\n---\n')
            return append_history(t, updates['history'])
        process('history.md', history_transform, create=True)

    for spec in updates.get('status_rollups') or []:
        rel, content = render_status(spec)
        original = ''
        path = project_dir / rel
        if path.exists():
            original = path.read_text(encoding='utf-8', errors='replace')
        if content != original:
            all_diffs.extend(_diff(original, content, rel))
            write_ops.append((path, content))

    mem_bullets = updates.get('memory_current') or []
    constraints = updates.get('constraints') or []
    if (mem_bullets or constraints) and args.memory_file:
        mp = Path(args.memory_file).expanduser()
        if mp.exists():
            original = mp.read_text(encoding='utf-8', errors='replace')
            modified = replace_current(original, mem_bullets) if mem_bullets else original
            if constraints:
                modified = append_constraints(modified, constraints)
            n_lines = len(modified.splitlines())
            if n_lines > MAX_MEMORY_LINES:
                print(f'warning: {mp.name} now {n_lines} lines (cap {MAX_MEMORY_LINES}) — '
                      f'move dated detail to history.md', file=sys.stderr)
            if modified != original:
                all_diffs.extend(_diff(original, modified, str(mp)))
                write_ops.append((mp, modified))
        else:
            print(f'warning: memory file not found: {mp}', file=sys.stderr)

    galaxy = updates.get('galaxy_candidates', [])

    if args.dry_run:
        print('\n'.join(all_diffs) if all_diffs else '(no changes)')
        if galaxy:
            print('\nGalaxy note candidates (not written):')
            for c in galaxy:
                print(f'  - {c}')
        sys.exit(0)

    for path, content in write_ops:
        path.parent.mkdir(parents=True, exist_ok=True)
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

    if args.agent_scratch and (updates.get('status_rollups') or []):
        scratch = Path(args.agent_scratch).expanduser()
        if scratch.is_dir():
            n = mark_deltas_processed(scratch)
            print(f'Marked {n} worker delta(s) processed in {scratch} '
                  f'(rollup written — safe to clear context / delete worktree)')


if __name__ == '__main__':
    main()
