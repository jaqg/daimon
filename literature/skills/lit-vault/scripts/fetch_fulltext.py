#!/usr/bin/env python3
"""Fetch full text for papers in papers.json.

Tries per paper (stops at first success):
  (1) arXiv HTML → arXiv PDF
  (2) Springer direct PDF (10.1007/*, 10.1038/*)
  (3) chemRxiv Figshare PDF (10.26434/*)
  (4) Unpaywall OA PDF/HTML (all oa_locations)
  (5) Europe PMC full text XML
  (6) Elsevier ScienceDirect XML/PDF (requires ELSEVIER_API_KEY + institutional IP)
  (7) Wiley TDM PDF (requires WILEY_TDM_TOKEN + library agreement)
  (8) CORE OA repository full text / PDF (requires CORE_API_KEY)
  (9) Semantic Scholar openAccessPdf (key optional via SS_API_KEY)
  (10) abstract fallback

Usage:
    python3 fetch_fulltext.py --papers INPUT.json --output OUTPUT.json [--email EMAIL]
                              [--cache-dir DIR] [--pdf-dir DIR]
                              [--core-key KEY] [--ss-key KEY]
                              [--elsevier-key KEY] [--wiley-token TOKEN]

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

_ELSEVIER_PREFIXES  = {"10.1016/", "10.1006/", "10.1053/", "10.1054/", "10.1078/"}
_WILEY_PREFIXES     = {"10.1002/", "10.1111/"}
_ACS_PREFIXES       = {"10.1021/"}
_RSC_PREFIXES       = {"10.1039/"}
_SPRINGER_PREFIXES  = {"10.1007/", "10.1038/"}
_CHEMRXIV_PREFIXES  = {"10.26434/"}


def _detect_publisher(doi: str) -> str | None:
    if not doi:
        return None
    for p in _ELSEVIER_PREFIXES:
        if doi.startswith(p):
            return "elsevier"
    for p in _WILEY_PREFIXES:
        if doi.startswith(p):
            return "wiley"
    for p in _ACS_PREFIXES:
        if doi.startswith(p):
            return "acs"
    for p in _RSC_PREFIXES:
        if doi.startswith(p):
            return "rsc"
    for p in _SPRINGER_PREFIXES:
        if doi.startswith(p):
            return "springer"
    for p in _CHEMRXIV_PREFIXES:
        if doi.startswith(p):
            return "chemrxiv"
    return None


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


def fetch_elsevier(doi: str, api_key: str, save_path: str = None):
    """Fetch full text from Elsevier ScienceDirect API (institutional IP/VPN required).
    Tries XML first (no PyMuPDF), then PDF. Returns (text, source, failure_reason)."""
    encoded = urllib.parse.quote(doi, safe="")
    base = f"https://api.elsevier.com/content/article/doi/{encoded}"

    # XML
    try:
        req = urllib.request.Request(
            f"{base}?apiKey={api_key}&httpAccept=text/xml",
            headers={"User-Agent": UA},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
        if "xml" in ct or data[:5] in (b"<?xml", b"<els:"):
            text = _strip_html(data.decode("utf-8", errors="replace"))
            if len(text) >= 500:
                return text, "elsevier-xml", None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, None, f"elsevier-http-{e.code}-check-ip-or-key"
        if e.code != 404:
            return None, None, f"elsevier-xml-http-{e.code}"
    except Exception as e:
        return None, None, f"elsevier-xml-{type(e).__name__}"

    # PDF fallback
    pdf_url = f"{base}?apiKey={api_key}&httpAccept=application/pdf"
    text, reason = _extract_pdf(pdf_url, save_path=save_path)
    if text:
        return text, "elsevier-pdf", None
    return None, None, reason or "elsevier-pdf-failed"


def fetch_wiley(doi: str, token: str, save_path: str = None):
    """Fetch PDF from Wiley TDM API (ORCID token + library TDM agreement required).
    Returns (text, source, failure_reason)."""
    try:
        import fitz
    except ImportError:
        return None, None, "pymupdf-not-installed"

    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{encoded}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Authorization": f"Bearer {token}",
                "Accept": "application/pdf",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, None, f"wiley-http-{e.code}-check-token-or-agreement"
        return None, None, f"wiley-http-{e.code}"
    except Exception as e:
        return None, None, f"wiley-{type(e).__name__}"

    if "pdf" not in ct and not data[:4] == b"%PDF":
        return None, None, "wiley-unexpected-content-type"

    if save_path:
        try:
            actual = _resolve_save_path(save_path, data)
            if actual:
                with open(actual, "wb") as f:
                    f.write(data)
        except OSError:
            pass

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        doc = fitz.open(tmp)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if len(text) < 500:
            return None, None, "wiley-pdf-text-too-short"
        return text, "wiley-pdf", None
    except Exception as e:
        return None, None, f"wiley-pdf-fitz-{type(e).__name__}"
    finally:
        os.unlink(tmp)


def fetch_springer_direct(doi: str, save_path: str = None):
    """Try Springer direct PDF link before Unpaywall (works for many Springer OA/hybrid).
    Returns (text, source, failure_reason)."""
    # Strip scheme/host prefix if present
    clean_doi = re.sub(r"^https?://[^/]+/", "", doi)
    pdf_url = f"https://link.springer.com/content/pdf/{clean_doi}.pdf"
    text, reason = _extract_pdf(pdf_url, save_path=save_path)
    if text:
        return text, "springer-direct", None
    return None, None, reason or "springer-direct-failed"


def fetch_chemrxiv(doi: str, save_path: str = None):
    """Fetch full text from chemRxiv preprints (10.26434/* DOIs) via Figshare CDN.
    Returns (text, source, failure_reason)."""
    # chemRxiv uses Figshare backend; DOI resolves to a landing page with a PDF link
    try:
        encoded = urllib.parse.quote(doi, safe="")
        doi_url = f"https://doi.org/{doi}"
        # Follow redirect to get canonical URL
        req = urllib.request.Request(doi_url, headers={"User-Agent": UA_BROWSER})
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.url
            page_html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return None, None, f"chemrxiv-http-{e.code}"
    except Exception as e:
        return None, None, f"chemrxiv-{type(e).__name__}"

    # Extract PDF URL from Figshare/chemRxiv landing page
    # Patterns: data-download-url, og:url with .pdf, or direct /ndownloader/ links
    pdf_url = None
    for pat in (
        r'href="(https://[^"]*ndownloader[^"]*\.pdf[^"]*)"',
        r'content="(https://[^"]*\.pdf)"',
        r'"downloadUrl"\s*:\s*"([^"]+\.pdf)"',
        r'(https://chemrxiv\.org/engage/[^"\']+\.pdf)',
    ):
        m = re.search(pat, page_html)
        if m:
            pdf_url = m.group(1)
            break

    if not pdf_url:
        return None, None, "chemrxiv-no-pdf-url"

    text, reason = _extract_pdf(pdf_url, save_path=save_path)
    if text:
        return text, "chemrxiv-pdf", None
    return None, None, reason or "chemrxiv-pdf-failed"


def fetch_core(doi: str, api_key: str, save_path: str = None):
    """Fetch full text from CORE API (core.ac.uk). Free API key required.
    Returns (text, source, failure_reason)."""
    encoded = urllib.parse.quote(f"doi:{doi}", safe="")
    url = f"https://api.core.ac.uk/v3/search/works?q={encoded}&limit=1&apiKey={api_key}"
    try:
        data, _ = _get(url, timeout=15)
        resp = json.loads(data)
    except urllib.error.HTTPError as e:
        return None, None, f"core-http-{e.code}"
    except Exception as e:
        return None, None, f"core-{type(e).__name__}"

    hits = resp.get("results") or []
    if not hits:
        return None, None, "core-not-found"

    hit = hits[0]

    # fullText field: CORE sometimes includes extracted plain text directly
    full_text_field = hit.get("fullText")
    if full_text_field and len(full_text_field.strip()) >= 500:
        return full_text_field.strip(), "core-fulltext", None

    # downloadUrl: OA PDF from CORE repository
    download_url = hit.get("downloadUrl")
    if download_url:
        text, reason = _extract_pdf(download_url, save_path=save_path)
        if text:
            return text, "core-pdf", None

    # sourceFulltextUrls: list of repo URLs
    for src_url in (hit.get("sourceFulltextUrls") or []):
        if src_url.endswith(".pdf"):
            text, reason = _extract_pdf(src_url, save_path=save_path)
            if text:
                return text, "core-pdf", None
        else:
            text, reason = _fetch_html(src_url)
            if text:
                return text, "core-html", None

    return None, None, "core-no-fulltext"


def fetch_semanticscholar(doi: str, api_key: str = None, save_path: str = None):
    """Fetch OA PDF URL from Semantic Scholar, then extract text.
    Returns (text, source, failure_reason)."""
    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded}?fields=openAccessPdf"
    headers = {"User-Agent": UA}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return None, None, f"s2-http-{e.code}"
    except Exception as e:
        return None, None, f"s2-{type(e).__name__}"

    oa = data.get("openAccessPdf")
    if not oa or not oa.get("url"):
        return None, None, "s2-no-oa-pdf"

    pdf_url = oa["url"]
    text, reason = _extract_pdf(pdf_url, save_path=save_path)
    if text:
        return text, "s2-pdf", None

    # If PDF URL looks like HTML (repo landing page), try as HTML
    if reason and "fitz" in reason:
        text, reason = _fetch_html(pdf_url)
        if text:
            return text, "s2-html", None

    return None, None, reason or "s2-pdf-failed"


# ---------------------------------------------------------------------------
# Paper processor
# ---------------------------------------------------------------------------

def process_paper(
    paper: dict,
    email: str,
    pdf_dir: str = None,
    cache: dict = None,
    cache_path: str = None,
    elsevier_key: str = None,
    wiley_token: str = None,
    core_key: str = None,
    ss_key: str = None,
) -> dict:
    paper_id = paper.get("id", "")

    if cache is not None and paper_id in cache and cache[paper_id].get("full_text_available"):
        return {**cache[paper_id], "_from_cache": True}

    arxiv_id = paper.get("arxiv") or (
        paper_id if paper_id.startswith("arxiv:") else None
    )
    doi = paper.get("doi")
    publisher = _detect_publisher(doi)

    save_path = None
    if pdf_dir:
        stem = _derive_note_stem(paper) or _sanitize_filename(paper_id)
        save_path = os.path.join(pdf_dir, stem + ".pdf")

    full_text = source = reason = None

    if arxiv_id:
        full_text, source, reason = fetch_arxiv(arxiv_id, save_path=save_path)
        time.sleep(DELAY)

    # Springer direct PDF before Unpaywall (better URL for many Springer OA/hybrid)
    if not full_text and doi and publisher == "springer":
        full_text, source, reason = fetch_springer_direct(doi, save_path=save_path)
        time.sleep(DELAY)

    # chemRxiv preprints (10.26434/*)
    if not full_text and doi and publisher == "chemrxiv":
        full_text, source, reason = fetch_chemrxiv(doi, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source, reason = fetch_unpaywall(doi, email, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source, reason = fetch_europepmc(doi)
        time.sleep(DELAY)

    if not full_text and doi and elsevier_key and publisher == "elsevier":
        full_text, source, reason = fetch_elsevier(doi, elsevier_key, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi and wiley_token and publisher == "wiley":
        full_text, source, reason = fetch_wiley(doi, wiley_token, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi and core_key:
        full_text, source, reason = fetch_core(doi, core_key, save_path=save_path)
        time.sleep(DELAY)

    if not full_text and doi:
        full_text, source, reason = fetch_semanticscholar(doi, api_key=ss_key or None, save_path=save_path)
        time.sleep(DELAY)

    if not full_text:
        source = "abstract"

    result = {
        "full_text": full_text,
        "source": source,
        "full_text_available": full_text is not None,
        "fetch_reason": reason,
        "publisher": publisher,
    }

    if cache is not None and cache_path and result["full_text_available"]:
        cache[paper_id] = result
        _save_cache(cache, cache_path)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write_manual_download_manifest(
    papers: list,
    results: dict,
    out_path: str,
    pdf_dir: str = None,
) -> int:
    """Write TSV manifest of papers that could not be fetched automatically.
    Returns count of entries written."""
    import datetime

    manual = []
    for paper in papers:
        pid = paper.get("id", "")
        res = results.get(pid, {})
        if res.get("full_text_available"):
            continue
        doi = paper.get("doi", "")
        publisher = res.get("publisher") or _detect_publisher(doi) or "unknown"
        stem = _derive_note_stem(paper)
        manual.append({
            "publisher": publisher,
            "filename": stem + ".pdf",
            "doi": doi,
            "title": (paper.get("title") or "")[:80],
            "year": str(paper.get("year") or ""),
            "venue": (paper.get("venue") or paper.get("journal") or ""),
            "reason": res.get("fetch_reason") or "not-attempted",
        })

    if not manual:
        return 0

    # Sort: by publisher then year
    manual.sort(key=lambda x: (x["publisher"], x["year"]))

    date_str = datetime.date.today().isoformat()
    drop_dir = pdf_dir or "<your-pdf-dir>"

    lines = [
        f"# Manual download list — {date_str}",
        "# Papers that could not be fetched automatically.",
        f"# Download PDFs via institutional access (VPN if off-campus).",
        f"# Drop files in: {drop_dir}",
        "# Name each PDF as shown in the FILENAME column.",
        "# Re-run with --pdf-dir to pick them up.",
        "#",
        "# PUBLISHER\tFILENAME\tDOI\tTITLE\tYEAR\tVENUE\tFAIL_REASON",
    ]

    current_pub = None
    for entry in manual:
        pub = entry["publisher"]
        if pub != current_pub:
            current_pub = pub
            hint = {
                "acs": "https://pubs.acs.org/doi/{doi}",
                "rsc": "https://pubs.rsc.org/en/content/articlehtml/{doi}",
                "springer": "https://link.springer.com/article/{doi}",
                "elsevier": "https://www.sciencedirect.com/science/article/pii/ (search by DOI) — check ELSEVIER_API_KEY + institutional IP",
                "wiley": "https://onlinelibrary.wiley.com/doi/{doi} — check WILEY_TDM_TOKEN",
            }.get(pub, "search by DOI")
            lines.append(f"#")
            lines.append(f"# === {pub.upper()} — {hint} ===")
        row = "\t".join([
            entry["publisher"], entry["filename"], entry["doi"],
            entry["title"], entry["year"], entry["venue"], entry["reason"],
        ])
        lines.append(row)

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return len(manual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", required=True, help="Input papers.json path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--email", default="anonymous@example.com")
    parser.add_argument("--cache-dir", default=None, help="Dir for fulltext-cache.json (skip re-fetching cached papers)")
    parser.add_argument("--pdf-dir", default=None, help="Dir to save downloaded PDFs")
    parser.add_argument("--elsevier-key", default=None, help="Elsevier API key (dev.elsevier.com; requires institutional IP/VPN)")
    parser.add_argument("--wiley-token", default=None, help="Wiley TDM bearer token (ORCID-linked; requires library TDM agreement)")
    parser.add_argument("--core-key", default=None, help="CORE API key (core.ac.uk/services/api; free registration)")
    parser.add_argument("--ss-key", default=None, help="Semantic Scholar API key (optional; raises rate limits; api.semanticscholar.org)")
    parser.add_argument("--manual-download-out", default=None, help="Path for manual-download TSV manifest (default: <output>-to-download.tsv)")
    args = parser.parse_args()

    elsevier_key = args.elsevier_key or os.environ.get("ELSEVIER_API_KEY") or None
    wiley_token  = args.wiley_token  or os.environ.get("WILEY_TDM_TOKEN")  or None
    core_key     = args.core_key     or os.environ.get("CORE_API_KEY")     or None
    ss_key       = args.ss_key       or os.environ.get("SS_API_KEY")       or None

    if elsevier_key:
        print("Elsevier API: enabled")
    if wiley_token:
        print("Wiley TDM API: enabled")
    if core_key:
        print("CORE API: enabled")
    if ss_key:
        print("Semantic Scholar API: key provided")

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
            elsevier_key=elsevier_key,
            wiley_token=wiley_token,
            core_key=core_key,
            ss_key=ss_key,
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
            pub = result.get("publisher") or ""
            abstract_count += 1
            print(f"[abstract-only: {reason_str}{' (' + pub + ')' if pub else ''}]")

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    # Manual download manifest
    manifest_path = args.manual_download_out
    if not manifest_path:
        base = args.output
        if base.endswith(".json"):
            base = base[:-5]
        manifest_path = base + "-to-download.tsv"
    manual_count = _write_manual_download_manifest(papers, results, manifest_path, pdf_dir=args.pdf_dir)

    total = len(papers)
    fetched = sum(src_counts.values())
    src_summary = " | ".join(f"{k}: {v}" for k, v in sorted(src_counts.items()))
    print(
        f"\nFull text fetched: {fetched}/{total} "
        f"({src_summary} | abstract-only: {abstract_count})"
    )
    if cache_hit_count:
        print(f"Cache hits: {cache_hit_count}/{fetched} (skipped re-fetch)")
    if manual_count:
        print(f"Manual download list: {manual_count} papers → {manifest_path}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
