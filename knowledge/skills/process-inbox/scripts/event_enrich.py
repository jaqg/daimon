#!/usr/bin/env python3
"""Gap-driven link enrichment for event ingest (mode B, plan §0/§3 step 4).

Usage:
  event_enrich.py --schema SCHEMA.json [--max-pages 3] [--timeout 10]
                  [--delay 0.5] [--user-agent UA] [--local-root DIR]

Runs only when (a) missing_fields is non-empty AND (b) a candidate link
exists (registration/fee/cost/prices/travel-grant in anchor or URL).
Fetches at most --max-pages pages with urllib (UA 'daimon research tool',
--delay seconds between requests, --timeout seconds per request), fails
soft: a dead link becomes {"url", "error"} in the payload, never a crash.

Writes NOTHING itself — prints a gap-only JSON payload for the second
Claude pass:

  {"missing_fields": [...],
   "links": [{"url", "anchor"}],
   "pages": [{"url", "ok": true, "title": ..., "lines": [...]} |
             {"url", "ok": false, "error": ...}],
   "status": "payload" | "no_gaps" | "no_candidate_link"}

--local-root maps each link URL to <root>/<basename> so fixture HTML can
be exercised with zero network (tests only).
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_stage import compute_missing_fields  # noqa: E402

DEFAULT_UA = "daimon research tool"
LINK_HINT_RE = re.compile(
    r"regist|sign[\s-]?up|enroll|fee|cost|price|payment|travel[\s-]?grant|grant|bursar",
    re.I,
)
# Lines worth showing the 2nd pass for the fields we still lack.
GAP_HINT_RE = {
    "cost": re.compile(r"fee|cost|price|eur|usd|gbp|€|\$|£|free|waiv|rate", re.I),
    "registration_deadline": re.compile(r"regist|deadline|due|by\s+\d|clos", re.I),
    "abstract_deadline": re.compile(r"abstract|deadline|due|submit|submission", re.I),
    "dates": re.compile(r"\d{4}-\d{2}-\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", re.I),
    "location": re.compile(r"location|venue|city|address|held in|takes place|online|zoom", re.I),
}
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
MAX_LINE = 240
MAX_LINES_PER_FIELD = 8


def candidate_links(schema):
    """Ordered, deduped links whose anchor or URL hints at registration/fees."""
    seen, out = set(), []
    urls = schema.get("urls") or {}
    cands = list((schema.get("candidates") or {}).get("urls") or [])
    for key in ("registration", "homepage", "abstracts"):
        if urls.get(key):
            cands.append({"url": urls[key], "anchor": key})
    for u in urls.get("other") or []:
        cands.append({"url": u, "anchor": "other"})
    for c in cands:
        url, anchor = c.get("url") or "", c.get("anchor") or ""
        if not url.startswith("http") or url in seen:
            continue
        if LINK_HINT_RE.search(anchor) or LINK_HINT_RE.search(url):
            seen.add(url)
            out.append({"url": url, "anchor": anchor})
    return out


def strip_html(page):
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    text = re.sub(r"<[^>]+>", "\n", page)
    text = html.unescape(text)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line[:MAX_LINE])
    return lines


def local_path(url, root):
    name = url.rstrip("/").rsplit("/", 1)[-1] or "index.html"
    if "." not in name:
        name += ".html"
    return root / name


def fetch(url, args, now):
    if args.local_root:
        path = local_path(url, Path(args.local_root))
        if not path.is_file():
            raise FileNotFoundError(f"no local fixture for {url}: {path.name}")
        return path.read_text(encoding="utf-8", errors="replace")
    if now:
        time.sleep(args.delay)  # 0.5 s between network requests
    req = urllib.request.Request(url, headers={"User-Agent": args.user_agent})
    with urllib.request.urlopen(req, timeout=args.timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def gap_lines(lines, missing):
    """Pre-filter: only lines plausibly about a still-missing field."""
    out = {}
    for field in missing:
        hint = GAP_HINT_RE[field]
        hits = [l for l in lines if hint.search(l)]
        out[field] = hits[:MAX_LINES_PER_FIELD]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, metavar="PATH")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--local-root", metavar="DIR",
                        help="resolve URL basenames against DIR (fixture tests, no network)")
    args = parser.parse_args()

    try:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "detail": f"cannot read schema: {exc}"}))
        return 2

    missing = compute_missing_fields(schema)
    if not missing:
        print(json.dumps({"missing_fields": [], "links": [], "pages": [],
                          "status": "no_gaps"}))
        return 0

    links = candidate_links(schema)[: args.max_pages]
    if not links:
        print(json.dumps({"missing_fields": missing, "links": [], "pages": [],
                          "status": "no_candidate_link"}))
        return 0

    pages = []
    for i, link in enumerate(links):
        try:
            page = fetch(link["url"], args, now=i > 0)
            lines = strip_html(page)
            title_m = TITLE_RE.search(page)
            pages.append({
                "url": link["url"],
                "ok": True,
                "title": html.unescape(title_m.group(1)).strip() if title_m else None,
                "lines": gap_lines(lines, missing),
            })
        except Exception as exc:  # fail soft — dead link never crashes the run
            pages.append({"url": link["url"], "ok": False,
                          "error": f"{type(exc).__name__}: {exc}"})

    print(json.dumps({"missing_fields": missing, "links": links,
                      "pages": pages, "status": "payload"}, indent=2,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
