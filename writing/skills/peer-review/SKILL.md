---
name: peer-review
disable-model-invocation: true
description: >
  Inject peer-review comments directly into a LaTeX manuscript as colored environments.
  Use this skill when the user says /peer-review, asks to "review my manuscript", "peer-review my paper",
  "add reviewer comments to my .tex file", "review my LaTeX paper", "give me reviewer feedback on my manuscript",
  or wants journal-style critique of a .tex document.
  Produces two custom LaTeX environments injected after each relevant paragraph: `review` (reviewer criticism)
  and `addition-suggestion` (suggested improvement), both rendered in `reviewcolor`, plus
  `revieweditor` for the synthesis editor block (Step 6).
  Use --expert to load vault project context for field-specific review.
  Always invoke this skill when the user asks for manuscript review and a .tex file is involved.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# peer-review

Conduct a rigorous peer review of a LaTeX manuscript and inject comments directly into the `.tex`
source as colored environments — no terminal output. Each flagged paragraph gets a `review` block
(the criticism) immediately followed by an `addition-suggestion` block (a concrete fix).

## Invocation

```
/peer-review --file <root.tex> [--expert] [--project <id>] [--no-suggest] [--dry-run]
            [--structural-only] [--journal <name>] [--preprint] [--blind]
            [--claims] [--check-resolved] [--passes N]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--file <root.tex>` | required | Root `.tex` file (the one with `\documentclass`) |
| `--expert` | off | Load vault project memory + research interests for field-specific review |
| `--project <id>` | infer | Which `memory/project_<id>.md` to read; inferred from cwd if omitted |
| `--no-suggest` | off | Inject only `review` blocks; skip `addition-suggestion` |
| `--dry-run` | off | Print unified diff to stdout; do not write any files |
| `--structural-only` | off | Run lens 1 only (manuscript structure); skip lenses 2–8 |
| `--journal <name>` | off | Journal calibration: `reporting_standards.md` "Journal-Specific Standards" + `references/journals/<name>.md` if it exists; format/fit violations → `severity: "major"` |
| `--preprint` | off | Preprint calibration: no format constraints (skip journal-format items in Lens 7), Lens 1d stays signal-only, novelty comments keep the AI-unreliable caveat |
| `--blind` | off | Fresh external-reviewer simulation: skip all Step 4 context levels; condensed references still load (see Step 4) |
| `--claims` | off | Extract heuristic claim candidates (`extract_manuscript.py --claims`); pre-filters Step 4b and r2's claim–evidence check |
| `--check-resolved` | off | R&R mode: scan injected review blocks vs current paragraph text, print per-comment status (see "R&R round") |
| `--passes N` | 3 | Reviewer passes; `--passes 1` = one call, all lenses, no synopsis/synthesis (v1-equivalent eval arm) |

## Calibration (`--journal` / `--preprint` / `--blind`)

Target-journal calibration precedence: **CLI flag > `manuscript-context.md` "Target journal"
(Step 4 Level 1) > default** (generic high-impact: Nature/JACS/PNAS-level review).

- **`--journal <name>`**: load `references/reporting_standards.md` → "Journal-Specific Standards"
  section, plus `$SKILL_DIR/references/journals/<name>.md` when it exists (missing file: standards
  section only, no error). Under `--journal`, format/fit violations (length limits, required
  sections, article-type mismatch) are `severity: "major"`. Loads regardless of `--expert`.
- **`--preprint`**: no format constraints — skip journal-format items in Lens 7; Lens 1d fraction
  checks are signals only (never a format violation); novelty comments still carry the mandatory
  AI-unreliable caveat.
- **`--blind`**: overrides `--expert` if both are passed; skips all Step 4 context levels
  (manuscript-context, project knowledge, memory). References condensation STAYS — a real external
  reviewer knows the public literature. With `--blind` there is no manuscript-context level, so
  precedence collapses to CLI flag > default.

## Required config keys (from `config/config.local`)

- `VAULT_DIR` — needed only with `--expert` (path to Obsidian vault root)

## Step 1 — Locate scripts and config

```bash
# $SKILL_MD = path of this SKILL.md (verify with readlink -f if symlinked)
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"

EXTRACT_SCRIPT="$SKILL_DIR/scripts/extract_manuscript.py"
CHECK_SCRIPT="$SKILL_DIR/scripts/check_review_envs.py"
STRUCT_SCRIPT="$SKILL_DIR/scripts/check_structure.py"
CHECK_REVIEWS_SCRIPT="$SKILL_DIR/scripts/check_reviews.py"
INJECT_SCRIPT="$SKILL_DIR/scripts/inject_reviews.py"
```

Read `VAULT_DIR` from `$CONFIG_LOCAL` only if `--expert` was passed.

## Step 2 — Check environment definitions (do NOT patch yet)

```bash
python3 "$CHECK_SCRIPT" --file <root.tex>
```

Output JSON:
```json
{
  "review_defined": false,
  "suggestion_defined": false,
  "insert_line": 14,
  "xcolor_defined": false,
  "reviewcolor_defined": false,
  "revieweditor_defined": false,
  "macro": "reviewcolor",
  "patch": "% peer-review annotations — inserted by /peer-review skill\n\\usepackage{xcolor}\n\\definecolor{reviewcolor}{HTML}{D97757}\n\\newenvironment{review}{\\par\\noindent\\color{reviewcolor}\\textbf{Reviewer: }}{\\par}\n\\newenvironment{addition-suggestion}{\\par\\noindent\\color{reviewcolor}\\itshape\\textbf{Suggested addition: }}{\\par}\n\\newenvironment{revieweditor}{\\par\\noindent\\color{reviewcolor}\\textbf{Editor summary: }}{\\par}"
}
```

**Legacy-compat note (intentional; the only place that legacy name appears):** manuscripts patched
by skill v1 define `claudeorange` instead of `reviewcolor`; `macro` reports whichever name is found,
the patch adds only what is missing, and injected blocks reuse the existing environments unchanged
(zero migration).

**Save this JSON as `$ENV_JSON`** — do NOT patch the file yet. The preamble patch will be
applied atomically together with the review injections in Step 6. This avoids a line-number
shift bug where patching first would invalidate the `line_end` values from Step 3.

If `patch` is empty (everything already defined): no patch needed, set `ENV_JSON=null`.

Otherwise: show the user the `patch` lines and confirm they understand what will be added.

## Step 3 — Extract manuscript

```bash
python3 "$EXTRACT_SCRIPT" --file <root.tex> [--claims]
```

Output: JSON array of paragraphs:
```json
[
  {
    "section": "Introduction",
    "para_idx": 0,
    "text": "Density functional theory (DFT) has become the workhorse...",
    "source_file": "/abs/path/to/intro.tex",
    "line_end": 23
  }
]
```

The script follows `\input{}`/`\include{}` includes, strips LaTeX markup to plain text,
and assigns a global `para_idx` used later for injection targeting.

`--claims` additionally outputs a `claims` array of heuristic candidates (regexes: "we
show/demonstrate/report/find", number+unit, significance terms) alongside the paragraph list.
Save it for Step 4b and r2's claim–evidence check — candidates only, the model still judges
which claims are real.

Save the full JSON output for Steps 3b, 4b, 5 and 5e.

## Step 3b — Structural check

```bash
python3 "$STRUCT_SCRIPT" --paragraphs '<JSON from Step 3>'
```

Output: structural summary JSON. Save as `$STRUCT_JSON`.

```json
{
  "top_level_sections": ["Abstract", "Introduction", "Discussion", "Conclusions"],
  "word_counts": {"Abstract": 120, "Introduction": 430, "Discussion": 160, "Conclusions": 80},
  "body_word_count": 670,
  "body_fractions": {"Introduction": 0.642, "Discussion": 0.239, "Conclusions": 0.119},
  "last_para_idx": {"Abstract": 0, "Introduction": 3, "Discussion": 11, "Conclusions": 12}
}
```

`top_level_sections` only includes sections that have direct paragraph content (`section_level == 1`).
Sections present only as headings (all content in subsections) will not appear — check the paragraph
JSON for subsections (e.g. `section_level == 2` entries named "DFT calculations", "Experimental")
when assessing whether a Methods or Results section exists structurally.

## Step 4 — Load expert context (only with `--expert`)

**`--blind` skips Levels 1–3 entirely** (no manuscript-context, project knowledge, or memory —
simulate a fresh external reviewer). Only the "Reference files (always load)" block below runs:
references condensation stays (a real reviewer knows the public literature).

Derive the vault project directory:
```bash
PROJECT_DIR="$VAULT_DIR/10-Projects/<project-id>"
MEMORY_DIR="$VAULT_DIR/memory"
```

Load context in **priority order** — stop at the first level that provides manuscript-specific detail:

### Level 1 — Manuscript-specific (highest value)
Check for `$PROJECT_DIR/manuscript-context.md`. If present, read it. This file contains the
target journal, manuscript claims, key methods as used, and anticipated reviewer concerns.

If absent, print: `manuscript-context.md not found for <project>. Run \`/open-manuscript --project <id>\` before the next expert review for field-specific comments. Falling back to project files.`

### Level 2 — Project knowledge files
Read if they exist:
- `$PROJECT_DIR/methods.md` — computational software + parameters actually used
- `$PROJECT_DIR/open-questions.md` — known unresolved issues the author is aware of

### Level 3 — Memory files (fallback)
Always read:
- `$MEMORY_DIR/research_interests.md` — field-level reporting standards + relevance rubric
- `$MEMORY_DIR/project_<id>.md` — project goals, Review context section

### Reference files (always load — even with `--blind`)
```bash
COMMON_ISSUES="$SKILL_DIR/references/common_issues.md"
REP_STANDARDS="$SKILL_DIR/references/reporting_standards.md"
```

Condense both references to headers + first bullet per section (~1500 chars total) and prepend
as a `## Reference: Common Issues` and `## Reference: Reporting Standards` block in your context.

## Step 4b — Synopsis (shared anchor, 1 call)

Build the anchor every reviewer shares: section map, claim list, and the 3 strongest hostile
objections. (The v1 pre-step that identified objections inside the single review call moved here.)

Perform this call now using `$STRUCT_JSON`, the paragraph JSON from Step 3, and — when `--claims`
was passed — the `claims` candidate array. Output exactly this JSON object and nothing else:

```json
{
  "sections": [{"section": "", "role": "", "para_range": [0, 0], "purpose": ""}],
  "claims": [{"id": "c1", "section": "", "para_idx": 0, "text": "", "type": "quantitative"}],
  "top_objections": ["", "", ""]
}
```

Requirements:
- `sections`: one entry per section with paragraph content; `role` = IMRaD canonical role (the
  Lens 1a mapping below), `para_range` = `[first_para_idx, last_para_idx]`, `purpose` = one line.
- `claims`: every factual/quantitative/novelty/significance claim worth checking; `type` ∈
  `quantitative | factual | novelty | significance`; ids `c1, c2, …`. With `--claims`, start from
  the script candidates and prune false positives; without it, derive candidates while reading
  using the same heuristics.
- `top_objections`: exactly 3, ordered most damaging first — the kind that would cause rejection
  at the target journal. Positional ids: 1st = `obj1`, 2nd = `obj2`, 3rd = `obj3`; reviewers
  reference them through `addresses` in Step 5.

Save as `$SYNOPSIS_JSON`. Every reviewer pass (Step 5) receives it, and **each reviewer must
anchor at least 2 comments on these objections** — that adversarial framing surfaces weaknesses
a charitable read misses.

## Step 5 — Reviewer passes (3 sequential in-pane calls)

Sequential, in-pane: run r1 → r2 → r3 one at a time in this conversation. No subagent spawning,
no parallelism — this skill stays a single-pane workflow.

Every pass receives: the FULL paragraph JSON (C1) — the document is never split, only the lens
focus —; the condensed references from Step 4 (also under `--blind`); `$SYNOPSIS_JSON` (C2);
`$STRUCT_JSON`; and the expert context from Step 4 when present.

**Lens redistribution map** — split the lens, not the document. Everything not primary is
secondary: flag it only if critical, never pad:

| Pass | Primary lenses | Focus |
|------|----------------|-------|
| **r1** | Lens 4, Lens 5, comp-chem checks (`common_issues.md` §23–25 + `reporting_standards.md` comp-chem) | methods & reproducibility: controls, protocols, sample sizes, data/code availability, convergence/force-field/version reporting |
| **r2** | Lens 2, Lens 1e, Lens 1f, Lens 3 | claims & novelty & statistics: whole-paper claim–evidence, statistics–claims consistency, abstract fidelity, no-new-claims-in-Conclusions |
| **r3** | Lens 1a–1d, Lens 6, Lens 7, Lens 8 | structure & editorial: section map/presence/order/balance, figures, disclosures, writing quality |

Each pass executes the **shared reviewer prompt** at the end of this step with its own
`reviewer` / `primary_lenses` substituted. The full lens reference follows.

### Lens 1 — Manuscript structure & editorial fitness

Split across passes: **r3 owns 1a–1d** (map, presence, order, balance); **r2 owns 1e–1f**
(abstract fidelity, conclusions) as claim-integrity checks. Other passes flag only critical
structural finds.

Use `$STRUCT_JSON` from Step 3b plus the full paragraph JSON. This lens runs first because
structural gaps (missing sections, severe imbalance) affect the validity of all other comments.

**Step 1a — Map section names to IMRaD canonical roles.**
`top_level_sections` contains raw author-written names. Before assessing structure, map them:
- "Computational Details", "Experimental Section", "Experimental", "Materials and Methods",
  "Theoretical Background", "Theory", "Simulation Details" → **Methods**
- "Results and Discussion" → satisfies both **Results** and **Discussion**
- "Summary", "Concluding Remarks" → **Conclusions**
- Unrecognised names: use your judgment given the field and paper type

Note: if "Methods" (or its equivalent) is absent from `top_level_sections` but subsections
(section_level 2) like "DFT calculations" or "Monte Carlo simulations" exist in the paragraph
JSON, Methods is structurally present as a heading-only section — do not flag as missing.

**Step 1b — Check section presence.**
Standard IMRaD sections: Abstract, Introduction, Methods, Results, Discussion, Conclusions.
Flag genuinely absent sections at `severity: "major"`. Anchor the comment to the
`last_para_idx` of the preceding section (e.g. missing Conclusions → anchor to last Discussion
paragraph). For short communications and letters, a combined Results+Discussion and absent
standalone Conclusions are acceptable — calibrate to the target journal type if known from
expert context.

**Step 1c — Check section order.**
Expected order: Abstract → Introduction → Methods → Results → Discussion → Conclusions.
Flag inversions (e.g. Discussion before Results) at `severity: "major"`.
Methods-last placement (common in some society journals) is acceptable.

**Step 1d — Check body balance.**
Use `body_fractions` from `$STRUCT_JSON`. There is no single correct ratio — calibrate to
article type and target journal:
- Full research article: Introduction typically 20–35% of body; Methods 25–40%.
  Introduction > 40% suggests over-contextualization at the expense of Results/Discussion.
  Methods < 15% in a computational paper suggests reproducibility risk.
- Letter / communication: compressed sections, no standalone Methods normal.
- Review article: Introduction + thematic sections >> Results/Discussion fractions.

Do not flag as major purely on fraction. Use fractions as a signal, then read the section
content to decide whether the imbalance is a real problem. Assign `severity: "minor"` for
moderate imbalance, `severity: "major"` only for extreme cases that likely cause reviewer rejection.

**Step 1e — Abstract completeness and fidelity.**
The abstract should state: background/motivation, objective, methods (briefly), key
quantitative result(s), and conclusion/implication. Flag if any of these are absent.
More critically: check that the abstract's stated results match the actual results reported
in the paper. Aspirational abstracts ("this study will show…") or abstracts that claim
broader results than the manuscript supports are `severity: "major"`.

**Step 1f — Conclusions do not introduce new claims.**
Check the Conclusions section: it should synthesize, not introduce new data, new comparisons,
or new mechanistic claims not discussed earlier. Flag any new claim appearing first in
Conclusions at `severity: "major"`.

Anchor all lens 1 comments using `last_para_idx` from `$STRUCT_JSON`.

### Lens 2 — Initial assessment *(r2 primary)*
Novelty, scope, and overall soundness. Does the paper address a real gap?
Is the claim supported by the evidence presented?

### Lens 3 — Section by section (content quality) *(r2 primary)*
Assess content quality within each section — not structural presence or balance (covered in
lens 1). For each section: is the content accurate, complete, and appropriately scoped?
- Abstract: clarity of contribution statement
- Introduction: gap clearly identified; objective stated at the end
- Methods: sufficient detail for reproduction
- Results: results reported objectively, without interpretation bleeding in
- Discussion: interprets results; connects back to the gap stated in Introduction;
  acknowledges limitations
- References: representative and current

Beyond per-section quality, r2 runs two paper-wide checks:
- **Whole-paper claim–evidence (scope: every claim in the body)** — walk `$SYNOPSIS_JSON.claims`
  (pre-filtered by `--claims` when passed) and verify each factual/quantitative claim against the
  evidence actually presented: number reported but never derived, result asserted in Discussion
  but only shown in the Abstract, significance claimed without a test. This is the Lens 1e
  abstract-fidelity pattern extended paper-wide. Central-claim support missing → `major`;
  secondary overreach → `minor`.
- **Statistics–claims consistency** — do the text's claims match the numbers in tables/figures
  (n, uncertainty, significance level)?

### Lens 4 — Methodological rigor *(r1 primary)*
Statistics, controls, reproducibility, sample sizes.

### Lens 5 — Reproducibility *(r1 primary)*
Data/code availability, protocol detail, software versioning.

### Lens 6 — Figures and data *(r3 primary)*
Visualization quality, axis labels, statistical annotations.

### Lens 7 — Editorial compliance *(r3 primary)*
Conflict of interest, ethics statement, data availability, missing disclosures.
With `--preprint`, journal format/fit items are out of scope (no format constraints).

### Lens 8 — Writing quality *(r3 primary)*
Clarity, precision, logical flow; overstatement vs. actual evidence.

**For computational chemistry papers** (DFT, MD, GCMC, periodic calculations): also apply the
discipline-specific checks from `common_issues.md` sections 23–25 and `reporting_standards.md`
computational chemistry section. Flag missing convergence criteria, force field citations,
k-point mesh, software versions, etc. as `severity: "major"` — these block reproducibility.

**Normal mode** (no `--expert`): act as a rigorous general reviewer at a high-impact journal
(Nature, JACS, PNAS level). Flag methodology gaps, missing citations, unclear claims, statistical
issues, and reproducibility concerns.

**Expert mode** (`--expert`): act as a field specialist who knows the project context. Reference
specific prior work gaps, flag whether methods are state-of-the-art for this subfield, and note
whether the project's own stated goals are met by the manuscript.

### Shared reviewer prompt — outputs C3 (one execution per pass)

Stand: the Normal/Expert mode guidance above. Perform the review now, in-pane, using the full
paragraph JSON, `$SYNOPSIS_JSON`, `$STRUCT_JSON`, condensed references, and expert context (if
present). Your primary lenses from the redistribution map come first; secondary lenses only when
a find is critical — never pad to fill a quota.

Output exactly one object, no prose around it:

```json
{
  "reviewer": "r1",
  "primary_lenses": ["4", "5"],
  "comments": [
    {
      "id": "r1-01",
      "para_idx": 3,
      "section": "Methods",
      "severity": "major",
      "lens": "4",
      "comment": "The convergence criterion for the SCF calculation is not stated. Without this, the results are not reproducible.",
      "suggestion": "Specify the SCF convergence threshold used (e.g., 'SCF convergence was set to 10^{-8} hartree').",
      "evidence": "convergence criterion for the SCF calculation",
      "addresses": "obj1"
    }
  ]
}
```

Requirements:
- `reviewer`: the pass id (`r1`/`r2`/`r3`); `primary_lenses`: that pass's lenses as strings, from
  the redistribution map.
- Volume: **4–10 comments** for a full manuscript, **1–4** for a short paper or section. Do not
  comment on every paragraph; deduplicate within the pass (the three sets merge in Step 5e).
- `id`: `<reviewer>-NN`, zero-padded, ascending by priority within the pass (`r2-01`, `r2-02`, …).
- `para_idx` + `section`: anchor from the paragraph JSON, `section` verbatim as extracted.
- `lens`: the lens that motivated the comment, as a string (e.g. `"4"`, `"1e"`).
- `severity`: `"major"` (blocks acceptance) or `"minor"` (should fix but not critical).
- `comment`: state the problem precisely, as a real journal reviewer would write it. No
  "Reviewer:" or "Suggested addition:" prefixes — the LaTeX environments provide them.
- `suggestion`: concrete, actionable fix — a sentence to add, a citation to include, a
  clarification to make. `null` if `--no-suggest` was passed.
- `evidence`: **exact ≥8-character substring copied verbatim from some paragraph `text` or
  `section` value** in C1 — or a literal number string from the manuscript. No paraphrase, no
  reconstruction. `check_reviews.py` enforces this mechanically (anti-generic).
- `addresses`: `obj1`/`obj2`/`obj3` when the comment stems from a synopsis objection, else
  `null`. **At least 2 comments in every pass must have non-null `addresses`** (the shared-anchor
  rule).
- **Anti-generic filter**: before finalizing, reject any comment that could apply verbatim to a
  different paper without changing a word. Each comment must cite specific text, numbers, claims,
  or section content from this manuscript. Generic advice ("add more detail to methods") is not
  acceptable; specific critique ("the SCF threshold is absent from the VASP parameters in §2.1")
  is required.
- **Novelty caveat**: flag novelty/theoretical contribution gaps at `severity: "minor"` only,
  with explicit note that AI assessment of novelty is unreliable — the author should verify
  against their own comprehensive literature search. Do not claim a contribution is non-novel
  without specific citation evidence.

### Pass r1 — methods & reproducibility

`reviewer: "r1"`, `primary_lenses: ["4", "5"]`. Primary: Lens 4 (controls, protocols, sample
sizes), Lens 5 (reproducibility, data/code availability), and the comp-chem checks
(`common_issues.md` §23–25 + the computational-chemistry section of `reporting_standards.md` —
missing convergence criteria, force-field citations, k-point meshes, software versions block
reproducibility → `major`).

### Pass r2 — claims, novelty & statistics

`reviewer: "r2"`, `primary_lenses: ["2", "1e", "1f", "3"]`. Primary: Lens 2 (gap, soundness,
claim support), Lens 1e (abstract fidelity), Lens 1f (no new claims in Conclusions), Lens 3 plus
its two paper-wide checks (whole-paper claim–evidence over `$SYNOPSIS_JSON.claims`,
statistics–claims consistency).

### Pass r3 — structure & editorial

`reviewer: "r3"`, `primary_lenses: ["1a", "1b", "1c", "1d", "6", "7", "8"]`. Primary: drive
Lens 1a–1d from `$STRUCT_JSON` (IMRaD mapping, presence, order, balance), then Lens 6 (figures
and data), Lens 7 (disclosures/editorial compliance), Lens 8 (writing quality).

### Validation after each pass

```bash
python3 "$CHECK_REVIEWS_SCRIPT" --reviews '<C3 from this pass>' --paragraphs '<C1>'
```

Must exit 0 with `"generic": []`. Any listed id: rewrite that comment with a verbatim evidence
quote and re-run before starting the next pass.

### Mode knobs

- **`--passes N`** (default 3): three reviewer passes above; together with Steps 4b and 5e the
  full run is 5 LLM calls (v1 used 1).
- **`--passes 1`**: skip Steps 4b and 5e — one call, all 8 lenses, no synopsis (v1-equivalent
  eval arm). Output goes straight to Step 6 as a C4 object: `header` (`summary` +
  `recommendation` per the Step 5e mapping) with comments carrying `rank` = your priority order
  1..N and `merged_from: []`; `addresses` always `null` (no synopsis exists).
- **`--structural-only`**: v1 semantics — Lens 1 only, single pass, skip lenses 2–8, no
  synopsis/synthesis. Output a plain v1 array `[{para_idx, severity, comment, suggestion}]` (no
  envelope); Step 6 renders it in the legacy shape.

## Step 5e — Synthesis (1 call)

Merge the three C3 sets into the injector input. Perform this call now using `$SYNOPSIS_JSON` and
the r1/r2/r3 outputs. Output exactly this C4 object and nothing else:

```json
{
  "header": {"summary": "", "recommendation": "major"},
  "comments": [
    {
      "id": "s-01",
      "para_idx": 3,
      "section": "Methods",
      "severity": "major",
      "lens": "4",
      "comment": "",
      "suggestion": "",
      "evidence": "",
      "merged_from": ["r1-01", "r2-03"],
      "rank": 1
    }
  ]
}
```

- `header.summary`: 3–5 sentences — what the paper does, the main verdict, the decisive reasons.
- `header.recommendation` — apply the mapping mechanically:

  | Recommendation | Rule |
  |---|---|
  | `accept` | 0 comments survive synthesis |
  | `minor` | only `minor` comments survive |
  | `major` | exactly 1–2 `major` comments |
  | `reject` | ≥3 `major` comments, **or** any `major` on support for the central claim |

- `comments`: one entry per distinct issue. When ≥2 passes raise the same issue, merge into ONE
  comment listing every source id in `merged_from` (single-source comments list their single
  source id as well — the field is never empty). On merge: sharper wording wins, `severity` =
  highest raised, `evidence` copied verbatim from a source (must still satisfy the evidence
  rule), `lens` of the primary source.
- `rank`: 1..N, ascending importance (1 = most damaging); Step 6 injects in this order.
  `id`: `s-01`, `s-02`, … assigned in rank order.
- Keep every unique `major`; drop duplicate and nitpick minors; final set typically 6–15 comments.
- `suggestion`: `null` if `--no-suggest`.

Validate before Step 6:

```bash
python3 "$CHECK_REVIEWS_SCRIPT" --reviews '<C4>' --paragraphs '<C1>'
```

Must exit 0 with `"generic": []`; rewrite any listed id and re-run. Save as `$REVIEWS_JSON`.

## Step 6 — Preview and inject (atomic: reviews + preamble patch)

Consumes `$REVIEWS_JSON` from Step 5e — a C4 object (legacy bare arrays from
`--structural-only` also accepted, rendered exactly as v1).

Pass the preamble JSON from Step 2 via `--preamble-json` so both the preamble patch and
review injections happen in one operation. This ensures correct line numbers (the preamble
shift does not affect the body insertion positions).

```bash
python3 "$INJECT_SCRIPT" \
  --file <root.tex> \
  --reviews '<JSON from Step 5e — $REVIEWS_JSON>' \
  --paragraphs '<JSON from Step 3>' \
  --preamble-json '<ENV_JSON from Step 2>' \
  --dry-run [--no-suggest]
```

With `--dry-run`: prints a unified diff. Show this to the user and ask for confirmation.

After approval, run without `--dry-run`:
```bash
python3 "$INJECT_SCRIPT" \
  --file <root.tex> \
  --reviews '<JSON from Step 5e — $REVIEWS_JSON>' \
  --paragraphs '<JSON from Step 3>' \
  --preamble-json '<ENV_JSON from Step 2>' \
  [--no-suggest]
```

Summary output:
```
Injected 7 review blocks into 3 file(s).
  intro.tex: 3 comments (2 major, 1 minor)
  methods.tex: 2 comments (2 major)
  results.tex: 2 comments (1 major, 1 minor)
```

**Approval gate**: always show the diff before writing. Do not write without explicit user
confirmation ("yes", "go ahead", "looks good", etc.).

If `ENV_JSON` is null (environments already defined), omit `--preamble-json` or pass `null`.

Each injected block appears immediately after the flagged paragraph:
```latex

\begin{review}
The convergence criterion for the SCF calculation is not stated...
\end{review}
\begin{addition-suggestion}
Specify the SCF convergence threshold used...
\end{addition-suggestion}
```

(If `--no-suggest`: only the `review` block is inserted.)

### Editor block and block layout (C4 input)

When `--reviews` is a C4 object (Step 5e or `--passes 1`), the injector renders:

1. **Editor block first** — one block, before any comment block in document order: the
   `revieweditor` env containing `header.summary` plus a
   `Recommendation: <accept|minor|major|reject>` line (the env supplies the
   `Editor summary: ` prefix). Fallback for manuscripts where the editor env cannot be added
   (previously patched preambles): render the block in the `review` env with an `EDITOR SUMMARY:`
   prefix in the text instead.
2. **Comment blocks ascending by `rank`**, each immediately after its anchored paragraph: the
   `review` block, then `addition-suggestion` when `suggestion` is non-null (unchanged).
3. **Every block is prefixed with an invisible LaTeX comment line `% pr:<id>`** — `% pr:s-01` for
   comments, `% pr:editor` for the editor block. No rendered change; `--check-resolved` matches
   on these ids.
4. New preamble patches define `\definecolor{reviewcolor}` (Step 2). Manuscripts patched by an
   earlier skill version reuse their existing environments unchanged — blocks are injected as-is,
   zero migration.
5. **Legacy bare array input** (v1 shape / `--structural-only` output): renders exactly as v1 —
   no editor block, no `% pr:` lines.

`--dry-run` shows the editor block and `% pr:` lines in the diff like every other line; the
approval gate and the atomic write are unchanged.

## R&R round — `--check-resolved`

When the author returns a revised manuscript, run the resolution scan instead of re-reviewing
blindly. `--check-resolved` is a standalone mode: after Step 1 (locate scripts), run only the
scan — skip Steps 2–6.

```bash
python3 "$CHECK_SCRIPT" --file <root.tex> --check-resolved --reviews '<C4.json>'
```

`--reviews` is optional: given C4, each comment is matched by its `evidence` quote; when omitted,
the scanner falls back to the longest quoted span or number inside the injected comment text.

Output — one entry per injected comment:

```json
[{"id": "s-01", "status": "unresolved", "matched_quote": "convergence criterion for the SCF calculation"}]
```

- `resolved` — the quoted text/number the comment anchored on no longer appears in the current paragraph.
- `unresolved` — still present verbatim.
- `uncertain` — partial or ambiguous match (paraphrase, common number); read the paragraph before deciding.

Show the user the per-comment table. `unresolved` + `uncertain` comments scope the next round:
re-run the pipeline (Steps 4b–5e) on the revised file targeting those; `resolved` comments need
no action.

## Edge cases

- **`\input{}`/`\include{}` files**: the extract script follows them; injections go into the
  correct included file at the correct line.
- **Math-heavy paragraphs**: `[MATH]` placeholders in extracted text are fine for review purposes.
- **Empty sections**: skip; do not comment on section headers with no content.
- **Approval denied**: do not write anything; tell the user what was found and offer to adjust.
- **No paragraphs extracted**: warn and stop; the .tex may be empty or contain only figures.
- **`--journal <name>` with no `references/journals/<name>.md`**: fall back to the
  reporting_standards "Journal-Specific Standards" section only; no error, continue.
- **`--check-resolved` on a file with no injected review blocks**: warn and stop — nothing to check.
- **`--journal` and `--preprint` both passed**: error out and ask the user which calibration applies.
