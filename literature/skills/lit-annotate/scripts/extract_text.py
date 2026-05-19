#!/usr/bin/env python3
"""Extract text from a local PDF or URL for lit-annotate.

Usage:
  extract_text.py --pdf PATH
  extract_text.py --url URL

Output (stdout, JSON):
{
  "source": "pdf" | "url",
  "path_or_url": "...",
  "text": "...",
  "char_count": N,
  "truncated": true | false,
  "error": null | "message"
}

Text is truncated to MAX_CHARS to keep context manageable.
On error, "text" is empty string and "error" contains the message.
PDFs downloaded from URLs are saved to /tmp/ and deleted after extraction.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

MAX_CHARS = 20_000  # ~4k tokens; covers most paper full-texts


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf(path):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "", "PyMuPDF (fitz) not installed. Install with: pip install pymupdf"

    try:
        doc = fitz.open(path)
    except Exception as e:
        return "", f"Could not open PDF '{path}': {e}"

    pages = []
    for page in doc:
        try:
            pages.append(page.get_text())
        except Exception:
            continue
    doc.close()

    if not pages:
        return "", f"PDF '{path}' yielded no extractable text (may be scanned/image-only)"

    return "\n".join(pages), None


# ---------------------------------------------------------------------------
# URL fetch
# ---------------------------------------------------------------------------

HEADERS = {"User-Agent": "daimon-lit-annotate/1.0 (research tool)"}


def fetch_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            return data, content_type, None
    except urllib.error.HTTPError as e:
        return None, "", f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, "", f"URL error: {e.reason}"
    except Exception as e:
        return None, "", str(e)


def strip_html(html_text):
    # Remove script/style blocks
    html_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    # Collapse whitespace
    html_text = re.sub(r"\s+", " ", html_text).strip()
    return html_text


def arxiv_html_url(url):
    """Convert arxiv abstract/pdf URL to HTML URL if possible."""
    # https://arxiv.org/abs/XXXX → https://arxiv.org/html/XXXX
    m = re.match(r"https?://arxiv\.org/(?:abs|pdf)/([0-9v.]+)", url)
    if m:
        return f"https://arxiv.org/html/{m.group(1)}"
    return None


def extract_url(url):
    # Try arXiv HTML first (much cleaner than PDF extraction)
    html_url = arxiv_html_url(url)
    if html_url:
        data, content_type, err = fetch_bytes(html_url)
        if data and "html" in content_type.lower():
            text = strip_html(data.decode("utf-8", errors="replace"))
            if len(text) > 500:
                return text, None

    # Fetch the original URL
    data, content_type, err = fetch_bytes(url)
    if err:
        return "", err
    if data is None:
        return "", "No data received"

    # HTML response
    if "html" in content_type.lower():
        text = strip_html(data.decode("utf-8", errors="replace"))
        return text, None

    # PDF response — save to tmp, extract with PyMuPDF
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(data)
            tmp.close()
            text, err = extract_pdf(tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return text, err

    # Fallback: decode as text
    try:
        text = data.decode("utf-8", errors="replace")
        return strip_html(text), None
    except Exception as e:
        return "", str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf", metavar="PATH", help="Local PDF file to extract")
    group.add_argument("--url", metavar="URL", help="URL to fetch (arXiv HTML or PDF)")
    args = parser.parse_args()

    if args.pdf:
        source = "pdf"
        path_or_url = args.pdf
        if not Path(args.pdf).exists():
            result = {
                "source": source, "path_or_url": path_or_url,
                "text": "", "char_count": 0, "truncated": False,
                "error": f"File not found: {args.pdf}",
            }
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)
        text, error = extract_pdf(args.pdf)
    else:
        source = "url"
        path_or_url = args.url
        text, error = extract_url(args.url)

    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]

    result = {
        "source": source,
        "path_or_url": path_or_url,
        "text": text,
        "char_count": len(text),
        "truncated": truncated,
        "error": error,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
