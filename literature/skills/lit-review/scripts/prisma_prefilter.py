#!/usr/bin/env python3
"""PRISMA pre-filter: deterministic pass before Claude abstract screening.

Usage:
  prisma_prefilter.py --papers PATH
                      [--keywords "K1,K2,..."]
                      [--exclude-terms "T1,T2,..."]
                      [--high-cited-recent N]   (citations >= N for paper < 3yr old → auto-include)
                      [--high-cited-older N]    (citations >= N for paper >= 5yr old → auto-include)

Two deterministic rules applied in order:

1. AUTO-EXCLUDE (score 1):
   - Title contains ANY --exclude-terms token.
   - OR --keywords provided AND title contains NONE of the keyword tokens.
   - Papers with citations=null are never auto-excluded by citation count.

2. AUTO-INCLUDE (score 4):
   - Not already excluded.
   - citations is known (non-null).
   - Paper age < 3yr and citations >= high-cited-recent (default 20).
   - OR paper age >= 5yr and citations >= high-cited-older (default 100).

Remaining papers → for_claude (abstract screening by Claude).

Output (stdout, JSON):
{
  "auto_excluded": [...paper records with screening_status/score/reason set],
  "auto_included": [...paper records],
  "for_claude":    [...paper records],
  "stats": {
    "total": N, "auto_excluded": N, "auto_included": N, "for_claude": N,
    "reduction_pct": N   # % reduction in Claude's workload
  }
}
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

CURRENT_YEAR = date.today().year
DEFAULT_HIGH_CITED_RECENT = 20   # < 3yr old
DEFAULT_HIGH_CITED_OLDER = 100   # >= 5yr old


def tokenize_title(title):
    return set(re.findall(r"[a-zA-Z0-9]+", title.lower()))


def paper_age(paper):
    """Years since publication. Returns None if year unknown."""
    year = paper.get("year")
    if year is None:
        return None
    return CURRENT_YEAR - int(year)


def apply_prefilter(papers, keywords, exclude_terms, hc_recent, hc_older):
    kw_tokens = {k.lower() for k in keywords} if keywords else set()
    ex_tokens = {t.lower() for t in exclude_terms} if exclude_terms else set()

    auto_excluded = []
    auto_included = []
    for_claude = []

    for paper in papers:
        title_tokens = tokenize_title(paper.get("title", ""))
        citations = paper.get("citations")
        age = paper_age(paper)

        # --- Auto-exclude pass ---
        excluded = False
        reason = None

        if ex_tokens and ex_tokens & title_tokens:
            matched = sorted(ex_tokens & title_tokens)
            excluded = True
            reason = f"title matches exclude-term(s): {', '.join(matched)}"

        elif kw_tokens and not (kw_tokens & title_tokens):
            excluded = True
            reason = "title contains none of the required keywords"

        if excluded:
            p = dict(paper)
            p["screening_status"] = "excluded"
            p["screening_score"] = 1
            p["exclusion_reason"] = reason
            auto_excluded.append(p)
            continue

        # --- Auto-include pass (high-citation) ---
        included = False
        if citations is not None:
            if age is not None and age < 3 and citations >= hc_recent:
                included = True
                inc_reason = f"highly cited recent paper ({citations} citations, {age}yr old)"
            elif age is not None and age >= 5 and citations >= hc_older:
                included = True
                inc_reason = f"highly cited established paper ({citations} citations, {age}yr old)"

        if included:
            p = dict(paper)
            p["screening_status"] = "included"
            p["screening_score"] = 4
            p["exclusion_reason"] = None
            p["_prefilter_note"] = inc_reason
            auto_included.append(p)
            continue

        # --- Remaining: needs Claude ---
        for_claude.append(paper)

    total = len(papers)
    n_claude = len(for_claude)
    reduction = round((1 - n_claude / total) * 100) if total else 0

    return {
        "auto_excluded": auto_excluded,
        "auto_included": auto_included,
        "for_claude": for_claude,
        "stats": {
            "total": total,
            "auto_excluded": len(auto_excluded),
            "auto_included": len(auto_included),
            "for_claude": n_claude,
            "reduction_pct": reduction,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", required=True, metavar="PATH",
                        help="Path to papers.json from lit-search")
    parser.add_argument("--keywords", default="",
                        help="Comma-separated keywords; title must match ≥1")
    parser.add_argument("--exclude-terms", default="", dest="exclude_terms",
                        help="Comma-separated terms; title match → auto-exclude")
    parser.add_argument("--high-cited-recent", type=int, default=DEFAULT_HIGH_CITED_RECENT,
                        dest="hc_recent",
                        help=f"Citations threshold for papers <3yr (default: {DEFAULT_HIGH_CITED_RECENT})")
    parser.add_argument("--high-cited-older", type=int, default=DEFAULT_HIGH_CITED_OLDER,
                        dest="hc_older",
                        help=f"Citations threshold for papers ≥5yr (default: {DEFAULT_HIGH_CITED_OLDER})")
    args = parser.parse_args()

    papers_path = Path(args.papers)
    if not papers_path.exists():
        print(json.dumps({"error": f"File not found: {args.papers}"}))
        sys.exit(1)

    with open(papers_path, encoding="utf-8") as f:
        data = json.load(f)

    # Accept both papers.json format {"papers": [...]} and plain list
    if isinstance(data, dict):
        papers = data.get("papers", [])
    else:
        papers = data

    if not papers:
        print(json.dumps({
            "auto_excluded": [], "auto_included": [], "for_claude": [],
            "stats": {"total": 0, "auto_excluded": 0, "auto_included": 0,
                      "for_claude": 0, "reduction_pct": 0},
        }))
        return

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    exclude_terms = [t.strip() for t in args.exclude_terms.split(",") if t.strip()]

    result = apply_prefilter(papers, keywords, exclude_terms, args.hc_recent, args.hc_older)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
