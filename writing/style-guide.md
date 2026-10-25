# Style guide — project documents

Authoritative voice rules for `sci-doc` and the report-writer agent. Generic
scientific-writing advice from vendored skills yields to this file.

Refine as you notice annoyances. Keep it under ~120 lines — every rule here is
read on every drafting pass, so each line costs context.

## Global voice

- Person: 1st plural "we" ("We computed...", "We observe that...").
- Tense: methods past ("we optimized"); results/conclusions present
  ("Fig. 2 shows", "the energy decreases"); never mixed within a sentence.
- Register: terse-technical. Assume an expert reader; no explanation of known
  concepts. One idea per sentence; short sentences preferred.
- Banned words: novel, robust, comprehensive, efficient, impressive,
  state-of-the-art (unless literally verified), "significant" as hype
  (fine as statistics, with test/uncertainty stated), "interestingly"
  (and kin: "notably", "remarkably", "curiously") — if it's interesting,
  state the finding; the reader decides.
- Banned claims: proves, demonstrates (see claim ladder), unambiguously,
  clearly shows, for the first time.
- Numbers/units: SI; space between value and unit; unit exponents
  ("12.4 kcal mol⁻¹", "36.0 Å"); sig figs match method accuracy — DFT energies
  never more precise than 0.1 kcal mol⁻¹, do not fake precision.
  In LaTeX: siunitx `\qty{12.4}{\kilo\calorie\per\mole}` (template declares
  `\calorie`; v3 dropped it).
- Notation: symbol table at end of each document; bold for vectors, italic for
  scalars; follow it exactly once defined.

## Hedging and claims

Claim-strength ladder — use the weakest word the evidence supports:

```
demonstrates       → proof, exact reproduction only
establishes        → strong evidence, studied scope stated
shows              → solid result, no mechanism claim
indicates          → default for findings
suggests           → tentative/mechanistic reading
is consistent with → mechanism not uniquely determined
```

- Every quantitative claim from a sample carries value ± spread, with basis and
  n stated ("12.4 ± 0.3 kcal mol⁻¹ (SD, 100 frames)"). Deterministic values
  carry method precision only.
- Scope is forced: every generalization names its scope ("for the three
  molecules studied", "within the FC approximation"). No scope → writer
  inserts qualifier or `[TODO: scope]`.
- Correlation ≠ causation: "correlates with", "tracks", "is associated with"
  unless the causal chain is actually demonstrated.
- Null/negative results stated plainly with magnitude, no burying, no
  apology: "B3LYP fails to reproduce the gap (Δ = 0.8 eV); we did not pursue
  the cause."

## Document-type rules

### Internal report
- Structure: TL;DR (≤5 lines) → context (why, 2–3 lines) → what was done →
  results → implications → open questions/blockers.
- Length: soft guidance — aim ≤1 page per section; overflow → point to
  scripts/notes instead of pasting.
- Audience: you + advisor. Deep familiarity assumed; abbreviations free; no
  background beyond 2–3 lines.
- May: cite unfinished results, name internal scripts/branches directly,
  state half-tested interpretations (marked as such).

### Manuscript
- Structure: IMRAD from vendored skill unless venue says otherwise.
- Venue: undecided — venue-specific pass at submission time; default format
  below.
- Abstract: unstructured, ≤250 words: context → gap → what we did → key
  result (with number + uncertainty) → implication.
- Figure/table density: write with as many as clarity demands; trim at
  submission. No upfront budget.
- Scope disclaimers welcome when relevant ("we do not attempt a direct
  comparison with experiment, as ... is beyond the scope of this study").

## Exemplars

Match these, not abstract rules.

### Exemplar 1 — results paragraph (published ECD/CPL manuscript)
```
We first observe that the magnetic TDMs can exhibit substantial dependence
on the choice of coordinate origin, particularly for molecules 2 and 3,
confirming the expected behavior according to Eq. (4). If we look instead to
the values of the rotatory strength, they vary significantly in the length
gauge, with those computed at the CoM being similar to those computed with
the velocity gauge. Such a finding indicates that, for these systems, the
CoM is a good gauge origin in order to minimize origin dependence in the
length gauge. [...] In the case of molecule 2, the shift vector is
particularly large (|R| = 36.0 Å), and the angle between this vector and
the electric TDM is close to perpendicular (deviating by ~15°).
```
Voice traits: "We first observe / Turning to / We now focus" as paragraph
openers; claim ladder respected ("indicates", "confirms" only when expected
behavior verified); numbers inline with units; each comparison justified
immediately by geometry/physics.

### Exemplar 2 — methods/context paragraph
```
This work focuses on the three chiral systems shown in Figure 1. [...] It
should be noted that the focus of this work lies in analyzing how the
simulated spectra vary with the choice of gauge and the specific expansion
of the TDMs. Therefore, we do not attempt a direct comparison with
experimental spectra, as the relative accuracy of the simulations may depend
on various computational factors, such as electronic structure method and
environmental effects, whose systematic benchmarking is beyond the scope of
this study.
```
Voice traits: scope stated up front, disclaimer with reason attached
("as ... beyond the scope"), no apologizing; concrete settings named
(functional, basis, code, displacements) with justification for choices.

## Pet peeves list

- Bullet-point everything: prose that carries continuous reasoning stays
  prose. Bullets only for genuinely parallel items (params, blockers, TODOs).
- Hollow openers: "In recent years, X has attracted attention" — start with
  the finding.
- Question-restating: "To address this challenge, we propose..." — just answer.
- Summary transitions: "In summary, as we have seen..." — no rehashing the
  previous paragraph.
- Restating the question instead of answering it.
