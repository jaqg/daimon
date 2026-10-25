#!/usr/bin/env python3
"""
lit-bib: fetch BibTeX entries from CrossRef and arXiv.
Validates via Levenshtein title similarity (≥85%) to prevent hallucinated fields.
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
import papers_io


def fetch(url, headers=None, timeout=30, retries=2, accept=None):
    h = {"User-Agent": "daimon-lit-bib/1.0 (research; mailto:daimon@example.com)"}
    if headers:
        h.update(headers)
    if accept:
        h["Accept"] = accept
    req = Request(url, headers=h)
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
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
# Levenshtein similarity (no external deps)
# ---------------------------------------------------------------------------

def _levenshtein(a, b):
    a, b = a.lower(), b.lower()
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = curr
    dist = prev[-1]
    max_len = max(len(a), len(b))
    return (max_len - dist) / max_len if max_len else 1.0


def title_ok(fetched_title, expected_title, threshold=0.85):
    if not expected_title:
        return True
    return _levenshtein(fetched_title, expected_title) >= threshold


# ---------------------------------------------------------------------------
# Author-set verification
# ---------------------------------------------------------------------------
# Failure mode this guards (observed 2026-10-21): a hand-typed entry with a
# REAL, resolving DOI but a WRONG author set (e.g. doi of Nation et al.
# attributed to "Tiwari, Babbush, Hayden"; Bader/MacDougall/Lau paper
# attributed to "Bader, Heroux, Car"). DOI resolution alone passes these.

def _norm_name(s):
    """Accent-stripped, lowercase, alpha-only form of a name."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.lower())


def _family_names(author_str):
    """Family names from a BibTeX-style 'A and B and C' author string.
    Handles both 'Last, First' and 'First Last' forms."""
    families = []
    for part in re.split(r"\s+and\s+", author_str or ""):
        part = part.strip().strip("{}")
        if not part:
            continue
        token = part.split(",")[0] if "," in part else part.split()[-1]
        f = _norm_name(token)
        if f:
            families.append(f)
    return families


def authors_ok(bibtex_str, expected_authors):
    """Check fetched entry's author set against the expected set.
    Rule: first-author family must match AND >=50% of expected family names
    must appear among fetched families (when 2+ expected authors given).
    No expected authors -> pass (nothing to check against).
    Returns (ok, detail)."""
    if not expected_authors:
        return True, ""
    m = re.search(r"author\s*=\s*\{([^}]+)\}", bibtex_str, re.IGNORECASE)
    if not m:
        return True, ""  # no author field to check; other validators govern
    fetched = _family_names(m.group(1))
    expected = [_norm_name(a.split(",")[0] if "," in a else a.split()[-1]) for a in expected_authors]
    expected = [e for e in expected if e]
    if not expected or not fetched:
        return True, ""
    if expected[0] != fetched[0]:
        return False, (f"first author mismatch: expected '{expected_authors[0]}', "
                       f"fetched family '{fetched[0]}'")
    if len(expected) >= 2:
        overlap = sum(1 for e in expected if e in fetched)
        if overlap < (len(expected) + 1) // 2:
            return False, (f"author-set mismatch: expected families {expected}, "
                           f"fetched {fetched} (overlap {overlap}/{len(expected)})")
    return True, ""


# ---------------------------------------------------------------------------
# DOI resolution check
# ---------------------------------------------------------------------------

def doi_resolves(doi):
    url = f"https://doi.org/{doi}"
    h = {"User-Agent": "daimon-lit-bib/1.0"}
    req = Request(url, headers=h, method="HEAD")
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CrossRef BibTeX fetch
# ---------------------------------------------------------------------------

def fetch_bibtex_crossref(doi, expected_title=None):
    """
    Fetch BibTeX from CrossRef. Returns (bibtex_str, title, status).
    status: 'fetched' | 'title-mismatch' | 'failed'
    """
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}/transform/application/x-bibtex"
    data = fetch(url, accept="application/x-bibtex", timeout=20)
    if not data or not data.strip().startswith("@"):
        return None, None, "failed"

    # Extract title from BibTeX
    m = re.search(r"title\s*=\s*\{([^}]+)\}", data, re.IGNORECASE)
    fetched_title = m.group(1) if m else ""

    if expected_title and not title_ok(fetched_title, expected_title):
        return data, fetched_title, "title-mismatch"

    return data, fetched_title, "fetched"


# ---------------------------------------------------------------------------
# arXiv BibTeX generation
# ---------------------------------------------------------------------------

def fetch_bibtex_arxiv(arxiv_id, expected_title=None):
    """
    Build BibTeX from arXiv metadata API. Returns (bibtex_str, title, status).
    """
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    data = fetch(url, timeout=20)
    if not data:
        return None, None, "failed"

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None, None, "failed"

    entry = root.find("atom:entry", ns)
    if entry is None:
        return None, None, "failed"

    title_el = entry.find("atom:title", ns)
    title = " ".join((title_el.text or "").split()) if title_el is not None else ""

    if expected_title and not title_ok(title, expected_title):
        return None, title, "title-mismatch"

    pub_el = entry.find("atom:published", ns)
    year = (pub_el.text or "")[:4] if pub_el is not None else ""

    authors = []
    for a in entry.findall("atom:author", ns):
        name_el = a.find("atom:name", ns)
        if name_el is not None:
            authors.append(name_el.text.strip())
    author_str = " and ".join(authors)

    # arXiv DOI if available
    doi = None
    for link in entry.findall("atom:link", ns):
        if link.get("title") == "doi":
            href = link.get("href", "")
            m = re.search(r"10\.\d{4,}/\S+", href)
            if m:
                doi = m.group(0)

    key = _make_key(authors[0] if authors else "anon", year, title)

    bib = f"@article{{{key},\n"
    bib += f"  title = {{{title}}},\n"
    bib += f"  author = {{{author_str}}},\n"
    bib += f"  year = {{{year}}},\n"
    bib += f"  eprint = {{{arxiv_id}}},\n"
    bib += f"  archivePrefix = {{arXiv}},\n"
    if doi:
        bib += f"  doi = {{{doi}}},\n"
    bib += "}\n"

    return bib, title, "fetched"


# ---------------------------------------------------------------------------
# Citekey generation
# ---------------------------------------------------------------------------

def _make_key(first_author, year, title, style="phys"):
    """
    Styles:
      phys (default): firstauthorYEARkeyword (e.g. smith2023density)
      acs:  firstauthorYEARjournal (same as phys, caller provides journal as title)
      apa:  firstauthor_YEAR
      ieee: firstauthorYYkeyword
    """
    name = first_author.strip()
    if "," in name:
        name = name.split(",")[0]
    last = re.split(r"\s+", name.strip())[-1].lower()
    last = re.sub(r"[^a-z]", "", last)
    yr = str(year)[:4]

    # keyword: first significant word of title
    stopwords = {"a", "an", "the", "of", "in", "on", "for", "and", "to", "with", "via", "by"}
    words = [w.lower() for w in re.split(r"\W+", title) if w and w.lower() not in stopwords]
    kw = re.sub(r"[^a-z]", "", words[0]) if words else "paper"

    if style == "phys":
        return f"{last}{yr}{kw}"
    elif style == "acs":
        return f"{last}{yr}{kw}"
    elif style == "apa":
        return f"{last}_{yr}"
    elif style == "ieee":
        return f"{last}{yr[2:]}{kw}"
    return f"{last}{yr}{kw}"


def inject_citekey(bibtex_str, new_key):
    """Replace the citekey in a BibTeX entry."""
    return re.sub(r"(@\w+\{)[^,]+", rf"\g<1>{new_key}", bibtex_str, count=1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_papers(papers, style="phys", validate_doi=False):
    """
    Given list of paper dicts (papers.json format), fetch BibTeX for each.
    Returns (entries, failed, manual_needed).
    Each entry: dict with 'bibtex', 'key', 'doi', 'arxiv_id', 'status'.
    """
    entries = []
    failed = []
    manual_needed = []

    for p in papers:
        doi = p.get("doi")
        _pid = papers_io.paper_id(p)
        arxiv_id = _pid[len("arxiv:"):] if (_pid and _pid.startswith("arxiv:")) else None
        title = p.get("title", "")
        authors = p.get("authors", [])
        year = p.get("year", "")

        bibtex = None
        fetched_title = title
        status = "failed"

        # Security: DOI resolution check
        if doi and validate_doi:
            if not doi_resolves(doi):
                manual_needed.append({"id": p.get("id"), "reason": "DOI does not resolve"})
                continue

        # Try CrossRef first (if DOI available)
        if doi:
            bibtex, fetched_title, status = fetch_bibtex_crossref(doi, title)
            if status == "title-mismatch":
                manual_needed.append({
                    "id": p.get("id"),
                    "reason": f"Title mismatch: expected '{title[:60]}', got '{fetched_title[:60]}'"
                })
                continue
            ok, detail = authors_ok(bibtex, authors)
            if not ok:
                manual_needed.append({
                    "id": p.get("id"),
                    "reason": f"Author mismatch (CrossRef): {detail}"
                })
                continue
            time.sleep(0.1)

        # Fallback: arXiv
        if (bibtex is None or status == "failed") and arxiv_id:
            bibtex, fetched_title, status = fetch_bibtex_arxiv(arxiv_id, title)
            if status == "title-mismatch":
                manual_needed.append({
                    "id": p.get("id"),
                    "reason": f"Title mismatch (arXiv): expected '{title[:60]}', got '{fetched_title[:60]}'"
                })
                continue

        if bibtex is None or status == "failed":
            failed.append({"id": p.get("id"), "title": title[:80], "reason": "No DOI or arXiv ID, or all fetches failed"})
            continue

        # Security: author-set verification (both crossref and arxiv paths)
        ok, detail = authors_ok(bibtex, authors)
        if not ok:
            manual_needed.append({
                "id": p.get("id"),
                "reason": f"Author mismatch: {detail}"
            })
            continue

        # Generate citekey
        if authors:
            first_author = authors[0]
        else:
            am = re.search(r"author\s*=\s*\{([^}]+)\}", bibtex or "", re.IGNORECASE)
            first_author = am.group(1).split(" and ")[0].strip() if am else "anon"
        if not year:
            ym = re.search(r"year\s*=\s*\{?(\d{4})", bibtex or "", re.IGNORECASE)
            year = ym.group(1) if ym else ""
        key = _make_key(first_author, year, fetched_title or title, style)
        bibtex = inject_citekey(bibtex, key)

        entries.append({
            "bibtex": bibtex.strip(),
            "key": key,
            "doi": doi,
            "arxiv_id": arxiv_id,
            "title": fetched_title or title,
            "status": status,
        })

    return entries, failed, manual_needed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--papers")
    parser.add_argument("--dois", help="comma-separated DOI list (manual input)")
    parser.add_argument("--arxiv", help="comma-separated arXiv ID list (manual input)")
    parser.add_argument("--style", default="phys", choices=["phys", "acs", "apa", "ieee"])
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.papers:
        data = papers_io.load(args.papers)
        papers = data["papers"]
    elif args.dois or args.arxiv:
        # Manual inputs carry no expected title/authors: title/author checks
        # pass vacuously. DOI resolution (--validate) is the guard here.
        papers = []
        for d in filter(None, (x.strip() for x in (args.dois or "").split(","))):
            papers.append({"doi": d, "title": "", "authors": []})
        for a in filter(None, (x.strip() for x in (args.arxiv or "").split(","))):
            papers.append({"doi": None, "title": "", "authors": [], "id": f"arxiv:{a}"})
    else:
        parser.error("one of --papers, --dois, --arxiv is required")

    entries, failed, manual = process_papers(papers, args.style, args.validate)
    print(f"Fetched: {len(entries)} | Failed: {len(failed)} | Manual needed: {len(manual)}")
    for e in entries:
        print(e["bibtex"])
        print()
    for m in manual:
        print(f"MANUAL NEEDED: {m.get('id')}: {m.get('reason')}", file=sys.stderr)
