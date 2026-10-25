#!/usr/bin/env python3
"""
lit-bib verify: QC verification of .bib entries against Crossref/arXiv.

Usage:
  verify_bibtex.py FILE.bib | DIR | -   [--strict]

Input : .bib file, directory (all *.bib), or '-' for stdin.
Output: stdout = structured JSON:
          {"entries": [{"key", "status", "provenance", "details"} ...],
           "summary": {"verified": N, "fabricated": N, "mismatch": N, "unverified": N}}
        stderr = one human summary line matching fetch_bibtex header shape:
          "Verified: N | Fabricated: N | Mismatch: N | Unverified: N"
Exit  : 1 if any fabricated|mismatch, or duplicate keys; --strict also 1 on
        unverified.

Classification (title Levenshtein sim vs resolved record):
  DOI/eprint does not resolve OR sim < 0.5            -> fabricated
  sim 0.5-0.85 OR author/year field disagreement      -> mismatch
  sim >= 0.85 AND author+year match                   -> verified
  no DOI and no eprint                                -> unverified
Key check (default on, whenever metadata resolved): key must contain
first-author surname (STRICT) AND resolved year (+-1, online-first vs issue
year) -> otherwise mismatch (e.g. various2024quantifying, dipaola2023).
--key-check off: metadata-only (legacy bibs). Duplicate keys (same key on >1
real entry) are a hard finding: report.duplicates + exit 1.

Deterministic: all parsing/comparison logic is code; no model judgment.
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

# fetch_bibtex helpers (module level, importable — no CLI side effects)
from fetch_bibtex import (
    fetch,
    _levenshtein,
    title_ok,
    doi_resolves,
    fetch_bibtex_crossref,
    fetch_bibtex_arxiv,
    _family_names,
    _norm_name,
)

GENERIC_UA = "daimon-lit-bib-verify/1.0 (research)"
THRESH_FABRICATED = 0.5
THRESH_VERIFIED = 0.85


# ---------------------------------------------------------------------------
# Config (CROSSREF_MAILTO for Crossref polite pool)
# ---------------------------------------------------------------------------

def _config_value(key):
    """Read KEY from config.local (repo root /config/config.local), else None."""
    cfg = Path(__file__).resolve().parents[4] / "config" / "config.local"
    try:
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line.startswith(key) and "=" in line:
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    return val
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# BibTeX parser: brace-balanced, no regex entry matching.
# Handles multi-line AND single-line entries, field = {value} and field = "value",
# nested braces in values, skips @comment/@string/@preamble, captures the key.
# This kills the format-variance bug class (regex merges match zero single-line
# entries).
# ---------------------------------------------------------------------------

def _find_balanced(text, start, open_ch, close_ch):
    """Index of bracket matching text[start] == open_ch; -1 if unbalanced.
    Brackets inside double quotes are ignored.
    Backslash escapes are skipped (2026-10-24: LaTeX `\"o` in `{\"o}wdin`
    must not toggle the quote state — it swallowed the following entry)."""
    depth = 0
    in_quote = False
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            in_quote = not in_quote
        elif not in_quote:
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _parse_fields(body, pos):
    """Parse `field = {v}` / `field = "v"` / `field = bare` pairs from body[pos:].
    Returns (fields, pos)."""
    fields = {}
    n = len(body)
    while pos < n:
        while pos < n and (body[pos].isspace() or body[pos] == ","):
            pos += 1
        if pos >= n:
            break
        # field name
        start = pos
        while pos < n and (body[pos].isalnum() or body[pos] in "_-:"):
            pos += 1
        name = body[start:pos]
        if not name:
            pos += 1  # stray char; skip
            continue
        while pos < n and body[pos].isspace():
            pos += 1
        if pos >= n or body[pos] != "=":
            # malformed field: recover at next comma
            nxt = body.find(",", pos)
            pos = nxt + 1 if nxt != -1 else n
            continue
        pos += 1
        while pos < n and body[pos].isspace():
            pos += 1
        # value(s), possibly #-concatenated
        value = ""
        while True:
            if pos >= n:
                break
            if body[pos] == "{":
                end = _find_balanced(body, pos, "{", "}")
                if end == -1:
                    value += body[pos + 1:]
                    pos = n
                    break
                value += body[pos + 1:end]
                pos = end + 1
            elif body[pos] == '"':
                end = pos + 1
                while end < n and body[end] != '"':
                    end += 1
                value += body[pos + 1:end]
                pos = min(end + 1, n)
            else:
                end = pos
                while end < n and body[end] not in ",}":
                    end += 1
                value += body[pos:end].strip()
                pos = end
            # concatenation?
            probe = pos
            while probe < n and body[probe].isspace():
                probe += 1
            if probe < n and body[probe] == "#":
                pos = probe + 1
                while pos < n and body[pos].isspace():
                    pos += 1
                continue
            break
        fields[name.lower()] = value.strip()
        # advance to next field: past a top-level comma
        while pos < n and body[pos] != ",":
            # skip over a quoted/braced region we did not consume above
            if body[pos] == "{":
                end = _find_balanced(body, pos, "{", "}")
                pos = (end + 1) if end != -1 else n
            elif body[pos] == '"':
                end = body.find('"', pos + 1)
                pos = (end + 1) if end != -1 else n
            else:
                pos += 1
        pos += 1 if pos < n else 0
    return fields, pos


def parse_bibtex(text):
    """Parse .bib text into [{"type", "key", "fields"}]. @comment/@string/@preamble
    skipped. %-comment lines (first non-ws char '%') between entries are
    skipped whole — never scanned for @ (a comment quoting '@misc{key}' is not
    an entry). '%' inside an entry body is a literal character.
    Malformed tails are skipped, never raise."""
    entries = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "@":
            # inter-entry state: whole-line % comment skip
            if (i == 0 or text[i - 1] == "\n"):
                j = i
                while j < n and text[j] in " \t\r":
                    j += 1
                if j < n and text[j] == "%":
                    nl = text.find("\n", j)
                    i = (nl + 1) if nl != -1 else n
                    continue
            i += 1
            continue
        j = i + 1
        while j < n and text[j].isalpha():
            j += 1
        etype = text[i + 1:j].lower()
        while j < n and text[j].isspace():
            j += 1
        if j >= n or text[j] not in "{(":
            i += 1
            continue
        open_ch = text[j]
        close_ch = "}" if open_ch == "{" else ")"
        end = _find_balanced(text, j, open_ch, close_ch)
        if end == -1:  # unbalanced tail: stop
            break
        if etype in ("comment", "string", "preamble"):
            i = end + 1
            continue
        body = text[j + 1:end]
        # key = up to first top-level comma
        comma = -1
        depth = 0
        for k, c in enumerate(body):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == "," and depth == 0:
                comma = k
                break
        if comma == -1:
            key, fields = body.strip(), {}
        else:
            key = body[:comma].strip()
            fields, _ = _parse_fields(body, comma + 1)
        if key:
            entries.append({"type": etype, "key": key, "fields": fields})
        i = end + 1
    return entries


# ---------------------------------------------------------------------------
# Metadata resolution (network; injectable for tests)
# ---------------------------------------------------------------------------

def _crossref_bibtex(doi):
    mailto = _config_value("CROSSREF_MAILTO")
    if mailto:
        # Crossref polite pool: UA carries mailto; fetch() retries/backoff applies
        url = ("https://api.crossref.org/works/%s"
               "/transform/application/x-bibtex" % quote(doi, safe=""))
        data = fetch(url,
                     headers={"User-Agent": "daimon-lit-bib-verify/1.0 (mailto:%s)" % mailto},
                     accept="application/x-bibtex", timeout=20)
        if data and data.strip().startswith("@"):
            return data
        return None
    bibtex, _title, _status = fetch_bibtex_crossref(doi)
    return bibtex


def _meta_from_bibtex(bibtex):
    parsed = parse_bibtex(bibtex)
    if not parsed:
        return None
    f = parsed[0]["fields"]
    return {
        "title": f.get("title", ""),
        "author": f.get("author", ""),
        "year": _year_of(f),
    }


def resolve_metadata(doi=None, eprint=None):
    """(meta | None, provenance). DOI present -> Crossref; else eprint -> arXiv.
    meta = {"title", "author", "year"}; year may be None."""
    if doi:
        bibtex = _crossref_bibtex(doi)
        if not bibtex:
            return None, "crossref"
        meta = _meta_from_bibtex(bibtex)
        return (meta, "crossref") if meta else (None, "crossref")
    if eprint:
        bibtex, _title, status = fetch_bibtex_arxiv(eprint)
        if not bibtex or status != "fetched":
            return None, "arxiv"
        meta = _meta_from_bibtex(bibtex)
        return (meta, "arxiv") if meta else (None, "arxiv")
    return None, "unverified"


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------

def _clean_title(s):
    """Brace/backslash-stripped, accent-folded, whitespace-collapsed title."""
    s = (s or "").replace("{", "").replace("}", "").replace("\\", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def _year_of(fields):
    y = (fields.get("year") or fields.get("date") or "")[:4]
    return y if y.isdigit() else None


def _first_surname(author_str):
    fams = _family_names(author_str or "")
    return fams[0] if fams else None


def _first_author_token(author_str):
    """Raw (un-normalized) first-author family token, e.g. 'Martín Pendás'
    or latex-escaped 'Mart{\'i}n Pend{\'a}s'. For key matching, which
    normalizes AFTER tokenizing (multiword surnames must keep their split)."""
    for part in (author_str or "").replace("\n", " ").split(" and "):
        part = part.strip().strip("{}")
        if not part:
            continue
        return (part.split(",")[0] if "," in part else part.split()[-1]).strip()
    return None


def _surname_in_key(surname_raw, key):
    """Key must contain the resolved first-author surname (normalized).
    Multiword surnames ('Martin a-collaborator') also match on any whitespace token
    >= 4 chars (key 'pendas2005'), otherwise every multiword surname
    false-fails."""
    if not surname_raw:
        return True
    k = _norm_name(key)
    full = _norm_name(surname_raw)
    if full and full in k:
        return True
    toks = [_norm_name(t) for t in surname_raw.split()]
    return any(len(t) >= 4 and t in k for t in toks)


def _year_in_key(year, key):
    """Key must contain the resolved year, +-1 tolerated (online-first vs issue
    year: key francisco2006 verifies against resolved 2005). Full yyyy, or a
    standalone yy digit group for the exact year."""
    if not year:
        return True
    digits = []
    cur = ""
    for c in key:
        if c.isdigit():
            cur += c
        else:
            if cur:
                digits.append(cur)
            cur = ""
    if cur:
        digits.append(cur)
    try:
        y = int(year)
    except ValueError:
        return False
    accepted = {str(y - 1), str(y), str(y + 1)}
    if any(d in accepted for d in digits):
        return True
    if len(year) == 4:
        return any(d == year[2:] for d in digits)
    return False


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_entry(entry, resolve=None, key_check=True):
    """One entry -> {"key", "status", "provenance", "details"}.
    key_check=False: metadata-only verification (legacy bibs)."""
    resolve = resolve or resolve_metadata
    key = entry["key"]
    f = entry["fields"]
    doi = f.get("doi")
    eprint = f.get("eprint") or f.get("arxivid") or f.get("arxiv")
    details = {}

    if not doi and not eprint:
        reason = "no DOI and no eprint/arXiv ID; nothing to verify against"
        return {"key": key, "status": "unverified", "provenance": "unverified",
                "details": {"reason": reason, "reasons": [reason]}}

    meta, provenance = resolve(doi=doi, eprint=eprint)
    if meta is None:
        reason = ("identifier did not resolve via %s (404 or unreachable "
                  "record)" % provenance)
        details = {"reason": reason, "reasons": [reason]}
        details.update({"doi": doi} if doi else {"eprint": eprint})
        return {"key": key, "status": "fabricated",
                "provenance": provenance, "details": details}

    # --- field comparisons --------------------------------------------------
    entry_title = _clean_title(f.get("title"))
    res_title = _clean_title(meta.get("title"))
    sim = round(_levenshtein(entry_title, res_title), 3) if entry_title else None

    entry_surname = _first_surname(f.get("author"))
    res_surname = _first_surname(meta.get("author"))
    entry_year = _year_of(f)
    res_year = meta.get("year")

    reasons = []
    # Resolver record with no title (metadata-poor publisher records, e.g.
    # Elsevier legacy chapters): an empty resolved title is NOT evidence of
    # fabrication — levenshtein vs '' is always 0. Classify unverified with
    # an explicit manual-check reason instead (2026-10-24).
    resolved_title_missing = bool(entry_title) and not res_title
    author_disagree = (entry_surname and res_surname
                       and entry_surname != res_surname)
    year_disagree = False
    if entry_year and res_year:
        try:
            year_disagree = abs(int(entry_year) - int(res_year)) > 1
        except ValueError:
            pass

    if resolved_title_missing:
        status = "unverified"
        reasons.append("resolved %s record carries no title (metadata-poor "
                       "record) — not machine-checkable; verify against the "
                       "publisher landing page" % provenance)
    elif sim is not None and sim < THRESH_FABRICATED:
        status = "fabricated"
        reasons.append("title similarity to resolved record %.3f < %.2f — "
                       "resolved paper is '%s'" % (sim, THRESH_FABRICATED,
                                                   res_title[:80]))
    elif author_disagree:
        status = "mismatch"
        reasons.append("first-author disagreement: entry '%s' vs resolved '%s'"
                       % (entry_surname, res_surname))
    elif year_disagree:
        status = "mismatch"
        reasons.append("year disagreement: entry %s vs resolved %s"
                       % (entry_year, res_year))
    elif sim is not None and sim < THRESH_VERIFIED:
        status = "mismatch"
        reasons.append("title similarity %.3f in [%g, %g) — unresolved "
                       "difference" % (sim, THRESH_FABRICATED, THRESH_VERIFIED))
    elif sim is None:
        # no entry title: identity rests on author+year
        status = "verified" if not author_disagree and not year_disagree \
            else "mismatch"
        reasons.append("entry has no title field; matched on author+year")
    else:
        status = "verified"

    details.update({
        "title_sim": sim,
        "entry": {"title": entry_title[:120], "first_author": entry_surname,
                  "year": entry_year},
        "resolved": {"title": res_title[:120], "first_author": res_surname,
                     "year": res_year, "id": doi or eprint},
    })

    # --- key check (default on, whenever metadata resolved) -----------------
    key_problems = []
    res_surname_raw = _first_author_token(meta.get("author"))
    if key_check and res_surname and not _surname_in_key(res_surname_raw, key):
        key_problems.append("key does not contain first-author surname '%s'"
                            % res_surname)
    if res_year and not _year_in_key(res_year, key):
        key_problems.append("key does not contain resolved year '%s'" % res_year)
    if key_check:
        details["key_check"] = {
            "expected_surname": res_surname,
            "expected_year": res_year,
            "ok": not key_problems,
        }
    if key_problems:
        reasons.extend(key_problems)
        if status != "fabricated":
            status = "mismatch"  # key mislabel outranks verified

    details["reasons"] = reasons
    return {"key": key, "status": status, "provenance": provenance,
            "details": details}


def verify_entries(entries, resolve=None, key_check=True):
    """List of parsed entries -> full report dict.
    duplicates: same key used by >1 REAL entry (hard finding, blocks exit)."""
    results = [verify_entry(e, resolve=resolve, key_check=key_check)
               for e in entries]
    summary = {"verified": 0, "fabricated": 0, "mismatch": 0, "unverified": 0}
    for r in results:
        summary[r["status"]] += 1
    key_counts = {}
    for e in entries:
        key_counts[e["key"]] = key_counts.get(e["key"], 0) + 1
    duplicates = {k: c for k, c in key_counts.items() if c > 1}
    return {"entries": results, "summary": summary, "duplicates": duplicates}


# ---------------------------------------------------------------------------
# I/O + CLI
# ---------------------------------------------------------------------------

def collect_sources(arg):
    """arg -> [(source_name, text)]. file | directory(all *.bib) | '-' stdin."""
    if arg == "-":
        return [("<stdin>", sys.stdin.read())]
    p = Path(arg)
    if p.is_dir():
        files = sorted(p.glob("*.bib"))
        if not files:
            raise SystemExit("no *.bib files in %s" % p)
        return [(str(f), f.read_text(encoding="utf-8", errors="replace"))
                for f in files]
    if not p.exists():
        raise SystemExit("not found: %s" % p)
    return [(str(p), p.read_text(encoding="utf-8", errors="replace"))]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify .bib entries against "
                                             "Crossref/arXiv")
    ap.add_argument("path", help=".bib file, directory of *.bib, or '-'")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on unverified too")
    ap.add_argument("--key-check", dest="key_check", default="on",
                    choices=["on", "off"],
                    help="verify citekey contains resolved surname+year "
                         "(default on; off = metadata-only, legacy bibs)")
    args = ap.parse_args(argv)

    all_entries = []
    for _name, text in collect_sources(args.path):
        all_entries.extend(parse_bibtex(text))

    report = verify_entries(all_entries, key_check=(args.key_check == "on"))

    s = report["summary"]
    line = ("Verified: %d | Fabricated: %d | Mismatch: %d | Unverified: %d"
            % (s["verified"], s["fabricated"], s["mismatch"], s["unverified"]))
    print(line, file=sys.stderr)          # human line: stderr
    if report["duplicates"]:
        print("Duplicate keys: %s"
              % ", ".join(sorted(report["duplicates"])), file=sys.stderr)
    print(json.dumps(report, indent=2))    # structured report: stdout

    if s["fabricated"] or s["mismatch"] or report["duplicates"]:
        return 1
    if args.strict and s["unverified"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
