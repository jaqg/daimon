---
name: workflow-diagram
description: >
  Generates TikZ flowchart/workflow/scheme diagrams for LaTeX scientific and
  technical documents. Use this skill whenever the user asks to "draw a workflow",
  "create a flowchart", "make a scheme", "sketch a pipeline", "draw a diagram",
  "make a figure showing the process", or describes a scientific/computational/
  coding process that needs a visual representation — even if they don't say
  "TikZ" or "LaTeX" explicitly. Also triggers for: "diagram this pipeline",
  "show the steps as a figure", "make a schematic of the method".
  Default output: print TikZ code to conversation. Flags: --save, --horizontal,
  --scheme, --style, --box-style, --template, --template-only, --file,
  --from-image, --sketch.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# Workflow Diagram Skill (TikZ)

Generates TikZ flowchart/workflow diagrams. Output is printed by default; use
`--save <path>` to write a `.tex` file.

---

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--save <path>` | off | Write output to `.tex` file at path |
| `--file <path>` | — | Read workflow description from `.md` file |
| `--horizontal` | off | Main flow left→right instead of top→bottom |
| `--scheme <name>` | `tol-bright` | Color scheme: `tol-bright` or `monochrome` |
| `--style <name>` | `science` | Shape style: `science` or `coding` |
| `--box-style <name>` | `band` | Box appearance: `band` (title header strip, colored border) or `classic` (rounded corners, gray border) |
| `--template [path]` | — | Print (or save) empty skeleton `.md` instead of diagram |
| `--template-only` | off | Print populated block format for this workflow, no TikZ |
| `--from-image <path>` | — | Parse diagram from image or PDF file |
| `--sketch` | off | With `--from-image`: extract structure only, output skeleton block format |

---

## Step 0 — Parse image/PDF input (only when `--from-image` is given)

Read the file at the given path using the Read tool (handles images and PDFs natively).

### Full extraction mode (default, no `--sketch`)

Identify in the image:
- **Nodes**: bounding shape, text label (title + subtitle if present), color/position in flow (use to infer type if not labeled)
- **Connections**: arrow source → target, direction (down/right/left/up), any edge labels
- **Layout orientation**: predominantly top-to-bottom or left-to-right
- **Side branches**: nodes that connect laterally into the main flow

Build the internal node list (label, title, inferred type, subtitle) and connection map, exactly as if the user had typed a description. Then proceed to Step 1 with this parsed content.

If the source is a multi-page PDF, parse only page 1 unless the user specifies otherwise.

If anything is ambiguous (illegible text, unclear arrow direction), make a best guess and note it briefly before the block format output — e.g., "Note: arrow between Node A and Node C direction was unclear; assumed A→C."

### Sketch mode (`--sketch`)

Treat the source as a hand-drawn sketch — boxes and arrows with minimal or no labels.

Extract only topology:
- Count and rough position of nodes
- Connection graph (which connects to which, in what direction)
- Any visible text, even partial or guessed

Generate a **skeleton block format only** — no TikZ. Use placeholder titles ("Node 1", "Node 2", etc.), infer types for first node (→ `input`) and last node (→ `output`), leave all others as `process`. Connectivity matches the sketch topology.

After printing the skeleton, tell the user: "Fill in titles and subtitles, then re-feed with `/workflow-diagram --file <path>`."

---

## Step 1 — Understand the workflow

Three input modes — handle whichever the user provides:

**Mode A — from context**: User says "diagram what we discussed" or "make a figure
of the pipeline above." Extract nodes, types, and connections from the conversation.

**Mode B — natural language**: User describes it inline, e.g. "Input is molecular
geometry, then compute Hamiltonian, then run VQE, output is the ground state energy.
An ansatz design step feeds in from the right."

**Mode C — structured file or pasted block format** (via `--file <path>` or pasted directly):

```
---
[label] Node Title [type]
subtitle / tools line
---
|
---
[label2] Next Node
subtitle
---
|>left [sidelabel]
|
---
[label3] Output [output]
subtitle
---

---
[sidelabel] Side Node [side]
auxiliary description
---
```

**Block format rules:**
- `---` on its own line delimits each block
- Inside a block: first line is `[label] Title [type]` (label and type optional); second line is subtitle
- `|` between blocks = arrow from previous block to next (implicit source = preceding block)
- `[src]|` prefix = explicit source: arrow from `[src]` to next block (enables forks)
- `[s1][s2]|` prefix = merge: arrows from both `[s1]` and `[s2]` into next block (join)
- `|>left [label]` or `|>right [label]` on an arrow line = side branch: the named node
  connects into the node that follows this arrow (i.e., the downstream node). To make a
  side node appear to feed into the *middle of an arrow* rather than a node, note this
  in the subtitle — the skill will use a TikZ `coordinate` midpoint on that edge.
- Labels in natural language also work: "p1->p2->out, check1 feeds left into p2"
- Unlabelled blocks get auto-IDs: n1, n2, n3, ...
- `@group [n1][n2]...[nN] Label Text` at the **end** of the block format (after all node blocks) = labelled bounding box around those nodes. Optional `color=#RRGGBB` before the label overrides the default group color. Multiple `@group` lines supported — one per line.

**Branching example:**
```
---
[split] Fork Point [process]
---
[split]|
---
[brA] Branch A [process]
---
[split]|
---
[brB] Branch B [process]
---
[brA][brB]|
---
[merge] Merge / Combine [output]
---
```

**Group box example:**
```
---
[geom] Molecular Geometry [input]
3-D structure / coordinates
---
|
---
[hamil] Electronic Hamiltonian [process]
OpenFermion + PySCF
---
@group [geom][hamil] Phase 1
```

After parsing, confirm your understanding: list the nodes (ID, title, type) and
connections before generating code, especially for complex diagrams.

---

## Step 2 — Assign node types

If type is not given, infer from title keywords:

| Keywords in title | Inferred type |
|---|---|
| input, data, problem, geometry, start | `input` |
| output, result, application, end, final | `output` |
| check, valid, test, verify, simulate | `intermediate` |
| hardware, device, real, experimental | `hardware` |
| anything else | `process` |
| side branch with no clear fit | `side` |

For `--style coding`, also recognize:
- decision, if, branch, condition → `decision` (diamond shape)
- I/O, read, write, print, file → uses parallelogram shape

---

## Step 3 — Generate TikZ code

### Color definitions (add to preamble, or note as a comment)

**`--scheme tol-bright`** (default — Paul Tol's bright qualitative, colorblind-safe):

```latex
% Paul Tol bright palette — colorblind-safe
\definecolor{wfinput}{HTML}{CCBB44}        % yellow
\definecolor{wfprocess}{HTML}{4477AA}      % blue
\definecolor{wfintermediate}{HTML}{66CCEE} % cyan
\definecolor{wfhardware}{HTML}{EE6677}     % red
\definecolor{wfoutput}{HTML}{228833}       % green
\definecolor{wfside}{HTML}{AA3377}         % purple
\definecolor{wfgroup}{HTML}{BBBBCC}        % group box (muted blue-gray)
```

**`--scheme monochrome`**: all boxes white fill; distinguish by border:
- input: `dashed`, intermediate: `solid thin`, process: `solid, line width=1.2pt`,
  output: `double`, side: `dotted`

### TikZ preamble (include as comment above figure)

```latex
% Required packages:
% \usepackage{tikz}
% \usetikzlibrary{shapes.geometric, arrows.meta, positioning}
% For group boxes: also \usetikzlibrary{fit, backgrounds}
% For --style coding: also \usepackage{flowchart}
```

### Full figure template — `--box-style band` (default)

The `band` style gives each box a title header strip in a lighter shade of the block
color, a subtitle on the medium fill, and a colored border (same hue, full saturation).
No rounded corners. Matches the style of Inkscape/vector-editor scientific diagrams.

**How the title strip positioning works:** Do NOT set `minimum height` on band-style
nodes. Without a height floor, the node height is determined entirely by content plus
`inner sep`, so there is no excess vertical space for TikZ to center into. The title
`\colorbox` naturally sits `inner sep` (4pt) from the top border — the same distance as
the lateral padding. This is the "equal padding on all sides" the style requires.

For the border: use the full `<colorname>` (no `!` modifier) — clearly darker than the
`!40` fill. For the title strip: `<color>!20` inside a `\colorbox` with `\fboxsep=3pt`.

**Node text pattern (band style) — use `\parbox` not `\makebox`:**
```latex
{\setlength{\fboxsep}{3pt}%
 \colorbox{wfinput!20}{\parbox{4.04cm}{\centering\strut\textbf{Title}}}}\\[4pt]
{\footnotesize\strut subtitle}
```
`\parbox` width = `text width − 2×\fboxsep` (4.3 − 6pt ≈ 4.04 cm for main nodes;
3.3 − 6pt ≈ 3.04 cm for side nodes). Using `\parbox` instead of `\makebox` is
important: it wraps the title if it is long, and the `\colorbox` grows in height
automatically — multi-line titles are handled without any extra work.

Use the matching color name per type: `wfinput`, `wfprocess`, `wfintermediate`,
`wfhardware`, `wfoutput`, `wfside`.

```latex
\begin{figure}[htbp]
    \centering
    \begin{tikzpicture}[
        node distance=0.8cm and 2.5cm,
        every node/.style={align=center, font=\small},
        % -- band style: colored border, title header strip, no rounded corners --
        % No minimum height: node height = content + inner sep. Title sits at top.
        wf-input/.style={rectangle,
            minimum width=4.5cm, text width=4.3cm,
            draw=wfinput, line width=0.8pt, fill=wfinput!40, inner sep=4pt},
        wf-process/.style={rectangle,
            minimum width=4.5cm, text width=4.3cm,
            draw=wfprocess, line width=0.8pt, fill=wfprocess!40, inner sep=4pt},
        wf-intermediate/.style={rectangle,
            minimum width=4.5cm, text width=4.3cm,
            draw=wfintermediate, line width=0.8pt, fill=wfintermediate!40, inner sep=4pt},
        wf-hardware/.style={rectangle,
            minimum width=4.5cm, text width=4.3cm,
            draw=wfhardware, line width=0.8pt, fill=wfhardware!40, inner sep=4pt},
        wf-output/.style={rectangle,
            minimum width=4.5cm, text width=4.3cm,
            draw=wfoutput, line width=0.8pt, fill=wfoutput!40, inner sep=4pt},
        wf-side/.style={rectangle,
            minimum width=3.5cm, text width=3.3cm,
            draw=wfside, line width=0.8pt, fill=wfside!40, inner sep=4pt},
        % -- coding extras (--style coding only) --
        wf-decision/.style={diamond, aspect=2,
            minimum width=4.0cm, minimum height=1.1cm, text width=3.0cm,
            draw=wfhardware, line width=0.8pt, fill=wfhardware!30},
        % -- arrow --
        wf-arrow/.style={-{Stealth[length=2.5mm, width=2mm]}, thick},
    ]
        % ---- NODES (main chain, vertical: below=0.8cm of prev) ----
        \node[wf-input] (n1) {%
            {\setlength{\fboxsep}{3pt}%
             \colorbox{wfinput!20}{\parbox{4.04cm}{\centering\strut\textbf{Title}}}}\\[4pt]
            {\footnotesize\strut subtitle}};
        \node[wf-process, below=0.8cm of n1] (n2) {%
            {\setlength{\fboxsep}{3pt}%
             \colorbox{wfprocess!20}{\parbox{4.04cm}{\centering\strut\textbf{Title}}}}\\[4pt]
            {\footnotesize\strut subtitle}};
        % ... continue chain ...

        % ---- PARALLEL BRANCHES (position relative to fork node) ----
        \node[wf-process, below left=0.8cm and 1.5cm of split] (brA) {%
            {\setlength{\fboxsep}{3pt}%
             \colorbox{wfprocess!20}{\parbox{4.04cm}{\centering\strut\textbf{Branch A}}}}\\[4pt]
            {\footnotesize\strut description}};
        \node[wf-process, below right=0.8cm and 1.5cm of split] (brB) {%
            {\setlength{\fboxsep}{3pt}%
             \colorbox{wfprocess!20}{\parbox{4.04cm}{\centering\strut\textbf{Branch B}}}}\\[4pt]
            {\footnotesize\strut description}};

        % ---- SIDE BRANCH (left example) ----
        \node[wf-side, left=2.5cm of n2] (s1) {%
            {\setlength{\fboxsep}{3pt}%
             \colorbox{wfside!20}{\parbox{3.04cm}{\centering\strut\textbf{Title}}}}\\[4pt]
            {\footnotesize\strut subtitle}};

        % ---- SIDE → ARROW MIDPOINT (when side feeds into edge, not node) ----
        % \coordinate (midAB) at ($(n1)!0.5!(n2)$);
        % \draw[wf-arrow] (n1) -- (midAB) -- (n2);
        % \draw[wf-arrow] (sideX) -- (midAB);

        % ---- ARROWS ----
        \draw[wf-arrow] (n1) -- (n2);
        \draw[wf-arrow] (s1) -- (n2);
        % Labelled arrow: \draw[wf-arrow] (a) -- node[right]{\tiny label} (b);
        % Merge arrows converging to one node: draw from each branch separately

    \end{tikzpicture}
    \caption{CAPTION.}
    \label{fig:workflow}
\end{figure}
```

### Full figure template — `--box-style classic`

The `classic` style uses rounded corners, a uniform gray-black border (`black!70`),
and a more saturated fill (`!60`). Title and subtitle are plain text with no header
strip. Use this when you want a softer look or consistency with existing diagrams.

```latex
\begin{figure}[htbp]
    \centering
    \begin{tikzpicture}[
        node distance=0.8cm and 2.5cm,
        every node/.style={align=center, font=\small},
        % -- classic style: rounded corners, gray border, uniform fill --
        wf-input/.style={rectangle, rounded corners=3pt,
            minimum width=4.5cm, minimum height=1.1cm, text width=4.3cm,
            draw=black!70, fill=wfinput!60},
        wf-process/.style={rectangle, rounded corners=3pt,
            minimum width=4.5cm, minimum height=1.1cm, text width=4.3cm,
            draw=black!70, fill=wfprocess!60},
        wf-intermediate/.style={rectangle, rounded corners=3pt,
            minimum width=4.5cm, minimum height=1.1cm, text width=4.3cm,
            draw=black!70, fill=wfintermediate!60},
        wf-hardware/.style={rectangle, rounded corners=3pt,
            minimum width=4.5cm, minimum height=1.1cm, text width=4.3cm,
            draw=black!70, fill=wfhardware!60},
        wf-output/.style={rectangle, rounded corners=3pt,
            minimum width=4.5cm, minimum height=1.1cm, text width=4.3cm,
            draw=black!70, fill=wfoutput!60},
        wf-side/.style={rectangle, rounded corners=3pt,
            minimum width=3.5cm, minimum height=1.1cm, text width=3.3cm,
            draw=black!70, fill=wfside!60},
        wf-decision/.style={diamond, aspect=2,
            minimum width=4.0cm, minimum height=1.1cm, text width=3.0cm,
            draw=black!70, fill=wfhardware!40},
        wf-arrow/.style={-{Stealth[length=2.5mm, width=2mm]}, thick},
    ]
        \node[wf-input] (n1) {\textbf{Title}\\{\footnotesize subtitle}};
        \node[wf-process, below=0.8cm of n1] (n2) {\textbf{Title}\\{\footnotesize subtitle}};
        % ...
        \draw[wf-arrow] (n1) -- (n2);
    \end{tikzpicture}
    \caption{CAPTION.}
    \label{fig:workflow}
\end{figure}
```

---

**Horizontal layout (`--horizontal`)**: replace `below=0.8cm of prev` with
`right=0.8cm of prev`; side branches use `above=` or `below=` instead of
`left=`/`right=`; parallel branches use `above right=` / `below right=`.

**Parallel/branching layout**: use `below left=` and `below right=` relative to the
fork node to separate branches visually. For a join, position the merge node centered
below both branch endpoints.

**Side branch positioning**: left-side nodes use `left=2.5cm of <target>`,
right-side nodes use `right=2.5cm of <target>`. If multiple side nodes attach
at the same level, offset with `xshift` to prevent overlap.

### Group boxes (`@group` in block format)

Group boxes mark phases or stages. They span the **full diagram width** — think of
them as horizontal bands, not node-hugging boxes. Default appearance: dashed border,
rounded corners, low-opacity fill, label at the bottom-right corner inside the box.

**Required libraries**: `fit, backgrounds, calc` in `\usetikzlibrary`.
**Required colors** (define before `\begin{document}`):

```latex
\definecolor{wfgroup1}{HTML}{BBBBCC}   % muted blue-gray
\definecolor{wfgroup2}{HTML}{BBCCBB}   % muted green
\definecolor{wfgroup3}{HTML}{CCBBBB}   % muted rose
```

Override per group with `color=#RRGGBB` in the `@group` line — define a one-off
`\definecolor{wfgrpN}{HTML}{RRGGBB}` and use it in place of `wfgroupN`.

#### Anti-collision rules — check whenever `@group` lines are present

**1. Group border vs. adjacent group border (cross-phase node gaps)**

Each group box extends `inner sep=12pt` above its top node and below its bottom node.
Two vertically adjacent groups need the gap between the last node of phase N and the
first node of phase N+1 to be ≥ 26 pt (2 × 12 pt + 2 pt clearance). Default node
distance 0.8 cm ≈ 22.7 pt is NOT enough. For every node at a phase boundary (first
node of phase N+1 placed directly below last node of phase N), use `below=1.4cm`
instead of the default. Nodes within the same phase keep 0.8 cm.

**2. Label text vs. group box bottom (label overflow)**

The label sits inside the box at the bottom-right using `inner sep=4pt`. Label height
at `\footnotesize` ≈ 7 pt + 4 pt padding = 11 pt. The box has 12 pt of padding below
the last phase node — just enough for one-line labels. If a label wraps to two lines,
increase both `inner sep` on that group and the adjacent cross-phase gap to 1.6 cm.

#### TikZ pattern

```latex
% ---- REQUIRES IN \usetikzlibrary: fit, backgrounds, calc ----

% Step 1 — capture full diagram width AFTER all \node declarations, BEFORE group boxes:
\coordinate (bb-w) at (current bounding box.west);
\coordinate (bb-e) at (current bounding box.east);

% Step 2 — one block per @group line, AFTER \coordinate above, BEFORE arrows:
% For a phase with only main-chain nodes (no side branches at the same level):
\begin{scope}[on background layer]
    \node[draw=wfgroup1, dashed, line width=1pt, rounded corners=4pt,
          fill=wfgroup1!15, inner sep=12pt,
          fit=(bb-w |- top-node.north)(bb-e |- bottom-node.south)] (grp1) {};
\end{scope}
\node[text=wfgroup1!70!black, font=\footnotesize\itshape, anchor=south east, inner sep=4pt]
    at (grp1.south east) {Phase 1 --- Label};

% For a phase that includes side branches at the same vertical level as a main node —
% list those side nodes explicitly in fit() so their heights are encompassed:
\begin{scope}[on background layer]
    \node[draw=wfgroup2, dashed, line width=1pt, rounded corners=4pt,
          fill=wfgroup2!15, inner sep=12pt,
          fit=(bb-w |- main-node.north)(bb-e |- main-node.south)(side-nodeA)(side-nodeB)] (grp2) {};
\end{scope}
\node[text=wfgroup2!70!black, font=\footnotesize\itshape, anchor=south east, inner sep=4pt]
    at (grp2.south east) {Phase 2 --- Label};
```

`bb-w |- top-node.north` = x of `bb-w`, y of `top-node.north`. This overrides horizontal
extent to full diagram width regardless of which nodes are in the phase. Vertical extent
comes from the nodes listed in `fit()`. When side nodes are present (they may be taller
than the main chain node due to multi-line titles), always include them explicitly in the
`fit()` list — TikZ takes the union of all bounding boxes, so listing them ensures no node
clips the phase border. Repeat with `grp2`, `grp3`, … and matching color names.

#### Cross-phase node distance in `\node` declarations

```latex
% Within same phase — default 0.8cm:
\node[wf-process, below=0.8cm of geom] (hamil) {...};

% At a phase boundary — increase to 1.4cm:
\node[wf-process, below=1.4cm of hamil] (vqe) {...};   % Phase 1 → Phase 2
\node[wf-intermediate, below=1.4cm of vqe] (sim) {...}; % Phase 2 → Phase 3
```

---

## Step 4 — Output

**Default (print)**: output the complete figure code in a fenced `latex` code block,
preceded by the required `\usepackage` lines as a comment. State which packages need
to be added to the preamble.

After the TikZ code, always also print the **populated block format** of the workflow
you just generated. This lets the user verify your interpretation and edit the structure
without touching the TikZ directly. Label it clearly:

```
### Workflow block format (edit and re-feed with --file)
---
[label] Title [type]
subtitle
---
| (or [src]| for explicit source, [s1][s2]| for merge)
...
```

**`--template-only`**: instead of generating TikZ, only print the populated block
format for the current workflow. Useful when the user wants to verify your
interpretation first.

**`--save <path>`**: write the `.tex` file. Confirm with: `Written to <path>.`

If the user wants a **preview PDF** (they'll ask), compile standalone:

```bash
cat > /tmp/wf_preview.tex << 'EOF'
\documentclass[border=8pt]{standalone}
\usepackage{tikz}
\usetikzlibrary{shapes.geometric, arrows.meta, positioning, calc, fit, backgrounds}
\usepackage{xcolor}
\definecolor{wfinput}{HTML}{CCBB44}
\definecolor{wfprocess}{HTML}{4477AA}
\definecolor{wfintermediate}{HTML}{66CCEE}
\definecolor{wfhardware}{HTML}{EE6677}
\definecolor{wfoutput}{HTML}{228833}
\definecolor{wfside}{HTML}{AA3377}
\begin{document}
% PASTE tikzpicture ONLY (no \begin{figure})
\end{document}
EOF
pdflatex -interaction=nonstopmode -output-directory /tmp /tmp/wf_preview.tex 2>&1 | tail -8
```

---

## --template flag

Instead of generating a diagram, print (or save) this **empty skeleton** for the user to fill in:

```markdown
# Workflow diagram input
# Edit and feed back with: /workflow-diagram --file <path>
# Types: input, process, intermediate, hardware, output, side, decision
# Linear chain: | (from previous block)
# Explicit source: [src]| (arrow from named source to next)
# Merge: [s1][s2]| (arrows from multiple sources to next)
# Side branch: |>left [label] or |>right [label] (before the | that points to target)
# Side → arrow midpoint: note "feeds into arrow" in subtitle; skill uses TikZ coordinate

---
[start] Start / Input [input]
describe input here
---
|
---
[main] Main Process [process]
tools / methods used
---
|>left [side1]
|
---
[validate] Validation [intermediate]
how validation is done
---
|
---
[out] Output [output]
what is produced
---

---
[side1] Side Input [side]
auxiliary method or tool
---

# @group [start][main] Phase label (optional; delete if not needed)

# --- Branching example (delete if not needed) ---
# [fork] Fork [process]
# [fork]|
# ---
# [brA] Branch A [process]
# ---
# [fork]|
# ---
# [brB] Branch B [process]
# ---
# [brA][brB]|
# ---
# [join] Join [output]
# ---
```

If `--template <path>` given, write to that path and confirm. Otherwise print.

---

## Quality checklist

Before outputting, verify:
- Every node (band style): `\colorbox{<type-color>!20}{\parbox{WIDTH}{\centering\strut\textbf{Title}}}` — `\parbox` not `\makebox`; `WIDTH` = `text width − 2×\fboxsep (6pt ≈ 0.21cm)`; matching color per type; `inner sep=4pt`, NO `minimum height`
- Every node (classic style): bold title + footnotesize subtitle (neither blank)
- Arrow directions match actual data/information flow
- No text overflows box (`text width` = `minimum width` − 0.2 cm for main nodes)
- Side branches on consistent side (left vs right) per logical role
- Parallel branches visually separated with `below left=` / `below right=` positioning
- Caption is descriptive (not "Workflow diagram")
- `\label` uses `fig:` prefix
- No placeholder text left in output (`Title`, `CAPTION`, etc.)
- Required packages listed as comments above the figure code
- `calc` library included in `\usetikzlibrary` if midpoint coordinates used
- Populated block format printed after TikZ (unless `--template` or `--template-only`)
- If `--from-image` used: any guessed/ambiguous text or arrow directions are noted before the block format output
- If `--from-image --sketch` used: only skeleton block format printed, no TikZ generated, user instructed to fill in and re-feed with `--file`
- If `@group` lines present: `fit, backgrounds, calc` in `\usetikzlibrary`; `\coordinate (bb-w/bb-e)` captured after all `\node` declarations; group boxes use `fit=(bb-w |- top.north)(bb-e |- bottom.south)`, `dashed`, `rounded corners=4pt`, `inner sep=12pt`; label uses `text=wfgroupN!70!black` (NOT bare `wfgroupN` — too light); cross-phase connections use `below=1.4cm`
