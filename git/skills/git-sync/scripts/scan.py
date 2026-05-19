#!/usr/bin/env python3
"""Scan git working tree and emit structured JSON for Claude to group and message.

Output schema:
  {
    "clean": bool,
    "tracked": [{"path": str, "status": str, "diff_stat": str, "diff_excerpt": str}],
    "untracked": [{"path": str, "ignored": bool, "ambiguous": bool, "content_excerpt": str}],
    "already_staged": [str],
    "log": [str]
  }
"""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AMBIGUOUS_EXTS = {".log", ".tmp", ".pyc", ".pyo", ".o", ".a", ".so", ".out", ".bak", ".swp"}
SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".json", ".ini", ".cfg",
    ".sh", ".bash", ".fish", ".zsh", ".rb", ".go", ".rs", ".c", ".cpp", ".h",
    ".css", ".scss", ".html", ".tex", ".bib", ".r", ".jl",
}

DIFF_MAX_LINES = 200
CONTENT_MAX_LINES = 80


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def is_binary(path):
    try:
        with open(path, "rb") as f:
            chunk = f.read(8000)
        return b"\x00" in chunk
    except OSError:
        return False


def check_ignored(path):
    r = run(["git", "check-ignore", "-q", path])
    return r.returncode == 0


def get_diff(path, status):
    if status.startswith("D") or status.endswith("D"):
        r = run(["git", "diff", "--", path])
    else:
        r = run(["git", "diff", "--", path])

    stat_r = run(["git", "diff", "--stat", "--", path])
    stat = stat_r.stdout.strip().splitlines()[-1] if stat_r.stdout.strip() else ""

    lines = r.stdout.splitlines()
    if len(lines) > DIFF_MAX_LINES:
        excerpt = "\n".join(lines[:DIFF_MAX_LINES]) + f"\n... ({len(lines) - DIFF_MAX_LINES} more lines)"
    else:
        excerpt = r.stdout

    return stat, excerpt


def get_content(path):
    p = Path(path)
    if not p.exists():
        return ""
    if is_binary(path):
        return "[binary file]"
    try:
        lines = p.read_text(errors="replace").splitlines()
        if len(lines) > CONTENT_MAX_LINES:
            return "\n".join(lines[:CONTENT_MAX_LINES]) + f"\n... ({len(lines) - CONTENT_MAX_LINES} more lines)"
        return "\n".join(lines)
    except OSError:
        return "[unreadable]"


def classify_untracked(path):
    ext = Path(path).suffix.lower()
    if ext in AMBIGUOUS_EXTS:
        return True  # ambiguous
    if ext in SOURCE_EXTS:
        return False  # clear source file
    # No known extension or unknown → ambiguous
    return True


def main():
    r = run(["git", "status", "--short"])
    if r.returncode != 0:
        print(json.dumps({"error": r.stderr.strip()}))
        sys.exit(1)

    lines = r.stdout.splitlines()
    if not lines:
        print(json.dumps({"clean": True, "tracked": [], "untracked": [], "already_staged": [], "log": []}))
        return

    tracked_paths = []
    untracked_paths = []
    already_staged = []

    for line in lines:
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:]

        if xy == "??":
            untracked_paths.append(path)
        elif xy[0] == "A":
            already_staged.append(path)
        else:
            tracked_paths.append((path, xy.strip()))

    # Check-ignore in parallel for untracked files
    ignored_set = set()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_ignored, p): p for p in untracked_paths}
        for fut in as_completed(futures):
            p = futures[fut]
            if fut.result():
                ignored_set.add(p)

    # Build untracked entries (skip ignored)
    untracked = []
    for path in untracked_paths:
        if path in ignored_set:
            continue
        ambiguous = classify_untracked(path)
        content = get_content(path) if not ambiguous else ""
        untracked.append({
            "path": path,
            "ignored": False,
            "ambiguous": ambiguous,
            "content_excerpt": content,
        })

    # Build tracked entries with diffs
    tracked = []
    for path, status in tracked_paths:
        stat, excerpt = get_diff(path, status)
        tracked.append({
            "path": path,
            "status": status,
            "diff_stat": stat,
            "diff_excerpt": excerpt,
        })

    # Recent log for style context
    log_r = run(["git", "log", "--oneline", "-10"])
    log = log_r.stdout.strip().splitlines() if log_r.returncode == 0 else []

    print(json.dumps({
        "clean": False,
        "tracked": tracked,
        "untracked": untracked,
        "already_staged": already_staged,
        "log": log,
    }, indent=2))


if __name__ == "__main__":
    main()
