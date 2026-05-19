#!/usr/bin/env python3
"""Collect git branch/worktree state and emit structured JSON.

Usage:
  branch_info.py                    -- default status
  branch_info.py --list             -- full branch table
  branch_info.py --clean            -- deletion candidates
  branch_info.py --merge BRANCH     -- merge preparation
  branch_info.py --new NAME         -- compute worktree path

Output shapes described per subcommand below.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PROTECTED = {'main', 'master', 'develop', 'staging'}


def run(cmd, **kwargs):
    r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def git_ok():
    _, _, rc = run(['git', 'rev-parse', '--git-dir'])
    return rc == 0


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_branches():
    """Return list of branch dicts from git branch -vv."""
    out, _, rc = run(['git', 'branch', '-vv'])
    if rc != 0:
        return []
    branches = []
    for line in out.splitlines():
        current = line.startswith('*')
        line = line.lstrip('* ').strip()
        # format: name sha [upstream: ahead N, behind M] subject
        m = re.match(r'(\S+)\s+([0-9a-f]+)\s*(.*)', line)
        if not m:
            continue
        name, sha, rest = m.group(1), m.group(2), m.group(3)
        ahead = behind = 0
        upstream = None
        track_m = re.search(r'\[([^\]]+)\]', rest)
        if track_m:
            track_str = track_m.group(1)
            up_m = re.match(r'([^:]+)', track_str)
            if up_m:
                upstream = up_m.group(1).strip()
            a_m = re.search(r'ahead (\d+)', track_str)
            b_m = re.search(r'behind (\d+)', track_str)
            if a_m:
                ahead = int(a_m.group(1))
            if b_m:
                behind = int(b_m.group(1))
        branches.append({
            'name': name,
            'sha': sha,
            'current': current,
            'upstream': upstream,
            'ahead': ahead,
            'behind': behind,
        })
    return branches


def parse_worktrees():
    """Return dict mapping branch_name -> worktree_path."""
    out, _, _ = run(['git', 'worktree', 'list', '--porcelain'])
    mapping = {}
    current_path = None
    for line in out.splitlines():
        if line.startswith('worktree '):
            current_path = line[len('worktree '):]
        elif line.startswith('branch refs/heads/'):
            branch = line[len('branch refs/heads/'):]
            if current_path:
                mapping[branch] = current_path
                current_path = None
        elif line == '':
            current_path = None
    return mapping


def parse_ages():
    """Return dict mapping branch_name -> {'relative': str, 'unix': int}."""
    out, _, _ = run([
        'git', 'for-each-ref',
        '--format=%(refname:short)\t%(committerdate:relative)\t%(committerdate:unix)',
        'refs/heads',
    ])
    ages = {}
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) == 3:
            ages[parts[0]] = {'relative': parts[1], 'unix': int(parts[2]) if parts[2] else 0}
    return ages


def merged_branches():
    out, _, _ = run(['git', 'branch', '--merged', 'main'])
    return {l.strip().lstrip('* ') for l in out.splitlines() if l.strip()} - PROTECTED


def repo_root():
    out, _, _ = run(['git', 'rev-parse', '--show-toplevel'])
    return out


def current_branch():
    out, _, _ = run(['git', 'branch', '--show-current'])
    return out


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_default():
    status_out, _, _ = run(['git', 'status', '--short'])
    branch = current_branch()
    branches = parse_branches()
    worktrees = parse_worktrees()
    merged = merged_branches()

    cur = next((b for b in branches if b['name'] == branch), None)
    uncommitted = bool(status_out.strip())

    linked = [
        {'branch': br, 'path': path}
        for br, path in worktrees.items()
        if br != branch
    ]

    log_out, _, _ = run(['git', 'log', '--oneline', '-5'])
    log = log_out.splitlines()

    return {
        'subcommand': 'default',
        'current_branch': branch,
        'uncommitted_changes': uncommitted,
        'status_short': status_out,
        'tracking': cur,
        'linked_worktrees': linked,
        'merged_stale': sorted(merged - {branch}),
        'recent_log': log,
    }


def cmd_list():
    branches = parse_branches()
    worktrees = parse_worktrees()
    ages = parse_ages()
    merged = merged_branches()

    result = []
    for b in branches:
        name = b['name']
        result.append({
            **b,
            'worktree_path': worktrees.get(name),
            'age': ages.get(name, {}).get('relative', ''),
            'merged': name in merged,
        })

    return {'subcommand': 'list', 'branches': result}


def cmd_clean():
    branches = parse_branches()
    worktrees = parse_worktrees()
    ages = parse_ages()
    merged = merged_branches()
    checked_out = set(worktrees.keys())

    candidates = []
    for b in branches:
        name = b['name']
        if name in PROTECTED:
            continue
        if name not in merged:
            continue
        if name in checked_out:
            continue
        candidates.append({
            'name': name,
            'age': ages.get(name, {}).get('relative', ''),
            'worktree_path': worktrees.get(name),
        })

    # Orphaned worktrees
    prune_out, _, _ = run(['git', 'worktree', 'prune', '--dry-run'])
    orphaned = [
        line.replace('Removing worktrees/', '').strip()
        for line in prune_out.splitlines()
        if line.strip()
    ]

    return {
        'subcommand': 'clean',
        'candidates': candidates,
        'orphaned_worktrees': orphaned,
    }


def cmd_merge(branch_name):
    # Verify branch exists
    _, _, rc = run(['git', 'rev-parse', '--verify', branch_name])
    if rc != 0:
        return {'error': f"Branch '{branch_name}' not found"}

    current = current_branch()

    log_out, _, _ = run(['git', 'log', f'{current}..{branch_name}', '--oneline'])
    commits = log_out.splitlines()

    stat_out, _, _ = run(['git', 'diff', f'{current}...{branch_name}', '--stat'])

    # Check if fast-forward is possible
    base_out, _, _ = run(['git', 'merge-base', current, branch_name])
    cur_sha, _, _ = run(['git', 'rev-parse', current])
    ff_possible = base_out.strip() == cur_sha.strip()

    worktrees = parse_worktrees()
    worktree_path = worktrees.get(branch_name)

    return {
        'subcommand': 'merge',
        'branch': branch_name,
        'target': current,
        'commits': commits,
        'commit_count': len(commits),
        'diff_stat': stat_out,
        'ff_possible': ff_possible,
        'worktree_path': worktree_path,
    }


def cmd_new(name):
    root = repo_root()
    if not root:
        return {'error': 'Not in a git repo'}

    repo_name = Path(root).name
    # Strip feature/ fix/ etc. prefix for directory name
    dir_suffix = re.sub(r'^(feature|fix|hotfix|chore|docs|refactor)/', '', name)
    worktree_path = str(Path(root).parent / f'{repo_name}-{dir_suffix}')

    status_out, _, _ = run(['git', 'status', '--short'])
    cur = current_branch()

    # Check if branch already exists
    _, _, rc = run(['git', 'rev-parse', '--verify', name])
    branch_exists = (rc == 0)

    # Check if worktree path already exists
    path_exists = Path(worktree_path).exists()

    return {
        'subcommand': 'new',
        'branch': name,
        'worktree_path': worktree_path,
        'current_branch': cur,
        'uncommitted_changes': bool(status_out.strip()),
        'branch_exists': branch_exists,
        'path_exists': path_exists,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd')
    sub.add_parser('list')
    sub.add_parser('clean')
    merge_p = sub.add_parser('merge')
    merge_p.add_argument('branch')
    new_p = sub.add_parser('new')
    new_p.add_argument('name')
    args = p.parse_args()

    if not git_ok():
        print(json.dumps({'error': 'Not in a git repository'}))
        sys.exit(1)

    if args.cmd == 'list':
        result = cmd_list()
    elif args.cmd == 'clean':
        result = cmd_clean()
    elif args.cmd == 'merge':
        result = cmd_merge(args.branch)
    elif args.cmd == 'new':
        result = cmd_new(args.name)
    else:
        result = cmd_default()

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
