---
name: manuscript-audit-math
description: "Interactive sequential audit of mathematical derivations in a manuscript. Extracts all equations from a markdown or LaTeX file, classifies them as claims vs declarations, verifies each claim with SymPy, and stops on the first error for user decision. Supports error propagation (fix cascading to subsequent equations) and generates a full audit report. Use when you have a manuscript with hand-derived equations to check step-by-step, or when you want to verify that a chain of manipulations has no algebraic mistakes. Trigger: \"audit my derivation\", \"check manuscript equations\", \"verify my calculations\", \"audit math\", \"check my steps\"."
compatibility: "Requires Python 3.8+ and sympy>=1.12 (pip install sympy). Reads markdown (.md) and LaTeX (.tex) manuscripts."
---

# Manuscript Audit — Math

Sequential equation-by-equation audit of a manuscript. Finds the first error, stops, lets you decide what to do. Fixes propagate downstream.

## Flags

| Flag | Default | Description |
|---|---|---|
| `--propagate` | off | Auto-fix errors without asking. Continues verification with corrected values. |
| `--stop-on N` | `error` | When to pause: `error` (default), `warning` (also pause on uncertain results), `all` (pause after every equation) |
| `--save-report PATH` | `audit-report.md` | Where to write the final audit report |
| `--skip-before N` | 1 | Start auditing from equation N (skip earlier steps) |

## Workflow

### Phase 1: Read and parse

Read the manuscript file completely. Extract every equation with its context.

**For markdown (`.md`):**
- Display equations: `$$...$$`
- Inline equations: `$...$`
- Numbered equations may have `(1)`, `(2)`, etc. after them

**For LaTeX (`.tex`):**
- `\begin{equation}...\end{equation}`
- `\begin{align}...\end{align}` (treat each `\\` line as separate)
- `\begin{gather}...\end{gather}`
- `\[...\]` (display)
- `$$...$$` (display)
- `$...$` (inline)
- `\(...\)` (inline)

**Context capture:** For each equation, capture 1-2 lines of surrounding text so the agent can classify it.

### Phase 2: Classify

For each extracted equation, the agent reads its context and classifies:

| Label | Meaning | Action |
|---|---|---|
| `CHECK` | Asserted equality, identity, or result | Verify with SymPy |
| `DECLARATION` | Variable definition, notation setup | Skip |
| `HYPOTHESIS` | Assumed premise, condition, constraint | Skip |
| `NOTATION` | Inline math that's just symbols | Skip |

**Classification rules (agent judgment):**

CHECK when:
- The equation asserts equality: $F(x) = \int_0^x t^2 \sin t\,dt$, $A = B + C$
- The equation is the result of a manipulation: "we obtain", "therefore", "hence", "which gives"
- The equation states a numeric value or simplified form
- The equation is a derivation step between two other equations

SKIP when:
- "Let $x \in \mathbb{R}$" → DECLARATION
- "Assume $x > 0$" → HYPOTHESIS
- "For all $n \in \mathbb{N}$" → HYPOTHESIS
- "where $F$ is the antiderivative" → NOTATION
- "$\alpha$, $\beta$, $\gamma$" → NOTATION
- "since $n \to \infty$" → NOTATION
- "We define $S_n = \sum_{i=1}^n a_i$" → DECLARATION (this is definition, not claim to verify)

**Present the classification to the user** as a numbered list:

```
EQUATION AUDIT PLAN
───────────────────
  Eq 1: $F(x) = \int_0^x t^2 \sin t\,dt$  → CHECK
  Eq 2: "Let $u = t^2$, $dv = \sin t\,dt$" → DECLARATION
  Eq 3: $F(x) = -x^2\cos x + 2\int_0^x t\cos t\,dt$  → CHECK
  Eq 4: "Assume $x > 0$" → HYPOTHESIS (skip)
  Eq 5: $F(x) = ...$  → CHECK
  ...
───────────────────
12 equations found: 8 to CHECK, 4 to SKIP
Begin audit? (y/n)
```

Wait for user confirmation before verifying.

### Phase 3: Sequential verify loop

For each CHECK equation in order:

#### Step A: SymPy verification

Follow the sympy-verify procedure:
1. Generate Python code using sympy that asserts the equation is correct
2. Write to `/tmp/audit-step-N.py` (where N is the equation number)
3. Run with 30s timeout: `timeout 30 python3 /tmp/audit-step-N.py`
4. Classify result

**Critical:** When the equation uses variables defined in earlier steps (e.g., $F(x)$ from Eq 1 is used in Eq 3), the sympy script MUST include the definitions from all prior equations. The audit maintains a running state.

#### Step B: Outcome

| Result | Action |
|---|---|
| ✅ VERIFIED | Mark green. Move to next equation. |
| ❌ FAILED | The equation as written in the manuscript is wrong. STOP. |
| ⚠️ UNCERTAIN | SymPy can't verify (NotImplementedError, timeout). Mark warning, continue. |

#### Step C: Error gating (when FAILED)

**STOP the audit** and present:

```
━━━━━━━━━━━━━━━━━━━━━━━
❌ ERROR FOUND — Eq {N}
━━━━━━━━━━━━━━━━━━━━━━━
Manuscript says:
  $${manuscript_equation}$$

SymPy result:
  $${correct_equation}$$

━━━━━━━━━━━━━━━━━━━━━━━
[Fix & propagate]  Correct this equation and recalculate all
                   subsequent equations with the correct value.
[Skip]             Mark as known error, keep manuscript values,
                   continue auditing remaining equations.
[Stop audit]       End here. Report so far.
```

**If user chooses "Fix & propagate":**
- Update the running state with the correct result
- When verifying subsequent equations, use the corrected value (not the manuscript's wrong value)
- Mark the fix in the report

**If user chooses "Skip":**
- Mark ⚠️ ERROR-KNOWN
- Continue with manuscript values (cascading errors expected)
- Each subsequent equation may fail — that's informational, showing propagation

**If user chooses "Stop audit":**
- End the loop
- Generate partial report

**If `--propagate` flag is set:**
- Auto-apply "Fix & propagate" without asking
- Continue to next equation

#### Step D: Warning gating (when UNCERTAIN)

If `--stop-on warning` or `--stop-on all`:
- Pause and show the uncertainty
- Ask: [Skip] (continue) or [Stop audit]

Otherwise: mark ⚠️ and continue automatically.

### Phase 4: Audit report

After all equations are processed (or audit is stopped), generate a markdown report:

```markdown
# Math Audit Report — {manuscript filename}
**Date:** {date}
**Auditor:** pi + sympy-verify
**Status:** ✅ CLEAN / ⚠️ ISSUES FOUND / ❌ ERRORS REMAIN

## Summary

| Total equations | CHECK | DECLARATION | HYPOTHESIS | NOTATION |
|-----------------|-------|-------------|------------|----------|
| {N} | {n} | {n} | {n} | {n} |

| Status | Count |
|--------|-------|
| ✅ Verified | {n} |
| ❌ Error found & fixed | {n} |
| ⚠️ Error known (not fixed) | {n} |
| ⚠️ Uncertain | {n} |
| — Skipped (declarations etc.) | {n} |

## Equation-by-equation

| # | Label | Status | Manuscript | Correct |
|---|---|---------|------------|---------|
| 1 | CHECK | ✅ | $F(x) = \int_0^x t^2\sin t\,dt$ | — |
| 2 | DECL | — | "Let $u=t^2$..." | — |
| 3 | CHECK | ✅ | $F(x) = -x^2\cos x + 2\int_0^x...$ | — |
| 4 | CHECK | ❌→✅ | $F(x) = -x^2\cos x$ | $-x^2\cos x + 2\int_0^x t\cos t\,dt$ |
| 5 | CHECK | ✅* | $F(x) = ...$ | *Recomputed after Eq 4 fix |
| 6 | CHECK | ⚠️ | (timeout) | — |

\* Re-verified with propagation from corrected Eq 4.

## Errors Found

### Eq 4: Missing term in integration by parts
**Manuscript:** $-x^2\cos x$
**Correct:** $-x^2\cos x + 2\int_0^x t\cos t\,dt$
**Fix:** Applied. Eqs 5-8 recomputed.
```

Save to `--save-report` path (default: `audit-report.md`).

### Phase 5: Cleanup

```bash
rm -f /tmp/audit-step-*.py
```

Keep the report file.

## Running state

The audit tracks a running SymPy state — all variables and functions defined so far. When verifying Eq N, include all definitions from Eqs 1..N-1.

Example state tracking (in the agent's working memory):
```
State after Eq 1: x = Symbol('x'); F = Integral(t**2*sin(t), (t,0,x))
State after Eq 3: x, F defined; F_expr = -x**2*cos(x) + 2*Integral(t*cos(t), (t,0,x))
```

When Eq 4 is verified, the sympy script imports state from previous steps.

**Propagation:** If Eq 4 is corrected, recompute all subsequent equations that depend on it using the corrected value. The agent generates fresh sympy scripts for downstream equations.

## Handling complex manuscripts

### Aligned equations (`\begin{align}`)

```latex
\begin{align}
A &= B + C \\
  &= D + E \\
  &= F
\end{align}
```

Treat each line as a separate CHECK equation. The first line defines A in terms of B+C. The second line asserts (B+C) = (D+E). The third asserts (D+E) = F.

### Piecewise definitions

```latex
f(x) = \begin{cases}
x^2 & x \geq 0 \\
0 & x < 0
\end{cases}
```

Treat as DECLARATION (definition, not claim to verify). If the manuscript later asserts $f(3)=9$, that's a CHECK.

### Multi-step derivations with text

```
From Eq 3, we substitute u = sin x:
$$F(x) = \int_0^x u^2 \cos u\,du$$
Integrating by parts:
$$F(x) = x^2\sin x - 2\int_0^x u\sin u\,du$$
which simplifies to:
$$F(x) = x^2\sin x + 2x\cos x - 2\sin x$$
```

All three display equations are CHECK. The surrounding text is classification context.

### Cross-references

If Eq 7 says "From Eq 3, we have...", the sympy script for Eq 7 must include the definition from Eq 3. Track equation numbers and their definitions.

## Example session

```
User: /skill:manuscript-audit-math --save-report derivation-report.md derivation.md

Agent:
  Reading derivation.md...
  Extracting equations...

  EQUATION AUDIT PLAN
  ───────────────────
    Eq 1: $F(x) = \int_0^x t^2\sin t\,dt$ → CHECK
    Eq 2: "Let $u = t^2$" → DECLARATION
    Eq 3: $F(x) = -x^2\cos x + 2\int_0^x t\cos t\,dt$ → CHECK
    Eq 4: $F(x) = x^2\sin x + 2x\cos x - 2\sin x$ → CHECK
  ───────────────────
  4 equations: 3 CHECK, 1 DECLARATION
  Begin audit? (y/n)

User: y

Agent:
  --- Eq 1: $F(x) = \int_0^x t^2\sin t\,dt$ ---
  Running sympy-verify... ✅ VERIFIED

  --- Eq 3: $F(x) = -x^2\cos x + 2\int_0^x t\cos t\,dt$ ---
  Running sympy-verify... ✅ VERIFIED

  --- Eq 4: $F(x) = x^2\sin x + 2x\cos x - 2\sin x$ ---
  Running sympy-verify... ❌ FAILED

  ━━━━━━━━━━━━━━━━━━━━━━━
  ❌ ERROR FOUND — Eq 4
  ━━━━━━━━━━━━━━━━━━━━━━━
  Manuscript: $F(x) = x^2\sin x + 2x\cos x - 2\sin x$
  SymPy:      $F(x) = x^2\sin x + 2x\cos x - 2\sin x + 2$

  Missing constant term +2.

  [Fix & propagate] [Skip] [Stop audit]

User: Fix & propagate

Agent:
  Applied fix. Reprocessing Eq 4 and subsequent...

  --- Eq 4 (recomputed): $F(x) = x^2\sin x + 2x\cos x - 2\sin x + 2$
  ✅ CORRECTED

  No more equations.

  Audit complete. Report saved to derivation-report.md.
```

## Anti-patterns

- Don't skip classification — the user must see the plan before verification starts
- Don't continue past an error without gating (unless `--propagate`)
- Don't lose track of the running state — each sympy script must include all prior definitions
- Don't verify declarations or hypotheses — only verify claimed equalities
- Don't delete temp scripts until the audit is complete (they're evidence for the report)
