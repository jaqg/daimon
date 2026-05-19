---
name: review-tags-tex
description: Process review tags embedded as LaTeX comments in .tex files. Use this skill whenever the user invokes /review-tags-tex, or asks to "process tags", "apply comments", "review tex tags", or mentions %CT / %CQ / %CQ(render) tags in .tex files. Given a .tex file or a folder of .tex files (defaults to the current working directory), find and act on two kinds of tags: (1) %CT: <comment> — apply the change described in <comment> to the surrounding code, then mark the tag done as %(done)CT; (2) %CQ: <question> — answer the question and insert the answer as %ANSWER: <answer> on the line below (or, with --render-notes, inside a rendered claude-answer environment in Claude's orange color using /scientific-writing), then mark the tag done as %(done)CQ; (3) %CQ(render): <question> — like %CQ but forces a rendered claude-answer environment for that specific tag even without --render-notes, marking it done as %(done)CQ(render). Always invoke this skill when the user says /review-tags-tex.
tools: Read, Edit, Grep, Glob, Bash
---

> **Dependency:** `--render-notes` mode requires the `/scientific-writing` skill from the `claude-scientific-writer` plugin. Without it, render-mode tags will fall back to comment mode and a warning will be shown.

# review-tags-tex

Process embedded review tags in LaTeX source files.

## Tags

| Tag | Meaning | Action |
|-----|---------|--------|
| `%CT: <comment>` | **C**hange **T**ag — instruction to modify the surrounding code | Apply the change near the tagged line |
| `%CQ: <question>` | **C**hange **Q**uestion — a question about the surrounding code | Answer the question inline (as a comment by default) |
| `%CQ(render): <question>` | Same as `%CQ` but forces a rendered answer for this tag | Answer rendered in a `claude-answer` environment, even without `--render-notes` |

## Invocation

```
/review-tags-tex [target] [--render-notes] [--remove-tags]
```

- `target` can be a single `.tex` file or a directory (searched recursively for `*.tex`).
- If no target is given, use the **current working directory** (the directory where the Claude Code session was started).
- `--render-notes`: write **all** `%CQ` answers as rendered PDF content inside a `claude-answer` environment instead of as a comment (see below).
- `--remove-tags`: after processing, delete the tag lines entirely instead of marking them `%(done)`.

A `%CQ` tag can also carry a **per-tag render modifier**: `%CQ(render): <question>`. This forces that specific answer to be rendered inside a `claude-answer` environment regardless of whether `--render-notes` was passed. When `--render-notes` is active, all `%CQ` answers (including plain `%CQ:` ones) are rendered, so the `(render)` modifier is redundant but still valid.

## Workflow

### Step 1 — Discover tags

Grep the target file(s) for lines matching `%CT:`, `%CQ:`, or `%CQ(render):` that have **not** yet been marked done (i.e. do not start with `%(done)`). Collect them with their file path and line number.

If no open tags are found, tell the user and stop.

### Step 2 — Process each tag

Work through the tags in order (file by file, top to bottom). For each tag:

#### %CT tags — apply a change

1. Read the line and its surrounding context (typically ±10–20 lines is enough to understand what needs changing).
2. Interpret `<comment>` as a plain-language instruction about what to change *in or around* that location. The instruction is usually something like "rename this command", "add a label here", "fix the equation sign", "use \textbf instead of \textit", etc.
3. Apply the change directly to the file using the Edit tool.
4. Change `%CT:` to `%(done)CT:` on the tag line itself (leave the comment text intact).

**Unless the user explicitly passes `--remove-tags` when invoking the skill**, keep the tag line — just update the prefix so it is clear the tag has been processed.

#### %CQ tags — answer a question

When processing a `%CQ` tag, first determine the **render mode** for that tag:

- **Render this answer** if either (a) the tag is `%CQ(render): <question>`, or (b) `--render-notes` was passed.
- **Comment mode** otherwise (plain `%CQ:` without `--render-notes`).

**Comment mode:**

1. Read the line and its surrounding context to understand what the question refers to.
2. Compose a concise, accurate answer. The answer will live as a LaTeX comment, so keep it to 1–3 lines; if a longer explanation is needed, summarise and offer to elaborate in the chat.
3. Insert the answer on the line **immediately below** the `%CQ` line, formatted as:
   ```
   %ANSWER: <your answer>
   ```
4. Change `%CQ:` to `%(done)CQ:` on the original tag line (leave the question text intact).

**Render mode** (applies to `%CQ(render):` tags, or all `%CQ` tags when `--render-notes` is passed):

1. Read the line and its surrounding context to understand what the question refers to.
2. Use the `/scientific-writing` skill to compose the answer (unless the user explicitly requests a different writing approach when invoking the skill). Write the answer as proper LaTeX prose — it will be rendered in the PDF, so it should be well-written, not a brief comment.
3. Ensure the `claude-answer` environment exists in the project before inserting the answer:
   - Find the root `.tex` file (the one with `\documentclass`).
   - Check whether `\newenvironment{claude-answer}` is already defined anywhere in the project.
   - If it is **not** defined, add the following block to the preamble of the root file (after `\usepackage` declarations, before `\begin{document}`):
     ```latex
     % claude-answer environment: renders Claude's answers in orange
     \usepackage{xcolor}
     \definecolor{claudeorange}{HTML}{D97757}
     \newenvironment{claude-answer}{\color{claudeorange}}{}
     ```
     If `\usepackage{xcolor}` is already present, do **not** add it again. If `\definecolor{claudeorange}` is already defined, do **not** redefine it.
4. Insert the answer on the line **immediately below** the `%CQ` line, wrapped in the environment:
   ```latex
   \begin{claude-answer}
   <your answer in LaTeX prose>
   \end{claude-answer}
   ```
5. Change the tag to its done form: `%CQ(render):` → `%(done)CQ(render):`, plain `%CQ:` → `%(done)CQ:` (leave the question text intact).

### Step 3 — Report

After processing all tags, give the user a brief summary:
- How many `%CT` tags were applied (and to which files).
- How many `%CQ` tags were answered (and to which files).
- Any tags that were ambiguous or that you were unsure about (explain your interpretation and what you did, and invite correction).

## Edge cases

- **Ambiguous CT instruction**: if the instruction is unclear, make your best-effort interpretation, apply it, and flag the ambiguity in your report so the user can review.
- **Nested or escaped percent signs**: only match lines where `%CT:` or `%CQ:` appears as the first non-whitespace content of a comment (i.e. after optional spaces and a `%`).
- **Multiple tags on nearby lines**: process each independently in order; a change from one tag should not break the context of the next.
- **Tag inside a lstlisting or verbatim environment**: skip it — modifying code inside verbatim blocks based on a comment tag is almost certainly unintended. Report these as skipped.

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
%ANSWER: For a standalone equation that deserves visual emphasis, yes — use \[ V = x^4 \] or an equation environment. As a short inline expression within a sentence it is fine as-is.
The energy levels are $E_n$.  %(done)CQ(render): explain why we use discrete energy levels here
\begin{claude-answer}
The discretisation of energy levels follows from the boundary conditions imposed on the
wavefunction inside the potential well\ldots
\end{claude-answer}
```

Note that the plain `%CQ` got a comment answer while `%CQ(render)` was rendered in the `claude-answer` environment — even though `--render-notes` was not passed.

**After (`--render-notes`):** all `%CQ` answers — including plain `%CQ:` — are rendered in `claude-answer` environments. The `(render)` modifier is redundant but still accepted.
