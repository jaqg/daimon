---
name: poster
description: >
  Generate a scientific conference poster as a complete LaTeX project, optionally with a submission abstract and audience Q&A prep.
  Invoke this skill when the user says /poster, asks to "create a poster", "make a conference poster", "generate a poster for [project/conference]",
  or asks to "write an abstract" or "prepare conference Q&A" in the context of a poster or conference submission.
  Uses the Gemini beamerposter theme and the user's personal identity from config.local.
  Reads project context from memory files and vault notes when available.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# poster

Generate a scientific conference poster as a complete, compilable LaTeX project.
Optionally produce a submission abstract and an audience Q&A prep sheet.

## Invocation

```
/poster [--project PROJECT_ID] [--conference "CONF NAME"] [--date "DATE"]
        [--size a0|a1|a2|a3] [--orientation portrait|landscape]
        [--colortheme um|gemini|cam|mit|labsix|seagull|heriotwatt]
        [--empty]
        [--abstract] [--questions] [--full]
        [--output PATH]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--project` | infer from context | Project ID string (e.g. `PhD-Ch1-AIM4ML`) |
| `--conference` | ask if unknown | Conference name and location |
| `--date` | ask if unknown | Event date (shown in footer) |
| `--size` | `a0` | Print size; controls scale and figure recommendations |
| `--orientation` | `portrait` | `portrait` (2-col) or `landscape` (3-col for a0/a1, 2-col for a2/a3) |
| `--colortheme` | `um` | Gemini color theme |
| `--empty` | off | Copy template only — inject config identity but leave all content blocks as `%% TODO:` placeholders for manual editing. Skips context loading, content generation, abstract, and Q&A. |
| `--abstract` | off | Also generate a submission abstract |
| `--questions` | off | Also generate audience Q&A prep |
| `--full` | off | Enable `--abstract` + `--questions` together |
| `--output` | `./[project]-poster/` | Output directory |

If `--project` is omitted, infer from the current working directory name or the most recently mentioned project in memory.
If `--conference` or `--date` are missing and cannot be inferred, ask the user before proceeding.
If `--empty` is passed, `--conference` and `--date` are optional — leave as `%%CONFERENCE%%` / `%%DATE%%` placeholders in the output if not provided.

## Step 1 — Load config

Locate the skill's real path on disk and derive the daimon root:

```bash
SKILL_DIR=$(dirname "$(readlink -f "$(find -L ~/.claude/skills/poster -name SKILL.md 2>/dev/null | head -1)")")
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"
TEMPLATE_DIR="$SKILL_DIR/templates/portrait-poster"
FILL_SCRIPT=$(find -L ~/.claude -path "*/poster/scripts/fill_template.py" -type f | head -1)
```

Read `VAULT_DIR` from `$CONFIG_LOCAL` (needed for Step 2). All other identity values (`POSTER_AUTHOR`, `POSTER_AFFILIATION`, `POSTER_EMAIL`, `POSTER_LOGO_LEFT`, `POSTER_LOGO_RIGHT`) are handled by the fill script in Step 4c — do not read them manually.

If `CONFIG_LOCAL` does not exist, warn and proceed — the script uses `%%PLACEHOLDER%%` fallbacks.

## Step 1b — Early exit for `--empty`

If `--empty` was passed, skip Steps 2–7 entirely. Instead:

1. Run fill_template.py (Step 4c command) → get partially-filled template with `%%POSTER_BODY%%` remaining.
2. Replace `%%POSTER_BODY%%` with a structural skeleton of `%% TODO:` placeholders:

```latex
\begin{columns}[t]
    \separatorcolumn
    \begin{column}{\colwidth}

        \begin{block}{Introduction}
            %% TODO: State the problem and scientific objective.
            \begin{itemize}
                \item %% TODO: Motivation
                \item %% TODO: Research question
                \item %% TODO: Objective
            \end{itemize}
        \end{block}

        \begin{block}{Methods}
            %% TODO: Describe computational/experimental approach.
            \begin{itemize}
                \item %% TODO: Method 1
                \item %% TODO: Method 2
            \end{itemize}
            \begin{figure}
                \centering
                %% TODO: Insert workflow or scheme figure here
                \rule{0.6\textwidth}{4cm}
                \caption{%% TODO: Caption}
            \end{figure}
        \end{block}

    \end{column}
    \separatorcolumn
    \begin{column}{\colwidth}

        \begin{block}{Results}
            %% TODO: Key findings.
            \begin{figure}
                \centering
                %% TODO: Insert main result figure
                \rule{0.6\textwidth}{4cm}
                \caption{%% TODO: Caption}
            \end{figure}
        \end{block}

        \begin{alertblock}{Key Result}
            %% TODO: One highlighted equation or key finding.
        \end{alertblock}

        \begin{block}{Conclusions}
            \begin{itemize}
                \item %% TODO: Conclusion 1
                \item %% TODO: Conclusion 2
                \item %% TODO: Future work
            \end{itemize}
        \end{block}

        \begin{block}{References}
            \printbibliography[heading=none]
        \end{block}

    \end{column}
    \separatorcolumn
\end{columns}
```

For landscape 3-column, add a center column for Methods between the two above.

3. Substitute all `%%PLACEHOLDER%%` markers (identity from config, layout from Step 1b-1). Leave `%%CONFERENCE%%`, `%%DATE%%`, `%%TITLE%%` as literal placeholder text if not provided.
4. Write output files (same as Step 5).
5. Report: tell the user the template is ready, list `%% TODO:` markers by section, give compile command.
6. Stop — do not generate abstract or Q&A.

## Step 2 — Load project context

1. Derive memory dir: `MEMORY_DIR="$HOME/.claude/projects/$(echo "$VAULT_DIR" | sed 's|^/||; s|/|-|g')/memory"`
   (fall back to `"$HOME/.claude/projects/$(pwd | sed 's|^/||; s|/|-|g')/memory"` if `VAULT_DIR` not set)
2. Read `$MEMORY_DIR/MEMORY.md` — scan for the project line matching `--project`.
3. Read the referenced `project_*.md` file for that project.
4. If `--project` resolves to a vault project dir under `$VAULT_DIR/10-Projects/[PROJECT_ID]/`, read the dashboard and decisions-log.
5. Read `$MEMORY_DIR/research_interests.md` if present (for framing the introduction).

Use this context to understand:
- Project title and scientific objective
- Methods used
- Key results achieved or expected
- Target audience (conference field)

## Step 3 — Derive layout parameters

From `--size` and `--orientation`:

| Size | Scale | Max figure width |
|------|-------|-----------------|
| a0 | 1.3 | 0.9\textwidth |
| a1 | 1.1 | 0.85\textwidth |
| a2 | 0.9 | 0.8\textwidth |
| a3 | 0.7 | 0.7\textwidth |

Column layout:
- **portrait** (any size): 2 columns — `\sepwidth=0.03\paperwidth`, `\colwidth=0.45\paperwidth`
- **landscape, a0/a1**: 3 columns — `\sepwidth=0.025\paperwidth`, `\colwidth=0.29\paperwidth`
- **landscape, a2/a3**: 2 columns — `\sepwidth=0.03\paperwidth`, `\colwidth=0.45\paperwidth`

## Step 4 — Generate poster content

### 4a. Plan sections

For a typical scientific poster, plan these blocks in column order:

**2-column portrait (left → right):**
- Left: Introduction & Background, Methods / Computational Details, [optional: Theory]
- Right: Results & Discussion, Conclusions, Acknowledgements (inline), References

**3-column landscape (left → center → right):**
- Left: Introduction, Background/Theory
- Center: Methods, Computational Details
- Right: Results, Conclusions, References

Adjust based on the project type (e.g., ML projects may have a Dataset and Model sections; theory-heavy projects may have a Formalism block).

### 4b. Write content

Generate each block. Guidelines:
- **Introduction**: 3–5 bullet points. State the problem, its importance, and the specific objective of this work.
- **Methods**: concise; use bullet lists or a scheme diagram placeholder (`%% INSERT WORKFLOW FIGURE`). Reference key software/methods.
- **Results**: the most important 2–3 findings. Use a figure placeholder (`%% INSERT FIGURE: [description]`) for each key result. Include a representative equation or table if relevant.
- **Conclusions**: 3–4 bullet points. What was achieved, why it matters, what is next.
- **References**: leave as `\printbibliography[heading=none]` — the user will populate `refs.bib`.

Use proper LaTeX chemistry (`\ch{}`, `\ce{}`), math (`equation*`, inline `$...$`), and the tcolorbox environments from `custom-defs.tex` (e.g. `alertblock` for the key equation, `exampleblock` for a notable result).

Figure placeholders should be:
```latex
\begin{figure}
    \centering
    %% INSERT FIGURE: [description of what should go here]
    \rule{0.6\textwidth}{4cm} % placeholder box
    \caption{[Caption placeholder]}
\end{figure}
```

### 4c. Assemble the file

Run fill_template.py to substitute all identity/layout placeholders, leaving only `%%POSTER_BODY%%`:

```bash
python3 "$FILL_SCRIPT" \
  --template "$TEMPLATE_DIR/main.tex" \
  --config "$CONFIG_LOCAL" \
  --size SIZE --orientation ORIENTATION \
  --colortheme COLORTHEME \
  --conference "CONFERENCE" \
  --date "DATE" \
  --title "TITLE" \
  --output /tmp/poster-partial.tex
```

Script stderr reports which placeholders were filled and confirms `%%POSTER_BODY%%` is the only remaining one. Then replace `%%POSTER_BODY%%` in `/tmp/poster-partial.tex` with the content generated in Step 4b.

## Step 5 — Write output

Create the output directory. Write:
- `main.tex` — assembled poster
- `custom-defs.tex` — copied from `$TEMPLATE_DIR/custom-defs.tex`
- `refs.bib` — copied from `$TEMPLATE_DIR/refs.bib`
- All `*.sty` files — copied from `$TEMPLATE_DIR/`

Logo handling: logos live wherever the user keeps them on their machine — do not create a `logos/` in the daimon repo.
If `POSTER_LOGO_LEFT` / `POSTER_LOGO_RIGHT` are set in config.local and the files exist:
- Create a `logos/` directory inside the output directory
- Copy the logo files there as `logo-left.pdf` / `logo-right.pdf`
- Reference them with relative paths: `logos/logo-left.pdf` and `logos/logo-right.pdf`

If a logo path is empty or the file does not exist, omit the corresponding `\logoleft` / `\logoright` line from `main.tex` and note the missing logo in the report.

## Step 6 — Generate abstract (if `--abstract` or `--full`)

Write a standalone submission abstract. Format:

```
[CONFERENCE NAME] — Abstract submission
[PROJECT TITLE]
[AUTHOR(S)] — [AFFILIATION]

[300–400 word abstract]

Keywords: [5–8 keywords]
```

The abstract should:
- Open with the scientific problem and its significance (1–2 sentences)
- State the approach and methods (2–3 sentences)
- Summarise key results (2–3 sentences)
- Close with conclusions and outlook (1–2 sentences)

Write this to `abstract.md` in the output directory and print it inline in the report.

## Step 7 — Generate Q&A prep (if `--questions` or `--full`)

Generate a `questions.md` file with 12–15 anticipated audience questions covering:
- Conceptual / "why" questions (why this method, why this system)
- Technical questions (implementation details, convergence, validation)
- Comparison questions (how does this compare to X?)
- Limitations and future work
- Broader impact

For each question, provide a concise 2–4 sentence answer drawn from the project context.

Format:
```markdown
## Q1: [Question]
[Answer]

## Q2: [Question]
[Answer]
...
```

## Step 8 — PDF quality check

After the user compiles the poster, they should run these checks. Include them in the report (Step 9).

**Dimensions:**
```bash
pdfinfo main.pdf | grep "Page size"
# A0 portrait: 2384 x 3370 pt (841 x 1189 mm)
# A1 portrait: 1684 x 2384 pt (594 x 841 mm)
```

**Overflow (most common failure):**
```bash
grep -i "overfull" main.log
# Any "Overfull \hbox" = content spills beyond column/page boundary — must fix before printing
```

Common overflow fixes:
- Figures: use `width=0.85\textwidth` not `width=\textwidth`
- Text: add `\usepackage{microtype}` to preamble for better spacing
- Severe cases: cut a section or reduce bullet points

**Font embedding (required before sending to printer):**
```bash
pdffonts main.pdf
# All fonts must show "yes" in the "emb" column
# If any show "no": recompile with lualatex instead of pdflatex
```

**File size (for email/portal submission):**
```bash
ls -lh main.pdf
# If >30 MB: compress with:
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/printer \
   -dNOPAUSE -dQUIET -dBATCH -sOutputFile=main_compressed.pdf main.pdf
```

## Step 9 — Report

Tell the user:
- Output directory created at `[path]`
- Files written: `main.tex`, `custom-defs.tex`, `refs.bib`, `*.sty` files
- Logo status: copied / missing (with paths needed)
- Figure placeholders inserted: list them with descriptions
- How to compile: `latexmk -pdf main.tex` or `pdflatex main.tex && biber main && pdflatex main.tex`
- PDF QC commands to run after compilation (from Step 8)
- If abstract generated: summary printed inline
- If Q&A generated: `questions.md` written to output dir

Invite the user to:
1. Replace figure placeholders with actual figures — or use `scientific-schematics` / `generate-image` skills for AI-generated diagrams
2. Add references to `refs.bib`
3. Add logos to `logos/` if not already copied
4. Add a QR code linking to code/paper if desired: `\usepackage{qrcode}` + `\qrcode[height=3cm]{https://github.com/...}`
5. Review and refine content with `/review-tags-tex` (tag any sections they want changed with `%CT:`)

## Edge cases

- **No project context found**: generate a structural skeleton only, with `%% TODO:` comments marking each section. Tell the user to run again with `--project` or provide context inline.
- **Vault not accessible**: proceed with memory files only; note the limitation.
- **`--full` with no conference info**: ask for conference name and date before generating abstract; the poster body can be generated first while waiting.
- **Landscape A0 with many results**: recommend 3 columns and offer to add a center column for methods if content is dense.
