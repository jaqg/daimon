#!/usr/bin/env python3
"""Scan vault 00-Inbox/ and return structured JSON for Claude to process.

Usage:
  scan_inbox.py --vault-dir PATH

Output (stdout, JSON):
{
  "emails": [{"file", "email_type", "frontmatter", "content"}],
  "loose_notes": [{"file", "frontmatter", "first_200_chars"}],
  "daily_notes": [{"file", "frontmatter"}],
  "stats": {"total", "emails", "loose_notes", "daily_notes"}
}

Emails get full content. Loose notes get frontmatter + 200-char preview only
(Claude needs content to categorize but not the full text for routing decisions).
Daily notes get frontmatter only.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DAILY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def parse_frontmatter(text):
    """Extract YAML frontmatter. Returns (dict, body_str). No YAML dep required."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")

    fm = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        fm[key] = value

    return fm, body


def scan_inbox(vault_dir):
    inbox = Path(vault_dir) / "00-Inbox"
    if not inbox.exists():
        return {"error": f"00-Inbox not found at {inbox}"}

    emails = []
    loose_notes = []
    daily_notes = []

    for path in sorted(inbox.glob("*.md")):
        filename = path.name
        text = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)

        if filename.startswith("email-"):
            email_type = (
                fm.get("email-type")
                or fm.get("email_type")
                or "other"
            )
            emails.append({
                "file": filename,
                "email_type": email_type,
                "frontmatter": fm,
                "content": text,
            })
        elif DAILY_PATTERN.match(filename):
            daily_notes.append({
                "file": filename,
                "frontmatter": fm,
            })
        else:
            loose_notes.append({
                "file": filename,
                "frontmatter": fm,
                "first_200_chars": body[:200].strip() if body else "",
            })

    total = len(emails) + len(loose_notes) + len(daily_notes)
    return {
        "emails": emails,
        "loose_notes": loose_notes,
        "daily_notes": daily_notes,
        "stats": {
            "total": total,
            "emails": len(emails),
            "loose_notes": len(loose_notes),
            "daily_notes": len(daily_notes),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-dir", required=True, metavar="PATH",
                        help="Path to vault root directory")
    args = parser.parse_args()

    result = scan_inbox(args.vault_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
