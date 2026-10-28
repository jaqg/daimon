#!/usr/bin/env python3
"""Deterministic pre-parse for event ingest mode B (single email).

Usage:
  event_stage.py --input PATH        # email file
  event_stage.py --stdin             # pasted content on stdin
  event_stage.py --refresh-missing SCHEMA.json   # recompute missing_fields, print schema

Output (stdout, JSON): the §2 extraction schema skeleton —
all content fields null, source_email filled from frontmatter/headers,
plus `candidates` (all URLs with anchor text, ISO date candidates
pre-filtered from the body) and `missing_fields` derived as
nulls ∩ {cost, registration_deadline, abstract_deadline, dates, location}.

Claude fills the skeleton in ONE pass; `--refresh-missing` recomputes gaps
after that pass (and after enrichment) so scripts, not the model, own the
gap logic.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from scan_inbox import parse_frontmatter

# Fields enrichment may fill. Order = plan §2.
MISSING_POOL = ["cost", "registration_deadline", "abstract_deadline", "dates", "location"]

URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
A_TAG_RE = re.compile(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
HEADER_RE = re.compile(r"^(From|Subject|Date):\s*(.+)$", re.M)


def strip_html(text):
    """Drop tags (keeping anchor text handled separately) for URL/anchor scans."""
    return re.sub(r"<[^>]+>", " ", text)


def extract_candidates(body):
    """All URLs with anchor text (ordered, deduped) + ISO date candidates."""
    urls = []
    seen = set()

    def add(url, anchor):
        url = url.rstrip(".,;:)")
        if url.startswith("http") and url not in seen:
            seen.add(url)
            urls.append({"url": url, "anchor": (anchor or "").strip() or url})

    for m in MD_LINK_RE.finditer(body):
        add(m.group(2), m.group(1))
    for m in A_TAG_RE.finditer(body):
        add(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)))
    plain = MD_LINK_RE.sub(" ", A_TAG_RE.sub(" ", body))
    for m in URL_RE.finditer(plain):
        add(m.group(0), m.group(0))

    # ISO dates from the body only (frontmatter excluded upstream).
    dates = sorted(set(ISO_RE.findall(body)))
    return urls, dates


def extract_source_email(frontmatter, body):
    src = {
        "date": frontmatter.get("date"),
        "from": frontmatter.get("from"),
        "subject": frontmatter.get("subject"),
    }
    headers = dict((k.lower(), v.strip()) for k, v in HEADER_RE.findall(body))
    for key in ("date", "from", "subject"):
        if not src[key]:
            src[key] = headers.get(key)
    return src


def compute_missing_fields(schema):
    """nulls ∩ MISSING_POOL — the single source of truth for enrichment gaps."""
    return [f for f in MISSING_POOL if not schema.get(f)]


def build_schema(text):
    frontmatter, body = parse_frontmatter(text)
    candidates_urls, candidates_dates = extract_candidates(body)
    schema = {
        "event_name": None,
        "series": None,
        "dates": None,
        "location": None,
        "abstract_deadline": None,
        "registration_deadline": None,
        "cost": None,
        "urls": {"homepage": None, "registration": None, "abstracts": None, "other": []},
        "relevance": None,
        "relevance_reason": None,
        "source_email": extract_source_email(frontmatter, body),
        "missing_fields": [],
        "candidates": {"urls": candidates_urls, "dates": candidates_dates},
    }
    schema["missing_fields"] = compute_missing_fields(schema)
    return schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", metavar="PATH", help="email file path")
    src.add_argument("--stdin", action="store_true", help="read pasted content from stdin")
    src.add_argument("--refresh-missing", metavar="SCHEMA",
                     help="recompute missing_fields for a filled schema, print to stdout")
    args = parser.parse_args()

    if args.refresh_missing:
        path = Path(args.refresh_missing)
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"event_stage: cannot read schema {path}: {exc}", file=sys.stderr)
            return 2
        schema["missing_fields"] = compute_missing_fields(schema)
        print(json.dumps(schema, indent=2, ensure_ascii=False))
        return 0

    if args.stdin:
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.is_file():
            print(f"event_stage: no such file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")

    print(json.dumps(build_schema(text), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
