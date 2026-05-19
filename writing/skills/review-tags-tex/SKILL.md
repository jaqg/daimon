---
name: review-tags-tex
description: Process review tags embedded as LaTeX comments in .tex files. Use this skill whenever the user invokes /review-tags-tex, or asks to "process tags", "apply comments", "review tex tags", or mentions %CT / %CQ / %CQ(render) tags in .tex files. Given a .tex file or a folder of .tex files (defaults to the current working directory), find and act on two kinds of tags: (1) %CT: <comment> — apply the change described in <comment> to the surrounding code, then mark the tag done as %(done)CT; (2) %CQ: <question> — answer the question and insert the answer as %ANSWER: <answer> on the line below (or, with --render-notes, inside a rendered claude-answer environment in Claude's orange color using /scientific-writing), then mark the tag done as %(done)CQ; (3) %CQ(render): <question> — like %CQ but forces a rendered claude-answer environment for that specific tag even without --render-notes, marking it done as %(done)CQ(render). Always invoke this skill when the user says /review-tags-tex.
tools: Read, Edit, Bash
---

> **Dependency:** `--render-notes` mode requires the `/scientific-writing` skill from the `claude-scientific-writer` plugin. Without it, render-mode tags will fall back to comment mode and a warning will be shown.

# review-tags-tex

Process embedded review tags in LaTeX source files.

## Tags

| Tag | Meaning | Action |
|-----|---------|--------|
| `%CT: <comment>` | **C**hange **T**ag — instruction to modify surrounding code | Apply the change near the tagged line |
| `%CQ: <question>` | **C**hange **Q**uestion — a question about surrounding code | Answer inline (comment by default) |
| `%CQ(render): <question>` | Same as `%CQ` but forces rendered answer | Answer in `claude-answer` environment |

## Invocation

```
/review-tags-tex [target] [--render-notes] [--remove-tags]
```

- `target`: single `.tex` file or directory (searched recursively). Default: current working directory.
- `--render-notes`: write **all** `%CQ` answers as rendered PDF content in `claude-answer` environment.
- `--remove-tags`: after processing, delete tag lines instead of marking `%(done)`.

## Step 1 — Extract tags

```bash
SCRIPT=$(find -L ~/.claude -path "*/review-tags-tex/scripts/extract_tags.py" -type f | head -1)
python3 "$SCRIPT" <target>
```

The script outputs a JSON array. Each entry has:
- `file` — absolute path to `.tex` file
- `line` — 1-based line number
- `type` — `"CT"`, `"CQ"`, or `"CQrender"`
- `content` — text after the tag prefix (the instruction or question)
- `context_before` — up to 15 lines before the tag
- `context_after` — up to 15 lines after the tag

Script already skips:
- Tags inside `lstlisting`, `verbatim`, `Verbatim` environments
- Tags already marked `%(done)...`

If the array is empty: tell the user "No open tags found." and stop.

## Step 2 — Process each tag

Work through tags in order (file by file, top to bottom). For each tag, use `context_before`
and `context_after` from the JSON to understand intent — only call Read if context is
insufficient to interpret the change.

### %CT tags — apply a change

1. Interpret `content` as a plain-language instruction about what to change near that line.
2. Apply the change to the file using Edit.
3. Mark the tag done: change `%CT:` → `%(done)CT:` on that line (keep comment text).

If `--remove-tags`: delete the tag line instead of marking done.

### %CQ tags — answer a question

Determine render mode for each tag:
- **Render** if `type == "CQrender"`, or if `--render-notes` was passed.
- **Comment mode** otherwise.

**Comment mode:**
1. Compose a concise answer (1–3 lines; it lives as a LaTeX comment).
2. Insert `%ANSWER: <answer>` on the line immediately below the `%CQ` line using Edit.
3. Mark done: `%CQ:` → `%(done)CQ:` (keep question text).

**Render mode:**
1. Use `/scientific-writing` to compose the answer as LaTeX prose.
2. Ensure `claude-answer` environment is defined in the root `.tex` file (the one with `\documentclass`):
   - If `\newenvironment{claude-answer}` not already present, add to preamble:
     ```latex
     % claude-answer environment: renders Claude's answers in orange
     \usepackage{xcolor}
     \definecolor{claudeorange}{HTML}{D97757}
     \newenvironment{claude-answer}{\color{claudeorange}}{}
     ```
     Do not duplicate `\usepackage{xcolor}` or `\definecolor{claudeorange}` if already present.
3. Insert immediately below the tag line:
   ```latex
   \begin{claude-answer}
   <answer>
   \end{claude-answer}
   ```
4. Mark done: `%CQ(render):` → `%(done)CQ(render):`, plain `%CQ:` → `%(done)CQ:`.

## Step 3 — Report

```
Processed N tags across M file(s):
  %CT applied: K  (file1.tex:3, file2.tex:17)
  %CQ answered: J  (file1.tex:5)
  %CQ(render) answered: L
  Skipped (ambiguous): 0
```

Flag any tags where interpretation was uncertain; show what was done and invite correction.

## Edge cases

- **Ambiguous CT instruction**: apply best-effort interpretation, flag in report.
- **Multiple tags on nearby lines**: process each independently in order.
- **`--render-notes` without `/scientific-writing`**: fall back to comment mode, warn user.

## Example

**Before:**
```latex
\section{Introduction}   %CT: rename to "Introducción"
The potential is $V = x^4$.  %CQ: should this be in display math instead?
The energy levels are $E_n$.  %CQ(render): explain why we use discrete energy levels here
```

**After (default — no flags):**
```latex
\section{Introducción}   %(done)CT: rename to "Introducción"
The potential is $V = x^4$.  %(done)CQ: should this be in display math instead?
%ANSWER: For a standalone equation, yes — use \[ V = x^4 \]. Inline is fine as-is.
The energy levels are $E_n$.  %(done)CQ(render): explain why we use discrete energy levels here
\begin{claude-answer}
The discretisation of energy levels follows from the boundary conditions\ldots
\end{claude-answer}
```
