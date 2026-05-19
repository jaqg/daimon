#!/usr/bin/env python3
"""
lit-search --chase: citation graph expansion.

Given a paper (DOI / arXiv ID / URL / local PDF), returns citing and/or
cited-by papers as papers.json format.

Sources: Semantic Scholar (primary), OpenAlex, CrossRef.
WoS added when WOS_API_KEY is set.
PDF mode: extract references via PyMuPDF → resolve via CrossRef fuzzy search.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen, Request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Transport (shared with search.py; duplicated to keep scripts standalone)
# ---------------------------------------------------------------------------

def fetch(url, headers=None, timeout=30, retries=2):
    h = {"User-Agent": "daimon-lit-search/1.0 (research; mailto:daimon@example.com)"}
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
                time.sleep(2 ** attempt * 2)
                continue
            return None
        except Exception:
            return None
    return None

# ---------------------------------------------------------------------------
# ID resolution: DOI / arXiv from user input
# ---------------------------------------------------------------------------

def resolve_input(paper_str):
    """Return (arxiv_id, doi) from a DOI, arXiv ID, URL, or local PDF path."""
    # arXiv: bare ID like "2301.01234" or "cs/0612144"
    m = re.match(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+/\d{7})$", paper_str.strip())
    if m:
        return m.group(1).split("v")[0], None

    # arXiv URL
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/v]+)", paper_str)
    if m:
        return m.group(1), None

    # DOI: bare or URL
    m = re.search(r"10\.\d{4,}/\S+", paper_str)
    if m:
        return None, m.group(0).rstrip(".")

    # Local PDF
    p = Path(paper_str)
    if p.exists() and p.suffix.lower() == ".pdf":
        return None, None  # signal PDF mode to caller

    return None, None


def resolve_s2_id(arxiv_id=None, doi=None, api_key=None):
    """Get S2 paper ID for API calls."""
    h = {}
    if api_key:
        h["x-api-key"] = api_key
    if arxiv_id:
        url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=paperId,title"
    elif doi:
        url = f"https://api.semanticscholar.org/graph/v1/paper/{quote_plus(doi)}?fields=paperId,title"
    else:
        return None
    data = fetch(url, headers=h)
    if not data:
        return None
    try:
        return json.loads(data).get("paperId")
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Helpers (duplicated from search.py — scripts are standalone)
# ---------------------------------------------------------------------------

def _reconstruct_abstract(inverted_index):
    """Reconstruct plain-text abstract from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    try:
        pos_word = []
        for word, positions in inverted_index.items():
            for pos in positions:
                pos_word.append((pos, word))
        pos_word.sort()
        return " ".join(w for _, w in pos_word)[:800]
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# Citation fetch: Semantic Scholar
# ---------------------------------------------------------------------------

def s2_citations(s2_id, mode, api_key=None, limit=100):
    """mode: 'citations' (papers that cite this) or 'references' (papers cited by this)."""
    h = {}
    if api_key:
        h["x-api-key"] = api_key
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}/{mode}"
        f"?limit={limit}&fields=title,year,authors,externalIds,openAccessPdf,citationCount,venue,abstract"
    )
    data = fetch(url, headers=h, retries=2)
    if not data:
        return []
    try:
        items = json.loads(data).get("data") or []
    except Exception:
        return []

    papers = []
    for item in items:
        p = item.get("citingPaper") or item.get("citedPaper") or {}
        if not p.get("title"):
            continue
        ext = p.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        doi = ext.get("DOI")
        if not arxiv_id and not doi:
            continue

        oa = p.get("openAccessPdf") or {}
        oa_url = oa.get("url")
        authors = [a.get("name", "") for a in (p.get("authors") or [])[:5]]
        year = str(p.get("year") or "")

        if arxiv_id:
            url_ = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        elif oa_url:
            url_ = oa_url
            pdf_url = oa_url
        elif doi:
            url_ = f"https://doi.org/{doi}"
            pdf_url = None
        else:
            continue

        papers.append({
            "source": "semantic_scholar",
            "title": p.get("title", ""),
            "arxiv_id": arxiv_id,
            "doi": doi,
            "authors": authors,
            "year": year,
            "pub_date": year + "-01-01" if year else "",
            "abstract": (p.get("abstract") or "")[:800],
            "url": url_,
            "pdf_url": pdf_url,
            "citations": p.get("citationCount"),
            "venue": p.get("venue"),
        })
    return papers

# ---------------------------------------------------------------------------
# Citation fetch: OpenAlex
# ---------------------------------------------------------------------------

def openalex_citations(doi=None, arxiv_id=None, mode="both"):
    """mode: 'forward' (cites), 'backward' (references), 'both'."""
    papers = []

    # Resolve OpenAlex ID
    if doi:
        filter_val = f"doi:{doi}"
    elif arxiv_id:
        filter_val = f"ids.arxiv:{arxiv_id}"
    else:
        return papers

    id_url = f"https://api.openalex.org/works?filter={filter_val}&mailto=daimon@example.com"
    data = fetch(id_url)
    if not data:
        return papers
    try:
        results = json.loads(data).get("results", [])
    except Exception:
        return papers
    if not results:
        return papers

    work = results[0]
    oa_id = work.get("id", "").replace("https://openalex.org/", "")

    def _fetch_page(url):
        d = fetch(url)
        if not d:
            return []
        try:
            return json.loads(d).get("results", [])
        except Exception:
            return []

    def _parse_work(w):
        doi_url = w.get("doi") or ""
        d = doi_url.replace("https://doi.org/", "") if doi_url else None
        oa = w.get("open_access") or {}
        oa_url = oa.get("oa_url")
        ax_id = None
        for loc in (w.get("locations") or []):
            for field in ("landing_page_url", "pdf_url"):
                val = loc.get(field) or ""
                m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/v]+)", val)
                if m:
                    ax_id = m.group(1)
                    break
            if ax_id:
                break
        if not ax_id and not d:
            return None
        url_ = f"https://arxiv.org/abs/{ax_id}" if ax_id else (oa_url or doi_url or "")
        pdf_url = f"https://arxiv.org/pdf/{ax_id}" if ax_id else (oa_url if oa_url else None)
        pub_date = w.get("publication_date") or ""
        authors = []
        for a in (w.get("authorships") or [])[:5]:
            name = (a.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)
        return {
            "source": "openalex",
            "title": w.get("title") or "",
            "arxiv_id": ax_id,
            "doi": d,
            "authors": authors,
            "year": pub_date[:4],
            "pub_date": pub_date,
            "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
            "url": url_,
            "pdf_url": pdf_url,
            "citations": w.get("cited_by_count"),
            "venue": None,
        }

    if mode in ("forward", "both"):
        # Works that cite this work
        cited_by_url = (
            f"https://api.openalex.org/works?filter=cites:{oa_id}"
            f"&per-page=100&mailto=daimon@example.com"
        )
        for w in _fetch_page(cited_by_url):
            p = _parse_work(w)
            if p:
                papers.append(p)

    if mode in ("backward", "both"):
        # References of this work (embedded in the work record)
        refs = work.get("referenced_works") or []
        if refs:
            ids_str = "|".join(r.replace("https://openalex.org/", "") for r in refs[:200])
            refs_url = (
                f"https://api.openalex.org/works?filter=openalex:{ids_str}"
                f"&per-page=200&mailto=daimon@example.com"
            )
            for w in _fetch_page(refs_url):
                p = _parse_work(w)
                if p:
                    papers.append(p)

    return papers

# ---------------------------------------------------------------------------
# PDF reference extraction via PyMuPDF
# ---------------------------------------------------------------------------

def extract_refs_from_pdf(pdf_path):
    """Extract reference strings from a local PDF. Returns list of strings."""
    try:
        import fitz  # pymupdf
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install pymupdf", file=sys.stderr)
        return []

    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    # Find the reference section heuristically
    ref_section = re.search(
        r"(?i)(?:references|bibliography|works cited)\s*\n(.*)",
        text,
        re.DOTALL,
    )
    if ref_section:
        text = ref_section.group(1)

    # Split into individual references (numbered or unnumbered)
    refs = re.split(r"\n(?:\[\d+\]|\d+\.)\s+", text)
    refs = [r.replace("\n", " ").strip() for r in refs if len(r.strip()) > 40]
    return refs[:300]


def resolve_ref_via_crossref(ref_str, confidence_threshold=80):
    """Resolve a reference string to DOI via CrossRef fuzzy search.
    Returns (doi, title, confidence) or None."""
    url = (
        f"https://api.crossref.org/works"
        f"?query.bibliographic={quote_plus(ref_str[:300])}&rows=1"
        f"&mailto=daimon@example.com"
    )
    data = fetch(url)
    if not data:
        return None
    try:
        items = json.loads(data).get("message", {}).get("items", [])
    except Exception:
        return None
    if not items:
        return None
    item = items[0]
    score = item.get("score", 0)
    doi = item.get("DOI")
    title_list = item.get("title") or []
    title = title_list[0] if title_list else ""
    if score >= confidence_threshold and doi:
        return doi, title, score
    return None


def pdf_chase(pdf_path, mode="backward"):
    """Extract references from PDF and resolve to DOI/arXiv records."""
    refs = extract_refs_from_pdf(pdf_path)
    if not refs:
        print("WARNING: No references extracted from PDF.", file=sys.stderr)
        return [], []

    print(f"Extracted {len(refs)} reference strings. Resolving via CrossRef...", file=sys.stderr)
    resolved = []
    manual_check = []

    for i, ref in enumerate(refs, 1):
        result = resolve_ref_via_crossref(ref)
        if result:
            doi, title, score = result
            # Fetch metadata for this DOI
            meta_url = f"https://api.crossref.org/works/{quote_plus(doi)}?mailto=daimon@example.com"
            meta_data = fetch(meta_url)
            paper = {"source": "crossref", "doi": doi, "title": title, "arxiv_id": None,
                     "authors": [], "year": "", "pub_date": "", "abstract": "", "venue": None,
                     "url": f"https://doi.org/{doi}", "pdf_url": None, "citations": None}
            if meta_data:
                try:
                    m = json.loads(meta_data).get("message", {})
                    authors = []
                    for a in (m.get("author") or [])[:5]:
                        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                        if name:
                            authors.append(name)
                    paper["authors"] = authors
                    dates = m.get("published-print") or m.get("published-online") or {}
                    parts = dates.get("date-parts", [[]])[0]
                    paper["year"] = str(parts[0]) if parts else ""
                    paper["pub_date"] = "-".join(str(x) for x in parts[:3]) if parts else ""
                    paper["venue"] = (m.get("container-title") or [""])[0]
                    paper["citations"] = m.get("is-referenced-by-count")
                    t_list = m.get("title") or []
                    if t_list:
                        paper["title"] = t_list[0]
                except Exception:
                    pass
            resolved.append(paper)
        else:
            manual_check.append(ref[:120])

        # Rate limit: CrossRef allows ~50 req/s politely
        if i % 10 == 0:
            time.sleep(0.5)

    return resolved, manual_check

# ---------------------------------------------------------------------------
# Dedup and output (mirrors search.py)
# ---------------------------------------------------------------------------

def _canonical_id(p):
    if p.get("arxiv_id"):
        return f"arxiv:{p['arxiv_id']}"
    if p.get("doi"):
        return f"doi:{p['doi']}"
    return None


def _impact_score(p):
    cites = p.get("citations")
    if cites is None:
        return 0.0
    try:
        age = max(__import__("datetime").datetime.now().year - int((p.get("year") or "2000")) + 1, 1)
    except Exception:
        age = 1
    return cites / age


def deduplicate_chase(papers, max_results=200):
    seen = {}
    unique = []
    for p in papers:
        cid = _canonical_id(p)
        if cid and cid in seen:
            existing = seen[cid]
            if existing.get("citations") is None and p.get("citations") is not None:
                existing["citations"] = p["citations"]
            continue
        if cid:
            seen[cid] = p
        unique.append(p)
    unique.sort(key=_impact_score, reverse=True)
    return unique[:max_results]


def to_papers_json(papers, source_paper_id, mode, sources_searched, sources_skipped):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for p in papers:
        cid = _canonical_id(p) or f"unknown:{p.get('title', '')[:30]}"
        chase_type = p.get("_chase_type") or ("citing" if mode == "forward" else "cited_by" if mode == "backward" else None)
        records.append({
            "id": cid,
            "doi": p.get("doi"),
            "title": p.get("title", ""),
            "authors": p.get("authors", []),
            "year": p.get("year"),
            "venue": p.get("venue"),
            "citations": p.get("citations"),
            "abstract": p.get("abstract") or "",
            "url": p.get("url"),
            "pdf_url": p.get("pdf_url"),
            "sources": [p.get("source", "")],
            "impact_score": round(_impact_score(p), 2) if p.get("citations") is not None else None,
            "chase_type": chase_type,
            "screening_status": "pending",
            "screening_score": None,
            "exclusion_reason": None,
            "notebooklm_batch": None,
            "notebooklm_source_id": None,
            "bibtex_key": None,
            "bibtex_status": None,
            "zotero_key": None,
        })
    return {
        "meta": {
            "query": f"chase:{source_paper_id}",
            "generated_at": now,
            "sources_searched": sorted(sources_searched),
            "sources_skipped": sorted(sources_skipped),
            "total_found": len(records),
            "after_dedup": len(records),
            "chase_source": source_paper_id,
            "chase_mode": mode,
        },
        "papers": records,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="lit-search --chase: citation graph expansion")
    parser.add_argument("paper", help="DOI, arXiv ID, URL, or local PDF path")
    parser.add_argument("--mode", choices=["forward", "backward", "both"], default="both",
                        help="forward=papers citing this; backward=references; both (default)")
    parser.add_argument("--results", type=int, default=100)
    parser.add_argument("--output", default=None, help="Save papers.json to this path")
    parser.add_argument("--append", default=None, help="Merge into existing papers.json")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None
    wos_key = os.environ.get("WOS_API_KEY") or None

    # Detect PDF mode
    paper_path = Path(args.paper)
    if paper_path.exists() and paper_path.suffix.lower() == ".pdf":
        print(f"PDF mode: extracting references from {paper_path}", file=sys.stderr)
        resolved, manual_check = pdf_chase(str(paper_path), mode=args.mode)
        if manual_check:
            print(f"\nCould not resolve {len(manual_check)} references (manual check needed):", file=sys.stderr)
            for ref in manual_check[:10]:
                print(f"  - {ref}", file=sys.stderr)
            if len(manual_check) > 10:
                print(f"  ... and {len(manual_check)-10} more", file=sys.stderr)
        papers = deduplicate_chase(resolved, args.results)
        sources_searched = ["crossref", "pymupdf"]
        sources_skipped = []
        source_id = str(paper_path)
    else:
        arxiv_id, doi = resolve_input(args.paper)
        if not arxiv_id and not doi:
            print(f"ERROR: Could not parse '{args.paper}' as DOI, arXiv ID, URL, or PDF path.", file=sys.stderr)
            sys.exit(1)

        source_id = f"arxiv:{arxiv_id}" if arxiv_id else f"doi:{doi}"
        print(f"Resolving citation graph for {source_id} (mode={args.mode})...", file=sys.stderr)

        # Verify source paper resolves
        s2_id = resolve_s2_id(arxiv_id, doi, s2_key)
        if not s2_id:
            print(f"WARNING: Could not resolve {source_id} in Semantic Scholar. Trying OpenAlex only.", file=sys.stderr)

        all_papers = []
        sources_searched = []
        sources_skipped = []

        if s2_id:
            sources_searched.append("semantic_scholar")
            if args.mode in ("forward", "both"):
                cites = s2_citations(s2_id, "citations", s2_key, args.results)
                for p in cites:
                    p["_chase_type"] = "citing"
                all_papers.extend(cites)
            if args.mode in ("backward", "both"):
                refs = s2_citations(s2_id, "references", s2_key, args.results)
                for p in refs:
                    p["_chase_type"] = "cited_by"
                all_papers.extend(refs)
        else:
            sources_skipped.append("semantic_scholar")

        # OpenAlex
        try:
            oa_papers = openalex_citations(doi, arxiv_id, args.mode)
            for p in oa_papers:
                p["_chase_type"] = "citing" if args.mode == "forward" else "cited_by"
            all_papers.extend(oa_papers)
            sources_searched.append("openalex")
        except Exception as e:
            print(f"WARNING: OpenAlex chase failed: {e}", file=sys.stderr)
            sources_skipped.append("openalex")

        if wos_key:
            sources_skipped.append("wos")  # WoS bulk chase not yet implemented
            print("NOTE: WoS API key found but WoS citation chase not yet implemented.", file=sys.stderr)

        papers = deduplicate_chase(all_papers, args.results)
        print(f"Chase complete: {len(papers)} unique papers found.", file=sys.stderr)

    data = to_papers_json(papers, source_id, args.mode, sources_searched, sources_skipped)

    if args.append:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts"))
        try:
            import papers_io
            base = papers_io.load(args.append)
            added = papers_io.merge(base, data)
            papers_io.save(base, args.append)
            print(f"Merged: {added} new papers into {args.append}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: --append failed: {e}", file=sys.stderr)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved: {out}", file=sys.stderr)

    if args.json_out or (not args.output and not args.append):
        print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
