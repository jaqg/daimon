#!/usr/bin/env python3
"""Extract metadata from a PDF directory → papers.json for lit-vault.

Strategy per PDF:
  1. Extract text from first 2 pages (fitz/PyMuPDF)
  2. Find DOI via regex
  3. DOI found → CrossRef lookup; S2 supplements missing abstract
  4. CrossRef fails → S2 by DOI
  5. No DOI → title heuristic → S2 title search
  6. All fail → filename stub entry (no abstract)

Output: papers.json compatible with lit-vault --papers flag (same schema as
lit-search; no screening fields → lit-vault imports all entries).

Optional --precache writes extracted full text keyed by paper id to
~/.cache/daimon/lit-vault/fulltext-cache.json so lit-vault skips re-fetching
already-local PDFs.
"""

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF (fitz) required: pip install pymupdf")

try:
    import requests
except ImportError:
    sys.exit("requests required: pip install requests")

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\[\]]{4,}", re.IGNORECASE)
ARXIV_RE = re.compile(r"arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
JATS_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, min_interval: float):
        self._lock = threading.Lock()
        self._last = 0.0
        self._min = min_interval

    def wait(self):
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._min:
                time.sleep(self._min - elapsed)
            self._last = time.monotonic()


_CR_RATE = _RateLimiter(0.3)
_S2_RATE = _RateLimiter(0.5)

# ---------------------------------------------------------------------------
# HTTP session (set User-Agent at call time)
# ---------------------------------------------------------------------------

_SESSION = requests.Session()


def _make_ua(email: Optional[str]) -> str:
    contact = f"; mailto:{email}" if email else ""
    return f"pdf2papers/1.0 (daimon lit-vault{contact})"


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def _extract_text(pdf_path: Path, n_pages: int = 2) -> str:
    try:
        doc = fitz.open(str(pdf_path))
        parts = []
        for i in range(min(n_pages, len(doc))):
            parts.append(doc[i].get_text())
        return "\n".join(parts)
    except Exception as exc:
        print(f"  [fitz] {pdf_path.name}: {exc}", file=sys.stderr)
        return ""


def _extract_fulltext(pdf_path: Path) -> str:
    try:
        doc = fitz.open(str(pdf_path))
        return "\n".join(page.get_text() for page in doc)
    except Exception as exc:
        print(f"  [fitz full] {pdf_path.name}: {exc}", file=sys.stderr)
        return ""


def _find_doi(text: str) -> Optional[str]:
    m = DOI_RE.search(text)
    if not m:
        return None
    doi = m.group(0)
    doi = re.sub(r"[.,;)\]]+$", "", doi)
    return doi


ABSTRACT_START_RE = re.compile(
    r"(?:^|\n)\s*(?:Abstract|ABSTRACT)\s*[\n:]?\s*",
    re.MULTILINE,
)
SECTION_END_RE = re.compile(
    r"\n\s*(?:1[\.\s]|Introduction|Keywords|KEYWORDS|Key\s+[Ww]ords)",
    re.MULTILINE,
)


def _extract_abstract_from_text(text: str) -> str:
    m = ABSTRACT_START_RE.search(text)
    if not m:
        return ""
    start = m.end()
    rest = text[start:]
    end_m = SECTION_END_RE.search(rest)
    raw = rest[:end_m.start()] if end_m else rest[:1500]
    cleaned = WHITESPACE_RE.sub(" ", raw.replace("\n", " ")).strip()
    if len(cleaned) < 50:
        return ""
    return cleaned[:1500]


def _find_arxiv(text: str) -> Optional[str]:
    m = ARXIV_RE.search(text)
    return m.group(1) if m else None


def _extract_title(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:20]:
        if 20 < len(line) < 300 and not re.match(r"^\d+$", line):
            return line
    return lines[0] if lines else ""


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _crossref(doi: str, ua: str) -> Optional[dict]:
    _CR_RATE.wait()
    try:
        r = _SESSION.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": ua},
            timeout=12,
        )
        if r.status_code == 200:
            return r.json().get("message", {})
    except Exception as exc:
        print(f"  [crossref] {doi}: {exc}", file=sys.stderr)
    return None


def _s2_by_doi(doi: str, ua: str) -> Optional[dict]:
    _S2_RATE.wait()
    try:
        r = _SESSION.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{doi}",
            params={"fields": "title,authors,year,venue,abstract,citationCount,externalIds"},
            headers={"User-Agent": ua},
            timeout=12,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        print(f"  [s2 doi] {doi}: {exc}", file=sys.stderr)
    return None


def _s2_by_title(title: str, ua: str) -> Optional[dict]:
    _S2_RATE.wait()
    try:
        r = _SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": title,
                "fields": "title,authors,year,venue,abstract,citationCount,externalIds",
                "limit": 1,
            },
            headers={"User-Agent": ua},
            timeout=12,
        )
        if r.status_code == 200:
            hits = r.json().get("data", [])
            return hits[0] if hits else None
    except Exception as exc:
        print(f"  [s2 title] {title[:60]}: {exc}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Schema normalisers
# ---------------------------------------------------------------------------

def _parse_crossref(cr: dict, doi: str, arxiv: Optional[str]) -> dict:
    title_list = cr.get("title") or []
    title = title_list[0] if title_list else "Unknown title"

    authors = []
    for a in cr.get("author") or []:
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    year = None
    for key in ("published-print", "published-online", "created"):
        dp = cr.get(key, {}).get("date-parts", [[None]])
        if dp and dp[0] and dp[0][0]:
            year = str(dp[0][0])
            break

    venues = cr.get("container-title") or []
    venue = venues[0] if venues else (cr.get("publisher") or "")

    abstract = cr.get("abstract") or ""
    abstract = JATS_TAG_RE.sub(" ", abstract)
    abstract = WHITESPACE_RE.sub(" ", abstract).strip()

    citations = cr.get("is-referenced-by-count")

    return {
        "_doi": doi,
        "_arxiv": arxiv,
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "abstract": abstract,
        "citations": citations,
    }


def _parse_s2(s2: dict, doi: Optional[str], arxiv: Optional[str]) -> dict:
    ext = s2.get("externalIds") or {}
    return {
        "_doi": doi or ext.get("DOI"),
        "_arxiv": arxiv or ext.get("ArXiv"),
        "title": s2.get("title") or "",
        "authors": [a["name"] for a in (s2.get("authors") or [])],
        "year": str(s2["year"]) if s2.get("year") else None,
        "venue": s2.get("venue") or "",
        "abstract": s2.get("abstract") or "",
        "citations": s2.get("citationCount"),
    }


def _make_record(data: dict, source_pdf: str) -> dict:
    doi = data.get("_doi")
    arxiv = data.get("_arxiv")

    if doi:
        paper_id = f"doi:{doi}"
    elif arxiv:
        paper_id = f"arxiv:{arxiv}"
    else:
        stem = Path(source_pdf).stem
        paper_id = f"pdf:{stem}"

    return {
        "id": paper_id,
        "doi": doi,
        "title": data.get("title", ""),
        "authors": data.get("authors", []),
        "year": data.get("year"),
        "venue": data.get("venue") or "",
        "citations": data.get("citations"),
        "abstract": data.get("abstract") or "",
        "url": f"https://doi.org/{doi}" if doi else None,
        "pdf_url": None,
        "sources": ["pdf"],
        "impact_score": None,
        "chase_type": None,
        "screening_status": None,
        "screening_score": None,
        "exclusion_reason": None,
        "notebooklm_batch": None,
        "notebooklm_source_id": None,
        "bibtex_key": None,
        "bibtex_status": None,
        "zotero_key": None,
        "_source_pdf": source_pdf,
    }


# ---------------------------------------------------------------------------
# Per-PDF processor
# ---------------------------------------------------------------------------

def _process_pdf(pdf_path: Path, ua: str) -> Optional[dict]:
    print(f"  {pdf_path.name}", flush=True)
    text = _extract_text(pdf_path)
    if not text.strip():
        print(f"    [skip] no text", file=sys.stderr)
        return None

    doi = _find_doi(text)
    arxiv = _find_arxiv(text)
    data = None

    if doi:
        cr = _crossref(doi, ua)
        if cr:
            data = _parse_crossref(cr, doi, arxiv)
            if not data["abstract"]:
                s2 = _s2_by_doi(doi, ua)
                if s2 and s2.get("abstract"):
                    data["abstract"] = s2["abstract"]
        else:
            s2 = _s2_by_doi(doi, ua)
            if s2:
                data = _parse_s2(s2, doi=doi, arxiv=arxiv)

    if not data:
        title = _extract_title(text)
        if title:
            s2 = _s2_by_title(title, ua)
            if s2:
                data = _parse_s2(s2, doi=doi, arxiv=arxiv)

    if not data:
        stem = pdf_path.stem
        print(f"    [stub] no metadata", file=sys.stderr)
        data = {
            "_doi": doi,
            "_arxiv": arxiv,
            "title": _extract_title(text) or stem,
            "authors": [],
            "year": None,
            "venue": "",
            "abstract": "",
            "citations": None,
        }

    # Abstract still missing → try extracting from PDF text directly
    if data and not data.get("abstract"):
        pdf_abstract = _extract_abstract_from_text(text)
        if pdf_abstract:
            data["abstract"] = pdf_abstract
            print(f"    [pdf abstract]", flush=True)

    return _make_record(data, pdf_path.name)


# ---------------------------------------------------------------------------
# Precache
# ---------------------------------------------------------------------------

def _precache(papers: list[dict], pdf_dir: Path, cache_path: Path) -> int:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            pass

    written = 0
    pdf_map = {p.name: p for p in pdf_dir.glob("*.pdf")}

    for paper in papers:
        pid = paper.get("id", "")
        if not pid or pid in cache:
            continue
        src = paper.get("_source_pdf")
        pdf_path = pdf_map.get(src)
        if not pdf_path:
            continue
        full_text = _extract_fulltext(pdf_path)
        if not full_text.strip():
            continue
        cache[pid] = {
            "full_text": full_text,
            "source": "local_pdf",
            "full_text_available": True,
            "fetch_reason": None,
            "publisher": None,
        }
        written += 1

    tmp = str(cache_path) + ".tmp"
    Path(tmp).write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    Path(tmp).replace(cache_path)
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract metadata from PDF directory → papers.json for lit-vault."
    )
    ap.add_argument("--pdf-dir", required=True, metavar="PATH",
                    help="Directory containing PDF files")
    ap.add_argument("--output", default="papers.json", metavar="PATH",
                    help="Output papers.json path (default: papers.json)")
    ap.add_argument("--email", default=None, metavar="EMAIL",
                    help="Contact email for CrossRef polite pool")
    ap.add_argument("--workers", type=int, default=1, metavar="N",
                    help="Parallel workers (default: 1; rate limits shared)")
    ap.add_argument("--manifest", default=None, metavar="TSV",
                    help="Optional TSV of entries missing abstract")
    ap.add_argument("--precache", action=argparse.BooleanOptionalAction, default=True,
                    help="Pre-populate lit-vault fulltext cache from local PDFs (default: on)")
    ap.add_argument("--cache-dir", default=None, metavar="DIR",
                    help="Cache dir override (default: ~/.cache/daimon/lit-vault/)")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    if not pdf_dir.is_dir():
        sys.exit(f"error: --pdf-dir not found: {pdf_dir}")

    output_path = Path(args.output).expanduser()
    ua = _make_ua(args.email)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"error: no PDFs found in {pdf_dir}")

    print(f"Found {len(pdfs)} PDFs in {pdf_dir}", flush=True)

    papers: list[dict] = []
    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(_process_pdf, p, ua): p for p in pdfs}
            for fut in as_completed(futs):
                result = fut.result()
                if result:
                    papers.append(result)
    else:
        for pdf in pdfs:
            result = _process_pdf(pdf, ua)
            if result:
                papers.append(result)

    # Build output
    now = datetime.now(timezone.utc).isoformat()
    output = {
        "meta": {
            "query": "pdf_import",
            "generated_at": now,
            "pdf_dir": str(pdf_dir),
            "total_found": len(papers),
            "after_dedup": len(papers),
            "sources_searched": ["pdf"],
            "sources_skipped": [],
            "domain": None,
            "sort": None,
        },
        "papers": papers,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(papers)} entries → {output_path}", flush=True)

    no_abstract = sum(1 for p in papers if not p.get("abstract"))
    no_doi = sum(1 for p in papers if not p.get("doi"))
    print(f"  No DOI:      {no_doi}/{len(papers)}")
    print(f"  No abstract: {no_abstract}/{len(papers)}")

    # Manifest of papers missing abstract
    if args.manifest and no_abstract:
        manifest_path = Path(args.manifest).expanduser()
        rows = [p for p in papers if not p.get("abstract")]
        with manifest_path.open("w") as f:
            f.write("id\tdoi\ttitle\tsource_pdf\n")
            for p in rows:
                f.write(f"{p['id']}\t{p.get('doi','')}\t{p.get('title','')}\t{p.get('_source_pdf','')}\n")
        print(f"  Manifest:    {manifest_path} ({len(rows)} rows)")

    # Pre-populate fulltext cache
    if args.precache:
        cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else Path.home() / ".cache/daimon/lit-vault"
        cache_path = cache_dir / "fulltext-cache.json"
        written = _precache(papers, pdf_dir, cache_path)
        print(f"  Precached:   {written} PDFs → {cache_path}")


if __name__ == "__main__":
    main()
