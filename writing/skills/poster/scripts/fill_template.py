#!/usr/bin/env python3
"""Fill identity/layout placeholders in the poster LaTeX template.

Reads config.local (bash key=value format), computes layout parameters,
substitutes all %%PLACEHOLDER%% markers except %%POSTER_BODY%%.
%%POSTER_BODY%% is left in place for Claude to fill with generated content.

Usage:
  fill_template.py --template PATH --config PATH
                   [--size a0|a1|a2|a3]
                   [--orientation portrait|landscape]
                   [--colortheme NAME]
                   [--conference "NAME"]
                   [--date "DATE"]
                   [--title "TITLE"]
                   [--logo-left PATH]
                   [--logo-right PATH]
                   [--output PATH]      (default: stdout)

Substitutions performed:
  %%SIZE%%           → --size value
  %%ORIENTATION%%    → --orientation value
  %%SCALE%%          → derived from size table (a0=1.3, a1=1.1, a2=0.9, a3=0.7)
  %%COLORTHEME%%     → --colortheme value
  %%COLUMN_LAYOUT%%  → \\setlength lines for sep/colwidth
  %%LOGO_LEFT%%      → \\logoleft{...} or empty if path missing/unset
  %%LOGO_RIGHT%%     → \\logoright{...} or empty if path missing/unset
  %%CONFERENCE%%     → --conference value
  %%DATE%%           → --date value
  %%EMAIL%%          → POSTER_EMAIL from config
  %%TITLE%%          → --title value
  %%AUTHOR%%         → POSTER_AUTHOR from config
  %%AFFILIATION%%    → POSTER_AFFILIATION from config

%%POSTER_BODY%% is intentionally left untouched.
"""

import argparse
import re
import sys
from pathlib import Path

SCALE_TABLE = {"a0": "1.3", "a1": "1.1", "a2": "0.9", "a3": "0.7"}


def read_config(config_path):
    config = {}
    try:
        text = Path(config_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return config
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def column_layout(size, orientation):
    if orientation == "portrait":
        return (
            r"\setlength{\sepwidth}{0.03\paperwidth}" + "\n"
            + r"\setlength{\colwidth}{0.45\paperwidth}"
        )
    if size in ("a0", "a1"):
        return (
            r"\setlength{\sepwidth}{0.025\paperwidth}" + "\n"
            + r"\setlength{\colwidth}{0.29\paperwidth}"
        )
    return (
        r"\setlength{\sepwidth}{0.03\paperwidth}" + "\n"
        + r"\setlength{\colwidth}{0.45\paperwidth}"
    )


def logo_line(cmd, path):
    if not path:
        return ""
    if not Path(path).exists():
        print(f"Warning: logo path not found: {path}", file=sys.stderr)
        return ""
    return f"\\{cmd}{{\\includegraphics[height=5cm]{{{path}}}}}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, metavar="PATH")
    parser.add_argument("--config", required=True, metavar="PATH",
                        help="Path to config.local")
    parser.add_argument("--size", default="a0",
                        choices=["a0", "a1", "a2", "a3"])
    parser.add_argument("--orientation", default="portrait",
                        choices=["portrait", "landscape"])
    parser.add_argument("--colortheme", default="um")
    parser.add_argument("--conference", default="%%CONFERENCE%%")
    parser.add_argument("--date", default="%%DATE%%")
    parser.add_argument("--title", default="%%TITLE%%")
    parser.add_argument("--logo-left", default=None, dest="logo_left")
    parser.add_argument("--logo-right", default=None, dest="logo_right")
    parser.add_argument("--output", default=None, metavar="PATH")
    args = parser.parse_args()

    config = read_config(args.config)

    logo_left_path = args.logo_left or config.get("POSTER_LOGO_LEFT", "")
    logo_right_path = args.logo_right or config.get("POSTER_LOGO_RIGHT", "")

    subs = {
        "SIZE": args.size,
        "ORIENTATION": args.orientation,
        "SCALE": SCALE_TABLE.get(args.size, "1.0"),
        "COLORTHEME": args.colortheme,
        "COLUMN_LAYOUT": column_layout(args.size, args.orientation),
        "LOGO_LEFT": logo_line("logoleft", logo_left_path),
        "LOGO_RIGHT": logo_line("logoright", logo_right_path),
        "CONFERENCE": args.conference,
        "DATE": args.date,
        "TITLE": args.title,
        "EMAIL": config.get("POSTER_EMAIL", "%%EMAIL%%"),
        "AUTHOR": config.get("POSTER_AUTHOR", "%%AUTHOR%%"),
        "AFFILIATION": config.get("POSTER_AFFILIATION", "%%AFFILIATION%%"),
    }

    text = Path(args.template).read_text(encoding="utf-8")
    for placeholder, value in subs.items():
        text = text.replace(f"%%{placeholder}%%", value)

    remaining = sorted(set(re.findall(r"%%[A-Z_]+%%", text)))
    print(
        f"Filled {len(subs)} placeholders. Remaining for Claude: {remaining}",
        file=sys.stderr,
    )

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
