---
name: sympy-verify
description: Verifies mathematical results by generating and executing SymPy verification scripts. Before returning any answer to a math query (integrate, differentiate, solve, simplify, limit, series, evaluate, compute, linear algebra, differential equations, etc.), generates a Python+SymPy script that checks the result and runs it. Only outputs results that pass verification. Use for any symbolic computation to catch errors before the user sees them.
compatibility: "Requires Python 3.8+ and sympy>=1.12. Install: pip install sympy"
---

# SymPy Verify

Every math answer gets a SymPy verification script. No unverified result leaves the session.

## Flags

Parse these from the user message or `/skill:sympy-verify` args:

| Flag | Default | Description |
|---|---|---|
| `--timeout N` | 30 | Seconds before killing stuck computation |
| `--retries N` | 3 | Max retry attempts on verification failure |
| `--save PATH` | (none) | Save verification script to PATH instead of /tmp/verify.py |

All flags optional. Defaults work for most use cases.

## Workflow

### Step 1: Receive math query

User provides any mathematical computation request. Examples:
- "integrate x^2 sin(x) from 0 to pi"
- "solve x^3 - 6x^2 + 11x - 6 = 0"
- "eigenvalues of [[1,2],[3,4]]"
- "limit of sin(x)/x as x→0"

### Step 2: Generate answer + verification code

Produce both:
- **Answer** in LaTeX: display math with `$$...$$`, inline with `$...$`
- **Python verification script** using sympy

The script must:
1. Import sympy and any needed submodules
2. Declare all symbols explicitly (`x = sp.Symbol('x', real=True)` when applicable)
3. Perform the computation via sympy
4. Compare with the claimed answer using `sp.simplify(result - expected) == 0` or equivalent
5. `assert` the comparison passes, with a descriptive error message
6. `print()` the verified result on success

### Step 3: Write and run

```bash
python3 /tmp/verify.py
```

Use bash `timeout` to enforce the limit:
```bash
timeout 30 python3 /tmp/verify.py
```

If `--save PATH` is set, write to that path instead of `/tmp/verify.py`.

### Step 4: Classify result

| Exit code / exception | Classification | Action |
|---|---|---|
| 0, no exception | **Verified** | Output answer to user. Session marks result as verified. |
| `NotImplementedError` | **Unsupported** | SymPy lacks the algorithm. Tell user honestly. Do not retry. |
| Timeout (124) or hangs | **Timeout** | Computation too expensive symbolically. Suggest numerical approach or simplification. |
| `AssertionError` | **Wrong answer** | LLM answer doesn't match sympy. Feed error back, retry up to N times. |
| `TypeError`, `ValueError`, `NameError` | **Bad code** | LLM generated broken Python. Feed error back, retry up to N times. |
| Other exception | **Unknown** | Show error to user. Offer retry. |

### Step 5: Retry loop (for Wrong answer / Bad code)

1. Feed the **full error message** and traceback back to the LLM
2. LLM regenerates the answer and verification script
3. Re-run
4. Repeat up to `--retries` times
5. If all retries exhausted: show last error, mark as unverified, let user decide

### Step 6: Session tracking

After each verification attempt, note in session context:
- Query
- Answer (marked VERIFIED or UNVERIFIED)
- Number of retries used
- Script path

## Code Template

```python
import sympy as sp

# === Declare symbols ===
x = sp.Symbol('x', real=True)
# Add more symbols as needed

# === Perform computation ===
result = sp.integrate(x**2 * sp.sin(x), (x, 0, sp.pi))

# === Expected answer (from LLM) ===
expected = sp.pi**2 - 4

# === Verify ===
assert sp.simplify(result - expected) == 0, f"Mismatch:\n  SymPy: {result}\n  Expected: {expected}"

print(f"VERIFIED: {result}")
```

Adapt the template to the query type:
- Integration: `sp.integrate`, `sp.Integral`
- Differentiation: `sp.diff`
- Solving: `sp.solve`, `sp.solveset`, `sp.dsolve`
- Limits: `sp.limit`
- Series: `sp.series`
- Linear algebra: `sp.Matrix(...).eigenvals()`, etc.
- Simplification: `sp.simplify`

For numerical answers, use `sp.N()` or `float()` with `abs(result - expected) < 1e-10` tolerance.

## Anti-patterns

- Do NOT output the answer before the script passes
- Do NOT retry on `NotImplementedError` — it will never work
- Do NOT run without timeout — SymPy can hang on hard problems
- Do NOT skip verification even for "obvious" results — LLMs hallucinate math

## Examples

### Single-variable integration

User: "integrate sin(x) from 0 to pi"

```python
import sympy as sp
x = sp.Symbol('x', real=True)
result = sp.integrate(sp.sin(x), (x, 0, sp.pi))
expected = 2
assert sp.simplify(result - expected) == 0, f"Mismatch: {result} != {expected}"
print(f"VERIFIED: {result}")
```

### Eigenvalues

User: "eigenvalues of [[1,2],[3,4]]"

```python
import sympy as sp
M = sp.Matrix([[1, 2], [3, 4]])
result = sorted(M.eigenvals().keys())
expected = [5/2 - sp.sqrt(33)/2, 5/2 + sp.sqrt(33)/2]
assert all(sp.simplify(a - b) == 0 for a, b in zip(result, expected)), f"Mismatch: {result} != {expected}"
print(f"VERIFIED: eigenvalues = {result}")
```

### Differential equation

User: "solve dy/dx = -2xy, y(0)=1"

```python
import sympy as sp
x = sp.Symbol('x')
y = sp.Function('y')
result = sp.dsolve(sp.Eq(y(x).diff(x), -2*x*y(x)), ics={y(0): 1})
expected = sp.Eq(y(x), sp.exp(-x**2))
assert sp.simplify(result.rhs - expected.rhs) == 0, f"Mismatch: {result} != {expected}"
print(f"VERIFIED: {result}")
```
