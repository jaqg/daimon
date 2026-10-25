#!/usr/bin/env python3
"""Migrate loose files out of vault project roots into class folders.

Contract: vault AGENTS.md § Agent artifact layout. Only files directly inside a
project folder are considered; subfolders are left alone. Moves use `git mv`
when the folder is inside a git work tree, so the vault history stays clean and
every move is revertible with `git checkout`.

Usage:
    python3 migrate_project_files.py --vault-dir DIR [--project NAME] [--dry-run]
                                     [--list]

Classification (first match wins; `papers.json` and the root allowlist files
from vault_hygiene.py are never moved):
    *.json / *.schema.json / *.csv         → queries/     (script I/O)
    *.gjf *.fch *.xyz *.wfn *.cube …       → data/        (calculation inputs/outputs)
    lit-review-*.md, overnight-lit-*.md    → lit-reviews/ (per-run review records)
    *handoff*.md, next-session-*.md        → handoffs/    (for the next session)
    email-draft-*.md                       → handoffs/
    *-log.md, dispatch-*.md, NEXT_ACTIONS* → ops/         (agent bookkeeping)
    everything else (.md)                  → research/    (curated prose)

Reports (never rewrites) references to a moved file: [[wikilink]], ![[embed]],
and ](path.md) style links, plus mentions of the exact filename anywhere in the
vault. Wikilinks resolve by basename in Obsidian, so plain [[name]] survives a
move; markdown-style relative links do not and are listed for manual fixing.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT_ALLOW = {'AGENTS.md', 'project-dashboard.md', 'decisions-log.md',
              'history.md', 'results-log.md', 'methods.md', 'open-questions.md',
              'papers.json', 'CLAUDE.md', 'README.md', '_index.md'}

DATA_EXT = {'.gjf', '.fch', '.xyz', '.wfn', '.wfx', '.cube', '.cub', '.molden',
            '.gbw', '.log', '.out', '.npy', '.npz', '.pdb', '.mol', '.sdf'}
MACHINE_EXT = {'.json', '.csv', '.tsv', '.yaml', '.yml', '.bib', '.txt'}

# Operational bookkeeping, not knowledge, not data. Anchored at .md so generic
# prose names (methods-table.md, curation-pipeline-review.md) are not caught.
OPS_PAT = re.compile(r'[-_](?:logs?|dispatch|errors?|status|sweep)\.md$'
                     r'|^dispatch[-_.]|^NEXT_ACTIONS|^TODO|^DIAGNOSTIC_', re.I)
LITREV_PAT = re.compile(r'^(lit-review-.*|overnight-lit-.*|.*lit-review.*)\.md$', re.I)
HANDOFF_PAT = re.compile(r'(handoff|next-session|email-draft)', re.I)
ARCHIVE_PAT = re.compile(r'-archive([-.]|$)', re.I)

# Explicit overrides for names that regexes classify badly (bare plurals, etc.).
OVERRIDES = {'errors.md': 'ops', 'error-log.md': 'ops',
             'dispatch-matrix.md': 'ops', 'dispatch.md': 'ops'}


def classify(name: str) -> str | None:
    """Return target subfolder, or None if the file stays at the root."""
    if name in ROOT_ALLOW or name.startswith('.'):
        return None
    if name in OVERRIDES:
        return OVERRIDES[name]
    p = Path(name)
    if p.suffix.lower() in DATA_EXT:
        return 'data'
    if ARCHIVE_PAT.search(name):          # decisions-log-archive.md etc. stay
        return None
    if p.suffix.lower() in MACHINE_EXT:
        return 'queries'
    if p.suffix.lower() != '.md':
        return 'data'
    if LITREV_PAT.match(name):
        return 'lit-reviews'
    if HANDOFF_PAT.search(name):
        return 'handoffs'
    if OPS_PAT.search(name):
        return 'ops'
    return 'research'


def scan_refs(vault: Path, stems: set[str], names: set[str]) -> dict[str, list[str]]:
    """One pass over the vault's markdown. Wikilinks resolve by basename in
    Obsidian, so [[stem]] survives a move and is only reported as a plain
    mention; ](path) links break and are reported as PATH LINK."""
    refs: dict[str, list[str]] = {}
    pat = re.compile(r'\[\[([^]|#]+?)(?:[#|][^\]]*)?\]\]|\]\(([^)]+)\)')
    for f in vault.rglob('*.md'):
        if any(skip in f.parts for skip in ('.git', '.obsidian', 'graphify-out',
                                           'smart-env', 'node_modules')):
            continue
        try:
            text = f.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        rel = str(f.relative_to(vault))
        for m in pat.finditer(text):
            inner = (m.group(1) or m.group(2)).strip()
            target = inner.split('/')[-1].split('#')[0].strip()
            if target in names:
                key, kind = target, ('PATH LINK (breaks)' if m.group(2)
                                     else 'wikilink (ok)')
            elif target in stems:
                key, kind = target + '.md', ('PATH LINK (breaks)' if m.group(2)
                                             else 'wikilink (ok)')
            else:
                continue
            refs.setdefault(key, []).append(f'  {rel}: {kind} → {inner[:60]}')
    return refs


def git_mv(src: Path, dst_dir: Path, vault: Path, dry: bool) -> str:
    dst = dst_dir / src.name
    if dry:
        return f'mv  {src.name} → {dst_dir.name}/'
    rel_src = str(src.relative_to(vault))
    rel_dst = str(dst.relative_to(vault))
    r = subprocess.run(['git', '-C', str(vault), 'mv', '--', rel_src, rel_dst],
                       capture_output=True, text=True)
    if r.returncode != 0:                      # untracked / dst dir missing
        dst_dir.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f'mv  {src.name} → {dst_dir.name}/  (fs, git mv failed: {r.stderr.strip()[:60]})'
    return f'mv  {src.name} → {dst_dir.name}/'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vault-dir', required=True)
    ap.add_argument('--project', action='append',
                    help='limit to a project folder name (repeatable); default: all')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--list', action='store_true', help='only print the plan')
    args = ap.parse_args()

    vault = Path(args.vault_dir).expanduser().resolve()
    bases = [vault / '10-Projects', vault / '10-Projects' / 'Collabs']

    # Pass 1: build the plan (folder/name -> target subfolder).
    todo: list[tuple[Path, Path, Path]] = []
    skipped = 0
    for base in bases:
        if not base.is_dir():
            continue
        for proj in sorted(p for p in base.iterdir() if p.is_dir()):
            if args.project and proj.name not in args.project:
                continue
            for f in sorted(p for p in proj.iterdir() if p.is_file()):
                target = classify(f.name)
                if not target:
                    skipped += 1
                    continue
                if (proj / target / f.name).exists():
                    print(f'SKIP collision: {proj.name}/{f.name} already in {target}/')
                    continue
                todo.append((proj, f, proj / target))

    names = {f.name for _, f, _ in todo}
    stems = {f.stem for _, f, _ in todo} - names
    refs = scan_refs(vault, stems, names)

    print(f'## Plan: {len(todo)} file(s) to move, {skipped} root file(s) stay '
          f'(allowlist/archive)')
    for proj, f, dst in todo:
        print(f'- {proj.name}/{f.name} → {dst.name}/')

    broken = {k: v for k, v in refs.items() if any('breaks' in r for r in v)}
    print(f'\n## References: {len(refs)} file(s) referenced, '
          f'{len(broken)} with path links that break on move')
    for k, v in sorted(refs.items()):
        print(f'{k}:')
        for r in v[:8]:
            print(r)
        if len(v) > 8:
            print(f'  … {len(v) - 8} more')

    if args.list:
        print('\n(nothing written — --list)')
        return
    for proj, f, dst in todo:
        print(git_mv(f, dst, vault, args.dry_run))
    if args.dry_run:
        print('(dry run — files unchanged)')


if __name__ == '__main__':
    main()
