#!/usr/bin/env python3
"""
lit-search: multi-database paper search for the daimon literature suite.

Extends sci-lit-pipeline/scripts/search.py with:
  - papers.json output format
  - --domain profiles (comp-chem, ml, physics, bio)
  - PubMed, WoS, Scopus adapters (key-gated)
  - --append to merge into existing papers.json
  - Security: coverage statement, source-diversity warning, recency-bias warning
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _fetch_post(url, data, headers=None, timeout=30):
    h = {"User-Agent": "daimon-lit-search/1.0 (research tool; mailto:daimon@example.com)"}
    if headers:
        h.update(headers)
    encoded = data.encode("utf-8") if isinstance(data, str) else data
    req = Request(url, data=encoded, headers=h)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8"), 200
    except URLError as e:
        code = getattr(e, "code", None)
        return None, code
    except Exception:
        return None, None


def fetch(url, headers=None, timeout=30, retries=2, api_key_header=None, api_key=None):
    h = {"User-Agent": "daimon-lit-search/1.0 (research tool; mailto:daimon@example.com)"}
    if headers:
        h.update(headers)
    if api_key_header and api_key:
        h[api_key_header] = api_key
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
# Domain profiles: query hints added to keyword searches
# ---------------------------------------------------------------------------

DOMAIN_PROFILES = {
    "general": {"arxiv_cats": [], "venue_hints": [], "query_suffix": ""},
    "comp-chem": {
        "arxiv_cats": ["physics.chem-ph", "physics.comp-ph", "quant-ph"],
        "venue_hints": ["JCTC", "JCP", "PCCP", "J. Chem. Theory Comput.", "Phys. Chem. Chem. Phys."],
        "query_suffix": "",
    },
    "ml": {
        "arxiv_cats": ["cs.LG", "cs.AI", "stat.ML"],
        "venue_hints": ["NeurIPS", "ICML", "ICLR", "JMLR"],
        "query_suffix": "",
    },
    "physics": {
        "arxiv_cats": ["cond-mat", "physics", "quant-ph", "hep-th"],
        "venue_hints": ["PRL", "PRB", "Phys. Rev. Lett.", "Phys. Rev. B"],
        "query_suffix": "",
    },
    "bio": {
        "arxiv_cats": ["q-bio", "cs.CE"],
        "venue_hints": ["Nature", "Science", "Cell", "PNAS", "JACS"],
        "query_suffix": "",
    },
}

# ---------------------------------------------------------------------------
# Source: arXiv
# ---------------------------------------------------------------------------

def search_arxiv(query, max_results, from_date=None, to_date=None, domain="general"):
    papers = []
    date_filter = ""
    if from_date or to_date:
        fd = from_date.replace("-", "") + "000000" if from_date else "19910101000000"
        td = to_date.replace("-", "") + "235959" if to_date else "*"
        date_filter = f"+AND+submittedDate:[{fd}+TO+{td}]"

    cats = DOMAIN_PROFILES.get(domain, {}).get("arxiv_cats", [])
    cat_filter = ""
    if cats:
        cat_terms = "+OR+".join(f"cat:{c}" for c in cats)
        cat_filter = f"+AND+({cat_terms})"

    url = (
        f"https://export.arxiv.org/api/query?"
        f"search_query=all:{quote_plus(query)}{date_filter}{cat_filter}"
        f"&max_results={max_results}&sortBy=relevance&sortOrder=descending"
    )
    data = fetch(url, timeout=45)
    if not data:
        return papers

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return papers

    for entry in root.findall("atom:entry", ns):
        id_el = entry.find("atom:id", ns)
        if id_el is None:
            continue
        m = re.search(r"arxiv\.org/abs/([^v\s]+)", id_el.text or "")
        if not m:
            continue
        arxiv_id = m.group(1).strip()

        title_el = entry.find("atom:title", ns)
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""
        summary_el = entry.find("atom:summary", ns)
        abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
        pub_el = entry.find("atom:published", ns)
        pub_date = (pub_el.text or "")[:10] if pub_el is not None else ""
        authors = []
        for a in entry.findall("atom:author", ns):
            name_el = a.find("atom:name", ns)
            if name_el is not None:
                authors.append(name_el.text.strip())

        # Journal ref (venue)
        jref = entry.find("{http://arxiv.org/schemas/atom}journal_ref", ns)
        venue = jref.text.strip() if jref is not None and jref.text else None

        papers.append({
            "source": "arxiv",
            "title": title,
            "arxiv_id": arxiv_id,
            "doi": None,
            "authors": authors[:5],
            "year": pub_date[:4],
            "pub_date": pub_date,
            "abstract": abstract[:800],
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "citations": None,
            "venue": venue,
        })
    return papers

# ---------------------------------------------------------------------------
# Source: Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(query, max_results, from_date=None, to_date=None, api_key=None):
    papers = []
    year_filter = ""
    if from_date or to_date:
        fy = from_date[:4] if from_date else ""
        ty = to_date[:4] if to_date else ""
        if fy and ty:
            year_filter = f"&year={fy}-{ty}"
        elif fy:
            year_filter = f"&year={fy}-"
        elif ty:
            year_filter = f"&year=-{ty}"

    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote_plus(query)}&limit={min(max_results, 100)}"
        f"&fields=title,year,authors,externalIds,openAccessPdf,abstract,citationCount,venue,publicationVenue"
        f"{year_filter}"
    )
    h = {}
    if api_key:
        h["x-api-key"] = api_key
    data = fetch(url, headers=h, retries=2)
    if not data:
        return papers
    try:
        result = json.loads(data)
    except json.JSONDecodeError:
        return papers

    for p in result.get("data", []):
        ext = p.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        doi = ext.get("DOI")
        oa = p.get("openAccessPdf") or {}
        oa_url = oa.get("url")
        authors = [a.get("name", "") for a in (p.get("authors") or [])[:5]]
        year = str(p.get("year") or "")

        if arxiv_id:
            best_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        elif oa_url:
            best_url = oa_url
            pdf_url = oa_url
        elif doi:
            best_url = f"https://doi.org/{doi}"
            pdf_url = None
        else:
            continue

        venue = p.get("venue") or (p.get("publicationVenue") or {}).get("name")

        papers.append({
            "source": "semantic_scholar",
            "title": p.get("title", ""),
            "arxiv_id": arxiv_id,
            "doi": doi,
            "authors": authors,
            "year": year,
            "pub_date": year + "-01-01" if year else "",
            "abstract": (p.get("abstract") or "")[:800],
            "url": best_url,
            "pdf_url": pdf_url,
            "citations": p.get("citationCount"),
            "venue": venue,
        })
    return papers

# ---------------------------------------------------------------------------
# Helpers
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
# Source: OpenAlex
# ---------------------------------------------------------------------------

def search_openalex(query, max_results, from_date=None, to_date=None):
    papers = []
    filters = []
    if from_date:
        filters.append(f"from_publication_date:{from_date}")
    if to_date:
        filters.append(f"to_publication_date:{to_date}")
    filter_param = f"&filter={','.join(filters)}" if filters else ""

    url = (
        f"https://api.openalex.org/works"
        f"?search={quote_plus(query)}&per-page={min(max_results, 200)}"
        f"&sort=relevance_score:desc"
        f"{filter_param}"
        f"&mailto=daimon@example.com"
    )
    data = fetch(url)
    if not data:
        return papers
    try:
        result = json.loads(data)
    except json.JSONDecodeError:
        return papers

    for w in result.get("results", []):
        doi_url = w.get("doi") or ""
        doi_short = doi_url.replace("https://doi.org/", "") if doi_url else None
        oa = w.get("open_access") or {}
        oa_url = oa.get("oa_url")

        arxiv_id = None
        for loc in (w.get("locations") or []):
            for field in ("landing_page_url", "pdf_url"):
                val = loc.get(field) or ""
                m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/v]+)", val)
                if m:
                    arxiv_id = m.group(1)
                    break
            if arxiv_id:
                break

        if arxiv_id:
            best_url = f"https://arxiv.org/abs/{arxiv_id}"
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        elif oa_url:
            best_url = oa_url
            pdf_url = oa_url
        elif doi_url:
            best_url = doi_url
            pdf_url = None
        else:
            continue

        pub_date = w.get("publication_date") or ""
        authors = []
        for a in (w.get("authorships") or [])[:5]:
            name = (a.get("author") or {}).get("display_name", "")
            if name:
                authors.append(name)

        venue = (w.get("primary_location") or {}).get("source", {})
        venue_name = (venue or {}).get("display_name") if isinstance(venue, dict) else None

        abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
        papers.append({
            "source": "openalex",
            "title": w.get("title") or "",
            "arxiv_id": arxiv_id,
            "doi": doi_short,
            "authors": authors,
            "year": pub_date[:4],
            "pub_date": pub_date,
            "abstract": abstract,
            "url": best_url,
            "pdf_url": pdf_url,
            "citations": w.get("cited_by_count"),
            "venue": venue_name,
        })
    return papers

# ---------------------------------------------------------------------------
# Source: ChemRxiv
# ---------------------------------------------------------------------------

def search_chemrxiv(query, max_results, from_date=None, to_date=None):
    papers = []
    url = (
        f"https://chemrxiv.org/engage/chemrxiv/search-results"
        f"?text={quote_plus(query)}&sort=relevant&itemsPerPage={min(max_results, 50)}&pageNumber=0"
    )
    data = fetch(url, headers={"Accept": "application/json"})
    if not data:
        return papers
    try:
        result = json.loads(data)
    except json.JSONDecodeError:
        return papers

    for item in result.get("itemHits", []):
        p = item.get("item") or {}
        title = (p.get("title") or "").strip()
        doi = p.get("doi") or ""
        if not doi:
            continue

        pub_date = p.get("publishedDate") or p.get("statusDate") or ""
        year = pub_date[:4]
        if from_date and pub_date and pub_date < from_date:
            continue
        if to_date and pub_date and pub_date > to_date:
            continue

        authors = []
        for a in (p.get("authors") or [])[:5]:
            name = (a.get("firstName", "") + " " + a.get("lastName", "")).strip()
            if name:
                authors.append(name)

        abstract = re.sub(r"<[^>]+>", "", p.get("abstract") or "")[:800]

        pdf_url = None
        orig = (p.get("asset") or {}).get("original") or {}
        if orig.get("mimeType") == "application/pdf":
            pdf_url = orig.get("url")

        papers.append({
            "source": "chemrxiv",
            "title": title,
            "arxiv_id": None,
            "doi": doi,
            "authors": authors,
            "year": year,
            "pub_date": pub_date,
            "abstract": abstract,
            "url": f"https://doi.org/{doi}",
            "pdf_url": pdf_url,
            "citations": None,
            "venue": "ChemRxiv",
        })
    return papers

# ---------------------------------------------------------------------------
# Source: PubMed (key-gated for higher rate limits; free otherwise)
# ---------------------------------------------------------------------------

def search_pubmed(query, max_results, from_date=None, to_date=None, api_key=None):
    papers = []
    date_param = ""
    if from_date:
        date_param += f"&mindate={from_date.replace('-', '/')}"
    if to_date:
        date_param += f"&maxdate={to_date.replace('-', '/')}"
    key_param = f"&api_key={api_key}" if api_key else ""

    search_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={quote_plus(query)}&retmax={min(max_results, 200)}"
        f"&retmode=json&sort=relevance{date_param}{key_param}"
    )
    data = fetch(search_url)
    if not data:
        return papers
    try:
        ids = json.loads(data).get("esearchresult", {}).get("idlist", [])
    except Exception:
        return papers
    if not ids:
        return papers

    # Fetch summaries in bulk
    ids_str = ",".join(ids[:max_results])
    summary_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&id={ids_str}&retmode=json{key_param}"
    )
    sdata = fetch(summary_url)
    if not sdata:
        return papers
    try:
        result = json.loads(sdata).get("result", {})
    except Exception:
        return papers

    # Fetch abstracts via efetch (esummary doesn't include abstract text)
    abstracts = {}
    fetch_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={ids_str}&rettype=abstract&retmode=xml{key_param}"
    )
    fdata = fetch(fetch_url)
    if fdata:
        try:
            root = ET.fromstring(fdata)
            for article in root.iter("PubmedArticle"):
                pmid_el = article.find(".//PMID")
                uid_key = pmid_el.text.strip() if pmid_el is not None else None
                if not uid_key:
                    continue
                parts = []
                for ab_el in article.findall(".//AbstractText"):
                    label = ab_el.get("Label")
                    text = (ab_el.text or "").strip()
                    if label and text:
                        parts.append(f"{label}: {text}")
                    elif text:
                        parts.append(text)
                if parts:
                    abstracts[uid_key] = " ".join(parts)[:800]
        except Exception:
            pass

    for uid in ids:
        p = result.get(uid) or {}
        title = p.get("title", "").strip()
        if not title:
            continue
        doi = None
        for art in p.get("articleids", []):
            if art.get("idtype") == "doi":
                doi = art.get("value")
        pub_date = p.get("pubdate", "")
        year = pub_date[:4]
        authors = [a.get("name", "") for a in (p.get("authors") or [])[:5]]
        venue = p.get("fulljournalname") or p.get("source") or None
        url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"

        papers.append({
            "source": "pubmed",
            "title": title,
            "arxiv_id": None,
            "doi": doi,
            "authors": authors,
            "year": year,
            "pub_date": pub_date,
            "abstract": abstracts.get(uid, ""),
            "url": url,
            "pdf_url": None,
            "citations": None,
            "venue": venue,
        })
    return papers

# ---------------------------------------------------------------------------
# Source: Web of Science (session-based fallback — no API key needed)
# ---------------------------------------------------------------------------

def search_wos_session(query, max_results, from_date=None, to_date=None, sid=None):
    """Search WoS via internal runQuerySearch API using a browser session SID.

    Requires WOS_SESSION_ID from config.local — extract from browser DevTools
    (Network tab → any webofscience.com request → Request Headers → Cookie → SID=<value>).
    Max 50 results per request (internal API limit). SID expires with browser session.
    """
    if not sid:
        return []

    url = f"https://www.webofscience.com/api/wosnx/core/runQuerySearch?SID={sid}"
    body = json.dumps({
        "product": "WOSCC",
        "search": {
            "query": [{"rowField": "TS", "rowText": query}],
        },
        "retrieve": {
            "count": min(max_results, 50),  # internal API max = 50
            "sortMethod": "relevance",
        },
        "searchMode": "general",
        "viewType": "search",
        "serviceMode": "summary",
    })

    raw, code = _fetch_post(
        url, body,
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "application/x-ndjson",
        },
    )

    if raw is None:
        if code in (401, 403):
            print(
                "WARNING: WoS session ID expired or invalid. "
                "Re-extract WOS_SESSION_ID in config.local: "
                "Chrome DevTools → Network → any webofscience.com request → Cookie: SID=<value>",
                file=sys.stderr,
            )
        elif code is not None:
            print(f"WARNING: WoS session search returned HTTP {code}.", file=sys.stderr)
        return []

    papers = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        records_data = obj.get("records")
        if not isinstance(records_data, dict):
            continue

        for _idx, rec in records_data.items():
            if not isinstance(rec, dict):
                continue

            # Title
            try:
                title = rec["titles"]["item"]["en"][0]["title"]
            except (KeyError, IndexError, TypeError):
                title = ""
            if not title:
                continue

            # Venue/journal
            try:
                venue = rec["titles"]["source"]["en"][0]["title"]
            except (KeyError, IndexError, TypeError):
                venue = None

            # Authors (wos_standard = "Last, F." format)
            authors = []
            try:
                for a in (rec["names"]["author"]["en"] or [])[:5]:
                    name = a.get("wos_standard") or a.get("full_name") or ""
                    if name:
                        authors.append(name)
            except (KeyError, TypeError):
                pass

            # Year
            try:
                year = str(rec["pub_info"]["pubyear"])
            except (KeyError, TypeError):
                year = ""

            # Date filter (year-level)
            if from_date and year and year < from_date[:4]:
                continue
            if to_date and year and year > to_date[:4]:
                continue

            # DOI
            doi = (rec.get("doi") or "").strip() or None

            # Citations (WoS Core Collection count)
            try:
                citations = rec["citation_related"]["counts"]["WOSCC"]
            except (KeyError, TypeError):
                citations = None

            # Abstract
            try:
                abstract = rec["abstract"]["basic"]["en"]["abstract"]
            except (KeyError, TypeError):
                abstract = ""

            # URL — prefer DOI, fall back to WoS record page
            wos_id = rec.get("colluid", "")
            if doi:
                paper_url = f"https://doi.org/{doi}"
            elif wos_id:
                paper_url = f"https://www.webofscience.com/wos/woscc/full-record/{wos_id}"
            else:
                paper_url = None

            papers.append({
                "source": "wos_session",
                "title": title,
                "arxiv_id": None,
                "doi": doi,
                "authors": authors,
                "year": year,
                "pub_date": year + "-01-01" if year else "",
                "abstract": (abstract or "")[:800],
                "url": paper_url,
                "pdf_url": None,
                "citations": citations,
                "venue": venue,
            })

    return papers


# ---------------------------------------------------------------------------
# Deduplication and scoring
# ---------------------------------------------------------------------------

def _impact_score(p):
    cites = p.get("citations")
    if cites is None:
        return 0.0
    year_str = (p.get("pub_date") or p.get("year") or "")[:4]
    try:
        age = max(datetime.now().year - int(year_str) + 1, 1)
    except ValueError:
        age = 1
    return cites / age


def _canonical_id(p):
    if p.get("arxiv_id"):
        return f"arxiv:{p['arxiv_id']}"
    if p.get("doi"):
        return f"doi:{p['doi']}"
    return None


def deduplicate(all_papers, max_results, sort_by="impact", min_citations=0):
    if min_citations > 0:
        all_papers = [
            p for p in all_papers
            if p.get("citations") is None or p.get("citations", 0) >= min_citations
        ]

    priority = {"arxiv": 0, "semantic_scholar": 1, "openalex": 2, "chemrxiv": 3, "pubmed": 4, "wos_session": 5}
    all_papers.sort(key=lambda p: priority.get(p["source"], 9))

    seen = {}
    unique = []
    for p in all_papers:
        cid = _canonical_id(p)
        if cid and cid in seen:
            existing = seen[cid]
            if existing.get("citations") is None and p.get("citations") is not None:
                existing["citations"] = p["citations"]
            existing.setdefault("_sources", set()).add(p["source"])
            continue
        p["_sources"] = {p["source"]}
        if cid:
            seen[cid] = p
        unique.append(p)

    if sort_by == "impact":
        unique.sort(key=_impact_score, reverse=True)
    elif sort_by == "citations":
        unique.sort(key=lambda p: p.get("citations") or 0, reverse=True)
    elif sort_by == "recency":
        unique.sort(key=lambda p: p.get("pub_date") or p.get("year") or "0000", reverse=True)

    return unique[:max_results]

# ---------------------------------------------------------------------------
# Security checks
# ---------------------------------------------------------------------------

def check_source_diversity(papers):
    if not papers:
        return
    from collections import Counter
    counts = Counter(p["source"] for p in papers)
    total = len(papers)
    for src, n in counts.items():
        if n / total > 0.80:
            print(
                f"WARNING: Source diversity — {n}/{total} papers ({n*100//total}%) from {src}. "
                "Results may not be representative.",
                file=sys.stderr,
            )


def check_recency_bias(papers, from_date):
    if from_date or not papers:
        return
    current_year = datetime.now().year
    recent = sum(1 for p in papers if (p.get("year") or "0000") >= str(current_year - 2))
    if recent / len(papers) > 0.70:
        print(
            f"WARNING: Recency bias — {recent}/{len(papers)} papers are from the last 2 years. "
            "Consider --months or --from-date to broaden the time window.",
            file=sys.stderr,
        )

# ---------------------------------------------------------------------------
# Output: papers.json format
# ---------------------------------------------------------------------------

def to_papers_json(papers, query, sources_searched, sources_skipped, domain, from_date, to_date, sort_by):
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for p in papers:
        cid = _canonical_id(p) or f"unknown:{p.get('title', '')[:30]}"
        rec = {
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
            "sources": sorted(p.get("_sources", {p.get("source", "")})),
            "impact_score": round(_impact_score(p), 2) if p.get("citations") is not None else None,
            "chase_type": None,
            "screening_status": "pending",
            "screening_score": None,
            "exclusion_reason": None,
            "notebooklm_batch": None,
            "notebooklm_source_id": None,
            "bibtex_key": None,
            "bibtex_status": None,
            "zotero_key": None,
        }
        records.append(rec)

    meta_obj = {
        "query": query,
        "generated_at": now,
        "sources_searched": sorted(sources_searched),
        "sources_skipped": sorted(sources_skipped),
        "total_found": len(papers),
        "after_dedup": len(records),
        "domain": domain,
        "sort": sort_by,
    }
    if from_date:
        meta_obj["from_date"] = from_date
    if to_date:
        meta_obj["to_date"] = to_date

    return {"meta": meta_obj, "papers": records}


def format_text(papers, query, sort_by="impact"):
    lines = [
        f"SEARCH RESULTS: {query}",
        f"Papers: {len(papers)} | Sort: {sort_by}",
        "=" * 60,
        "",
    ]
    for i, p in enumerate(papers, 1):
        auths = p.get("authors", [])[:3]
        auth_str = ", ".join(auths) + (" et al." if len(p.get("authors", [])) > 3 else "")
        lines.append(f"{i}. {p.get('title', '')}")
        lines.append(f"   Authors: {auth_str}")
        cites = p.get("citations")
        score = p.get("impact_score") or (_impact_score(p) if cites is not None else None)
        impact_str = f" | Impact: {score:.1f}/yr" if score is not None else ""
        cite_str = f" | Citations: {cites}" if cites is not None else ""
        srcs = ", ".join(sorted(p.get("_sources", {p.get("source", "")})))
        lines.append(f"   Year: {p.get('year', '?')} | Source(s): {srcs}{cite_str}{impact_str}")
        if p.get("venue"):
            lines.append(f"   Venue: {p['venue']}")
        if p.get("id", "").startswith("arxiv:"):
            lines.append(f"   arXiv: {p['id'].replace('arxiv:', '')}")
        if p.get("doi"):
            lines.append(f"   DOI: {p['doi']}")
        lines.append(f"   URL: {p.get('url', '')}")
        if p.get("abstract"):
            snippet = p["abstract"][:250]
            lines.append(f"   Abstract: {snippet}{'...' if len(p['abstract']) > 250 else ''}")
        lines.append("")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="lit-search: multi-database paper search"
    )
    parser.add_argument("query", help="Research topic / search query")
    parser.add_argument("--results", type=int, default=20)
    parser.add_argument("--months", type=int, default=0)
    parser.add_argument("--from-date", dest="from_date", metavar="YYYY-MM-DD")
    parser.add_argument("--to-date", dest="to_date", metavar="YYYY-MM-DD")
    parser.add_argument("--sort", choices=["impact", "citations", "recency", "relevance"], default="impact")
    parser.add_argument("--min-citations", type=int, default=0, dest="min_citations")
    parser.add_argument("--domain", choices=list(DOMAIN_PROFILES), default="general")
    parser.add_argument("--sources", default="arxiv,semantic_scholar,openalex,chemrxiv")
    parser.add_argument("--output", default=None, help="Save papers.json to this path")
    parser.add_argument("--append", default=None, help="Merge into existing papers.json")
    parser.add_argument("--text", action="store_true", help="Also print human-readable summary")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Print papers.json to stdout")
    args = parser.parse_args()

    max_results = min(max(args.results, 1), 200)
    per_source = max(max_results * 2, 30)
    requested_sources = {s.strip() for s in args.sources.split(",")}

    from_date = args.from_date
    to_date = args.to_date
    if not from_date and args.months > 0:
        cutoff = datetime.now() - timedelta(days=args.months * 30)
        from_date = cutoff.strftime("%Y-%m-%d")

    # Read optional API keys from environment (sourced from config.local)
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None
    ncbi_key = os.environ.get("NCBI_API_KEY") or None
    wos_key = os.environ.get("WOS_API_KEY") or None
    wos_session_id = os.environ.get("WOS_SESSION_ID") or None
    scopus_key = os.environ.get("SCOPUS_API_KEY") or None

    # Determine which sources are available
    available = {"arxiv", "semantic_scholar", "openalex", "chemrxiv"}
    if ncbi_key or "pubmed" in requested_sources:
        available.add("pubmed")
    # WoS session fallback: auto-activate when SID present; no browser dep needed at search time
    if wos_session_id:
        available.add("wos_session")
        requested_sources.add("wos_session")
    elif "wos_session" in requested_sources:
        # requested but no SID — treat as key-gated so it shows up in skipped list
        pass  # handled below
    # WoS official API and Scopus: chase-only for now (no bulk keyword search without full subscription)
    key_gated = set()
    if "wos" in requested_sources and not wos_key:
        key_gated.add("wos")
    if "wos_session" in requested_sources and not wos_session_id:
        key_gated.add("wos_session")
    if "scopus" in requested_sources and not scopus_key:
        key_gated.add("scopus")

    active_sources = requested_sources & available - key_gated
    skipped_sources = (requested_sources - active_sources) | key_gated

    all_papers = []
    if "arxiv" in active_sources:
        all_papers.extend(search_arxiv(args.query, per_source, from_date, to_date, args.domain))
    if "semantic_scholar" in active_sources:
        all_papers.extend(search_semantic_scholar(args.query, per_source, from_date, to_date, s2_key))
    if "openalex" in active_sources:
        all_papers.extend(search_openalex(args.query, per_source, from_date, to_date))
    if "chemrxiv" in active_sources:
        all_papers.extend(search_chemrxiv(args.query, per_source, from_date, to_date))
    if "pubmed" in active_sources:
        all_papers.extend(search_pubmed(args.query, per_source, from_date, to_date, ncbi_key))
    if "wos_session" in active_sources:
        all_papers.extend(search_wos_session(args.query, per_source, from_date, to_date, wos_session_id))

    papers = deduplicate(all_papers, max_results, sort_by=args.sort, min_citations=args.min_citations)

    # Security checks (to stderr)
    check_source_diversity(papers)
    check_recency_bias(papers, from_date)

    coverage = f"Searched: {', '.join(sorted(active_sources))}"
    if skipped_sources:
        coverage += f" | Not searched (no key): {', '.join(sorted(skipped_sources))}"
    print(coverage, file=sys.stderr)

    data = to_papers_json(papers, args.query, active_sources, skipped_sources, args.domain, from_date, to_date, args.sort)

    # Handle --append
    _append_saved = False
    if args.append:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
        try:
            import papers_io
            base = papers_io.load(args.append)
            added = papers_io.merge(base, data)
            papers_io.save(base, args.append)
            print(f"Merged: {added} new papers added to {args.append}", file=sys.stderr)
            _append_saved = True
        except Exception as e:
            print(f"WARNING: --append failed: {e}", file=sys.stderr)

    # Output — skip if --append already wrote to the same path
    _skip_output = (
        _append_saved
        and args.output
        and Path(args.output).resolve() == Path(args.append).resolve()
    )
    if args.output and not _skip_output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved: {out_path} ({len(papers)} papers)", file=sys.stderr)

    if args.json_out:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.text or (not args.output and not args.json_out):
        # Attach sources set for format_text
        for p, rec in zip(papers, data["papers"]):
            p["impact_score"] = rec["impact_score"]
        print(format_text(papers, args.query, args.sort))


if __name__ == "__main__":
    main()
