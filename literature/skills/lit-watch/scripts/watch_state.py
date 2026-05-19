#!/usr/bin/env python3
"""
lit-watch state management: read/write lit-watch-state.json.
Tracks last_run date and seen_ids per project to avoid re-reporting.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STATE_DIR = os.path.expanduser("~/.config/daimon")


def state_path(state_dir=None):
    d = state_dir or os.environ.get("LIT_WATCH_STATE_DIR") or DEFAULT_STATE_DIR
    return Path(d).expanduser() / "lit-watch-state.json"


def load(state_dir=None):
    p = state_path(state_dir)
    if not p.exists():
        return {"last_run": None, "seen_ids": [], "projects": {}}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)

    # Integrity check
    today = datetime.now(timezone.utc).date().isoformat()
    last_run = data.get("last_run")
    if last_run and last_run > today:
        print(
            f"WARNING: State file has future last_run date ({last_run}). "
            "Possible corruption. Override with --since if needed.",
            file=sys.stderr,
        )

    return data


def save(state, state_dir=None):
    p = state_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(p)


def get_last_run(state, project=None):
    if project and project in (state.get("projects") or {}):
        return state["projects"][project].get("last_run") or state.get("last_run")
    return state.get("last_run")


def get_seen_ids(state, project=None):
    global_ids = set(state.get("seen_ids") or [])
    if project:
        proj_ids = set((state.get("projects") or {}).get(project, {}).get("seen_ids") or [])
        return global_ids | proj_ids
    return global_ids


def update(state, new_ids, project=None, state_dir=None):
    today = datetime.now(timezone.utc).date().isoformat()

    # Update global seen_ids (cap at 50k to avoid unbounded growth)
    existing = set(state.get("seen_ids") or [])
    existing.update(new_ids)
    state["seen_ids"] = list(existing)[-50000:]
    state["last_run"] = today

    # Update per-project
    if project:
        if "projects" not in state:
            state["projects"] = {}
        proj = state["projects"].setdefault(project, {})
        proj_ids = set(proj.get("seen_ids") or [])
        proj_ids.update(new_ids)
        proj["seen_ids"] = list(proj_ids)[-10000:]
        proj["last_run"] = today
        proj["seen_count"] = proj.get("seen_count", 0) + len(new_ids)

    save(state, state_dir)
    return state


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Read or reset lit-watch state")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--state-dir", default=None)
    args = parser.parse_args()

    if args.reset:
        p = state_path(args.state_dir)
        if p.exists():
            p.unlink()
            print(f"State reset: {p}")
        else:
            print("No state file found.")
    else:
        state = load(args.state_dir)
        print(json.dumps(state, indent=2))
