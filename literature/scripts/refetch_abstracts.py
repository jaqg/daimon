#!/usr/bin/env python3
"""
Backfill missing abstracts in one or more papers.json files.

Usage:
    python3 refetch_abstracts.py papers1.json [papers2.json ...]
    python3 refetch_abstracts.py --dry-run papers.json
    python3 refetch_abstracts.py --all-papers papers.json   # re-fetch even non-empty

Sources tried in order for each paper: Semantic Scholar → OpenAlex → arXiv.
Rate-limited to stay within free-tier limits (1 req/s for S2, polite delay for others).

Exit codes: 0 = all abstracts resolved, 1 = some still missing, 2 = argument error.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import URLError
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

UA = "daimon-refetch-abstracts/1.0 (research tool; mailto:daimon@example.com)"


def _get(url, headers=None, timeout=20, retries=2):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = Request(url, headers=h)
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except URLError as e:
            code = getattr(getattr(e, "reason", None), "errno", None) or getattr(e, "code", None)
            if code == 429 and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Per-source fetchers
# ---------------------------------------------------------------------------

def _s2_abstract(paper_id, s2_key=None):
    """Fetch abstract from Semantic Scholar by DOI or arXiv ID."""
    headers = {}
    if s2_key:
        headers["x-api-key"] = s2_key
    raw = _get(
        f"https://api.semanticscholar.org/graph/v1/paper/{quote_plus(paper_id)}?fields=abstract",
        headers=headers,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        ab = (data.get("abstract") or "").strip()
        return ab[:800] if ab else None
    except Exception:
        return None


def _openalex_abstract(doi):
    """Fetch abstract from OpenAlex abstract_inverted_index by DOI."""
    raw = _get(
        f"https://api.openalex.org/works/https://doi.org/{quote_plus(doi)}"
        f"?select=abstract_inverted_index&mailto=daimon@example.com"
    )
    if not raw:
        return None
    try:
        inverted = json.loads(raw).get("abstract_inverted_index") or {}
        if not inverted:
            return None
        pos_word = []
        for word, positions in inverted.items():
            for pos in positions:
                pos_word.append((pos, word))
        pos_word.sort()
        text = " ".join(w for _, w in pos_word).strip()
        return text[:800] if text else None
    except Exception:
        return None


def _arxiv_abstract(arxiv_id):
    """Fetch abstract from arXiv Atom API."""
    clean = re.sub(r"^arxiv:", "", arxiv_id, flags=re.IGNORECASE)
    raw = _get(f"https://export.arxiv.org/api/query?id_list={quote_plus(clean)}&max_results=1")
    if not raw:
        return None
    try:
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        summary = entry.find("atom:summary", ns)
        if summary is None or not summary.text:
            return None
        return " ".join(summary.text.split())[:800]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main fetch logic
# ---------------------------------------------------------------------------

def fetch_abstract(paper, s2_key=None, delay=1.1):
    """
    Try sources in order: S2 → OpenAlex → arXiv.
    Returns (abstract_text, source_used) or (None, None).
    """
    paper_id = paper.get("id", "")
    doi = paper.get("doi") or ""
    is_arxiv = paper_id.startswith("arxiv:") or "arxiv" in paper_id.lower()
    arxiv_id = paper_id if is_arxiv else None
    if not arxiv_id:
        # try to find arXiv ID in sources
        for src in (paper.get("sources") or []):
            if "arxiv" in src.lower():
                arxiv_id = paper_id
                break

    # Semantic Scholar: accepts DOI or ArXiv:<id>
    if doi:
        ab = _s2_abstract(doi, s2_key)
        time.sleep(delay)
        if ab:
            return ab, "semantic_scholar"
    if arxiv_id:
        s2_id = arxiv_id if arxiv_id.startswith("arXiv:") else f"arXiv:{arxiv_id.replace('arxiv:', '')}"
        ab = _s2_abstract(s2_id, s2_key)
        time.sleep(delay)
        if ab:
            return ab, "semantic_scholar"

    # OpenAlex: DOI only
    if doi:
        ab = _openalex_abstract(doi)
        time.sleep(delay)
        if ab:
            return ab, "openalex"

    # arXiv: arXiv papers only
    if arxiv_id:
        ab = _arxiv_abstract(arxiv_id)
        time.sleep(delay)
        if ab:
            return ab, "arxiv"

    return None, None


def process_file(path, dry_run=False, all_papers=False, s2_key=None, delay=1.1):
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    list_format = isinstance(data, list)
    papers = data if list_format else data.get("papers", [])
    targets = [p for p in papers if all_papers or not (p.get("abstract") or "").strip()]

    if not targets:
        print(f"{path.name}: all {len(papers)} papers already have abstracts — nothing to do")
        return 0, 0

    print(f"{path.name}: {len(targets)}/{len(papers)} papers need abstracts")

    fetched = 0
    still_missing = 0

    for i, paper in enumerate(targets, 1):
        title = (paper.get("title") or "")[:60]
        print(f"  [{i}/{len(targets)}] {title}...", end=" ", flush=True)

        if dry_run:
            print("(dry-run)")
            continue

        ab, source = fetch_abstract(paper, s2_key=s2_key, delay=delay)
        if ab:
            paper["abstract"] = ab
            print(f"OK ({source})")
            fetched += 1
        else:
            print("MISSING")
            still_missing += 1

    if not dry_run:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(papers if list_format else data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        tmp.replace(path)
        print(f"  Saved: {path} ({fetched} filled, {still_missing} still missing)")

    return fetched, still_missing


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill missing abstracts in papers.json files via S2/OpenAlex/arXiv."
    )
    parser.add_argument("files", nargs="+", metavar="papers.json")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be fetched, don't write")
    parser.add_argument("--all-papers", action="store_true", help="Re-fetch even non-empty abstracts")
    parser.add_argument("--s2-key", default=None, metavar="KEY",
                        help="Semantic Scholar API key (or set SEMANTIC_SCHOLAR_API_KEY env var)")
    parser.add_argument("--delay", type=float, default=1.1, metavar="SEC",
                        help="Seconds between requests (default: 1.1 to stay under S2 free tier)")
    args = parser.parse_args()

    import os
    s2_key = args.s2_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if s2_key:
        print(f"Using Semantic Scholar API key (delay reduced to {min(args.delay, 0.15):.2f}s)")
        delay = min(args.delay, 0.15)
    else:
        delay = args.delay

    total_fetched = 0
    total_missing = 0

    for fpath in args.files:
        if not Path(fpath).exists():
            print(f"ERROR: {fpath} not found", file=sys.stderr)
            continue
        f, m = process_file(fpath, dry_run=args.dry_run, all_papers=args.all_papers,
                            s2_key=s2_key, delay=delay)
        total_fetched += f
        total_missing += m

    print(f"\nTotal: {total_fetched} abstracts filled, {total_missing} still missing")
    sys.exit(0 if total_missing == 0 else 1)


if __name__ == "__main__":
    main()
