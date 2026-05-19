#!/usr/bin/env python3
"""Fetch full text for papers in papers.json.

Tries per paper: (1) arXiv HTML, (2) Unpaywall OA PDF via PyMuPDF, (3) abstract fallback.

Usage:
    python3 fetch_fulltext.py --papers INPUT.json --output OUTPUT.json [--email EMAIL]

Output: JSON mapping paper_id -> {full_text, source, full_text_available}
"""

import argparse
import json
import os
import re
import sys
import time
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path


DELAY = 0.5  # seconds between API calls
UA = "lit-vault/1.0 (daimon research tool; github.com/jaqg/daimon)"


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]{2,6};", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_arxiv(arxiv_id: str):
    clean = arxiv_id.replace("arxiv:", "").strip()
    url = f"https://arxiv.org/html/{clean}"
    try:
        data, ctype = _get(url)
        html = data.decode("utf-8", errors="replace")
        # 404 or redirect to abstract page means no HTML version available
        if "<!DOCTYPE" not in html and "<html" not in html.lower():
            return None, None
        text = _strip_html(html)
        if len(text) < 500:
            return None, None
        return text, "arxiv"
    except Exception:
        return None, None


def fetch_unpaywall(doi: str, email: str):
    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.unpaywall.org/v2/{encoded}?email={urllib.parse.quote(email)}"
    try:
        data, _ = _get(url, timeout=10)
        info = json.loads(data)
        best = info.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf")
        if not pdf_url:
            return None, None
        return _extract_pdf(pdf_url)
    except Exception:
        return None, None


def _extract_pdf(pdf_url: str):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None, None
    try:
        data, _ = _get(pdf_url, timeout=30)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            doc = fitz.open(tmp)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            if len(text) < 500:
                return None, None
            return text, "unpaywall"
        finally:
            os.unlink(tmp)
    except Exception:
        return None, None


def process_paper(paper: dict, email: str):
    paper_id = paper.get("id", "")
    arxiv_id = paper.get("arxiv") or (
        paper_id if paper_id.startswith("arxiv:") else None
    )
    doi = paper.get("doi")

    full_text = source = None

    if arxiv_id:
        full_text, source = fetch_arxiv(arxiv_id)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source = fetch_unpaywall(doi, email)
        time.sleep(DELAY)

    if not full_text:
        source = "abstract"

    return {
        "full_text": full_text,
        "source": source,
        "full_text_available": full_text is not None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", required=True, help="Input papers.json path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--email", default="anonymous@example.com")
    args = parser.parse_args()

    with open(args.papers) as f:
        raw = json.load(f)

    papers = raw.get("papers", raw) if isinstance(raw, dict) else raw

    results = {}
    fetched = arxiv_count = unpaywall_count = abstract_count = 0

    for paper in papers:
        pid = paper.get("id", f"unknown-{len(results)}")
        print(f"  {pid} ...", end=" ", flush=True)
        result = process_paper(paper, args.email)
        results[pid] = result
        src = result["source"]
        if result["full_text_available"]:
            fetched += 1
            if src == "arxiv":
                arxiv_count += 1
            else:
                unpaywall_count += 1
            print(f"[{src}]")
        else:
            abstract_count += 1
            print("[abstract-only]")

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    total = len(papers)
    print(
        f"\nFull text fetched: {fetched}/{total} "
        f"(arXiv: {arxiv_count} | Unpaywall: {unpaywall_count} | abstract-only: {abstract_count})"
    )
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
