#!/usr/bin/env python3
"""Fetch full text for papers in papers.json.

Tries per paper:
  (1) arXiv HTML → arXiv PDF
  (2) Unpaywall OA PDF (all oa_locations) → Unpaywall HTML (all oa_locations)
  (3) Europe PMC full text XML
  (4) abstract fallback

Usage:
    python3 fetch_fulltext.py --papers INPUT.json --output OUTPUT.json [--email EMAIL]
                              [--cache-dir DIR] [--pdf-dir DIR]

Output: JSON mapping paper_id -> {full_text, source, full_text_available, fetch_reason}
"""

import argparse
import json
import os
import re
import shutil
import time
import tempfile
import unicodedata
import urllib.request
import urllib.parse
import urllib.error


DELAY = 0.5  # seconds between API calls
UA = "lit-vault/1.0 (daimon research tool; github.com/jaqg/daimon)"
UA_BROWSER = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url, timeout=15, ua=None):
    req = urllib.request.Request(url, headers={"User-Agent": ua or UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def _math_alttext(m: re.Match) -> str:
    """Replace <math alttext="...">...</math> with $...$ or $$...$$."""
    opening = m.group(1)
    alt = re.search(r'alttext="([^"]*)"', opening)
    if not alt:
        return " "
    latex = (
        alt.group(1)
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )
    display = bool(re.search(r'display=["\']block["\']', opening, re.IGNORECASE))
    return f" $${latex}$$ " if display else f" ${latex}$ "


def _strip_html(html: str) -> str:
    # Preserve equations: extract LaTeX from MathML alttext before stripping tags
    # Applies to arXiv HTML and EuropePMC XML (both embed alttext on <math> elements)
    html = re.sub(
        r"<(math\b[^>]*)>.*?</math>", _math_alttext, html, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]{2,6};", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_filename(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.\-]", "_", s)


_NOTE_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "with", "by", "to", "from",
    "and", "or", "is", "are", "was", "new", "novel", "study", "investigation",
    "analysis", "approach", "method",
}


def _ascii_norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")


def _resolve_save_path(initial_path: str, data: bytes) -> str | None:
    """Return a collision-safe path for data, or None if already saved.

    Iterates stem.ext → stem-2.ext → ... until a free slot is found.
    If an existing slot has identical bytes, the file is already there — return None.
    """
    basename = os.path.basename(initial_path)
    if "." in basename:
        dot = initial_path.rfind(".")
        base, ext = initial_path[:dot], initial_path[dot:]
    else:
        base, ext = initial_path, ""
    for i in range(1, 100):
        suffix = "" if i == 1 else f"-{i}"
        path = f"{base}{suffix}{ext}"
        if not os.path.exists(path):
            return path
        try:
            with open(path, "rb") as f:
                if f.read() == data:
                    return None  # already on disk
        except OSError:
            return path  # can't read existing file; claim this slot
    return None  # give up after 99 collisions


def _derive_note_stem(paper: dict) -> str:
    """Derive vault note filename stem: {firstauthorlastname}{year}-{keyword}.
    Mirrors lit-vault Step 4a naming logic."""
    authors = paper.get("authors") or []
    last_name = ""
    if authors:
        first = authors[0] if isinstance(authors[0], str) else (authors[0].get("name") or "")
        first = first.strip()
        if "," in first:
            last_name = first.split(",")[0].strip()
        elif " " in first:
            last_name = first.rsplit(" ", 1)[-1].strip()
        else:
            last_name = first
    last_name = re.sub(r"[^a-z]", "", _ascii_norm(last_name).lower()) or "unknown"

    year = str(paper.get("year") or "0000")[:4]

    keyword = "paper"
    for word in re.split(r"\W+", paper.get("title") or ""):
        w = word.lower()
        if w and len(w) > 2 and w not in _NOTE_STOPWORDS:
            keyword = re.sub(r"[^a-z0-9]", "", _ascii_norm(w).lower()) or keyword
            break

    return f"{last_name}{year}-{keyword}"


def _save_cache(cache: dict, cache_path: str) -> None:
    tmp = cache_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, cache_path)  # atomic


# ---------------------------------------------------------------------------
# Fetch primitives
# ---------------------------------------------------------------------------

_LANDING_PAGE_PATTERNS = re.compile(
    r"(sign in|log in|create account|purchase access|buy article"
    r"|subscribe to|access options|download pdf|view pdf"
    r"|cookie policy|accept cookies|your privacy)",
    re.IGNORECASE,
)

def _fetch_html(url: str):
    """Fetch and strip HTML page. Returns (text, failure_reason)."""
    try:
        data, _ = _get(url, timeout=20, ua=UA_BROWSER)
        text = _strip_html(data.decode("utf-8", errors="replace"))
        if len(text) < 1500:
            return None, "html-too-short"
        if _LANDING_PAGE_PATTERNS.search(text[:3000]):
            return None, "html-landing-page"
        return text, None
    except urllib.error.HTTPError as e:
        return None, f"html-http-{e.code}"
    except Exception as e:
        return None, f"html-{type(e).__name__}"


def _extract_pdf(pdf_url: str, save_path: str = None):
    """Fetch PDF and extract text via PyMuPDF. Returns (text, failure_reason).
    Retries with browser UA on 403. Saves PDF to save_path on successful download."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None, "pymupdf-not-installed"

    data = None
    last_err = None
    for ua in (UA, UA_BROWSER):
        try:
            data, _ = _get(pdf_url, timeout=30, ua=ua)
            break
        except urllib.error.HTTPError as e:
            last_err = f"pdf-http-{e.code}"
            if e.code == 403 and ua == UA:
                continue
            return None, last_err
        except Exception as e:
            return None, f"pdf-{type(e).__name__}"

    if data is None:
        return None, last_err or "pdf-fetch-failed"

    if save_path:
        try:
            actual_path = _resolve_save_path(save_path, data)
            if actual_path:
                with open(actual_path, "wb") as f:
                    f.write(data)
        except OSError:
            pass  # don't abort extraction if save fails

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        doc = fitz.open(tmp)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if len(text) < 500:
            return None, "pdf-text-too-short"
        return text, None
    except Exception as e:
        return None, f"pdf-fitz-{type(e).__name__}"
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# Per-source fetchers
# ---------------------------------------------------------------------------

def fetch_arxiv(arxiv_id: str, save_path: str = None):
    """Try arXiv HTML then PDF. Returns (text, source, failure_reason)."""
    clean = arxiv_id.replace("arxiv:", "").strip()

    try:
        data, _ = _get(f"https://arxiv.org/html/{clean}")
        html = data.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in html or "<html" in html.lower():
            text = _strip_html(html)
            if len(text) >= 500:
                return text, "arxiv-html", None
    except Exception:
        pass

    text, reason = _extract_pdf(f"https://arxiv.org/pdf/{clean}", save_path=save_path)
    if text:
        return text, "arxiv-pdf", None
    return None, None, reason or "arxiv-pdf-failed"


def fetch_unpaywall(doi: str, email: str, save_path: str = None):
    """Try all Unpaywall OA PDF URLs then HTML URLs. Returns (text, source, failure_reason)."""
    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.unpaywall.org/v2/{encoded}?email={urllib.parse.quote(email)}"
    try:
        data, _ = _get(url, timeout=10)
        info = json.loads(data)
    except urllib.error.HTTPError as e:
        return None, None, f"unpaywall-http-{e.code}"
    except Exception as e:
        return None, None, f"unpaywall-{type(e).__name__}"

    best = info.get("best_oa_location") or {}
    all_locs = info.get("oa_locations") or []

    pdf_urls = []
    if best.get("url_for_pdf"):
        pdf_urls.append(best["url_for_pdf"])
    for loc in all_locs:
        u = loc.get("url_for_pdf")
        if u and u not in pdf_urls:
            pdf_urls.append(u)

    html_urls = []
    if best.get("url") and not best["url"].endswith(".pdf"):
        html_urls.append(best["url"])
    for loc in all_locs:
        u = loc.get("url")
        if u and u not in html_urls and not u.endswith(".pdf"):
            html_urls.append(u)

    if not pdf_urls and not html_urls:
        return None, None, "unpaywall-no-oa-url"

    last_reason = None

    for pdf_url in pdf_urls:
        text, reason = _extract_pdf(pdf_url, save_path=save_path)
        if text:
            return text, "unpaywall-pdf", None
        last_reason = reason

    for html_url in html_urls:
        text, reason = _fetch_html(html_url)
        if text:
            return text, "unpaywall-html", None
        last_reason = reason

    return None, None, last_reason or "unpaywall-all-failed"


def fetch_europepmc(doi: str):
    """Look up DOI in Europe PMC, fetch full text XML if available.
    Returns (text, source, failure_reason)."""
    encoded = urllib.parse.quote(doi, safe="")
    search_url = (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query=DOI:{encoded}&format=json&resulttype=lite"
    )
    try:
        data, _ = _get(search_url, timeout=10)
        results = json.loads(data)
        hits = results.get("resultList", {}).get("result", [])
        if not hits:
            return None, None, "europepmc-not-found"
        pmcid = hits[0].get("pmcid")
        if not pmcid:
            return None, None, "europepmc-no-pmcid"
        pmc_num = pmcid[3:] if pmcid.startswith("PMC") else pmcid
        xml_url = (
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC/{pmc_num}/fullTextXML"
        )
        data, _ = _get(xml_url, timeout=15)
        text = _strip_html(data.decode("utf-8", errors="replace"))
        if len(text) < 500:
            return None, None, "europepmc-text-too-short"
        return text, "europepmc", None
    except urllib.error.HTTPError as e:
        return None, None, f"europepmc-http-{e.code}"
    except Exception as e:
        return None, None, f"europepmc-{type(e).__name__}"


# ---------------------------------------------------------------------------
# Paper processor
# ---------------------------------------------------------------------------

def process_paper(
    paper: dict,
    email: str,
    pdf_dir: str = None,
    cache: dict = None,
    cache_path: str = None,
) -> dict:
    paper_id = paper.get("id", "")

    if cache is not None and paper_id in cache and cache[paper_id].get("full_text_available"):
        return {**cache[paper_id], "_from_cache": True}

    arxiv_id = paper.get("arxiv") or (
        paper_id if paper_id.startswith("arxiv:") else None
    )
    doi = paper.get("doi")

    save_path = None
    if pdf_dir:
        stem = _derive_note_stem(paper) or _sanitize_filename(paper_id)
        save_path = os.path.join(pdf_dir, stem + ".pdf")

    full_text = source = reason = None

    if arxiv_id:
        full_text, source, reason = fetch_arxiv(arxiv_id, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source, reason = fetch_unpaywall(doi, email, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source, reason = fetch_europepmc(doi)
        time.sleep(DELAY)

    if not full_text:
        source = "abstract"

    result = {
        "full_text": full_text,
        "source": source,
        "full_text_available": full_text is not None,
        "fetch_reason": reason,
    }

    if cache is not None and cache_path and result["full_text_available"]:
        cache[paper_id] = result
        _save_cache(cache, cache_path)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", required=True, help="Input papers.json path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--email", default="anonymous@example.com")
    parser.add_argument("--cache-dir", default=None, help="Dir for fulltext-cache.json (skip re-fetching cached papers)")
    parser.add_argument("--pdf-dir", default=None, help="Dir to save downloaded PDFs")
    args = parser.parse_args()

    # Load cache
    cache: dict = {}
    cache_path = None
    if args.cache_dir:
        os.makedirs(args.cache_dir, exist_ok=True)
        cache_path = os.path.join(args.cache_dir, "fulltext-cache.json")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cache = json.load(f)
            print(f"Cache: {len(cache)} papers loaded from {cache_path}")

    if args.pdf_dir:
        os.makedirs(args.pdf_dir, exist_ok=True)

    with open(args.papers) as f:
        raw = json.load(f)
    papers = raw.get("papers", raw) if isinstance(raw, dict) else raw

    results = {}
    src_counts: dict[str, int] = {}
    abstract_count = 0
    cache_hit_count = 0

    for paper in papers:
        pid = paper.get("id", f"unknown-{len(results)}")
        print(f"  {pid} ...", end=" ", flush=True)

        result = process_paper(
            paper, args.email,
            pdf_dir=args.pdf_dir,
            cache=cache if cache_path else None,
            cache_path=cache_path,
        )
        from_cache = result.pop("_from_cache", False)
        results[pid] = result

        src = result["source"]
        if result["full_text_available"]:
            src_counts[src] = src_counts.get(src, 0) + 1
            if from_cache:
                cache_hit_count += 1
                print(f"[{src}] (cached)")
            else:
                print(f"[{src}]")
        else:
            reason_str = result.get("fetch_reason") or "unknown"
            abstract_count += 1
            print(f"[abstract-only: {reason_str}]")

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    total = len(papers)
    fetched = sum(src_counts.values())
    src_summary = " | ".join(f"{k}: {v}" for k, v in sorted(src_counts.items()))
    print(
        f"\nFull text fetched: {fetched}/{total} "
        f"({src_summary} | abstract-only: {abstract_count})"
    )
    if cache_hit_count:
        print(f"Cache hits: {cache_hit_count}/{fetched} (skipped re-fetch)")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
