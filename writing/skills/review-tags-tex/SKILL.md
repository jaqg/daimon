---
name: review-tags-tex
disable-model-invocation: true
description: "Process review tags embedded as LaTeX comments in .tex files. Use this skill whenever the user invokes /review-tags-tex, or asks to 'process tags', 'apply comments', 'review tex tags', or mentions %AIT / %AIQ / %AIQ(render) tags in .tex files. Given a .tex file or a folder of .tex files (defaults to the current working directory), find and act on two kinds of tags: (1) %AIT: <instruction> — apply the change described in <instruction> to the surrounding code, then mark the tag done as %(done)AIT; (2) %AIQ: <question> — answer the question and insert the answer as %ANSWER: <answer> on the line below, or inside a rendered AI-answer environment with --render-notes, then mark the tag done as %(done)AIQ; (3) %AIQ(render): <question> — like %AIQ but forces a rendered AI-answer environment for that specific tag even without --render-notes, marking it done as %(done)AIQ(render). Always invoke this skill when the user says /review-tags-tex."
tools: read, edit, bash
---

# review-tags-tex

Process embedded review tags in LaTeX source files.

## Tags

| Tag | Meaning | Action |
|-----|---------|--------|
| `%AIT: <instruction>` | **A**I **T**ask — instruction to modify surrounding code | Apply the change near the tagged line |
| `%AIQ: <question>` | **A**I **Q**uestion — a question about surrounding code | Answer inline (comment by default) |
| `%AIQ(render): <question>` | Same as `%AIQ` but forces rendered answer | Answer in `AI-answer` environment |

## Invocation

```
/review-tags-tex [target] [--render-notes] [--remove-tags]
```

- `target`: single `.tex` file or directory (searched recursively). Default: current working directory.
- `--render-notes`: write **all** `%AIQ` answers as rendered PDF content in `AI-answer` environment.
- `--remove-tags`: after processing, delete tag lines instead of marking `%(done)`.

## Step 1 — Extract tags

```bash
python3 <skill-dir>/scripts/extract_tags.py <target>
```

(`<skill-dir>` = the directory containing this SKILL.md.)

The script outputs a JSON array. Each entry has:
- `file` — absolute path to `.tex` file
- `line` — 1-based line number **at extraction time** (advisory only — edits shift lines)
- `type` — `"AIT"`, `"AIQ"`, or `"AIQrender"`
- `content` — text after the tag prefix (the instruction or question)
- `anchor` — the complete raw tag line, to be used as the Edit `oldText`
- `context_before` — up to 15 lines before the tag
- `context_after` — up to 15 lines after the tag

Script already skips:
- Tags inside `lstlisting`, `verbatim`, `Verbatim` environments
- Tags already marked `%(done)...`

If the array is empty: tell the user "No open tags found." and stop.

## Step 2 — Process each tag

**Anchor on text, never on line numbers.** Every Edit's `oldText` is the tag's `anchor` (or a
neighbouring line from the context) — line numbers exist only to orient you, so edits shifting
earlier lines cannot corrupt later ones. Use `context_before` / `context_after` to interpret intent;
only call Read if the context is insufficient.

### %AIT tags — apply a change

1. Interpret `content` as a plain-language instruction about what to change near that line.
2. Apply the change to the file using Edit.
3. Mark the tag done: change `%AIT:` → `%(done)AIT:` on the anchor line (keep instruction text).

If `--remove-tags`: delete the tag line instead of marking done.

### %AIQ tags — answer a question

Determine render mode for each tag:
- **Render** if `type == "AIQrender"`, or if `--render-notes` was passed.
- **Comment mode** otherwise.

**Comment mode — one atomic Edit** (done-mark + answer in a single replacement of the anchor line):
1. Compose a concise answer (1–3 lines; it lives as a LaTeX comment).
2. Replace the anchor line with the done-marked tag line plus the answer below it:

```latex
%AIQ: <question>   →   %(done)AIQ: <question>
                       %ANSWER: <answer>
```

**Render mode:**
1. Compose the answer as LaTeX prose: concise, matches the manuscript's register and notation, no filler.
2. Ensure `AI-answer` environment is defined in the root `.tex` file (the one with `\documentclass`):
   - If `\newenvironment{AI-answer}` not already present, add to preamble:
     ```latex
     % AI-answer environment: renders the agent's answers in teal
     \usepackage{xcolor}
     \definecolor{aianswer}{HTML}{1F6F8B}
     \newenvironment{AI-answer}{\color{aianswer}}{}
     ```
     Do not duplicate `\usepackage{xcolor}` or `\definecolor{aianswer}` if already present.
3. One atomic Edit: replace the anchor line with the done-marked tag line plus the environment block:
   ```latex
   %(done)AIQ(render): <question>
   \begin{AI-answer}
   <answer>
   \end{AI-answer}
   ```
4. Plain `%AIQ:` in render mode → `%(done)AIQ:`.

## Step 3 — Verify + report

Re-run the extraction script on the same target; it must return `[]`. Any tag it still finds was
missed or half-processed — fix it (again by anchor) before reporting.

```
Processed N tags across M file(s):
  %AIT applied: K
  %AIQ answered: J
  %AIQ(render) answered: L
  Verify: 0 open tags remaining
```

Name tags by content, not by the original line numbers (they shifted). Flag any tags where
interpretation was uncertain; show what was done and invite correction.

## Edge cases

- **Ambiguous AIT instruction**: apply best-effort interpretation, flag in report.
- **Anchor no longer found** (a previous edit changed the tag line itself): Read the file, locate the
  tag by its `content` text, edit there.
- **Multiple tags on nearby lines**: each anchor is its own line, so they compose safely.
- **`--render-notes` environment clash**: if `AI-answer` is already defined differently in the root
  file, do not redefine — insert answers as `%ANSWER:` comments and warn user.

## Example

**Before:**
```latex
\section{Introduction}   %AIT: rename to "Introducción"
The potential is $V = x^4$.  %AIQ: should this be in display math instead?
The energy levels are $E_n$.  %AIQ(render): explain why we use discrete energy levels here
```

**After (default — no flags):**
```latex
\section{Introducción}   %(done)AIT: rename to "Introducción"
The potential is $V = x^4$.  %(done)AIQ: should this be in display math instead?
%ANSWER: For a standalone equation, yes — use \[ V = x^4 \]. Inline is fine as-is.
The energy levels are $E_n$.  %(done)AIQ(render): explain why we use discrete energy levels here
\begin{AI-answer}
The discretisation of energy levels follows from the boundary conditions\ldots
\end{AI-answer}
```
