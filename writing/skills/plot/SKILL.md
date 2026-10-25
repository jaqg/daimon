---
name: plot
description: >
  Generate publication-quality plots (PDF/PNG) from data files via a JSON plot spec
  rendered by a deterministic script. Use when the user says "plot", "plot this",
  "make a figure", "generate plot", "graph", "spectrum plot", "energy profile",
  "parity plot", "RDF", "graficar", "haz un plot", "haz una figura", or asks for any
  chart/figure from CSV/TSV/DAT/NPZ data. You write the spec JSON; you NEVER write
  Python plotting code.
tools: Read, Write, Edit, Bash
---

# plot

Turn data files into figures. You (the agent) make all scientific judgments
(preset choice, column mapping, labels, colors); `scripts/render.py` does all
drawing deterministically. You never generate Python for a plot.

## Invocation

```bash
# $SKILL_DIR = directory of this SKILL.md (verify: readlink -f "$SKILL_MD")
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
RENDER="$SKILL_DIR/scripts/render.py"

# 1. Write the spec JSON (Write tool) next to the data files, e.g. ./plot_spec.json
# 2. Render:
python3 "$RENDER" plot_spec.json --data-dir . --outdir ./figures
```

`--data-dir`: directory where `data.file` paths resolve (default: spec's dir).
`--outdir`: where figures land (default: spec's dir).

stdout on success:

```json
{"ok": true, "files": ["/abs/path/figure.pdf", ".../figure.png"], "warnings": []}
```

stdout on failure (exit 1) — always structured JSON, never a traceback:

```json
{"error": "unknown preset 'violin' ...", "details": {"preset": "violin", "available": [...]}}
```

LaTeX failure in a label/annotation:

```json
{"error": "latex_render_failed",
 "details": {"message": "Extra }, or forgotten $.",
             "hint": "check $ / { / } balance in labels and annotations (unbalanced math delimiters break LaTeX); fix the spec and resubmit"}}
```

## Hard rules

1. **Unknown preset or data format → STOP.** Do not improvise a workaround,
   do not write Python. Tell the user: which preset/format is missing, and that
   the skill needs extending — ask them to request an extension. Same for
   unknown output formats (v1: `pdf`, `png` only).
2. **Never write matplotlib code.** Only JSON spec + `render.py`. If the spec
   cannot express something the user wants, STOP and flag it (extension request).
3. **Error → fix and resubmit.** On `{"error": ...}`, read `details`, correct the
   spec (bad column name, missing file, typo'd field), re-run.
   `latex_render_failed` = broken math syntax in a label/annotation — fix `$`/`{`/`}`
   balance per `details.hint`. After two failed
   attempts on the same spec, STOP and report to the user.
4. Labels/annotations in LaTeX math where chemistry demands it
   (`$\Delta E$`, `cm$^{-1}$`, `$\AA$` → write `(\AA)` or `$\mathrm{\AA}$`).
   TeX renders via LaTeX when available, mathtext fallback otherwise — either
   way, write standard math syntax.

## Supported presets

| Preset | Meaning | Notes |
|--------|---------|-------|
| `line` | Generic x–y line | markers off by default |
| `scatter` | Generic scatter | marker `o`, no line |
| `bar` | Bar chart | x = positions, y = heights, `yerr` supported |
| `heatmap` | Matrix image + colorbar | exactly 1 series; whole file = matrix; no `x`/`y` refs; headerless text file or single-array npz |
| `spectrum_ir` | IR spectrum | x-axis inverted, grid off |
| `spectrum_uvvis` | UV-Vis spectrum | grid off |
| `energy_profile` | Reaction energy profile | grid off; custom x tick labels via `axes.x.ticklabels` |
| `parity` | Calculated vs experimental | 1:1 dashed line + equal aspect auto-added |
| `radial_distribution` | g(r) RDF | grid off |

Histograms are intentionally NOT in v1. Preset = defaults, NOT constraints:
explicit spec fields always override preset defaults.

## Supported data formats

`csv` (comma), `tsv` (tab), `dat` (whitespace columns), `npz` (numpy keys).
Header row auto-detected (first row non-numeric → header). Columns referenced
by header name, or by 0-based integer index (headerless files: `"0"`, `"1"`, …).

## Spec schema

```json
{
  "preset": "spectrum_ir",
  "style": "paper",
  "layout": {
    "figsize": [4, 3],
    "nrows": 1, "ncols": 1,
    "sharex": false, "sharey": false,
    "letters": "auto",
    "panels": [
      {
        "series": [
          {"data": {"file": "ir.csv", "format": "csv",
                    "x": {"column": "wavenumber"}, "y": {"column": "transmittance"}},
           "label": "IRMPD", "color": "sky_blue", "linestyle": "-",
           "marker": "o", "yerr": {"column": "sigma"},
           "scale": 1.0, "offset": 0.0, "x_scale": 1.0, "x_offset": 0.0}
        ],
        "axes": {
          "x": {"label": "Wavenumber (cm$^{-1}$)", "invert": true, "grid": false,
                "lim": [400, 2000], "log": false, "minor": false,
                "ticklabels": []},
          "y": {"label": "Transmittance", "lim": [0, 110]}
        },
        "legend": {"on": true, "loc": "upper right"},
        "annotations": [
          {"text": "$\\nu$(O-H)", "x": 3500, "y": 95, "coords": "data",
           "fontsize": 10, "ha": "center", "va": "bottom"}
        ]
      }
    ]
  },
  "output": {"basename": "ir_spectrum", "formats": ["pdf", "png"], "transparent": false}
}
```

- **Single panel = one-element `panels` array.** No special case.
- **Multipanel**: `nrows`/`ncols` (omit both → 1 × len(panels)); panels fill
  row-major; `sharex`/`sharey` booleans; `letters: "auto"` adds (a), (b), …
- **`scale`/`offset`**: applied as `y' = y*scale + offset` (`x_*` for x).
- **`axes.*.ticklabels`**: full-length array of label strings placed evenly across
  the current x-limits (energy profiles: `["", "Reactants", "TS", "Products", ""]`).
  Empty string = blank tick.
- **`annotations.coords`**: `"data"` (default) or `"axes"` (0–1 fractions).
- **`transparent`**: real JSON boolean `true`/`false` — never the string `"True"`.
- Unknown fields anywhere → hard error. The schema is strict on purpose.

## Styles

`"style"`: `paper` (default; serif, Okabe-Ito palette, thin spines, grid on),
`poster` (paper ×2.5 fonts/lines), `screen` (sans-serif, mathtext only — use for
vault-note PNGs).

Colors: `"auto"` (Okabe-Ito cycle order) or palette name — `sky_blue`, `orange`,
`bluish_green`, `blue`, `vermillion`, `reddish_purple`, `yellow` — or `#RRGGBB`.
For multi-series panels: assign palette names by hand for distinguishability;
`"auto"` is fine for ≤3 series.

Grid: styles default ON; spectrum/energy/RDF/parity presets default it OFF;
per-axis override always possible (`"grid": true`).

## Your judgment checklist

Before writing the spec:

1. **Preset**: match table above. Not covered → STOP (rule 1).
2. **Columns**: `head` the data file; map x/y (and `yerr`) to the right columns;
   check units for labels.
3. **Labels**: full units, TeX math for symbols. No bare "Energy".
4. **Colors**: distinguishable palette names; consistent across panels/figures
   for the same species/condition.
5. **Annotations**: peaks, TS, regime markers — add when they carry information.
6. **Style**: `paper` for manuscripts, `poster` for slides/posters, `screen` for
   vault notes.

## Tests

```bash
PYTHON=python3 bash "$SKILL_DIR/tests/run_tests.sh"
```

Requires matplotlib+numpy (see repo `requirements.txt`).
