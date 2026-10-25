#!/usr/bin/env python3
"""Deterministic plot renderer: JSON plot spec -> figure(s) -> PDF/PNG.

Usage:
    python3 render.py SPEC.json [--data-dir DIR] [--outdir DIR]

stdout on success:
    {"ok": true, "files": ["/abs/path.pdf", ...], "warnings": [...]}
stdout on failure (exit 1):
    {"error": "<message>", "details": {...}}

No model judgment happens here. Unknown preset/format/field => structured
error; SKILL.md tells the agent to fix the spec or flag the user.
"""

import argparse
import json
import os
import shutil
import string
import sys

import matplotlib

matplotlib.use("Agg")  # must precede pyplot import; no GUI, no display

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palette import PALETTE, check_style_sync, resolve_color

STYLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "styles")

PRESETS = {
    # marker "None" overrides the prop_cycle marker; line presets draw pure lines
    # unless the spec asks for markers explicitly.
    "line": {"series": {"linestyle": "-", "marker": "None"}, "axes": {}},
    "scatter": {"series": {"linestyle": "none", "marker": "o"}, "axes": {}},
    "bar": {"series": {}, "axes": {}},
    "heatmap": {"series": {}, "axes": {}},
    "spectrum_ir": {
        "series": {"linestyle": "-", "marker": "None"},
        "axes": {"x": {"invert": True, "grid": False}, "y": {"grid": False}},
    },
    "spectrum_uvvis": {
        "series": {"linestyle": "-", "marker": "None"},
        "axes": {"x": {"grid": False}, "y": {"grid": False}},
    },
    "energy_profile": {
        "series": {"linestyle": "-", "marker": "None"},
        "axes": {"x": {"grid": False}, "y": {"grid": False}},
    },
    "parity": {
        "series": {"linestyle": "none", "marker": "o"},
        "axes": {"x": {"grid": False}, "y": {"grid": False}},
        "parity_line": True,
    },
    "radial_distribution": {
        "series": {"linestyle": "-", "marker": "None"},
        "axes": {"x": {"grid": False}, "y": {"grid": False}},
    },
}

DATA_FORMATS = ("csv", "tsv", "dat", "npz")
OUTPUT_FORMATS = ("pdf", "png")
STYLES = ("paper", "poster", "screen")

TOP_FIELDS = {"preset", "style", "layout", "output"}
LAYOUT_FIELDS = {"figsize", "nrows", "ncols", "sharex", "sharey", "letters", "panels"}
PANEL_FIELDS = {"series", "axes", "legend", "annotations"}
SERIES_FIELDS = {
    "data", "label", "color", "marker", "linestyle", "yerr",
    "scale", "offset", "x_scale", "x_offset",
}
DATA_FIELDS = {"file", "format", "x", "y", "column"}
AXES_FIELDS = {"label", "lim", "log", "invert", "grid", "minor", "ticklabels"}
ANNOTATION_FIELDS = {"text", "x", "y", "coords", "fontsize", "ha", "va"}
LEGEND_FIELDS = {"on", "loc"}
OUTPUT_FIELDS = {"basename", "formats", "transparent", "outdir"}
COLUMN_FIELDS = {"column"}


class SpecError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def _check_fields(obj, allowed, where):
    unknown = set(obj) - allowed
    if unknown:
        raise SpecError(
            "unknown field(s) in %s: %s" % (where, ", ".join(sorted(unknown))),
            {"where": where, "unknown": sorted(unknown), "allowed": sorted(allowed)},
        )


def _require(obj, key, where):
    if key not in obj:
        raise SpecError("missing required field '%s' in %s" % (key, where),
                        {"where": where, "missing": key})


def _check_column_ref(ref, where):
    if isinstance(ref, int):
        return
    if isinstance(ref, dict):
        _check_fields(ref, COLUMN_FIELDS, where)
        _require(ref, "column", where)
        if not isinstance(ref["column"], (str, int)):
            raise SpecError("'%s.column' must be a column name or integer index" % where)
        return
    raise SpecError("'%s' must be {\"column\": name-or-index}" % where)


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    _check_fields(spec, TOP_FIELDS, "spec")
    _require(spec, "preset", "spec")
    if spec["preset"] not in PRESETS:
        raise SpecError(
            "unknown preset %r (available: %s); abort and ask the user to "
            "extend the skill — do not improvise" % (spec["preset"], ", ".join(sorted(PRESETS))),
            {"preset": spec["preset"], "available": sorted(PRESETS)},
        )
    style = spec.get("style", "paper")
    if style not in STYLES:
        raise SpecError("unknown style %r (available: %s)" % (style, ", ".join(STYLES)))

    _require(spec, "layout", "spec")
    layout = spec["layout"]
    if not isinstance(layout, dict):
        raise SpecError("'layout' must be an object")
    _check_fields(layout, LAYOUT_FIELDS, "layout")
    _require(layout, "panels", "layout")
    panels = layout["panels"]
    if not isinstance(panels, list) or not panels:
        raise SpecError("'layout.panels' must be a non-empty array")
    nrows, ncols = layout.get("nrows"), layout.get("ncols")
    if nrows is None and ncols is None:
        nrows, ncols = 1, len(panels)
    elif nrows is None or ncols is None:
        raise SpecError("layout.nrows and layout.ncols must be given together")
    elif nrows * ncols != len(panels):
        raise SpecError(
            "nrows*ncols (%d*%d) != len(panels) (%d)" % (nrows, ncols, len(panels)),
            {"nrows": nrows, "ncols": ncols, "panels": len(panels)},
        )
    if layout.get("letters") not in (None, "auto"):
        raise SpecError("layout.letters must be 'auto' or absent")

    for i, panel in enumerate(panels):
        _validate_panel(panel, i, spec["preset"])

    _require(spec, "output", "spec")
    out = spec["output"]
    if not isinstance(out, dict):
        raise SpecError("'output' must be an object")
    _check_fields(out, OUTPUT_FIELDS, "output")
    _require(out, "basename", "output")
    if not isinstance(out["basename"], str) or not out["basename"]:
        raise SpecError("output.basename must be a non-empty string")
    formats = out.get("formats", ["pdf", "png"])
    if not isinstance(formats, list) or not formats:
        raise SpecError("output.formats must be a non-empty array")
    for fmt in formats:
        if fmt not in OUTPUT_FORMATS:
            raise SpecError(
                "unknown output format %r (v1 supports: %s); abort and ask the "
                "user to extend the skill" % (fmt, ", ".join(OUTPUT_FORMATS)),
                {"format": fmt, "available": list(OUTPUT_FORMATS)},
            )
    if "transparent" in out and not isinstance(out["transparent"], bool):
        raise SpecError("output.transparent must be a real JSON boolean (true/false)")


def _validate_panel(panel, i, preset):
    where = "layout.panels[%d]" % i
    if not isinstance(panel, dict):
        raise SpecError("%s must be an object" % where)
    _check_fields(panel, PANEL_FIELDS, where)
    _require(panel, "series", where)
    series = panel["series"]
    if not isinstance(series, list) or not series:
        raise SpecError("%s.series must be a non-empty array" % where)
    if preset == "heatmap" and len(series) != 1:
        raise SpecError("heatmap panels take exactly one series (the matrix)", {"where": where})
    for j, s in enumerate(series):
        _validate_series(s, "%s.series[%d]" % (where, j), preset)
    axes = panel.get("axes", {})
    if not isinstance(axes, dict):
        raise SpecError("%s.axes must be an object" % where)
    for axis in ("x", "y"):
        if axis in axes:
            if not isinstance(axes[axis], dict):
                raise SpecError("%s.axes.%s must be an object" % (where, axis))
            _check_fields(axes[axis], AXES_FIELDS, "%s.axes.%s" % (where, axis))
            if "lim" in axes[axis]:
                lim = axes[axis]["lim"]
                if (not isinstance(lim, list) or len(lim) != 2
                        or not all(isinstance(v, (int, float)) for v in lim)):
                    raise SpecError("%s.axes.%s.lim must be [min, max] of numbers"
                                    % (where, axis))
            if "ticklabels" in axes[axis]:
                tl = axes[axis]["ticklabels"]
                if not isinstance(tl, list) or not all(isinstance(t, str) for t in tl):
                    raise SpecError("%s.axes.%s.ticklabels must be an array of strings"
                                    % (where, axis))
    for j, ann in enumerate(panel.get("annotations", [])):
        where_a = "%s.annotations[%d]" % (where, j)
        if not isinstance(ann, dict):
            raise SpecError("%s must be an object" % where_a)
        _check_fields(ann, ANNOTATION_FIELDS, where_a)
        for key in ("text", "x", "y"):
            _require(ann, key, where_a)
        if ann.get("coords", "data") not in ("data", "axes"):
            raise SpecError("%s.coords must be 'data' or 'axes'" % where_a)
    legend = panel.get("legend")
    if legend is not None:
        if not isinstance(legend, dict):
            raise SpecError("%s.legend must be an object" % where)
        _check_fields(legend, LEGEND_FIELDS, "%s.legend" % where)


def _validate_series(s, where, preset):
    if not isinstance(s, dict):
        raise SpecError("%s must be an object" % where)
    _check_fields(s, SERIES_FIELDS, where)
    _require(s, "data", where)
    data = s["data"]
    if not isinstance(data, dict):
        raise SpecError("%s.data must be an object" % where)
    _check_fields(data, DATA_FIELDS, "%s.data" % where)
    _require(data, "file", "%s.data" % where)
    _require(data, "format", "%s.data" % where)
    if data["format"] not in DATA_FORMATS:
        raise SpecError(
            "unknown data format %r in %s (v1 supports: %s); abort and ask the "
            "user to extend the skill" % (data["format"], where, ", ".join(DATA_FORMATS)),
            {"format": data["format"], "available": list(DATA_FORMATS), "where": where},
        )
    if "color" in s:
        try:
            resolve_color(s["color"])
        except ValueError as exc:
            raise SpecError("%s: %s" % (where, exc))
    if "yerr" in s:
        _check_column_ref(s["yerr"], "%s.yerr" % where)
    if preset == "heatmap":
        # matrix comes from the whole file; x/y refs are meaningless
        for key in ("x", "y"):
            if key in data:
                raise SpecError("heatmap series must not set data.%s (whole file is the matrix)"
                                % key, {"where": where})
    else:
        _require(data, "x", "%s.data" % where)
        _require(data, "y", "%s.data" % where)
        _check_column_ref(data["x"], "%s.data.x" % where)
        _check_column_ref(data["y"], "%s.data.y" % where)


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------

def _is_number(tok):
    try:
        float(tok)
        return True
    except ValueError:
        return False


def load_table(path, fmt, data_dir):
    """Return table dict: for npz {key: array}; else {'names': [...], 'data': 2D array}."""
    full = os.path.join(data_dir, path)
    if not os.path.isfile(full):
        raise SpecError("data file not found: %s" % full, {"file": path, "resolved": full})
    if fmt == "npz":
        try:
            z = np.load(full)
        except Exception as exc:
            raise SpecError("cannot read npz %s: %s" % (path, exc))
        return {"npz": {k: np.asarray(z[k]) for k in z.files}}
    delimiter = {"csv": ",", "tsv": "\t"}.get(fmt)
    with open(full) as fh:
        first = fh.readline()
    tokens = [t for t in (first.strip().split(",") if fmt == "csv"
                          else first.strip().split() if fmt == "tsv"
                          else first.split()) if t != ""]
    has_header = bool(tokens) and not all(_is_number(t) for t in tokens)
    if has_header:
        names = tokens
        skip = 1
    else:
        names = None
        skip = 0
    try:
        data = np.loadtxt(full, delimiter=delimiter, skiprows=skip, ndmin=2)
    except Exception as exc:
        raise SpecError("cannot parse %s as %s: %s" % (path, fmt, exc))
    if names is None:
        names = [str(i) for i in range(data.shape[1])]
    elif len(names) != data.shape[1]:
        raise SpecError(
            "header/column count mismatch in %s: %d names, %d columns"
            % (path, len(names), data.shape[1])
        )
    return {"names": names, "data": data.T, "has_header": has_header}


def get_column(table, ref, where):
    """ref: int index or {'column': name-or-index}. Returns 1D array."""
    index = ref if isinstance(ref, int) else ref["column"]
    if "npz" in table:
        keys = sorted(table["npz"])
        if isinstance(index, int):
            if not 0 <= index < len(keys):
                raise SpecError("npz index %d out of range (%d arrays) in %s"
                                % (index, len(keys), where))
            return table["npz"][keys[index]]
        if index not in table["npz"]:
            raise SpecError("npz key %r not found in %s (available: %s)"
                            % (index, where, ", ".join(keys)))
        return table["npz"][index]
    names, data = table["names"], table["data"]
    if isinstance(index, int):
        if not 0 <= index < len(names):
            raise SpecError("column index %d out of range (%d columns) in %s"
                            % (index, len(names), where))
    elif index not in names:
        raise SpecError("column %r not found in %s (available: %s)"
                        % (index, where, ", ".join(names)))
    i = index if isinstance(index, int) else names.index(index)
    return data[i]


def load_matrix(table, path, where):
    """Whole-file numeric matrix for heatmap panels."""
    if "npz" in table:
        keys = sorted(table["npz"])
        if len(keys) != 1:
            raise SpecError("heatmap npz must contain exactly one array (found: %s) in %s"
                            % (", ".join(keys), where))
        return table["npz"][keys[0]]
    if table.get("has_header"):
        raise SpecError(
            "heatmap data file %s has a header row; heatmap matrices must be "
            "headerless numeric tables" % path)
    return table["data"].T


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def apply_axes(ax, axis_cfg):
    for axis in ("x", "y"):
        cfg = axis_cfg.get(axis, {})
        if "label" in cfg:
            (ax.set_xlabel if axis == "x" else ax.set_ylabel)(cfg["label"])
        if "lim" in cfg:
            (ax.set_xlim if axis == "x" else ax.set_ylim)(*cfg["lim"])
        if cfg.get("log"):
            (ax.set_xscale if axis == "x" else ax.set_yscale)("log")
        if cfg.get("invert"):
            (ax.invert_xaxis if axis == "x" else ax.invert_yaxis)()
        if "grid" in cfg:
            (ax.xaxis.grid if axis == "x" else ax.yaxis.grid)(bool(cfg["grid"]))
        if cfg.get("minor"):
            ax.minorticks_on()
        if "ticklabels" in cfg:
            labels = cfg["ticklabels"]
            pos = np.linspace(*ax.get_xlim(), len(labels))
            if axis == "x":
                ax.set_xticks(pos)
                ax.set_xticklabels(labels)
            else:
                ax.set_yticks(pos)
                ax.set_yticklabels(labels)


def merge_axes(preset_axes, spec_axes):
    """Preset axis defaults first; explicit spec fields win."""
    merged = {}
    for axis in ("x", "y"):
        cfg = dict(preset_axes.get(axis, {}))
        cfg.update(spec_axes.get(axis, {}))
        if cfg:
            merged[axis] = cfg
    return merged


def render_series(ax, series, preset, table_cache, data_dir, where):
    preset_defaults = PRESETS[preset]["series"]
    data = series["data"]
    table_key = (data["file"], data["format"])
    if table_key not in table_cache:
        table_cache[table_key] = load_table(data["file"], data["format"], data_dir)
    table = table_cache[table_key]

    color = resolve_color(series.get("color"))
    if preset == "heatmap":
        matrix = load_matrix(table, data["file"], where)
        im = ax.imshow(matrix, aspect="auto", origin="lower")
        return im

    x = get_column(table, data["x"], where)
    y = get_column(table, data["y"], where)
    if x.shape != y.shape:
        raise SpecError("x and y columns have different lengths in %s" % where,
                        {"x": x.shape, "y": y.shape})
    y = y * series.get("scale", 1.0) + series.get("offset", 0.0)
    x = x * series.get("x_scale", 1.0) + series.get("x_offset", 0.0)
    yerr = get_column(table, series["yerr"], where) if "yerr" in series else None

    linestyle = series.get("linestyle", preset_defaults.get("linestyle", "-"))
    marker = series.get("marker", preset_defaults.get("marker"))
    label = series.get("label")

    if preset == "bar":
        ax.bar(x, y, color=color, label=label, yerr=yerr, capsize=3)
    elif yerr is not None:
        ax.errorbar(x, y, yerr=yerr, color=color, marker=marker, linestyle=linestyle,
                    label=label, capsize=3)
    else:
        ax.plot(x, y, color=color, marker=marker, linestyle=linestyle, label=label)
    return None


def usetex_available():
    """Deterministic usetex check: PATH lookup + real LaTeX probe.

    Full usetex chain, per matplotlib.texmanager docs:
      latex   — DVI for every TeX string (layout metrics + draw)
      dvipng  — rasterize TeX text for PNG/Agg output
      kpsewhich (or luatex) — locate TeX font maps (pdftex.map) for PDF output
    Any missing piece, or a failing probe run (e.g. cm-super absent) => fallback
    to mathtext + structured warning. Never a traceback.
    Probe result is cached by matplotlib on disk (one LaTeX run per machine).
    """
    missing = [tool for tool in ("latex", "dvipng") if not shutil.which(tool)]
    if missing:
        return False, "not found on PATH: %s" % ", ".join(missing)
    if not (shutil.which("kpsewhich") or shutil.which("luatex")):
        return False, "not found on PATH: kpsewhich/luatex (needed for PDF TeX font maps)"
    try:
        from matplotlib.texmanager import TexManager
        TexManager().make_dvi("lp", 10)
        return True, ""
    except Exception as exc:
        msg = str(exc)
        pkg_err = next((ln for ln in msg.splitlines() if ln.startswith("! ")), None)
        return False, "LaTeX probe failed: %s" % (pkg_err or msg.splitlines()[0])


def render(spec, data_dir, outdir):
    warnings = []
    validate_spec(spec)

    # usetex: deterministic PATH check + probe, no model judgment
    usetex, why_not = usetex_available()
    if usetex:
        matplotlib.rcParams["text.usetex"] = True
    else:
        matplotlib.rcParams["text.usetex"] = False
        matplotlib.rcParams["mathtext.fontset"] = "cm"
        warnings.append({
            "warning": "usetex unavailable (%s); rendered with matplotlib mathtext "
                       "(math labels still render, minor font differences from LaTeX)" % why_not,
        })

    check_style_sync()
    plt.style.use(os.path.join(STYLE_DIR, spec.get("style", "paper") + ".mplstyle"))
    # re-apply rc overrides after style.load (style files set usetex: True)
    if not usetex:
        matplotlib.rcParams["text.usetex"] = False

    layout = spec["layout"]
    panels = layout["panels"]
    nrows, ncols = layout.get("nrows", 1), layout.get("ncols", len(panels))
    fig, axs = plt.subplots(
        nrows, ncols,
        figsize=tuple(layout.get("figsize", (4, 3))),
        sharex=layout.get("sharex", False),
        sharey=layout.get("sharey", False),
        constrained_layout=True,
    )
    axs_flat = np.atleast_1d(axs).ravel()
    preset = spec["preset"]
    table_cache = {}
    images = []

    for i, panel in enumerate(panels):
        ax = axs_flat[i]
        where = "layout.panels[%d]" % i
        for j, series in enumerate(panel["series"]):
            im = render_series(ax, series, preset, table_cache, data_dir,
                               "%s.series[%d]" % (where, j))
            if im is not None:
                images.append((ax, im))
        apply_axes(ax, merge_axes(PRESETS[preset]["axes"], panel.get("axes", {})))
        if PRESETS[preset].get("parity_line"):
            lo, hi = ax.get_xlim()
            ax.plot([lo, hi], [lo, hi], linestyle="--", color="0.5", linewidth=1.0,
                    zorder=0, label="_nolegend_")
            ax.set_aspect("equal", adjustable="box")
        legend = panel.get("legend", {})
        if legend.get("on", False):
            ax.legend(loc=legend.get("loc", "best"))
        for ann in panel.get("annotations", []):
            transform = ax.transAxes if ann.get("coords", "data") == "axes" else ax.transData
            kwargs = {"fontsize": ann.get("fontsize")}
            if "ha" in ann:
                kwargs["ha"] = ann["ha"]
            if "va" in ann:
                kwargs["va"] = ann["va"]
            ax.text(ann["x"], ann["y"], ann["text"], transform=transform,
                    **{k: v for k, v in kwargs.items() if v is not None})

    if layout.get("letters") == "auto":
        for i, ax in enumerate(axs_flat):
            ax.text(-0.08, 1.02, "(%s)" % string.ascii_lowercase[i],
                    transform=ax.transAxes, fontsize="medium", fontweight="bold",
                    va="bottom", ha="right")

    for ax, im in images:
        fig.colorbar(im, ax=ax)

    out = spec["output"]
    os.makedirs(outdir, exist_ok=True)
    transparent = out.get("transparent", False)  # real bool; schema rejects strings
    files = []
    for fmt in out["formats"]:
        path = os.path.join(outdir, "%s.%s" % (out["basename"], fmt))
        fig.savefig(path, transparent=transparent)
        files.append(os.path.abspath(path))
    plt.close(fig)
    return {"ok": True, "files": files, "warnings": warnings}


def _structured_render_error(exc):
    """Map any render/savefig exception to the structured-error contract.

    TeX failures (unbalanced $ in labels, missing tools) carry an actionable
    hint so the model can fix the spec and resubmit; everything else still
    returns JSON — stdout must never be empty.
    """
    msg = str(exc)
    is_latex = (
        (isinstance(exc, RuntimeError) and "latex was not able" in msg)
        or (isinstance(exc, FileNotFoundError)
            and getattr(exc, "filename", "") is not None
            and os.path.basename(str(getattr(exc, "filename", "")))
            in ("latex", "dvipng", "kpsewhich", "luatex"))
        or "matplotlib-support" in msg  # cm-super class of errors
    )
    if is_latex:
        lines = msg.splitlines()
        excerpt = next((ln for ln in lines if ln.startswith("! ")),
                       lines[0] if lines else "latex failed")
        return {
            "error": "latex_render_failed",
            "details": {
                "message": excerpt.strip(),
                "hint": "check $ / { / } balance in labels and annotations "
                        "(unbalanced math delimiters break LaTeX); fix the spec "
                        "and resubmit",
            },
        }
    return {
        "error": "render_failed",
        "details": {"type": type(exc).__name__, "message": msg[:500]},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", help="path to JSON plot spec")
    ap.add_argument("--data-dir", default=None,
                    help="directory for data files (default: spec's directory)")
    ap.add_argument("--outdir", default=None,
                    help="output directory (default: spec's directory)")
    args = ap.parse_args(argv)

    try:
        with open(args.spec) as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "cannot read spec: %s" % exc,
                          "details": {"spec": args.spec}}))
        return 1

    spec_dir = os.path.dirname(os.path.abspath(args.spec))
    data_dir = args.data_dir or spec_dir
    outdir = args.outdir or spec_dir
    try:
        result = render(spec, data_dir, outdir)
    except SpecError as exc:
        print(json.dumps({"error": str(exc), "details": exc.details}))
        return 1
    except Exception as exc:  # contract: stdout is always structured JSON
        print(json.dumps(_structured_render_error(exc)))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
