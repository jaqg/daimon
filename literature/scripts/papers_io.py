#!/usr/bin/env python3
"""Shared read/write helpers for papers.json format."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "papers.schema.json"


def load(path):
    """Load papers.json. Returns dict with 'meta' and 'papers' keys."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "meta" not in data or "papers" not in data:
        raise ValueError(f"{path}: missing 'meta' or 'papers' key")
    return data


def save(data, path):
    """Save papers.json atomically."""
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def new_meta(query, sources_searched, sources_skipped=None, domain="general", **kwargs):
    return {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_searched": list(sources_searched),
        "sources_skipped": list(sources_skipped or []),
        "total_found": 0,
        "after_dedup": 0,
        "domain": domain,
        **kwargs,
    }


def paper_id(p):
    """Return canonical ID: 'arxiv:XXX' or 'doi:10.xxx/yyy' or None."""
    if p.get("arxiv_id") or (p.get("id", "").startswith("arxiv:")):
        aid = p.get("arxiv_id") or p["id"].replace("arxiv:", "")
        return f"arxiv:{aid}"
    doi = p.get("doi") or (p.get("id", "").replace("doi:", "") if p.get("id", "").startswith("doi:") else None)
    if doi:
        return f"doi:{doi}"
    return None


def merge(base_data, new_data):
    """Merge new_data into base_data, deduplicating by canonical ID."""
    seen = {}
    for p in base_data["papers"]:
        pid = paper_id(p)
        if pid:
            seen[pid] = p

    added = 0
    for p in new_data["papers"]:
        pid = paper_id(p)
        if pid and pid not in seen:
            seen[pid] = p
            added += 1
        elif pid and seen[pid].get("citations") is None and p.get("citations") is not None:
            seen[pid]["citations"] = p["citations"]

    base_data["papers"] = list(seen.values())
    base_data["meta"]["after_dedup"] = len(base_data["papers"])
    return added


def coverage_statement(meta):
    searched = ", ".join(meta.get("sources_searched") or [])
    skipped = ", ".join(meta.get("sources_skipped") or [])
    parts = [f"Searched: {searched or 'none'}"]
    if skipped:
        parts.append(f"Not searched (no key): {skipped}")
    return " | ".join(parts)
