#!/usr/bin/env python3
"""Collect and merge lit-search results across multiple topics.

Usage:
  collect.py --topics "T1, T2" [--since DATE] [--results N]
             [--domains "arxiv,semantic_scholar,..."] [--project PROJECT_ID]
             [--state-dir PATH]

Runs lit-search/scripts/search.py once per topic in parallel (up to 4 workers),
merges all results, deduplicates by canonical ID, and cross-checks against
seen_ids in watch_state to return only new papers.

Output (stdout, JSON):
{
  "since": "YYYY-MM-DD",
  "topics": ["T1", "T2"],
  "papers": [...],        # all merged papers (deduped by ID)
  "new_papers": [...],    # papers not in seen_ids (Claude scores these)
  "meta": {
    "total_found": N,
    "after_dedup": M,
    "new_unseen": K,
    "topics_searched": ["T1", "T2"],
    "sources_coverage": {"arxiv": N, "semantic_scholar": N, ...},
    "sources_skipped": [...]
  }
}
"""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MAX_WORKERS = 4
DEFAULT_STATE_DIR = os.path.expanduser("~/.config/daimon")
DEFAULT_STATE_FILE = "lit-watch-state.json"


# ---------------------------------------------------------------------------
# Locate companion scripts
# ---------------------------------------------------------------------------

def find_script(pattern):
    result = subprocess.run(
        ["find", "-L", os.path.expanduser("~/.claude"), "-path", pattern, "-type", "f"],
        capture_output=True, text=True,
    )
    paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    return paths[0] if paths else None


# ---------------------------------------------------------------------------
# State: load seen_ids
# ---------------------------------------------------------------------------

def load_seen_ids(state_dir=None, project=None):
    d = state_dir or os.environ.get("LIT_WATCH_STATE_DIR") or DEFAULT_STATE_DIR
    p = Path(d).expanduser() / DEFAULT_STATE_FILE
    if not p.exists():
        return set(), None
    with open(p, encoding="utf-8") as f:
        state = json.load(f)

    today = date.today().isoformat()
    last_run = state.get("last_run")
    if last_run and last_run > today:
        print(
            f"WARNING: State last_run={last_run} is in the future (possible corruption). "
            "Override with --since.",
            file=sys.stderr,
        )

    global_ids = set(state.get("seen_ids") or [])
    if project:
        proj_ids = set((state.get("projects") or {}).get(project, {}).get("seen_ids") or [])
        return global_ids | proj_ids, last_run
    return global_ids, last_run


# ---------------------------------------------------------------------------
# Search one topic
# ---------------------------------------------------------------------------

def search_topic(search_script, topic, since, results, domains):
    cmd = [
        sys.executable, search_script,
        topic,
        "--results", str(results),
        "--sort", "recency",
        "--json",
    ]
    if since:
        cmd += ["--from-date", since]
    if domains:
        cmd += ["--sources", domains]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return topic, None, f"search.py failed for topic '{topic}': {proc.stderr[:200]}"

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return topic, None, f"JSON parse error for topic '{topic}': {e}"

    return topic, data, None


# ---------------------------------------------------------------------------
# Merge papers from multiple topic results
# ---------------------------------------------------------------------------

def merge_results(topic_results):
    """Deduplicate by ID, merging _topics and sources lists."""
    merged = {}  # id → paper record
    sources_coverage = {}
    sources_skipped = set()

    for topic, data, _err in topic_results:
        if data is None:
            continue
        meta = data.get("meta", {})
        for src in meta.get("sources_searched", []):
            sources_coverage[src] = sources_coverage.get(src, 0) + 1
        for src in meta.get("sources_skipped", []):
            sources_skipped.add(src)

        for paper in data.get("papers", []):
            pid = paper.get("id") or f"unknown:{paper.get('title', '')[:30]}"
            if pid not in merged:
                paper = dict(paper)
                paper["_topics"] = [topic]
                merged[pid] = paper
            else:
                # Merge topic attribution and sources
                merged[pid]["_topics"] = sorted(
                    set(merged[pid].get("_topics", [])) | {topic}
                )
                merged[pid]["sources"] = sorted(
                    set(merged[pid].get("sources", [])) | set(paper.get("sources", []))
                )

    return list(merged.values()), sources_coverage, sorted(sources_skipped)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", required=True,
                        help="Comma-separated list of search topics")
    parser.add_argument("--since", default=None,
                        help="Search from date (YYYY-MM-DD); overrides state last_run")
    parser.add_argument("--results", type=int, default=50,
                        help="Papers to fetch per topic (default: 50)")
    parser.add_argument("--domains", default=None,
                        help="Comma-separated DB list (default: all free DBs)")
    parser.add_argument("--project", default=None,
                        help="Project ID for per-project seen_ids tracking")
    parser.add_argument("--state-dir", default=None,
                        help="Path to state file directory")
    args = parser.parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    if not topics:
        print(json.dumps({"error": "No topics provided"}))
        sys.exit(1)

    # Load seen_ids and last_run from state
    seen_ids, state_last_run = load_seen_ids(args.state_dir, args.project)

    # Determine effective since date
    since = args.since or state_last_run
    if since is None:
        # First run: default to 7 days ago
        since = (date.today() - timedelta(days=7)).isoformat()

    # Locate search.py
    search_script = find_script("*/lit-search/scripts/search.py")
    if not search_script:
        print(json.dumps({"error": "lit-search/scripts/search.py not found in ~/.claude"}))
        sys.exit(1)

    # Run searches in parallel
    errors = []
    topic_results = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(topics))) as pool:
        futures = {
            pool.submit(search_topic, search_script, topic, since, args.results, args.domains): topic
            for topic in topics
        }
        for future in as_completed(futures):
            topic, data, err = future.result()
            topic_results.append((topic, data, err))
            if err:
                errors.append(err)

    # Merge and dedup
    all_papers, sources_coverage, sources_skipped = merge_results(topic_results)

    # Filter seen papers
    new_papers = [p for p in all_papers if p.get("id") not in seen_ids]

    # Build output
    output = {
        "since": since,
        "topics": topics,
        "papers": all_papers,
        "new_papers": new_papers,
        "meta": {
            "total_found": len(all_papers),
            "after_dedup": len(all_papers),
            "new_unseen": len(new_papers),
            "topics_searched": topics,
            "sources_coverage": sources_coverage,
            "sources_skipped": sources_skipped,
            "errors": errors,
        },
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
