"""Okabe-Ito palette — single source of truth for plot colors.

The mplstyles in ../styles/ must carry the same colors in their
axes.prop_cycle. check_style_sync() parses paper.mplstyle and asserts
the two stay in sync; render.py calls it before every render.
"""

import os
import re

# Order matters: series color "auto" consumes the prop_cycle in this order.
PALETTE = {
    "sky_blue": "#56B4E9",
    "orange": "#E69F00",
    "bluish_green": "#009E73",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
    "yellow": "#F0E442",
}

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def resolve_color(spec_color):
    """Map spec color to matplotlib color. None means 'let prop_cycle decide'."""
    if spec_color is None or spec_color == "auto":
        return None
    if spec_color in PALETTE:
        return PALETTE[spec_color]
    if _HEX_RE.match(spec_color):
        return spec_color if spec_color.startswith("#") else "#" + spec_color
    raise ValueError(
        "unknown color %r; use 'auto', a palette name (%s), or a #RRGGBB hex"
        % (spec_color, ", ".join(PALETTE))
    )


def check_style_sync(style_path=None):
    """Assert paper.mplstyle prop_cycle colors == PALETTE (in order)."""
    if style_path is None:
        style_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "styles", "paper.mplstyle"
        )
    with open(style_path) as fh:
        text = fh.read()
    m = re.search(r"axes\.prop_cycle:\s*\(cycler\(color=\[([^\]]+)\]\)", text)
    if not m:
        raise ValueError("no axes.prop_cycle color list found in %s" % style_path)
    found = ["#" + c.strip().strip("'\"") for c in m.group(1).split(",")]
    expected = list(PALETTE.values())
    if found != expected:
        raise ValueError(
            "prop_cycle in %s out of sync with palette.py: %s != %s"
            % (style_path, found, expected)
        )
    return True
