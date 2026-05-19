#!/usr/bin/env python3
"""
lit-bib: Zotero local API sync (port 23119 via Better BibTeX).
Gracefully degrades if Zotero is not running.
"""

import json
import os
import re
import sys
from urllib.parse import urljoin, quote
from urllib.request import urlopen, Request
from urllib.error import URLError


def _req(url, method="GET", data=None, headers=None):
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=h, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except URLError:
        return None, None
    except Exception:
        return None, None


class ZoteroClient:
    def __init__(self, base_url=None):
        self.base = (base_url or os.environ.get("ZOTERO_API_URL") or "http://localhost:23119").rstrip("/")

    def is_running(self):
        status, _ = _req(f"{self.base}/api")
        return status is not None and status < 500

    def has_doi(self, doi):
        if not doi:
            return False
        status, body = _req(f"{self.base}/api/items?q={quote(doi)}&qmode=everything&limit=5")
        if status != 200 or not body:
            return False
        try:
            items = json.loads(body)
            for item in items:
                if (item.get("data", {}) or {}).get("DOI", "").lower() == doi.lower():
                    return True
        except Exception:
            pass
        return False

    def import_bibtex(self, bibtex_str):
        """Import a BibTeX string into Zotero via Better BibTeX endpoint."""
        status, body = _req(
            f"{self.base}/api/items",
            method="POST",
            data={"format": "bibtex", "import": bibtex_str},
        )
        if status in (200, 201):
            return True, body
        return False, body


def sync_entries(entries, base_url=None):
    """
    Sync a list of fetched BibTeX entries to Zotero.
    entries: list of dicts with 'bibtex', 'doi', 'key', 'title'.
    Returns summary dict.
    """
    client = ZoteroClient(base_url)

    if not client.is_running():
        return {
            "status": "skipped",
            "reason": "Zotero not running (http://localhost:23119 unreachable). .bib file written without Zotero sync.",
            "new": 0,
            "skipped": 0,
            "failed": 0,
        }

    new_count = 0
    skipped_count = 0
    failed_count = 0
    errors = []

    for entry in entries:
        doi = entry.get("doi")
        if doi and client.has_doi(doi):
            skipped_count += 1
            continue

        ok, resp = client.import_bibtex(entry["bibtex"])
        if ok:
            new_count += 1
        else:
            failed_count += 1
            errors.append({"key": entry.get("key"), "error": (resp or "")[:100]})

    return {
        "status": "done",
        "new": new_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "errors": errors[:5],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bibtex", required=True, help="Path to .bib file to sync")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    with open(args.bibtex, encoding="utf-8") as f:
        content = f.read()

    # Split into individual entries
    raw_entries = re.findall(r"(@\w+\{[^@]+)", content, re.DOTALL)
    entries = [{"bibtex": e.strip(), "doi": None, "key": ""} for e in raw_entries]

    result = sync_entries(entries, args.base_url)
    print(json.dumps(result, indent=2))
