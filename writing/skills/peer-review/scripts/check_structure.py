#!/usr/bin/env python3
"""Compute structural metrics from extract_manuscript.py paragraph JSON.

Usage:
    python3 check_structure.py --paragraphs '<json-array>'

Input:  JSON array from extract_manuscript.py (requires section_level field).
Output: JSON structural summary consumed by the peer-review lens 1 (manuscript structure).

Only top-level sections (section_level == 1) are included in balance metrics.
Abstract is excluded from body_word_count and body_fractions.
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Structural metrics from manuscript paragraph JSON")
    parser.add_argument("--paragraphs", required=True, help="JSON array from extract_manuscript.py")
    args = parser.parse_args()

    try:
        paragraphs = json.loads(args.paragraphs)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)

    section_order = []   # first-appearance order of top-level sections
    seen = set()
    word_counts: dict[str, int] = {}
    last_para_idx: dict[str, int] = {}

    for p in paragraphs:
        if p.get("section_level", 0) != 1:
            continue
        sec = p["section"]
        words = len(p["text"].split())
        if sec not in seen:
            seen.add(sec)
            section_order.append(sec)
            word_counts[sec] = 0
        word_counts[sec] += words
        last_para_idx[sec] = p["para_idx"]

    # Body excludes Abstract for balance fractions
    body_sections = [s for s in section_order if s.lower() != "abstract"]
    body_word_count = sum(word_counts.get(s, 0) for s in body_sections)

    body_fractions: dict[str, float] = {}
    if body_word_count > 0:
        for sec in body_sections:
            body_fractions[sec] = round(word_counts[sec] / body_word_count, 3)

    print(json.dumps({
        "top_level_sections": section_order,
        "word_counts": word_counts,
        "body_word_count": body_word_count,
        "body_fractions": body_fractions,
        "last_para_idx": last_para_idx,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
