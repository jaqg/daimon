---
name: derivation-lab
disable-model-invocation: true
description: "Interactive mathematical derivation notebook. Creates a LaTeX document that grows step-by-step as you and the agent explore a problem, with every manipulation verified by SymPy. Appends each step to a single sympy script (re-runnable) and to a .tex file, compiling to PDF at milestones so you can read the progress in human-readable form. Use when exploring a new mathematical approach, developing a derivation collaboratively, or sketching a solution that needs verification and a durable PDF record. Trigger: \"derive with me\", \"new derivation\", \"explore this problem\", \"sketch a solution\", \"derivation lab\", \"work through this math\"."
compatibility: "Requires pdflatex (texlive), Python 3.8+ with sympy>=1.12. Install: pip install sympy. For pdflatex: sudo pacman -S texlive-core (Arch) or apt install texlive-latex-base (Debian/Ubuntu)."
---

# Derivation Lab

Exploratory math notebook. You and the agent derive together. Every step is verified and written to a durable, compilable LaTeX document. A companion SymPy script records all manipulations so the full derivation can be re-run.

Output: `derivation-{slug}.tex`, `derivation-{slug}.py`, `derivation-{slug}.pdf`

## Flags

| Flag | Default | Description |
|---|---|---|
| `--title TITLE` | (required) | Title for the derivation document |
| `--slug NAME` | from title | File name slug (lowercase, hyphens) |
| `--author NAME` | from config or user | Author name for the LaTeX document |
| `--compile-on STEP` | `ask` | When to compile PDF: `ask` (agent asks after each step), `milestone` (compile when user says "compile"), `end` (only at the end) |

## Workflow

### Phase 1: Initialize

Create three files:

#### `derivation-{slug}.tex`

```latex
\documentclass[12pt]{article}
\usepackage{amsmath, amssymb, amsthm}
\usepackage{geometry}
\geometry{margin=1in}
\usepackage{hyperref}

\title{Derivation: {title}}
\author{{author}}
\date{\today}

\begin{document}
\maketitle

% === Derivation steps ===

\end{document}
```

```bash
# Write the template
cat > derivation-{slug}.tex << 'TEXEOF'
...
TEXEOF
```

#### `derivation-{slug}.py`

```python
"""
Derivation: {title}
SymPy verification companion.
Run: python3 derivation-{slug}.py
"""
import sympy as sp

# Steps will be appended here
```

```bash
cat > derivation-{slug}.py << 'PYEOF'
...
PYEOF
```

Notify user: "Derivation lab initialized. Files: `derivation-{slug}.tex`, `derivation-{slug}.py`. Ready for Step 1."

### Phase 2: Step loop

For each step in the derivation:

#### Step A: Receive the step

User describes what to do next. Examples:
- "Try integration by parts with u = x²"
- "Substitute t = sin(x) and simplify"
- "Take the limit as n → ∞"
- "Factor and cancel the common term"

#### Step B: Derive with verification

1. Agent works through the manipulation mathematically
2. Agent appends the verification code to `derivation-{slug}.py`
3. Agent appends the step to `derivation-{slug}.tex`
4. Agent runs the script (or just the new step section) to verify

#### Step C: Write to .py (single accumulating script)

Append to the Python file. Each step is a clearly marked section that reuses variables from all prior steps:

```python
# === Step 1: Problem setup ===
x = sp.Symbol('x', real=True)
F = sp.integrate(x**2 * sp.sin(x), (x, 0, x))
# (definition, no assert needed for setup)
print("Step 1: Defined F(x) = ∫₀ˣ t² sin(t) dt")

# === Step 2: Integration by parts ===
u = x**2
dv = sp.sin(x)
du = 2*x
v = -sp.cos(x)
integrated = u*v - sp.integrate(v*du, (x, 0, x))
expected = -x**2*sp.cos(x) + 2*sp.integrate(x*sp.cos(x), (x, 0, x))
assert sp.simplify(integrated - expected) == 0, f"Step 2 mismatch: got {integrated}, expected {expected}"
print("Step 2: VERIFIED — integration by parts correct")

# === Step 3: Solve the remaining integral ===
inner = sp.integrate(x*sp.cos(x), (x, 0, x))
expected_inner = x*sp.sin(x) + sp.cos(x) - 1
assert sp.simplify(inner - expected_inner) == 0, f"Step 3 mismatch: got {inner}, expected {expected_inner}"
print("Step 3: VERIFIED — inner integral solved")

# === Step 4: Final expression ===
final = -x**2*sp.cos(x) + 2*(x*sp.sin(x) + sp.cos(x) - 1)
expected_final = -x**2*sp.cos(x) + 2*x*sp.sin(x) + 2*sp.cos(x) - 2
assert sp.simplify(final - expected_final) == 0, f"Step 4 mismatch: got {final}, expected {expected_final}"
print("Step 4: VERIFIED — final expression")

print("\n=== ALL STEPS VERIFIED ===")
```

The agent uses `write` to append to the file, or rewrites the full file with all accumulated steps.

**Critical rule:** Never start a new sympy script for a new step. Always append to the same `derivation-{slug}.py`. The single script is the ground truth.

#### Step D: Write to .tex (human-readable document)

Append a `\subsection{}` to the LaTeX file. The section includes:
- Step number and description
- The mathematical manipulation in LaTeX (using `align*` or `equation*`)
- Verification status badge

```latex
% Append this between \maketitle and \end{document}

\subsection{Step 1: Problem setup}

Define the function:
\begin{equation*}
F(x) = \int_0^x t^2 \sin t\,dt
\end{equation*}

\textit{Status:} $\checkmark$ defined

\subsection{Step 2: Integration by parts}

Let $u = t^2$, $dv = \sin t\,dt$, so $du = 2t\,dt$, $v = -\cos t$:

\begin{align*}
F(x) &= \left[-t^2\cos t\right]_0^x + 2\int_0^x t\cos t\,dt \\
     &= -x^2\cos x + 2\int_0^x t\cos t\,dt
\end{align*}

\textit{Status:} $\checkmark$ verified

\subsection{Step 3: Inner integral}

\[
\int_0^x t\cos t\,dt = x\sin x + \cos x - 1
\]

\textit{Status:} $\checkmark$ verified

\subsection{Step 4: Final expression}

\begin{align*}
F(x) &= -x^2\cos x + 2(x\sin x + \cos x - 1) \\
     &= -x^2\cos x + 2x\sin x + 2\cos x - 2
\end{align*}

\textit{Status:} $\checkmark$ verified
```

**Insertion strategy:** The agent reads `derivation-{slug}.tex`, finds `\end{document}`, and inserts the new step content right before it. Use sed or a simple edit:

```bash
# Insert before \end{document}
sed -i '/^\\end{document}/e cat /tmp/new-step.tex' derivation-{slug}.tex
```

Or better: read the file, use the `edit` tool to replace `\end{document}` with `{new step}\n\end{document}`.

#### Step E: Verify by running the script

```bash
timeout 30 python3 derivation-{slug}.py
```

If any step fails, report and fix before proceeding.

**On failure:** The failing assert pinpoints which step is wrong. Fix that step in both the .py and .tex, then continue.

#### Step F: Compile PDF (when appropriate)

Based on `--compile-on`:

- `ask`: After each step, ask "Compile PDF to review? (y/n)"
- `milestone`: User says "compile" or "show me the PDF"
- `end`: Only compile at the very end

Compilation:

```bash
pdflatex -interaction=nonstopmode derivation-{slug}.tex
# Run twice for cross-references (if any)
pdflatex -interaction=nonstopmode derivation-{slug}.tex
```

Check for LaTeX errors. If compilation fails, fix the .tex before continuing.

Clean aux files:

```bash
rm -f derivation-{slug}.aux derivation-{slug}.log derivation-{slug}.out
```

Show the PDF path to the user: `derivation-{slug}.pdf`

### Phase 3: Completion

When the user indicates the derivation is complete:

1. Add a final section to the .tex:

```latex
\section*{Verification}

All steps verified by SymPy. Companion script: \texttt{derivation-{slug}.py}\\
Run: \texttt{python3 derivation-{slug}.py}
```

2. Run the full script one final time to confirm everything passes:

```bash
python3 derivation-{slug}.py
```

3. Compile the final PDF:

```bash
pdflatex -interaction=nonstopmode derivation-{slug}.tex && pdflatex -interaction=nonstopmode derivation-{slug}.tex
```

4. Report:

```
DERIVATION COMPLETE
───────────────────
  derivation-{slug}.tex   — LaTeX source
  derivation-{slug}.py    — SymPy verification (all steps pass)
  derivation-{slug}.pdf   — Compiled PDF
───────────────────
All {N} steps verified ✅
```

## Collision handling

If `derivation-{slug}.tex` already exists, verify with user:

```
File derivation-{slug}.tex already exists.
[Resume]    Continue from where we left off (read existing files)
[Overwrite] Start fresh, delete existing
[New name]  Choose a different --slug
```

**Resume mode:** Read the existing .tex and .py, understand the current state, and continue from the last step. The agent reads both files and reports: "Resuming derivation with {N} existing steps. Last step: {description}. Ready for Step {N+1}."

## Anti-patterns

- Don't create separate sympy scripts per step — everything in one file
- Don't skip verification even when "obvious" — the script is the audit trail
- Don't compile PDF without checking for LaTeX errors
- Don't lose the .aux/.log divergence on first compilation — run pdflatex twice if needed
- Don't overwrite existing derivations without asking

## Example session

```
User: /skill:derivation-lab --title "Gaussian Integral" --slug gaussian-integral

Agent:
  Derivation lab initialized.
  Files: derivation-gaussian-integral.tex, derivation-gaussian-integral.py
  Ready for Step 1.

User: Start with I = ∫_{-∞}^{∞} e^{-x²} dx

Agent:
  --- Step 1: Problem setup ---
  Appending to .tex...
  Appending to .py...
  Running verification... ✅

  Step 1 done. I(x) = ∫ e^{-x²} dx defined.
  Compile PDF? (y/n)

User: n

User: Square it: I² = ∫∫ e^{-(x²+y²)} dx dy

Agent:
  --- Step 2: Square the integral ---
  ...
  Running verification... ✅

  Step 2 done. I² expressed as double integral.
  Compile PDF? (y/n)

User: y

Agent:
  Compiling...
  PDF ready: derivation-gaussian-integral.pdf

User: Switch to polar coordinates

Agent:
  --- Step 3: Polar transform ---
  ...
  Running verification... ✅

  Step 3 done. Jacobian applied.
  ...
```
