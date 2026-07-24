# Lean 4 + Mathlib4 Cheat Sheet for LLM Code Generation

Reference for generating syntactically correct, tactic-complete Lean 4 proofs. Use this before writing any `.lean` file.

## Quick Start Imports

```lean
import Mathlib                        -- imports everything (slow to compile, fine for single files)
import Mathlib.Tactic                 -- common tactics
import Mathlib.Data.Nat.Basic         -- natural numbers
import Mathlib.Data.Int.Basic         -- integers
import Mathlib.Data.Real.Basic        -- real numbers
import Mathlib.Data.Complex.Basic     -- complex numbers
import Mathlib.Algebra.Group.Basic    -- group theory
import Mathlib.Algebra.Ring.Basic     -- ring theory
import Mathlib.Algebra.Field.Basic    -- fields
import Mathlib.Algebra.BigOperators.Basic  -- ∑, ∏ notation
import Mathlib.Data.Set.Basic         -- sets
import Mathlib.Data.Finset.Basic      -- finite sets
import Mathlib.NumberTheory.Divisors  -- divisibility, primes
import Mathlib.Tactic.Linarith        -- linear arithmetic
import Mathlib.Tactic.Ring            -- ring expressions
import Mathlib.Tactic.Nlinarith       -- nonlinear arithmetic (ℕ, ℤ, ℝ)
import Mathlib.Tactic.Positivity      -- sign analysis
```

**Recommendation:** Start with `import Mathlib` for broad coverage. Switch to specific imports if compile time is an issue.

## Theorem Skeleton

```lean
import Mathlib

/-- A human-readable description of the theorem. -/
theorem my_theorem_name (hypotheses) : conclusion := by
  -- proof using tactics
```

### Naming conventions (Lean 4 style)
- `snake_case` for theorem names
- Descriptive: `sqrt_two_irrational`, `sum_first_n`, `triangle_inequality`
- Avoid starting with numbers

## Common Proof Patterns

### 1. Direct computation with `simp`, `ring`, `linarith`

```lean
example (a b : ℝ) : (a + b)^2 = a^2 + 2*a*b + b^2 := by
  ring
```

```lean
example (x y : ℤ) (h : x + y = 10) (h' : x - y = 2) : x = 6 := by
  linarith
```

```lean
example (n : ℕ) : n + 0 = n := by
  simp
```

### 2. Induction on `ℕ`

```lean
example (n : ℕ) : 2 ∣ n * (n + 1) := by
  induction n with
  | zero =>
      simp
  | succ k ih =>
      -- ih: 2 ∣ k * (k + 1)
      -- Goal: 2 ∣ (k+1) * ((k+1) + 1)
      rw [Nat.succ_eq_add_one]
      -- ... complete the proof
```

**Key:** `induction n with | zero => ... | succ k ih => ...` is the Lean 4 induction syntax.

### 3. Case analysis with `cases` or `by_cases`

```lean
example (n : ℕ) : n = 0 ∨ 1 ≤ n := by
  cases n with
  | zero => left; rfl
  | succ n => right; exact Nat.one_le_succ _
```

```lean
example (x : ℝ) : x ≤ |x| := by
  by_cases h : 0 ≤ x
  · rw [abs_of_nonneg h]
  · rw [abs_of_neg (not_le.mp h)]
    linarith
```

### 4. Working with quantifiers

```lean
-- ∀ (for all)
example : ∀ n : ℕ, n ≤ n^2 := by
  intro n
  -- now goal: n ≤ n^2
  cases n with
  | zero => simp
  | succ n => nlinarith

-- ∃ (there exists)
example : ∃ n : ℕ, n^2 = 9 := by
  use 3
  norm_num

-- → (implies)
example (h : 0 ≤ x) : 0 ≤ x^2 := by
  nlinarith
```

### 5. Contradiction proofs

```lean
example : ¬ (∃ n : ℕ, n < 0) := by
  intro h
  rcases h with ⟨n, hn⟩
  have := Nat.not_lt_zero n
  exact this hn
```

```lean
-- Standard irrationality pattern
theorem sqrt_two_irrational : ¬ ∃ (a b : ℕ), b ≠ 0 ∧ (a : ℝ) / (b : ℝ) = Real.sqrt 2 := by
  intro h
  rcases h with ⟨a, b, hb, h⟩
  -- derive a contradiction using properties of divisibility
  sorry
```

### 6. `calc` block for transitive reasoning

```lean
example (a b c : ℝ) (h1 : a = b + 1) (h2 : b = c - 1) : a = c := by
  calc
    a = b + 1 := h1
    _ = (c - 1) + 1 := by rw [h2]
    _ = c := by ring
```

### 7. Divisibility and modular arithmetic

```lean
open Nat

example (n : ℕ) (h : 3 ∣ n) : 3 ∣ n^2 := by
  rcases h with ⟨k, hk⟩
  rw [hk]
  use 3 * k^2
  ring

example (a b : ℕ) (ha : a % 2 = 0) (hb : b % 2 = 0) : (a + b) % 2 = 0 := by
  have ha' : 2 ∣ a := Nat.dvd_of_mod_eq_zero ha
  have hb' : 2 ∣ b := Nat.dvd_of_mod_eq_zero hb
  have hsum : 2 ∣ a + b := Nat.dvd_add ha' hb'
  exact Nat.mod_eq_zero_of_dvd hsum
```

### 8. Sums and products (big operators)

```lean
open BigOperators

example (n : ℕ) : (∑ i in Finset.range (n+1), i) = n * (n+1) / 2 := by
  induction n with
  | zero => simp
  | succ k ih =>
      rw [Finset.sum_range_succ, ih, Nat.succ_eq_add_one]
      ring
```

### 9. Sets and membership

```lean
open Set

example (x : ℝ) (A B : Set ℝ) (hx : x ∈ A ∩ B) : x ∈ A := by
  rcases hx with ⟨hxA, hxB⟩
  exact hxA

example (A B : Set ℕ) (h : A ⊆ B) : (∀ x, x ∈ A → x ∈ B) := by
  intro x hx
  exact h hx
```

### 10. Natural number inequalities

```lean
example (n m : ℕ) (h : n ≤ m) : n^2 ≤ m^2 := by
  nlinarith

-- WARNING: subtraction in ℕ is truncated! a - b = 0 if a < b
example (a b : ℕ) (h : b ≤ a) : (a - b) + b = a := by
  omega
```

## Common Pitfalls

### 1. ℕ subtraction is truncated
```lean
-- WRONG (fails when a < b)
example (a b : ℕ) : a - b + b = a := by
  omega -- only true if b ≤ a

-- BETTER: use ℤ or ℝ for subtraction, or add hypothesis b ≤ a
example (a b : ℕ) (h : b ≤ a) : (a - b) + b = a := by
  omega
```

### 2. Typeclass inference
```lean
-- May fail if Lean can't infer the ring/field structure
example (x : ℝ) : x + 0 = x := by
  ring  -- works because ℝ is a ring

-- BUT this fails:
example (x : ℕ) : x + 0 = x := by
  ring  -- ring doesn't work for ℕ (semiring, not ring)
  -- Use `simp` or `omega` instead
```

### 3. `exact` vs `apply` vs `refine`
```lean
h : A
goal: A
-- Use: exact h

h : A → B
goal: B
-- Use: apply h  (creates new goal: A)

h : A → B → C
goal: C
-- Use: refine h ?_ ?_  (creates two goals: A and B)
```

### 4. `rw` (rewrite) direction
```lean
h : a = b
goal: a + 1 = c
-- rw [h] changes goal to: b + 1 = c

h : a = b
goal: b + 1 = c
-- rw [← h] changes goal to: a + 1 = c
```

### 5. `simp` can be too aggressive or too weak
```lean
-- `simp` may not close the goal, try:
simp?  -- shows what simp can and can't do
simp [h]  -- add specific hypotheses
simp [my_lemma]  -- add custom lemmas
```

## Domain-Specific Patterns

### Number Theory

```lean
import Mathlib.NumberTheory.Divisors
open Nat

-- Prime definition
example : Nat.Prime 7 := by
  norm_num [Nat.prime_def_sqrt]

-- gcd
example (a b : ℕ) : Nat.gcd a b = Nat.gcd b a :=
  Nat.gcd_comm a b

-- Coprime
example (a b : ℕ) (h : Nat.Coprime a b) : Nat.gcd a b = 1 := h
```

### Real Analysis (basic)

```lean
import Mathlib.Analysis.SpecialFunctions.Pow.Real
open Real

-- Limits (filter-based, can be heavy)
example : Tendsto (fun x : ℝ => x^2) (𝓝 0) (𝓝 0) := by
  -- complex; often need `simp` + known limits
  sorry

-- Continuity (easier with existing lemmas)
example : Continuous (fun x : ℝ => x^2) := by
  continuity
```

### Linear Algebra

```lean
import Mathlib.LinearAlgebra.Matrix.Determinant
open Matrix

-- Determinant of 2x2
example (a b c d : ℝ) : det ![![a, b], ![c, d]] = a*d - b*c := by
  simp [det_fin_two]
```

## Tactics Quick Reference

| Tactic | Use | Example |
|---|---|---|
| `rfl` | Definitional equality | `1 + 1 = 2` |
| `simp` | Simplification with known lemmas | `0 + n = n` |
| `ring` | Ring expressions (ℝ, ℤ, ℚ) | `(a+b)^2 = a^2+2ab+b^2` |
| `linarith` | Linear arithmetic (ℤ, ℝ, ℚ) | `x+y=10, x-y=2 ⊢ x=6` |
| `nlinarith` | Nonlinear arithmetic | `n ≤ n^2` for ℕ |
| `omega` | Presburger arithmetic (ℕ, ℤ) | `a+b = c+d, a<c ⊢ b>d` |
| `positivity` | Sign of expressions | `x^2 ≥ 0` |
| `norm_num` | Numerical computation | `2+2 = 4`, `Nat.Prime 7` |
| `exact` | Provide exact term | `exact h` |
| `apply` | Match goal with implication | `apply h` |
| `refine` | Partial term with holes | `refine h ?_` |
| `intro` | Introduce ∀, → hypothesis | `intro h` |
| `intros` | Introduce multiple hypotheses | `intros x y h` |
| `rcases` | Destruct ∃, ∧, ∨, structures | `rcases h with ⟨x, hx⟩` |
| `have` | Create intermediate lemma | `have h2 : A := by ...` |
| `use` | Provide ∃ witness | `use 3` |
| `rw` | Rewrite with equality | `rw [h]` |
| `calc` | Chained equalities | `calc a = b := h1; _ = c := h2` |
| `induction` | Induction on inductive type | `induction n with \| zero => ...` |
| `cases` | Case analysis | `cases n with \| zero => ...` |
| `by_cases` | Case split on proposition | `by_cases h : P` |
| `by_contra` | Proof by contradiction | `by_contra h` |
| `push_neg` | Push negation inward | `¬(∀ x, P x)` to `∃ x, ¬P x` |
| `field_simp` | Clear denominators | `field_simp` when `h : b ≠ 0` |

## What Works Well (mathlib4 is mature)

- **Number theory**: divisibility, primes, gcd/lcm, modular arithmetic, Fermat/Euler theorems
- **Algebra**: groups, rings, fields, polynomials, linear algebra
- **Combinatorics**: finite sets, sums, products, binomial coefficients
- **Logic**: propositional logic, predicate logic, set theory basics
- **Real numbers as ordered field**: algebraic properties, inequalities via `linarith`/`nlinarith`

## What's Hard (mathlib4 gaps)

- **Analysis**: limits, continuity, differentiation have API but are complex (filter-based)
- **Probability**: very limited, mostly measure-theoretic foundation
- **Topology**: definitions exist, but many classical theorems missing
- **Advanced algebra**: representation theory, homological algebra — sparse
- **Geometry**: synthetic geometry, manifolds — very incomplete
- **Applied math**: ODEs, PDEs, numerical analysis — minimal

## Checking Your Proof

Before running `lake build`, the LLM should mentally verify:
1. All imported modules are actually needed (or just `import Mathlib`)
2. All variables in the theorem statement are typed
3. Every tactic either closes a goal or reduces to one goal
4. No `sorry` left in the proof
5. The statement is complete (no missing hypotheses)
6. `ℕ` subtraction has the `b ≤ a` guard if used
7. `ring` is not used on `ℕ` (use `omega` or `simp` instead)
8. The proof ends with `done` or the last tactic closes the last goal
