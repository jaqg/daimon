#!/usr/bin/env python3
"""Collect paper notes tagged with a project ID.

Usage:
    python3 collect_papers.py --project <id> --papers-dir <path>
    python3 collect_papers.py --project <id> --papers-dir <path> --exclude-slugs slug1,slug2

Reads all *.md files in papers-dir whose `project:` frontmatter includes <id>.
Outputs a JSON array of paper metadata.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). Handles YAML list and scalar forms."""
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip('\n')
    fm: dict = {}
    for line in fm_text.splitlines():
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip()
        val = val.strip()
        # Parse YAML list: [a, b] or - item style
        if val.startswith('[') and val.endswith(']'):
            items = [v.strip().strip('"\'') for v in val[1:-1].split(',') if v.strip()]
            fm[key] = items
        elif val:
            fm[key] = val
    return fm, body


def extract_key_relevance(body: str) -> str:
    """Extract 'Relevance to project' line from Key points section."""
    m = re.search(r'\*\*Relevance to project:\*\*\s*(.+)', body)
    if m:
        text = m.group(1).strip()
        return text[:200]
    # Fallback: first non-empty line of Summary section
    sm = re.search(r'## Summary\n+(.+)', body)
    if sm:
        return sm.group(1).strip()[:200]
    return ''


def extract_title(body: str, fallback_slug: str) -> str:
    """Extract title from first H1, or derive from slug."""
    m = re.search(r'^# (.+)', body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback_slug.replace('-', ' ').title()


def extract_authors(body: str) -> str:
    """Extract authors from **Authors:** line."""
    m = re.search(r'\*\*Authors?:\*\*\s*(.+)', body)
    if m:
        authors = m.group(1).strip()
        # Trim after | (venue separator)
        if '|' in authors:
            authors = authors[:authors.index('|')].strip()
        return authors
    return ''


def extract_why_included(body: str) -> str:
    """Extract Why included field."""
    m = re.search(r'\*\*Why included:\*\*\s*(.+)', body)
    return m.group(1).strip() if m else ''


def project_matches(fm_project, project_id: str) -> bool:
    """Check if project frontmatter matches the given project ID."""
    if isinstance(fm_project, list):
        return project_id in fm_project
    if isinstance(fm_project, str):
        # Handle [ProjectID] string format
        stripped = fm_project.strip('[]')
        return project_id in [p.strip() for p in stripped.split(',')]
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--papers-dir', required=True)
    parser.add_argument('--exclude-slugs', default='', help='Comma-separated slugs to exclude')
    args = parser.parse_args()

    papers_dir = Path(args.papers_dir)
    exclude = set(s.strip() for s in args.exclude_slugs.split(',') if s.strip())

    results = []
    for md_file in sorted(papers_dir.glob('*.md')):
        slug = md_file.stem
        if slug in exclude:
            continue
        try:
            text = md_file.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue

        fm, body = parse_frontmatter(text)
        fm_project = fm.get('project')
        if fm_project is None:
            continue
        if not project_matches(fm_project, args.project):
            continue

        # Parse year
        year_raw = fm.get('year', '')
        try:
            year = int(str(year_raw))
        except (ValueError, TypeError):
            year = None

        # Parse screening score
        score_raw = fm.get('screening_score', '')
        try:
            score = int(str(score_raw))
        except (ValueError, TypeError):
            score = None

        results.append({
            'slug': slug,
            'title': extract_title(body, slug),
            'authors': extract_authors(body),
            'year': year,
            'subject_tags': fm.get('subject', []) if isinstance(fm.get('subject'), list) else
                           [t.strip() for t in str(fm.get('subject', '')).strip('[]').split(',') if t.strip()],
            'why_included': extract_why_included(body),
            'key_relevance': extract_key_relevance(body),
            'screening_score': score,
        })

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
