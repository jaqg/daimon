---
name: lean-verify
description: "Formal proof verification using Lean 4 and mathlib4. Takes a theorem/lemma in natural language, generates Lean 4 code, and verifies it via the Lean type checker. If Lean accepts the proof, the result is mechanically verified. Use for theorems, lemmas, propositions, conjectures that need formal certification. Trigger: \"prove formally\", \"verify in Lean\", \"formal proof of\", \"Lean verification\", \"mechanically check this proof\"."
compatibility: "Requires Lean 4 (elan) and mathlib4. First build downloads and compiles mathlib4 (10-30 min, ~4GB). Arch: elan not in pacman, install via curl script. See instructions below."
---

# Lean Verify

Formal verification: the gold standard. If Lean 4 type-checks your proof, it's correct — no caveats, no "probably", no hand-waving.

## Flags

| Flag | Default | Description |
|---|---|---|
| `--lib PATH` | `.lean-proofs/` (project root) | Directory for the persistent Lean project and proof library |
| `--retries N` | 3 | Max repair attempts when Lean rejects a proof |
| `--name NAME` | auto-generated | Theorem name in Lean (camelCase, alphanumeric) |

## Setup

### Step 1: Install Lean 4

Check if Lean is installed:

```bash
lean --version
```

If not installed, install via `elan` (the Lean version manager, like rustup):

```bash
curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh
```

Restart your shell or source:

```bash
source ~/.bashrc   # or ~/.zshrc
```

Verify:

```bash
lean --version    # should show Lean 4.x.x
lake --version    # should show Lake x.x.x
```

### Step 2: Initialize the proof library

The skill maintains **one persistent Lean project** at `--lib` path. All verified proofs live there as separate `.lean` files.

If the directory doesn't exist, create and initialize it:

```bash
mkdir -p .lean-proofs
cd .lean-proofs
lake new proofs lib   # creates a library project called "Proofs"
```

This creates:
```
.lean-proofs/
├── Proofs/
│   ├── Proofs.lean
│   └── ...
├── lakefile.lean
├── lake-manifest.json
└── .lake/            # built dependencies (mathlib4 lives here after build)
```

**Important:** After `lake new`, edit `lakefile.lean` to add `mathlib4` as a dependency:

```lean
import Lake
open Lake DSL

package «proofs» where

@[default_target]
lean_lib «Proofs» where

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git"
```

### Step 3: First build

On first run, mathlib4 must be downloaded and compiled. This takes **10-30 minutes** and uses **~4GB of disk**.

**Before proceeding, ask the user for confirmation.** Say:

> "mathlib4 needs to be built first. This downloads ~4GB and compiles for 10-30 minutes. Proceed? (y/n)"

If the user approves:

```bash
cd .lean-proofs && lake build
```

If the user declines, abort and tell them to run `lake build` manually when ready.

On subsequent runs, `lake build` is fast (only changed files recompile).

## Workflow

### Step 1: Receive theorem

User provides a theorem/lemma/proposition in natural language. Examples:

- "Prove that sqrt(2) is irrational"
- "Prove the triangle inequality: |x + y| ≤ |x| + |y| for real numbers"
- "Prove that there are infinitely many primes"
- "Prove: if n is even, then n² is divisible by 4"

The skill works best for:
- **Number theory**: divisibility, primes, gcd, modular arithmetic
- **Algebra**: groups, rings, fields, linear algebra
- **Logic**: propositional, predicate, basic set theory
- **Combinatorics**: finite sets, counting, bijections
- **Analysis (basic)**: limits, continuity, differentiation (mathlib4 support improving)

Harder domains (mathlib4 gaps):
- Probability theory (limited)
- Topology (advanced topics spotty)
- Category theory (definitions exist, proofs sparse)
- Advanced analysis (measure theory, PDEs)

### Step 2: Load LLM context

Before generating Lean code, read the reference guide:

```
read theory/skills/lean-verify/references/lean-guide.md
```

This provides the LLM with common mathlib4 imports, proof patterns, and pitfalls. The LLM must consult this before writing any Lean code.

### Step 3: Check for name collisions

If `--name TheoremName` is provided, check if `.lean-proofs/Proofs/TheoremName.lean` already exists.

```bash
ls .lean-proofs/Proofs/TheoremName.lean 2>/dev/null
```

If it exists, warn the user and either:
- Append a number suffix (`TheoremName2.lean`)
- Ask the user to provide a different `--name`

If no `--name` given, auto-generate from the theorem:
- "sqrt(2) is irrational" → `sqrt2_irrational`
- "triangle inequality" → `triangle_inequality`
- Remove special characters, camelCase, prefix with `thm_` if needed

### Step 4: Generate Lean proof

LLM writes a complete `.lean` file with:

```lean
import Mathlib

/-!
# Theorem: {natural language statement}

Formal proof in Lean 4 using mathlib4.
-/

open Real
open Nat

/-- {Natural language statement} -/
theorem {name} : {formal_statement} := by
  {proof}
```

Write to `.lean-proofs/Proofs/{name}.lean`.

**Critical rules for the LLM:**
- Must `import Mathlib` (or specific mathlib4 modules from the reference guide)
- Theorem statement must be syntactically valid Lean 4
- Use tactics: `rfl`, `simp`, `ring`, `linarith`, `nlinarith`, `positivity`, `apply`, `intro`, `cases`, `induction`, `calc`, `have`, `show`, `refine`, `exact`
- For arithmetic: `ring`, `linarith`, `nlinarith`, `omega` are powerful
- For `ℕ` induction: `induction n with k ih`
- For `∃` proofs: `use` to provide the witness
- For `∀` proofs: `intro` the variable
- See `references/lean-guide.md` for complete patterns

### Step 5: Build and verify

Run `lake build` from the library directory:

```bash
cd .lean-proofs && lake build 2>&1
```

Two outcomes:

#### Success (exit code 0)

```
VERIFIED: {theorem_name}
Lean 4 type-checked the proof. The theorem is formally verified.

Proof saved: .lean-proofs/Proofs/{name}.lean
```

#### Failure (exit code ≠ 0)

Compiler error output. Feed the **complete error message** back to the LLM for repair.

### Step 6: Repair loop (up to N retries)

When Lean rejects the proof:

1. Read the compiler error carefully
2. Identify what failed: type mismatch? Missing hypothesis? Tactic can't close goal?
3. Regenerate the `.lean` file with the fix
4. Rebuild
5. Repeat up to `--retries` times

Common errors and fixes:

| Error | Meaning | Fix |
|---|---|---|
| `type mismatch` | Statement doesn't match proof | Check theorem signature vs what you're proving |
| `unsolved goals` | Tactic didn't close all subgoals | Add more steps, use `done` to isolate |
| `unknown identifier` | Missing import or typo | Import the right module, check spelling |
| `failed to synthesize instance` | Can't find typeclass (e.g., `AddCommGroup`) | Check types, open right namespace |
| `tactic 'ring' failed` | Expression not a ring | Check assumptions, use `ring_nf` or manual `simp` |
| `no goals to be solved` | Already done | Remove extra tactics, or the proof is complete |

If all retries exhausted:
- Show the last error
- Save the failed attempt (append `.failed` to filename)
- Tell user: "Proof not verified after N attempts. Last error: {error}. Failed file saved at .lean-proofs/Proofs/{name}.failed.lean for manual repair."

### Step 7: Save verified proof

On success, the proof is already saved at `.lean-proofs/Proofs/{name}.lean`. The persistent project keeps all verified proofs. To list them:

```bash
ls .lean-proofs/Proofs/*.lean
```

To use a verified theorem in a new proof, import it:

```lean
import Proofs.sqrt2_irrational
```

## Cleanup

No cleanup needed — the persistent project is the proof library. Failed attempts with `.failed` suffix can be removed manually.

## Example Session

```
User: /skill:lean-verify --name sqrt2_irrational "Prove sqrt(2) is irrational"

Agent:
  Reading reference guide...
  Checking lean4... installed (Lean 4.8.0)
  Library project exists at .lean-proofs/
  Checking name collision... none
  Generating Lean proof...

  File written: .lean-proofs/Proofs/sqrt2_irrational.lean
  Running lake build...

  Build successful ✓

  VERIFIED: sqrt2_irrational
  Theorem: sqrt(2) is irrational
  Proof saved: .lean-proofs/Proofs/sqrt2_irrational.lean
```

```
User: /skill:lean-verify "Prove the sum of first n natural numbers is n(n+1)/2"

Agent:
  Generating Lean proof... (attempt 1)
  Running lake build...
  Error: unsolved goals at line 12

  Repairing... (attempt 2)
  Running lake build...
  Error: type mismatch at line 8

  Repairing... (attempt 3)
  Running lake build...

  Build successful ✓

  VERIFIED: sum_first_n
  Theorem: ∑_{i=1}^n i = n(n+1)/2
  Proof saved: .lean-proofs/Proofs/sum_first_n.lean
  Retries used: 2
```
