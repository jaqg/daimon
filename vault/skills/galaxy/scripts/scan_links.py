#!/usr/bin/env python3
"""Scan paper notes for confirmed [[links]] and output missing Galaxy concepts as JSON.

Output schema:
  {
    "missing": [
      {
        "slug": str,
        "title_case": str,
        "source_papers": [
          {"key": str, "abstract_excerpt": str, "summary_excerpt": str}
        ]
      }
    ],
    "already_exists": [str],
    "total_papers_scanned": int,
    "total_confirmed_links": int
  }
"""

import argparse
import json
import re
import sys
from pathlib import Path

COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
WIKILINK_RE = re.compile(r'\[\[([^\]|#]+?)(?:\|[^\]]+?)?\]\]')

ABSTRACT_HEADERS = re.compile(
    r'^##\s+Abstract(?:\s+\(verbatim\))?$', re.IGNORECASE | re.MULTILINE
)
SUMMARY_HEADERS = re.compile(
    r'^##\s+(?:Summary|Key Points?|Key points?)$', re.IGNORECASE | re.MULTILINE
)
ANY_SECTION = re.compile(r'^##\s+', re.MULTILINE)

EXCERPT_MAX_CHARS = 800


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def title_case(slug: str) -> str:
    LOWER = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'so',
             'yet', 'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'if', 'vs'}
    words = slug.replace('-', ' ').split()
    return ' '.join(
        w if (i > 0 and w in LOWER) else w.capitalize()
        for i, w in enumerate(words)
    )


def extract_section(text: str, header_re: re.Pattern) -> str:
    """Return text of first matching section, up to the next ## header."""
    m = header_re.search(text)
    if not m:
        return ""
    start = m.end()
    rest = text[start:]
    next_section = ANY_SECTION.search(rest)
    section_text = rest[:next_section.start()] if next_section else rest
    section_text = section_text.strip()
    if len(section_text) > EXCERPT_MAX_CHARS:
        section_text = section_text[:EXCERPT_MAX_CHARS] + "..."
    return section_text


def get_confirmed_links(text: str) -> set[str]:
    """Return set of [[link]] targets that are NOT inside HTML comments."""
    clean = COMMENT_RE.sub('', text)
    return {m.group(1).strip() for m in WIKILINK_RE.finditer(clean)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vault-dir', required=True, help='Vault root directory')
    args = p.parse_args()

    vault = Path(args.vault_dir).expanduser()
    papers_dir = vault / '20-Sources' / 'papers'
    galaxy_dir = vault / '30-Galaxy'

    if not papers_dir.exists():
        print(json.dumps({'error': f'Papers dir not found: {papers_dir}'}))
        sys.exit(1)

    # Existing Galaxy slugs
    existing_slugs = {p.stem for p in galaxy_dir.glob('*.md')} if galaxy_dir.exists() else set()

    # Scan paper notes for confirmed links
    concept_to_papers: dict[str, list[str]] = {}
    total_papers = 0

    for note in sorted(papers_dir.glob('*.md')):
        total_papers += 1
        text = note.read_text(errors='replace')
        links = get_confirmed_links(text)
        for link in links:
            slug = slugify(link)
            if not slug:
                continue
            concept_to_papers.setdefault(slug, []).append(note.stem)

    # Partition into missing vs already_exists
    missing_slugs = {s for s in concept_to_papers if s not in existing_slugs}
    already_exists = [s for s in concept_to_papers if s in existing_slugs]

    # Build output for missing concepts with excerpts from linking papers
    missing = []
    for slug in sorted(missing_slugs):
        paper_keys = concept_to_papers[slug]
        source_papers = []
        for key in paper_keys:
            note_path = papers_dir / f'{key}.md'
            if not note_path.exists():
                continue
            text = note_path.read_text(errors='replace')
            abstract = extract_section(text, ABSTRACT_HEADERS)
            summary = extract_section(text, SUMMARY_HEADERS)
            source_papers.append({
                'key': key,
                'abstract_excerpt': abstract,
                'summary_excerpt': summary,
            })
        missing.append({
            'slug': slug,
            'title_case': title_case(slug),
            'source_papers': source_papers,
        })

    print(json.dumps({
        'missing': missing,
        'already_exists': sorted(already_exists),
        'total_papers_scanned': total_papers,
        'total_confirmed_links': sum(len(v) for v in concept_to_papers.values()),
    }, indent=2))


if __name__ == '__main__':
    main()
