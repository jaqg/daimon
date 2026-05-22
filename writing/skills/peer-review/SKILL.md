---
name: peer-review
description: >
  Inject peer-review comments directly into a LaTeX manuscript as colored environments.
  Use this skill when the user says /peer-review, asks to "review my manuscript", "peer-review my paper",
  "add reviewer comments to my .tex file", "review my LaTeX paper", "give me reviewer feedback on my manuscript",
  or wants journal-style critique of a .tex document.
  Produces two custom LaTeX environments injected after each relevant paragraph: `review` (reviewer criticism)
  and `addition-suggestion` (suggested improvement), both rendered in Claude orange.
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
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--file <root.tex>` | required | Root `.tex` file (the one with `\documentclass`) |
| `--expert` | off | Load vault project memory + research interests for field-specific review |
| `--project <id>` | infer | Which `memory/project_<id>.md` to read; inferred from cwd if omitted |
| `--no-suggest` | off | Inject only `review` blocks; skip `addition-suggestion` |
| `--dry-run` | off | Print unified diff to stdout; do not write any files |

## Required config keys (from `config/config.local`)

- `VAULT_DIR` — needed only with `--expert` (path to Obsidian vault root)

## Step 1 — Locate scripts and config

```bash
SKILL_DIR=$(dirname "$(readlink -f "$(find -L ~/.claude/skills/peer-review -name SKILL.md 2>/dev/null | head -1)")")
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"

EXTRACT_SCRIPT=$(find -L ~/.claude -path "*/peer-review/scripts/extract_manuscript.py" -type f | head -1)
CHECK_SCRIPT=$(find -L ~/.claude -path "*/peer-review/scripts/check_review_envs.py" -type f | head -1)
INJECT_SCRIPT=$(find -L ~/.claude -path "*/peer-review/scripts/inject_reviews.py" -type f | head -1)
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
  "claudeorange_defined": false,
  "patch": "% peer-review annotations\n\\usepackage{xcolor}\n\\definecolor{claudeorange}{HTML}{D97757}\n\\newenvironment{review}{\\par\\noindent\\color{claudeorange}\\textbf{Reviewer: }}{\\par}\n\\newenvironment{addition-suggestion}{\\par\\noindent\\color{claudeorange}\\itshape\\textbf{Suggested addition: }}{\\par}"
}
```

**Save this JSON as `$ENV_JSON`** — do NOT patch the file yet. The preamble patch will be
applied atomically together with the review injections in Step 6. This avoids a line-number
shift bug where patching first would invalidate the `line_end` values from Step 3.

If `review_defined` and `suggestion_defined` are both true: no patch needed, set `ENV_JSON=null`.

Otherwise: show the user the `patch` lines and confirm they understand what will be added.

## Step 3 — Extract manuscript

```bash
python3 "$EXTRACT_SCRIPT" --file <root.tex>
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
Save the full JSON output for Step 5.

## Step 4 — Load expert context (only with `--expert`)

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

### Reference files (always load)
```bash
COMMON_ISSUES="$SKILL_DIR/references/common_issues.md"
REP_STANDARDS="$SKILL_DIR/references/reporting_standards.md"
```

Condense both references to headers + first bullet per section (~1500 chars total) and prepend
as a `## Reference: Common Issues` and `## Reference: Reporting Standards` block in your context.

## Step 5 — Review pass (single Claude call)

You are the Claude doing the review. Perform this step now using the paragraph JSON from Step 3
and expert context from Step 4 (if present).

**Pre-review: identify the 3 strongest objections first.** Before writing any comment, ask:
"What are the three most damaging objections a hostile but fair reviewer could raise against
this manuscript — the kind that would cause rejection at the target journal?" Anchor at least
2 of your comments on those objections. This adversarial framing surfaces real weaknesses that
a charitable read would miss.

Read all paragraphs and conduct a rigorous peer review following these 7 lenses:
1. **Initial assessment** — novelty, scope, overall soundness
2. **Section by section** — abstract, intro, methods, results, discussion, references
3. **Methodological rigor** — statistics, controls, reproducibility, sample sizes
4. **Reproducibility** — data/code availability, protocol detail, software versioning
5. **Figures and data** — visualization quality, axis labels, statistical annotations
6. **Editorial compliance** — conflict of interest, ethics statement, data availability, missing disclosures
7. **Writing quality** — clarity, precision, logical flow; overstatement vs. actual evidence

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

Output a JSON array — one entry per flagged paragraph. Target **5–12 comments** for a full
manuscript, **2–5** for a short paper or section. Do not comment on every paragraph; focus on
the most important issues.

```json
[
  {
    "para_idx": 3,
    "severity": "major",
    "comment": "The convergence criterion for the SCF calculation is not stated. Without this, the results are not reproducible.",
    "suggestion": "Specify the SCF convergence threshold used (e.g., 'SCF convergence was set to 10^{-8} hartree')."
  },
  {
    "para_idx": 7,
    "severity": "minor",
    "comment": "The claim that the method 'outperforms all prior approaches' is not supported by any citation or quantitative comparison.",
    "suggestion": "Either cite prior benchmarks or replace with 'outperforms the approaches tested here, specifically [REF]'."
  }
]
```

Rules for comment text:
- Do not include "Reviewer:" or "Suggested addition:" prefixes — the LaTeX environments provide them.
- `comment`: state the problem precisely, as a real journal reviewer would write it.
- `suggestion`: concrete, actionable fix — a sentence to add, a citation to include, a clarification to make.
- `suggestion` is `null` if `--no-suggest` was passed.
- `severity`: `"major"` (blocks acceptance) or `"minor"` (should fix but not critical).
- **Anti-generic filter**: before finalizing, reject any comment that could apply verbatim to a
  different paper without changing a word. Each comment must cite specific text, numbers, claims,
  or section content from this manuscript. Generic advice ("add more detail to methods") is not
  acceptable; specific critique ("the SCF threshold is absent from the VASP parameters in §2.1")
  is required.
- **Novelty caveat**: flag novelty/theoretical contribution gaps at `severity: "minor"` only,
  with explicit note that AI assessment of novelty is unreliable — the author should verify
  against their own comprehensive literature search. Do not claim a contribution is non-novel
  without specific citation evidence.

## Step 6 — Preview and inject (atomic: reviews + preamble patch)

Pass the preamble JSON from Step 2 via `--preamble-json` so both the preamble patch and
review injections happen in one operation. This ensures correct line numbers (the preamble
shift does not affect the body insertion positions).

```bash
python3 "$INJECT_SCRIPT" \
  --file <root.tex> \
  --reviews '<JSON from Step 5>' \
  --paragraphs '<JSON from Step 3>' \
  --preamble-json '<ENV_JSON from Step 2>' \
  --dry-run [--no-suggest]
```

With `--dry-run`: prints a unified diff. Show this to the user and ask for confirmation.

After approval, run without `--dry-run`:
```bash
python3 "$INJECT_SCRIPT" \
  --file <root.tex> \
  --reviews '<JSON from Step 5>' \
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

## Edge cases

- **`\input{}`/`\include{}` files**: the extract script follows them; injections go into the
  correct included file at the correct line.
- **Math-heavy paragraphs**: `[MATH]` placeholders in extracted text are fine for review purposes.
- **Empty sections**: skip; do not comment on section headers with no content.
- **Approval denied**: do not write anything; tell the user what was found and offer to adjust.
- **No paragraphs extracted**: warn and stop; the .tex may be empty or contain only figures.
