#!/usr/bin/env python3
"""Suggest Galaxy concept links based on token overlap with source text.

Usage:
  suggest_galaxy.py --vault-dir PATH [--text "..."] [--text-file PATH]
                    [--exclude slug1,slug2,...] [--top N]

Reads existing 30-Galaxy/*.md filenames, tokenizes the input text, scores
each concept slug by token overlap, returns the top N candidates not in
the --exclude list.

Output (stdout, JSON):
["concept-slug-a", "concept-slug-b", ...]
"""

import argparse
import json
import re
import sys
from pathlib import Path

TOP_DEFAULT = 5

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "this", "that", "these", "those",
    "it", "its", "we", "our", "their", "they", "he", "she", "i", "you",
    "as", "so", "if", "not", "no", "also", "than", "then", "which", "who",
    "what", "when", "where", "how", "all", "both", "each", "more", "other",
    "such", "into", "about", "up", "out", "only", "over", "after", "while",
    "between", "through", "during", "before", "under", "between", "against",
    "however", "because", "therefore", "thus", "within", "without", "using",
    "based", "among", "paper", "study", "results", "show", "shows", "shown",
    "used", "use", "using", "new", "method", "methods", "approach", "approaches",
    "two", "three", "four", "five", "first", "second", "third", "fig", "table",
    "eq", "equation", "section", "et", "al",
}


def tokenize(text):
    """Lowercase, split on non-alpha, drop stopwords, keep tokens ≥3 chars."""
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in STOPWORDS}


def slug_tokens(slug):
    """Split a Galaxy slug into component tokens."""
    return set(slug.split("-")) - STOPWORDS


def load_galaxy_slugs(vault_dir):
    galaxy = Path(vault_dir) / "30-Galaxy"
    if not galaxy.is_dir():
        return []
    return [p.stem for p in sorted(galaxy.glob("*.md"))]


def score_slug(slug, text_tokens):
    """Token overlap: count slug component tokens that appear in text_tokens."""
    s_tokens = slug_tokens(slug)
    if not s_tokens:
        return 0
    return len(s_tokens & text_tokens) / len(s_tokens)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-dir", required=True, metavar="PATH",
                        help="Root of the Obsidian vault")
    parser.add_argument("--text", default=None,
                        help="Source text inline")
    parser.add_argument("--text-file", default=None, metavar="PATH",
                        help="Path to file containing source text")
    parser.add_argument("--exclude", default="",
                        help="Comma-separated slug list already present in note")
    parser.add_argument("--top", type=int, default=TOP_DEFAULT,
                        help=f"Number of suggestions to return (default: {TOP_DEFAULT})")
    args = parser.parse_args()

    # Load text
    text = ""
    if args.text:
        text += args.text + "\n"
    if args.text_file:
        try:
            text += Path(args.text_file).read_text(encoding="utf-8")
        except OSError as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
    if not text.strip():
        print(json.dumps([]))
        return

    text_tokens = tokenize(text)

    # Load exclusions
    excluded = {s.strip() for s in args.exclude.split(",") if s.strip()}

    # Load Galaxy slugs
    slugs = load_galaxy_slugs(args.vault_dir)
    if not slugs:
        print(json.dumps([]))
        return

    # Score and rank
    scored = []
    for slug in slugs:
        if slug in excluded:
            continue
        sc = score_slug(slug, text_tokens)
        if sc > 0:
            scored.append((sc, slug))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = [slug for _, slug in scored[: args.top]]

    print(json.dumps(top, ensure_ascii=False))


if __name__ == "__main__":
    main()
