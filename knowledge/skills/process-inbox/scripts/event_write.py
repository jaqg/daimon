#!/usr/bin/env python3
"""Write an event schema into the vault conference tracker (mode B writer).

Usage:
  event_write.py --schema SCHEMA.json --events PATH [--today YYYY-MM-DD]

Behaviour (plan §3 / SKILL.md § conference rules):
  * upserts a table row, deduped on normalised event name
    (normalised = lowercase, all non-alphanumeric stripped; containment match
    so "Short — Full" cells match a bare full-name schema);
  * appends/upserts the `### ...` block under `## Event Summaries`;
  * re-sorts the WHOLE table ascending by earliest upcoming registration
    deadline; rows with no deadline or past-only deadlines go last
    (stable, original order preserved inside each group);
  * writes `—` for missing fields; a null schema field never clobbers an
    existing cell (new value wins only when non-null);
  * duplicate pass with identical schema → byte-identical file, no write
    (action=no_change);
  * null event_name → prints a not-an-event message, writes nothing.

Prints a JSON summary on stdout: {"action": "created|updated|no_change|refused", ...}.
Exit 0 on success, 2 on usage/IO error.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

DASH = "—"
TABLE_HEADER = "| Conference | Relevance | Abstract deadline | Registration deadline | Dates | Location | Cost |"
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATE_RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[–-](\d{4}-\d{2}-\d{2})$")
HEADINGS_RE = re.compile(r"^#{2,3} ")


def norm(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def same_event(cell, name):
    a, b = norm(cell), norm(name)
    if not a or not b:
        return False
    return a == b or a.endswith(b) or b.endswith(a)


def compress_dates(value):
    """'2026-10-06–2026-10-08' -> '2026-10-06 – 08'; cross-month -> ' – MM-DD'."""
    m = DATE_RANGE_RE.match((value or "").strip())
    if not m:
        return value
    a, b = m.groups()
    if a[:7] == b[:7]:
        return f"{a} – {b[8:]}"
    if a[:4] == b[:4]:
        return f"{a} – {b[5:]}"
    return f"{a} – {b}"


def cell(value, compress=False):
    if not value:
        return DASH
    return compress_dates(value) if compress else str(value)


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def join_row(cells):
    return "| " + " | ".join(cells) + " |"


def display_name(schema):
    series = schema.get("series")
    name = schema.get("event_name") or ""
    if series and norm(series) not in norm(name):
        return f"{series} — {name}"
    return name


def build_row(schema, existing=None):
    old = existing or [DASH] * 7
    new = [
        display_name(schema),
        cell(schema.get("relevance")),
        cell(schema.get("abstract_deadline")),
        cell(schema.get("registration_deadline")),
        cell(schema.get("dates"), compress=True),
        cell(schema.get("location")),
        cell(schema.get("cost")),
    ]
    # Non-null schema values win; null schema fields keep the existing cell.
    if existing:
        new = [nv if nv != DASH else ov for nv, ov in zip(new, old)]
        # Keep an existing "Short — Full" conference cell when it already
        # contains this event's name (dedupe match); only a bare/absent cell
        # gets rewritten.
        if old[0] != DASH and same_event(old[0], name := schema.get("event_name")):
            new[0] = old[0]
    return new


def build_summary(schema):
    urls = schema.get("urls") or {}
    lines = [f"### {display_name(schema)}"]
    lines.append(f"- **Dates:** {cell(schema.get('dates'), compress=True)}")
    lines.append(f"- **Location:** {cell(schema.get('location'))}")
    lines.append(f"- **Homepage:** {cell(urls.get('homepage'))}")
    lines.append(f"- **Registration:** {cell(urls.get('registration'))}")
    if urls.get("abstracts"):
        lines.append(f"- **Abstract submission:** {urls['abstracts']}")
    relevance = schema.get("relevance")
    reason = schema.get("relevance_reason")
    if relevance and reason:
        lines.append(f"- **Relevance:** {relevance} — {reason}")
    elif relevance:
        lines.append(f"- **Relevance:** {relevance}")
    else:
        lines.append(f"- **Relevance:** {DASH}")
    lines.append(f"- **Notes:** {DASH}")
    return lines


def sort_rows(rows, today):
    """Ascending by earliest upcoming registration deadline; others last."""

    def key(cells):
        reg = cells[3] if len(cells) > 3 else ""
        upcoming = [d for d in ISO_RE.findall(reg) if d >= today]
        if upcoming:
            return (0, min(upcoming))
        return (1, "")

    return sorted(rows, key=key)  # stable


def process(text, schema, today):
    """Return (new_text, action)."""
    lines = text.split("\n")

    # --- locate table ---
    hdr = next((i for i, l in enumerate(lines) if l.startswith("| Conference |")), None)
    if hdr is None:
        return text, "error: no conference table found"
    sep = hdr + 1
    if sep >= len(lines) or not lines[sep].startswith("| ---"):
        return text, "error: malformed table (no separator row)"
    end = sep + 1
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1

    rows = [split_row(l) for l in lines[sep + 1:end]]
    rows = [r + [DASH] * (7 - len(r)) for r in rows]

    # --- upsert row ---
    name = schema.get("event_name")
    idx = next((i for i, r in enumerate(rows) if same_event(r[0], name)), None)
    if idx is None:
        rows.append(build_row(schema))
        row_action = "row_created"
    else:
        updated = build_row(schema, existing=rows[idx])
        if updated == rows[idx]:
            row_action = "row_unchanged"
        else:
            rows[idx] = updated
            row_action = "row_updated"

    rows = sort_rows(rows, today)
    table = [join_row(r) for r in rows]

    # --- summary block upsert ---
    sum_hdr = next((i for i, l in enumerate(lines) if l.strip() == "## Event Summaries"), None)
    if sum_hdr is None:
        lines = lines + ["", "---", "", "## Event Summaries"]
        sum_hdr = len(lines) - 1

    new_block = build_summary(schema)
    block_start = None
    for i in range(sum_hdr + 1, len(lines)):
        if lines[i].startswith("### "):
            if same_event(lines[i][4:], name):
                block_start = i
            elif block_start is not None:
                break
        elif lines[i].startswith("## ") and block_start is not None:
            break
    if block_start is None:
        # append at end of file (summaries is the last section)
        while lines and lines[-1] == "":
            lines.pop()
        lines = lines + [""] + new_block
        sum_action = "summary_created"
    else:
        b_end = block_start + 1
        while b_end < len(lines) and not lines[b_end].startswith("### ") and not lines[b_end].startswith("## "):
            b_end += 1
        old_block = [l for l in lines[block_start:b_end] if l != ""]
        if old_block == new_block:
            sum_action = "summary_unchanged"
        else:
            lines[block_start:b_end] = new_block + [""]
            sum_action = "summary_updated"

    # --- splice table back in ---
    new_lines = lines[:sep + 1] + table + lines[end:]

    # block indices shifted only if table length changed — recompute summary
    # location on new_lines instead of trusting stale indices:
    sum_hdr2 = next((i for i, l in enumerate(new_lines) if l.strip() == "## Event Summaries"), None)
    if sum_hdr2 is None:  # pragma: no cover - created above, always present
        return "\n".join(new_lines), "error: summaries section lost"

    new_text = "\n".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"

    changed = new_text != text if text else True
    if not changed:
        return new_text, "no_change"
    if row_action == "row_created":
        action = "created"
    else:
        action = "updated"
    return new_text, action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, metavar="PATH")
    parser.add_argument("--events", required=True, metavar="PATH")
    parser.add_argument("--today", metavar="YYYY-MM-DD",
                        help="override today for deadline sorting (tests)")
    args = parser.parse_args()

    try:
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"action": "error", "detail": f"cannot read schema: {exc}"}))
        return 2

    if not schema.get("event_name"):
        print(json.dumps({
            "action": "refused",
            "detail": "event_name is null — not an event; no writes performed. "
                      "Run /process-inbox for a normal inbox scan instead.",
        }))
        return 0

    today = args.today or datetime.date.today().isoformat()

    events_path = Path(args.events)
    try:
        text = events_path.read_text(encoding="utf-8") if events_path.exists() else ""
    except OSError as exc:
        print(json.dumps({"action": "error", "detail": f"cannot read events file: {exc}"}))
        return 2

    if not text:
        text = ("# Events & Conferences\n\n" + TABLE_HEADER + "\n"
                + "| --- | --- | --- | --- | --- | --- | --- |\n"
                + "\n---\n\n## Event Summaries\n")

    new_text, action = process(text, schema, today)
    if action.startswith("error"):
        print(json.dumps({"action": "error", "detail": action}))
        return 2

    if action != "no_change":
        try:
            events_path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"action": "error", "detail": f"cannot write events file: {exc}"}))
            return 2

    print(json.dumps({"action": action, "events_file": str(events_path)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
