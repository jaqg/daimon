#!/usr/bin/env python3
"""
verify_notes.py — validate vault paper note frontmatter against CrossRef/arXiv.

Reads YAML frontmatter from .md notes and checks doi, year, venue, volume, pages
against authoritative APIs. Approval-gated --fix mode for interactive correction.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# HTTP (copied verbatim from fetch_bibtex.py — scripts are standalone)
# ---------------------------------------------------------------------------

def fetch(url, headers=None, timeout=30, retries=2, accept=None):
    h = {"User-Agent": "daimon-verify-notes/1.0 (research; mailto:daimon@example.com)"}
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
# Levenshtein similarity (copied verbatim from fetch_bibtex.py)
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
# Note parsing
# ---------------------------------------------------------------------------

def parse_note(path: Path):
    """
    Parse a vault paper note. Returns dict with:
      frontmatter: {doi, year, venue, volume, pages, arxiv, ...}
      title_field: str or None   (**Title:** body line if present)
      h1_excerpt:  str or None   (part after ' — ' in H1)
      authors_line: str or None  (**Authors:** body line)
    """
    text = path.read_text(encoding="utf-8")

    # Split on frontmatter delimiters
    parts = re.split(r"^---\s*$", text, flags=re.MULTILINE)
    fm_raw = parts[1] if len(parts) >= 3 else ""
    body = parts[2] if len(parts) >= 3 else text

    # Parse frontmatter key: value pairs (no PyYAML dep)
    fm = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()

    # Extract **Title:** field (new notes only)
    m = re.search(r"^\*\*Title:\*\*\s+(.+)", body, re.MULTILINE)
    title_field = m.group(1).strip() if m else None

    # Extract H1 keyword excerpt (part after ' — ')
    m = re.search(r"^#\s+.+?—\s+(.+)", body, re.MULTILINE)
    h1_excerpt = m.group(1).strip() if m else None

    # Extract **Authors:** line → first author surname
    m = re.search(r"^\*\*Authors:\*\*\s+(.+)", body, re.MULTILINE)
    authors_line = m.group(1).strip() if m else None

    return {
        "frontmatter": fm,
        "title_field": title_field,
        "h1_excerpt": h1_excerpt,
        "authors_line": authors_line,
    }


def first_surname(authors_line: str) -> str:
    """Extract first author surname from 'First Last, Second Last, ...'"""
    if not authors_line:
        return ""
    first = authors_line.split(",")[0].strip()
    # Handle 'V. R. Choudhary' → 'Choudhary'
    parts = first.split()
    return parts[-1] if parts else first


def normalize_venue(v: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for venue comparison."""
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode()
    v = re.sub(r"[^\w\s]", " ", v.lower())
    return re.sub(r"\s+", " ", v).strip()


def detect_arxiv_id(fm: dict, body_parts: str) -> str | None:
    """Look for arXiv ID in frontmatter arxiv field or note body."""
    if fm.get("arxiv"):
        return fm["arxiv"].strip()
    m = re.search(r"arxiv[:\s/]+(\d{4}\.\d{4,5})", body_parts, re.I)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# CrossRef validation
# ---------------------------------------------------------------------------

def validate_doi(doi: str, note: dict, threshold: float) -> dict:
    """
    Fetch https://api.crossref.org/works/{doi} and compare fields.
    Returns {"status": ..., "cr": crossref_data, "proposed": proposed_fixes}.
    """
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    raw = fetch(url, accept="application/json")
    if raw is None:
        return {"status": "doi-not-found", "cr": None, "proposed": {}}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "doi-not-found", "cr": None, "proposed": {}}

    if data.get("status") != "ok":
        return {"status": "doi-not-found", "cr": None, "proposed": {}}

    msg = data["message"]
    cr_title = (msg.get("title") or [""])[0]
    cr_year = None
    dp = msg.get("published", {}).get("date-parts")
    if dp and dp[0]:
        cr_year = str(dp[0][0])
    cr_venue = (msg.get("container-title") or [""])[0]
    cr_volume = msg.get("volume", "")
    cr_page = msg.get("page", "")

    fm = note["frontmatter"]

    # Title comparison: only when **Title:** field present (verbatim API title).
    # H1 excerpt is intentionally a shorthand — Levenshtein vs full CrossRef title is unreliable.
    title_for_check = note.get("title_field")
    if title_for_check and cr_title:
        sim = _levenshtein(title_for_check, cr_title)
        if sim < threshold:
            return {
                "status": "title-mismatch",
                "cr": msg,
                "proposed": {},
                "detail": f"sim={sim:.2f} note='{title_for_check[:60]}' cr='{cr_title[:60]}'",
            }

    # Field comparison (normalize dashes in page ranges for comparison)
    def norm_pages(p):
        return re.sub(r"[–—-]+", "-", str(p).strip())

    mismatches = {}
    if cr_year and fm.get("year") and str(fm["year"]) != cr_year:
        mismatches["year"] = cr_year
    if cr_venue and fm.get("venue"):
        if normalize_venue(cr_venue) != normalize_venue(fm["venue"]):
            mismatches["venue"] = cr_venue
    if cr_volume and fm.get("volume") and str(fm["volume"]) != str(cr_volume):
        mismatches["volume"] = cr_volume
    if cr_page and fm.get("pages") and norm_pages(fm["pages"]) != norm_pages(cr_page):
        mismatches["pages"] = cr_page

    if mismatches:
        return {"status": "field-mismatch", "cr": msg, "proposed": mismatches}

    return {"status": "ok", "cr": msg, "proposed": {}}


def search_crossref_bibliographic(note: dict, threshold: float) -> dict:
    """
    No DOI present: try CrossRef bibliographic/title search.
    Returns {"status": ..., "proposed": {...}}.
    """
    fm = note["frontmatter"]
    authors_line = note.get("authors_line", "")
    surname = first_surname(authors_line)
    year = fm.get("year", "")
    venue = fm.get("venue", "")

    # Prefer **Title:** for query.title; fall back to author+year+venue bibliographic query
    title_field = note.get("title_field")
    if title_field:
        params = urlencode({"query.title": title_field, "rows": 5, "select": "DOI,title,published,container-title,author"})
        url = f"https://api.crossref.org/works?{params}"
    else:
        query = f"{surname} {year} {venue}".strip()
        params = urlencode({"query.bibliographic": query, "rows": 5, "select": "DOI,title,published,container-title,author"})
        url = f"https://api.crossref.org/works?{params}"

    raw = fetch(url, accept="application/json")
    if not raw:
        return {"status": "unverifiable", "proposed": {}}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "unverifiable", "proposed": {}}

    items = data.get("message", {}).get("items", [])
    for item in items:
        cr_title = (item.get("title") or [""])[0]
        cr_year_dp = item.get("published", {}).get("date-parts")
        cr_year = str(cr_year_dp[0][0]) if cr_year_dp and cr_year_dp[0] else ""
        cr_venue = (item.get("container-title") or [""])[0]
        cr_doi = item.get("DOI", "")

        # Check title similarity + year + venue
        title_for_check = title_field or ""
        sim = _levenshtein(title_for_check, cr_title) if title_for_check else 0.0

        year_match = (not year) or (cr_year == str(year))
        venue_match = (not venue) or (normalize_venue(cr_venue) == normalize_venue(venue))
        title_match = (not title_for_check) or (sim >= threshold)

        if title_match and year_match and venue_match and cr_doi:
            proposed = {"doi": cr_doi}
            if cr_venue and fm.get("venue") and normalize_venue(cr_venue) != normalize_venue(fm.get("venue", "")):
                proposed["venue"] = cr_venue
            if cr_year and fm.get("year") and str(cr_year) != str(fm.get("year", "")):
                proposed["year"] = cr_year
            return {
                "status": "candidate-doi-found",
                "proposed": proposed,
                "candidate_title": cr_title,
                "similarity": sim,
            }

    return {"status": "unverifiable", "proposed": {}}


def validate_arxiv(arxiv_id: str, note: dict, threshold: float) -> dict:
    """Validate note against arXiv Atom API."""
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    raw = fetch(url)
    if not raw:
        return {"status": "doi-not-found", "proposed": {}}

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {"status": "doi-not-found", "proposed": {}}

    entry = root.find("atom:entry", ns)
    if entry is None:
        return {"status": "doi-not-found", "proposed": {}}

    title_el = entry.find("atom:title", ns)
    cr_title = " ".join((title_el.text or "").split()) if title_el is not None else ""
    pub_el = entry.find("atom:published", ns)
    cr_year = (pub_el.text or "")[:4] if pub_el is not None else ""

    title_for_check = note.get("title_field") or ""

    if title_for_check and cr_title:
        sim = _levenshtein(title_for_check, cr_title)
        if sim < threshold:
            return {
                "status": "title-mismatch",
                "proposed": {},
                "detail": f"sim={sim:.2f} note='{title_for_check[:60]}' arxiv='{cr_title[:60]}'",
            }

    fm = note["frontmatter"]
    mismatches = {}
    if cr_year and fm.get("year") and str(fm["year"]) != cr_year:
        mismatches["year"] = (fm["year"], cr_year)

    if mismatches:
        return {"status": "field-mismatch", "proposed": mismatches}

    return {"status": "ok", "proposed": {}}


# ---------------------------------------------------------------------------
# Per-note dispatch
# ---------------------------------------------------------------------------

def verify_note(path: Path, threshold: float, rate_limit: float) -> dict:
    """
    Returns {"path": path, "status": ..., "proposed": {}, "detail": ""}.
    """
    note = parse_note(path)
    fm = note["frontmatter"]
    doi = fm.get("doi", "").strip()
    # Detect arXiv ID from frontmatter or body text
    body_text = path.read_text(encoding="utf-8")
    arxiv_id = detect_arxiv_id(fm, body_text)

    result = {"path": path, "status": "unverifiable", "proposed": {}, "detail": ""}

    if doi:
        time.sleep(rate_limit)
        r = validate_doi(doi, note, threshold)
        result["status"] = r["status"]
        result["proposed"] = r.get("proposed", {})
        result["detail"] = r.get("detail", "")
    elif arxiv_id:
        time.sleep(rate_limit)
        r = validate_arxiv(arxiv_id, note, threshold)
        result["status"] = r["status"]
        result["proposed"] = r.get("proposed", {})
        result["detail"] = r.get("detail", "")
    else:
        time.sleep(rate_limit)
        r = search_crossref_bibliographic(note, threshold)
        result["status"] = r["status"]
        result["proposed"] = r.get("proposed", {})
        if r.get("candidate_title"):
            result["detail"] = f"candidate: '{r['candidate_title'][:70]}' (sim={r.get('similarity', 0):.2f})"

    return result


# ---------------------------------------------------------------------------
# Fix mode: atomic frontmatter update
# ---------------------------------------------------------------------------

def apply_fix(path: Path, proposed: dict):
    """Write updated frontmatter values into the note file atomically."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^(---\s*)$", text, flags=re.MULTILINE)
    # parts: ['', '---', fm_block, '---', body, ...]
    if len(parts) < 5:
        print(f"  [WARN] Cannot parse frontmatter in {path.name} — skipping fix")
        return

    fm_lines = parts[2].splitlines(keepends=True)
    new_fm_lines = []
    keys_written = set()

    for line in fm_lines:
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m and m.group(1) in proposed:
            key = m.group(1)
            new_fm_lines.append(f"{key}: {proposed[key]}\n")
            keys_written.add(key)
        else:
            new_fm_lines.append(line)

    # Append any proposed keys that didn't exist yet
    for key, val in proposed.items():
        if key not in keys_written:
            new_fm_lines.append(f"{key}: {val}\n")

    parts[2] = "".join(new_fm_lines)
    new_text = "".join(parts)
    path.write_text(new_text, encoding="utf-8")


def print_diff(proposed: dict, path: Path, detail: str):
    """Print colored diff of proposed frontmatter changes."""
    use_color = sys.stdout.isatty()
    red = "\033[31m" if use_color else ""
    green = "\033[32m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^---\s*$", text, flags=re.MULTILINE)
    fm_raw = parts[1] if len(parts) >= 3 else ""
    fm = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()

    for key, new_val in proposed.items():
        old_val = fm.get(key, "(absent)")
        print(f"  {red}- {key}: {old_val}{reset}")
        print(f"  {green}+ {key}: {new_val}{reset}")
    if detail:
        print(f"  {detail}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_notes(path_arg: str) -> list[Path]:
    p = Path(path_arg)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.md"))
    return []


def main():
    parser = argparse.ArgumentParser(description="Verify vault paper note metadata against CrossRef/arXiv")
    parser.add_argument("--notes", required=True, nargs="+", help="Path(s) to .md files or a directory")
    parser.add_argument("--fix", action="store_true", help="Interactive approval + patch mode")
    parser.add_argument("--dry-run", action="store_true", help="Show diffs without prompting")
    parser.add_argument("--threshold", type=float, default=0.85, help="Levenshtein cutoff (default 0.85)")
    parser.add_argument("--rate-limit", type=float, default=1.0, help="Seconds between CrossRef calls (default 1.0)")
    args = parser.parse_args()

    notes = []
    for arg in args.notes:
        notes.extend(collect_notes(arg))

    if not notes:
        print("No .md files found.")
        sys.exit(1)

    results = []
    skip_rest = False

    # Header
    col1, col2, col3 = 36, 22, 0
    print(f"{'Note':<{col1}} {'Status':<{col2}} Action")
    print("-" * 80)

    for path in notes:
        r = verify_note(path, args.threshold, args.rate_limit)
        results.append(r)
        status = r["status"]
        stem = path.stem[:col1 - 1]

        action = "—"
        if r["proposed"]:
            if status == "candidate-doi-found":
                action = f"proposed doi: {r['proposed'].get('doi', '?')}"
            elif status == "field-mismatch":
                action = "proposed field fixes"
        print(f"{stem:<{col1}} {status:<{col2}} {action}")

        if r["detail"]:
            print(f"  {r['detail']}")

        if status != "ok" and (args.fix or args.dry_run) and not skip_rest and r["proposed"]:
            print(f"\n  [NOTE] {path.name} — {status}")
            print_diff(r["proposed"], path, r.get("detail", ""))

            if args.fix and not args.dry_run:
                answer = input("  Apply fix? [y]es / [n]o / [s]kip rest / [q]uit > ").strip().lower()
                if answer in ("q", "quit"):
                    print("Quit.")
                    break
                elif answer in ("s", "skip"):
                    skip_rest = True
                elif answer in ("y", "yes"):
                    apply_fix(path, r["proposed"])
                    print(f"  Fixed {path.name}")

    # Summary
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    total = len(results)
    ok = counts.get("ok", 0)
    issues = total - ok
    issue_parts = [f"{v} {k}" for k, v in counts.items() if k != "ok"]
    print("-" * 80)
    print(f"Total: {total} notes | ok: {ok} | issues: {issues} ({', '.join(issue_parts)})")


if __name__ == "__main__":
    main()
