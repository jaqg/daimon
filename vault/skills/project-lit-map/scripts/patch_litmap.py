#!/usr/bin/env python3
"""Write or update literature-map.md from Claude's themed groupings.

Usage:
    python3 patch_litmap.py \\
        --project-dir <path> \\
        --papers-dir <path> \\
        --groupings-file <json-file> \\
        [--update] \\
        [--dry-run]

In normal mode: writes a fresh literature-map.md.
In --update mode: appends only new papers (those not already in the file).
Prints a unified diff on --dry-run.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path


def _diff(original: str, modified: str, filename: str) -> list[str]:
    return list(difflib.unified_diff(
        original.splitlines(),
        modified.splitlines(),
        fromfile=f'a/{filename}',
        tofile=f'b/{filename}',
        lineterm='',
    ))


def slugs_in_map(text: str) -> set[str]:
    """Return set of slugs already referenced in the literature map."""
    return set(re.findall(r'\[\[([^\]]+)\]\]|\*\*\[([^\]]+)\]', text))


def paper_header_line(slug: str, papers_meta: dict) -> str:
    """Return a formatted header line for a paper entry."""
    meta = papers_meta.get(slug, {})
    title = meta.get('title', slug)
    authors = meta.get('authors', '')
    year = meta.get('year', '')
    parts = [f'**[[{slug}]]**']
    if authors:
        # First author only
        first_author = authors.split(',')[0].strip()
        parts.append(f'({first_author}')
        if year:
            parts[-1] += f', {year}'
        parts[-1] += ')'
    elif year:
        parts.append(f'({year})')
    return ' '.join(parts)


def build_fresh_map(themes: list[dict], papers_meta: dict, project_id: str) -> str:
    """Build a complete literature-map.md from scratch."""
    lines = [
        '---',
        'status: Seed',
        'type: SOP',
        f'subject: [{project_id}]',
        '---',
        '',
        f'# Literature Map — {project_id.replace("-", " ")}',
        '',
        f'*{sum(len(t["papers"]) for t in themes)} papers across {len(themes)} themes.*',
        '',
    ]

    for theme in themes:
        lines.append(f'## {theme["name"]}')
        lines.append('')
        for paper in theme.get('papers', []):
            slug = paper['slug']
            annotation = paper.get('annotation', '')
            header = paper_header_line(slug, papers_meta)
            lines.append(f'- {header}')
            if annotation:
                lines.append(f'  {annotation}')
        lines.append('')

    return '\n'.join(lines)


def build_update_section(new_papers_by_theme: list[dict], papers_meta: dict) -> str:
    """Build a 'Recent additions' section for --update mode."""
    if not any(t.get('papers') for t in new_papers_by_theme):
        return ''

    lines = ['## Recent additions', '']
    for theme in new_papers_by_theme:
        if not theme.get('papers'):
            continue
        lines.append(f'*{theme["name"]}*')
        lines.append('')
        for paper in theme['papers']:
            slug = paper['slug']
            annotation = paper.get('annotation', '')
            header = paper_header_line(slug, papers_meta)
            lines.append(f'- {header}')
            if annotation:
                lines.append(f'  {annotation}')
        lines.append('')

    return '\n'.join(lines)


def load_papers_meta(papers_dir: Path, slugs: list[str]) -> dict:
    """Load minimal metadata for listed slugs from papers-dir."""
    from collect_papers import parse_frontmatter, extract_title, extract_authors
    meta = {}
    for slug in slugs:
        path = papers_dir / f'{slug}.md'
        if not path.exists():
            meta[slug] = {}
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            meta[slug] = {}
            continue
        fm, body = parse_frontmatter(text)
        year_raw = fm.get('year', '')
        try:
            year = int(str(year_raw))
        except (ValueError, TypeError):
            year = None
        meta[slug] = {
            'title': extract_title(body, slug),
            'authors': extract_authors(body),
            'year': year,
        }
    return meta


def main():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))

    parser = argparse.ArgumentParser()
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--papers-dir', required=True)
    parser.add_argument('--groupings-file', required=True)
    parser.add_argument('--project-id', default='', help='Project ID for frontmatter; defaults to project-dir name')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    papers_dir = Path(args.papers_dir)
    map_path = project_dir / 'literature-map.md'

    try:
        groupings = json.loads(Path(args.groupings_file).read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        print(f'Error reading groupings: {e}', file=sys.stderr)
        sys.exit(1)

    themes = groupings.get('themes', [])
    all_slugs = [p['slug'] for t in themes for p in t.get('papers', [])]
    papers_meta = load_papers_meta(papers_dir, all_slugs)

    project_id = args.project_id or project_dir.name

    original = map_path.read_text(encoding='utf-8') if map_path.exists() else ''

    if args.update and original:
        existing_slugs = slugs_in_map(original)
        # Only keep papers not yet mapped
        new_themes = []
        for theme in themes:
            new_papers = [p for p in theme.get('papers', []) if p['slug'] not in existing_slugs]
            if new_papers:
                new_themes.append({'name': theme['name'], 'papers': new_papers})
        if not new_themes:
            print('No new papers to add — literature-map.md is up to date.')
            sys.exit(0)
        addition = build_update_section(new_themes, papers_meta)
        modified = original.rstrip('\n') + '\n\n' + addition
    else:
        modified = build_fresh_map(themes, papers_meta, project_id)

    if args.dry_run:
        diffs = _diff(original, modified, 'literature-map.md')
        if diffs:
            print('\n'.join(diffs))
        else:
            print('(no changes)')
        sys.exit(0)

    map_path.write_text(modified, encoding='utf-8')
    action = 'Updated' if original else 'Created'
    print(f'{action} {map_path}')


if __name__ == '__main__':
    main()
