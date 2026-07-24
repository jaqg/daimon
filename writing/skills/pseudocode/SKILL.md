---
name: pseudocode
description: >
  Generates LaTeX pseudocode from source code or natural-language algorithm
  descriptions. Use this skill when the user asks to "write pseudocode for",
  "generate pseudocode from this code", "convert to algorithm", "make a LaTeX
  algorithm block", "pseudocode this function", "algorithm block for my paper",
  or pastes code and asks for a LaTeX pseudocode version. Also triggers for:
  "turn this into an algorithm float", "algorithm environment for this",
  "write this as pseudocode in LaTeX".
  Default output: print preamble snippet + algorithm block to conversation.
  Flags: --save, --preamble-only, --algorithm-only, --file, --style.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# Pseudocode Skill (LaTeX)

Generates LaTeX pseudocode using `algorithm` + `algpseudocode` (the classic pairing).
Outputs both a preamble snippet and the `\begin{algorithm}...\end{algorithm}` block.
Prints to conversation by default; use `--save <path>` to write a `.tex` file.

---

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `--save <path>` | off | Write output to `.tex` file at path |
| `--file <path>` | — | Read source code from file instead of conversation |
| `--preamble-only` | off | Print only the preamble snippet, no algorithm block |
| `--algorithm-only` | off | Print only the algorithm block, no preamble |
| `--style <name>` | `full` | `full` (default, includes Input/Output/BState), `bare` (minimal, just `algorithm`+`algpseudocode` with `noend`), `standard` (vanilla `algpseudocode` without custom macros) |
| `--lang <name>` | auto | Source language hint (python, cpp, julia, fortran, etc.). Auto-detected if omitted. |

---

## Step 1 — Get the source code

Three input modes:

**Mode A — pasted code in conversation**: User says "pseudocode for this" and pastes a
function or script. Extract the code block from the conversation.

**Mode B — `--file <path>`**: Read the file. If it's a large file, ask the user which
function(s) to pseudocode. For small scripts (<100 lines), pseudocode the whole thing.

**Mode C — natural language description**: User describes an algorithm without code
("gradient descent with momentum, updates velocity then parameters, returns final
weights"). Build the algorithm from the description.

---

## Step 2 — Analyze the code

Extract:
- **Function signature**: name, parameters, return value
- **Main steps**: sequential blocks, loops, conditionals
- **Data flow**: what gets computed from what
- **Key operations**: mathematical formulas, data structure manipulations
- **Edge cases**: early returns, error handling

Simplify aggressively for pseudocode:
- Collapse boilerplate (imports, type hints, logging, assertions)
- Merge consecutive simple assignments into one logical step
- Replace library calls with descriptive text (e.g., `np.linalg.eigvals(H)` → "diagonalise H")
- Keep mathematical notation: subscripts, Greek letters, fractions → LaTeX math mode
- Use `\leftarrow` for assignment, `=` for equality tests

---

## Step 3 — Generate preamble snippet (`--style full`, default)

Output a preamble block with the user's preferred configuration. Wrap in comments
explaining where each line goes in the main `.tex` file.

```latex
% === Pseudocode preamble ===
% Add these lines to your main .tex preamble (before \begin{document}):

% Float container — numbered "Algorithm" box with caption
\usepackage{algorithm}

% Pseudocode typesetting engine — [noend] suppresses "end if/for/while" text
\usepackage[noend]{algpseudocode}

% Custom \Input and \Output commands (replace default \Require / \Ensure)
\algnewcommand\algorithmicInput{\textbf{Input:}}
\algnewcommand\Input[1]{\State\algorithmicInput\;#1}
\algnewcommand\algorithmicOutput{\textbf{Output:}}
\algnewcommand\Output[1]{\State\algorithmicOutput\;#1}

% \BState: begin-state without automatic indent (for block starts)
\makeatletter
\def\BState{\State\hskip-\ALG@thistlm}
\makeatother
```

**`--style bare`** — minimal preamble, just `noend`:

```latex
% === Pseudocode preamble (bare) ===
\usepackage{algorithm}
\usepackage[noend]{algpseudocode}
% Note: no custom \Input/\Output or \BState defined.
% Use \Require / \Ensure for input/output and \State for all statements.
```

**`--style standard`** — vanilla `algpseudocode` with no options:

```latex
% === Pseudocode preamble (standard) ===
\usepackage{algorithm}
\usepackage{algpseudocode}
```

---

## Step 4 — Generate the algorithm block

Follow the user's style (from Step 3). Structure:

```latex
\begin{algorithm}[htbp]
\caption{<descriptive title — what the algorithm does, not the function name>}
\label{alg:<label>}
\begin{algorithmic}[1]   % [1] = line numbers
    \Input{<parameters and their descriptions>}
    \Output{<return value and its meaning>}

    \State <first step>
    \State <next step>
    \For{<loop variable> \leftarrow <start> \textbf{to} <end>}
        \State <loop body>
    \EndFor
    \While{<condition>}
        \State <body>
    \EndWhile
    \If{<condition>}
        \State <true branch>
    \Else
        \State <false branch>
    \EndIf
    \State \Return <value>
\end{algorithmic}
\end{algorithm}
```

### Command reference

| Command | Use |
|---------|-----|
| `\State` | Single statement |
| `\BState` | Statement without indent (block start) |
| `\Input{...}` | Input parameters (`--style full`) |
| `\Output{...}` | Return value (`--style full`) |
| `\Require{...}` | Input (standard algpseudocode) |
| `\Ensure{...}` | Output (standard algpseudocode) |
| `\If{cond} ... \EndIf` | Conditional |
| `\ElsIf{cond} ...` | Else-if (requires `\Else` fallback: use `\Else\If{cond}`) |
| `\Else ...` | Else branch |
| `\For{var} ... \EndFor` | For loop |
| `\ForAll{var} ... \EndFor` | For-each loop |
| `\While{cond} ... \EndWhile` | While loop |
| `\Repeat ... \Until{cond}` | Repeat-until |
| `\Loop ... \EndLoop` | Infinite loop (needs internal break) |
| `\Procedure{name}{params} ... \EndProcedure` | Subroutine |
| `\Call{name}{args}` | Call a procedure |
| `\Comment{text}` | Inline comment (set off to right) |
| `\Return{value}` | Return statement |
| `\State $math$` | Inline math with `$...$` |
| `\State \text{text}` | Plain text inside math |
| `\textbf{keyword}` | Bold keywords (and, or, not, to, break) |

### Style conventions

- **Assignment**: `$x \leftarrow f(y)$` — use `\leftarrow`, not `=`
- **Equality test**: `$x = 0$` — bare `=` for conditions
- **Bold keywords**: `\textbf{and}`, `\textbf{or}`, `\textbf{not}`, `\textbf{to}`, `\textbf{break}`, `\textbf{continue}`, `\textbf{null}`, `\textbf{true}`, `\textbf{false}`
- **Math mode**: wrap all variables, formulas, and symbols in `$...$`
- **Text in math**: `$\text{if } x > 0$` — multi-word text inside math uses `\text{}`
- **Arrays/lists**: `$A[1..n]$` for indices, `$\{x_1, x_2, \ldots, x_n\}$` for sets
- **Comments**: `\Comment{explanation}` — appears right-aligned on same line
- **Line breaks**: `\Statex` for blank line, `\\` for line break inside a State
- **Nested blocks**: indent consistently (2 spaces per level)

### Naming the label

Use short, descriptive labels: `\label{alg:gradient-descent}`, `\label{alg:qr-factorization}`.
No spaces, no underscores in the label suffix (underscores before "alg:" are fine).

---

## Step 5 — Output

**Default behavior**: print both the preamble snippet and the algorithm block in the
conversation, separated clearly.

Format:

````
### Pseudocode preamble
```latex
... preamble lines ...
```

### Algorithm block
```latex
\begin{algorithm}[htbp]
...
\end{algorithm}
```
````

Follow with a usage note:

```
Include the preamble snippet in your main .tex preamble.
Use \input{alg-<label>.tex} (or paste the block directly) where you want the algorithm to appear.
```

**`--save <path>`**: before writing, show the complete file content as a diff preview
and ask for explicit approval. Once approved, write a single `.tex` file containing:
1. Comment block with preamble snippet (for reference — commented out)
2. The `\begin{algorithm}...\end{algorithm}` block

Do NOT include a `\documentclass` or standalone preamble — the file is meant for
`\input{}` into the user's main document. Confirm: `Written to <path>.`

**`--preamble-only`**: print only the preamble snippet. Useful when user already has
the algorithm block and just needs the style setup.

**`--algorithm-only`**: print only the algorithm block. Useful when preamble is already
configured.

---

## Step 6 — Quality checklist

Before outputting, verify:
- [ ] `\caption{}` is descriptive, not just the function name
- [ ] `\label{alg:...}` is unique and meaningful
- [ ] `\Input{}` and `\Output{}` describe parameters and return value clearly
- [ ] Mathematical notation is correct and in `$...$` math mode
- [ ] Assignment uses `\leftarrow`, not `=`
- [ ] Boolean keywords (`and`, `or`, `not`, `to`, `break`) are in `\textbf{}`
- [ ] No Python/Java/C++ syntax leaks into pseudocode (no `def`, `:=`, `==`, `!=`, `+=`, `[]` for array access — use `\leftarrow`, `=`, `\neq`, subscript notation)
- [ ] Line numbers enabled: `\begin{algorithmic}[1]`
- [ ] Float placement hint `[htbp]` on `\begin{algorithm}`
- [ ] No empty `\State` lines at beginning or end
- [ ] Consistent indentation (2 spaces per nesting level)
- [ ] `--style full`: preamble includes `\Input`, `\Output`, `\BState` definitions
- [ ] `--style bare` / `--style standard`: use `\Require`/`\Ensure` instead of `\Input`/`\Output`
