#!/usr/bin/env python3
"""Vault hygiene: deterministic checker + mechanical archiver.

Usage:
    python3 vault_hygiene.py --vault-dir DIR (--check | --archive) [--fix]
                             [--project NAME] [--dry-run]

Modes:
  --check    Report violations/warnings. Exit 1 if violations found.
  --archive  Mechanical archival splits (decisions-log, work-log, ai-changes).
             --dry-run prints planned moves without writing.

--fix (with --check): apply zero-judgment fixes — remove stale MEMORY.md
index lines. Judgment-requiring issues (compress bloated memory file, write
missing index hooks) are reported only.

Thresholds (single source — AGENTS.md § Memory contract):
  decisions-log.md   >400 lines → archive oldest, keep last 30 sections
  ai-changes.md      >400 lines → archive oldest entries (target 360)
  work-log entries   dated >30 days → archive
  memory/project_*.md >80 lines → report (Claude compresses)
  MEMORY.md          >60 lines → report
  results-log.md     >400 lines → warn only (citable record, never auto-move)
  history.md         >1000 lines → warn only (overflow valve by design)
  project root       files outside the 8-file allowlist → warn (move to
                     research/ or queries/; folders always allowed)
  ai-out/            files older than 14 days → warn (buffer, not a home)
  status/<part>.md   >15 lines → warn (the brain reads this directly)
  repo .agent/       newer worker deltas than the last rollup → violation
                     (do not delete that worktree before /update-project)
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

DECISIONS_CAP = 400
DECISIONS_KEEP = 30
AI_CHANGES_CAP = 400
AI_CHANGES_TARGET = 360
WORKLOG_DAYS = 30
MEMORY_FILE_CAP = 80
INDEX_CAP = 60
RESULTS_WARN = 400
HISTORY_WARN = 1000
AI_OUT_AGE_DAYS = 14
STATUS_ROLLUP_CAP = 15
# Files allowed directly in 10-Projects/<X>/ — everything else belongs in a
# subfolder (research/, queries/, plans/, digests/, ai-out/, …). Folders are
# always allowed; only loose files are reported.
ROOT_ALLOW = {'AGENTS.md', 'project-dashboard.md', 'decisions-log.md',
              'history.md', 'results-log.md', 'methods.md', 'open-questions.md',
              'papers.json', 'CLAUDE.md', 'README.md', '_index.md'}

SKIP_DIRS = {'.git', '.obsidian', '.smart-env', 'graphify-out', 'processed',
             'node_modules', '__pycache__'}

violations: list[str] = []
warnings: list[str] = []
fixed: list[str] = []
planned: list[str] = []


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace') if path.exists() else ''


def split_entries(text: str, start_pat: str) -> tuple[str, list[str]]:
    """Split into (header_before_first_entry, [entries...])."""
    matches = list(re.finditer(start_pat, text, re.M))
    if not matches:
        return text, []
    header = text[:matches[0].start()]
    entries = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append(text[m.start():end])
    return header, entries


def entry_key(entry: str) -> str:
    """Idempotency key: date + first 40 chars of the header line."""
    first = entry.strip().split('\n', 1)[0]
    return first[:60]


def d_numbers(entry: str) -> list[int]:
    return [int(n) for n in re.findall(r'^## D(\d+)', entry, re.M)]


# ── checks ────────────────────────────────────────────────────────────────────

def check_memory(memory_dir: Path, do_fix: bool):
    if not memory_dir.exists():
        violations.append(f'{memory_dir}: missing memory directory')
        return
    index = memory_dir / 'MEMORY.md'
    index_text = read(index)

    # Stale index lines (deterministic → auto-fixable)
    if index_text:
        keep_lines, removed = [], []
        for line in index_text.split('\n'):
            m = re.match(r'^- \[[^\]]+\]\(([^)]+)\)', line)
            if m and not (memory_dir / m.group(1)).exists():
                removed.append(m.group(1))
                if not do_fix:
                    violations.append(f'MEMORY.md: stale index line → {m.group(1)}'
                                      + (' (rerun with --fix to remove)' if not do_fix else ''))
                continue
            keep_lines.append(line)
        if removed and do_fix:
            index.write_text('\n'.join(keep_lines), encoding='utf-8')
            fixed.append(f'MEMORY.md: removed {len(removed)} stale index line(s): '
                         + ', '.join(removed))

    # Index coverage: memory files not indexed
    indexed = set(re.findall(r'\]\(([^)]+)\)', index_text)) if index_text else set()
    for f in sorted(memory_dir.glob('*.md')):
        if f.name != 'MEMORY.md' and f.name not in indexed:
            warnings.append(f'memory/{f.name}: not indexed in MEMORY.md')

    # Index size
    if index_text and len(index_text.splitlines()) > INDEX_CAP:
        warnings.append(f'MEMORY.md: {len(index_text.splitlines())} lines (cap {INDEX_CAP}) '
                        f'— consolidate index entries')

    # Per-file caps + frontmatter
    for f in sorted(memory_dir.glob('*.md')):
        if f.name == 'MEMORY.md':
            continue
        text = read(f)
        n = len(text.splitlines())
        if n > MEMORY_FILE_CAP:
            violations.append(f'memory/{f.name}: {n} lines (cap {MEMORY_FILE_CAP}) '
                              f'— move dated detail to history.md, keep CURRENT+CONSTRAINTS+POINTERS')
        for key in ('name:', 'description:', 'type:'):
            fm = text.split('---')[1] if text.startswith('---') and text.count('---') >= 2 else ''
            if key not in fm:
                warnings.append(f'memory/{f.name}: frontmatter missing `{key}`')
                break


def check_project(project_dir: Path, name: str, vault: Path | None = None):
    # Root allowlist: agent-generated loose files are the sprawl mechanism.
    # Archive files live next to their log by design; folders are always allowed.
    for f in sorted(project_dir.iterdir()):
        if f.is_dir() or f.name in ROOT_ALLOW or f.name.startswith('.'):
            continue
        if f.name.endswith('-archive.md') or '-archive-' in f.name:
            continue
        warnings.append(f'{name}/{f.name}: loose file at project root — move to '
                        f'research/ (prose) or queries/ (machine output), '
                        f'ai-out/ if unreviewed')

    # ai-out/ is a buffer: nothing may link into it, and it must not accumulate.
    buf = project_dir / 'ai-out'
    if buf.is_dir():
        cutoff = datetime.today() - timedelta(days=AI_OUT_AGE_DAYS)
        stale = [f for f in buf.rglob('*')
                 if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff]
        if stale:
            warnings.append(f'{name}/ai-out/: {len(stale)} file(s) older than '
                            f'{AI_OUT_AGE_DAYS} days — promote or delete')

    # status/ rollups must stay readable by the brain in one cheap read.
    sdir = project_dir / 'status'
    if sdir.is_dir():
        for f in sorted(sdir.glob('*.md')):
            n = len(read(f).splitlines())
            if n > STATUS_ROLLUP_CAP:
                warnings.append(f'{name}/status/{f.name}: {n} lines (cap '
                                f'{STATUS_ROLLUP_CAP}) — brain reads this directly; '
                                f'move detail to status/log/ or history.md')
        check_repos(project_dir, name, vault)

    dec = project_dir / 'decisions-log.md'
    if dec.exists():
        n = len(read(dec).splitlines())
        if n > DECISIONS_CAP:
            violations.append(f'{name}/decisions-log.md: {n} lines (cap {DECISIONS_CAP}) '
                              f'— run --archive')

    res = project_dir / 'results-log.md'
    if res.exists():
        n = len(read(res).splitlines())
        if n > RESULTS_WARN:
            warnings.append(f'{name}/results-log.md: {n} lines — citable record, '
                            f'archive manually if slow growth annoys')

    hist = project_dir / 'history.md'
    if hist.exists():
        n = len(read(hist).splitlines())
        if n > HISTORY_WARN:
            warnings.append(f'{name}/history.md: {n} lines — overflow valve, '
                            f'split manually if unwieldy')

    dash = project_dir / 'project-dashboard.md'
    if dash.exists():
        old = old_worklog_entries(read(dash))
        if old:
            violations.append(f'{name}/project-dashboard.md: {len(old)} work-log '
                              f'entries older than {WORKLOG_DAYS} days — run --archive')


def check_repos(project_dir: Path, name: str, vault: Path | None = None):
    """Repos listed in status/repos.txt hold ephemeral .agent/ scratch whose only
    durable copy is the worker delta — flag a worktree that is safe to delete
    too early. `repo:` lines may be absolute paths; '~' is expanded."""
    listfile = project_dir / 'status' / 'repos.txt'
    if not listfile.exists():
        return
    rollups = sorted((project_dir / 'status').glob('*.md'),
                     key=lambda p: p.stat().st_mtime)
    last_rollup = rollups[-1] if rollups else None
    for raw in read(listfile).splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        # Accepts "repo: /path", "name /path", or a bare path (paths may contain
        # ':' on Windows-style drive letters, so split on whitespace, not ':').
        target = re.sub(r'^[\w.-]+:\s*', '', line).strip().strip('`')
        repo = Path(os.path.expandvars(target)).expanduser()
        if not repo.is_absolute():
            repo = vault / repo          # relative entries resolve against the vault
        if not repo.is_dir():
            warnings.append(f'{name}: repo listed in status/repos.txt missing on disk '
                            f'— {repo}')
            continue
        scratch = repo / '.agent' / 'status'
        if not scratch.is_dir():
            warnings.append(f'{name}: {repo}/.agent/status/ absent — worker deltas are '
                            f'not being recorded')
            continue
        deltas = [f for f in scratch.rglob('*.md') if f.is_file()]
        if not deltas:
            continue
        newest = max(f.stat().st_mtime for f in deltas)
        if last_rollup is None or last_rollup.stat().st_mtime < newest:
            violations.append(f'{name}: {repo} has {len(deltas)} worker delta(s) newer than '
                              f'the last status rollup — run /update-project before clearing '
                              f'the brain or deleting that worktree')


def check_papers(vault: Path):
    for sub in ('20-Sources/papers', '20-Sources/datasets'):
        d = vault / sub
        if not d.exists():
            continue
        for f in sorted(d.glob('*.md')):
            text = read(f)
            fm = text.split('---')[1] if text.startswith('---') and text.count('---') >= 2 else ''
            missing = [k for k in ('status:', 'type:', 'subject:') if k not in fm]
            if missing:
                warnings.append(f'{sub}/{f.name}: frontmatter missing {", ".join(missing)}')


def check_symlinks(vault: Path):
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            p = Path(root) / fname
            if p.is_symlink() and not p.exists():
                rel = p.relative_to(vault)
                violations.append(f'{rel}: broken symlink → {os.readlink(p)}')


# ── archival (mechanical, idempotent) ─────────────────────────────────────────

def archive_decisions(project_dir: Path, name: str, dry_run: bool) -> bool:
    dec = project_dir / 'decisions-log.md'
    text = read(dec)
    if not text or len(text.splitlines()) <= DECISIONS_CAP:
        return False
    header, sections = split_entries(text, r'(?m)^## ')
    if len(sections) <= DECISIONS_KEEP:
        return False
    keep, arch = sections[-DECISIONS_KEEP:], sections[:-DECISIONS_KEEP]
    nums = [n for s in arch for n in d_numbers(s)]
    rng = f'D{min(nums):02d}–D{max(nums):02d}' if nums else f'{len(arch)} older entries'
    pointer = (f'\n> Archived {len(arch)} older entries ({rng}) → '
               f'`decisions-log-archive.md`. D-numbers final, never reused.\n\n')
    new_text = header.rstrip('\n') + '\n' + pointer + ''.join(keep)

    apath = project_dir / 'decisions-log-archive.md'
    aheader = read(apath) or (
        f'# {name} — Decisions Archive\n\n'
        f'Superseded decision entries, auto-archived by vault_hygiene.py '
        f'(>{DECISIONS_CAP} lines, keep last {DECISIONS_KEEP}).\n'
        f'D-numbers here are final — never reused in decisions-log.md.\n\n---\n')
    existing = read(apath)
    combined = (existing.rstrip('\n') + '\n\n' if existing else aheader) + \
        '\n'.join(arch).rstrip('\n') + '\n'

    planned.append(f'{name}/decisions-log.md: move {len(arch)} entries ({rng}) '
                   f'→ decisions-log-archive.md')
    if not dry_run:
        dec.write_text(new_text, encoding='utf-8')
        apath.write_text(combined, encoding='utf-8')
    return True


def old_worklog_entries(dash_text: str) -> list[str]:
    cutoff = datetime.today() - timedelta(days=WORKLOG_DAYS)
    _, entries = split_entries(dash_text, r'(?m)^### (\d{4}-\d{2}-\d{2})')
    old = []
    for e in entries:
        m = re.match(r'### (\d{4}-\d{2}-\d{2})', e)
        if m and datetime.strptime(m.group(1), '%Y-%m-%d') < cutoff:
            old.append(e)
    return old


def archive_worklog(project_dir: Path, name: str, dry_run: bool) -> bool:
    dash = project_dir / 'project-dashboard.md'
    text = read(dash)
    if not text:
        return False
    old = old_worklog_entries(text)
    if not old:
        return False
    new_text = text
    for e in old:
        new_text = new_text.replace(e, '', 1)
    new_text = re.sub(r'\n{3,}', '\n\n', new_text)

    apath = project_dir / 'worklog-archive.md'
    existing = read(apath)
    header = existing or (
        f'# {name} Work Log Archive\n\nEntries older than {WORKLOG_DAYS} days, '
        f'auto-archived by vault_hygiene.py. Decisions live in decisions-log.md; '
        f'dated detail in history.md.\n\n---\n')
    seen = existing
    to_add = [e for e in old if entry_key(e) not in seen]
    combined = (existing.rstrip('\n') + '\n\n' if existing else header) + \
        '\n'.join(to_add).rstrip('\n') + '\n'

    planned.append(f'{name}/project-dashboard.md: move {len(to_add)} work-log '
                   f'entries (>{WORKLOG_DAYS} days) → worklog-archive.md')
    if not dry_run:
        dash.write_text(new_text, encoding='utf-8')
        apath.write_text(combined, encoding='utf-8')
    return True


def archive_ai_changes(vault: Path, dry_run: bool) -> bool:
    log = vault / '40-Meta/ai-changes.md'
    text = read(log)
    if not text or len(text.splitlines()) <= AI_CHANGES_CAP:
        return False
    header, entries = split_entries(text, r'(?m)^(?:## )?(\d{4}-\d{2}-\d{2})')
    if not entries:
        return False
    # Move oldest entries until under target
    lines_total = len(text.splitlines())
    move: list[str] = []
    idx = 0
    while lines_total > AI_CHANGES_TARGET and idx < len(entries) - 10:
        move.append(entries[idx])
        lines_total -= len(entries[idx].splitlines())
        idx += 1
    if not move:
        return False
    keep = entries[idx:]
    new_text = header.rstrip('\n') + ('\n\n> Older entries archived in '
                                       '`ai-changes-archive-*.md`.\n\n' if 'archived' not in header else '\n\n') + \
        ''.join(keep)

    by_year: dict[str, list[str]] = {}
    for e in move:
        y = re.match(r'(?:## )?(\d{4})-', e).group(1)
        by_year.setdefault(y, []).append(e)
    for year, year_entries in sorted(by_year.items()):
        apath = vault / f'40-Meta/ai-changes-archive-{year}.md'
        existing = read(apath)
        aheader = existing or (
            f'# AI Changes Archive {year}\n\nSession logs moved from `ai-changes.md` '
            f'by vault_hygiene.py (> {AI_CHANGES_CAP} lines).\n\n---\n')
        seen = existing
        to_add = [e for e in year_entries if entry_key(e) not in seen]
        combined = (existing.rstrip('\n') + '\n\n' if existing else aheader) + \
            '\n'.join(to_add).rstrip('\n') + '\n'
        planned.append(f'40-Meta/ai-changes.md: move {len(to_add)} entries → '
                       f'ai-changes-archive-{year}.md')
        if not dry_run:
            apath.write_text(combined, encoding='utf-8')
    if not dry_run:
        log.write_text(new_text, encoding='utf-8')
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vault-dir', required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--archive', action='store_true')
    ap.add_argument('--fix', action='store_true',
                    help='apply zero-judgment fixes (stale MEMORY.md index lines)')
    ap.add_argument('--project', help='limit project checks to 10-Projects/[Collabs/]<NAME>')
    ap.add_argument('--dry-run', action='store_true',
                    help='with --archive: print planned moves without writing')
    args = ap.parse_args()

    vault = Path(args.vault_dir).expanduser().resolve()
    if not vault.exists():
        print(f'vault not found: {vault}', file=sys.stderr)
        sys.exit(2)

    check_memory(vault / 'memory', do_fix=args.fix and args.check)

    projects: list[Path] = []
    if args.project:
        for base in (vault / '10-Projects', vault / '10-Projects/Collabs'):
            p = base / args.project
            if p.exists():
                projects.append(p)
        if not projects:
            print(f'project not found: {args.project}', file=sys.stderr)
            sys.exit(2)
    else:
        projects = [p for p in (vault / '10-Projects').iterdir() if p.is_dir()]
        collabs = vault / '10-Projects/Collabs'
        if collabs.exists():
            projects += [p for p in collabs.iterdir() if p.is_dir()]

    for p in projects:
        check_project(p, p.name, vault)

    if not args.project:
        check_papers(vault)
        check_symlinks(vault)

    if args.archive:
        for p in projects:
            archive_decisions(p, p.name, args.dry_run)
            archive_worklog(p, p.name, args.dry_run)
        if not args.project:
            archive_ai_changes(vault, args.dry_run)
        if not args.dry_run:
            # Re-check: report post-archive state, not stale violations
            violations.clear()
            warnings.clear()
            check_memory(vault / 'memory', do_fix=False)
            for p in projects:
                check_project(p, p.name, vault)
            if not args.project:
                check_papers(vault)
                check_symlinks(vault)

    # Report
    print(f'## Vault hygiene — {datetime.today():%Y-%m-%d}'
          f'{" (dry run)" if args.dry_run else ""}')
    if violations:
        print(f'\n### Violations ({len(violations)})')
        for v in violations:
            print(f'- {v}')
    if planned:
        print(f'\n### Archival moves ({len(planned)})')
        for m in planned:
            print(f'- {m}')
    if fixed:
        print(f'\n### Auto-fixed ({len(fixed)})')
        for f in fixed:
            print(f'- {f}')
    if warnings:
        print(f'\n### Warnings ({len(warnings)})')
        for w in warnings:
            print(f'- {w}')
    if not (violations or planned or fixed or warnings):
        print('\nAll clean.')

    sys.exit(1 if violations else 0)


if __name__ == '__main__':
    main()
