# Vault Improvement Plan

**Date:** 2026-05-22  
**Status:** Proposed — not yet implemented

---

## Problem

The vault has disconnected islands: paper notes in `20-Sources/`, concept notes in `30-Galaxy/`, project files in `10-Projects/`. A normal work day generates theory insights, computational results, and literature connections that never make it into the vault in a retrievable, structured way. Project folders capture operational decisions but not scientific content.

This limits `--expert` mode in the peer-review skill (no methods/results context) and makes the vault a filing system rather than a living knowledge base.

---

## Current state audit

**What exists:**
- Paper notes have `project:` frontmatter field → link infrastructure is present but not exploited
- `lit-reviews/` subfolder inside projects → raw overnight review outputs, never synthesized into project context
- `decisions-log.md` captures decisions
- `project-dashboard.md` captures operational status

**What is missing:**

| Daily activity | Current vault coverage | Gap |
|---|---|---|
| Literature review | Paper notes created (✅) | No synthesis into project literature-map |
| Theory discussion | Nothing | Session insights evaporate |
| Coding/calculations | decisions-log catches decisions only | No methods changelog, no results log |
| Results analysis | Nothing | Numbers live in PhD/ raw files only |
| Paper writing | `/peer-review` skill (✅) | `--expert` mode blind — no methods/results in context |
| Deliverables | `/poster` (✅) | — |

**Key insight:** 69 paper notes in `20-Sources/papers/` → 0 literature-maps in project folders.

---

## Proposed project folder structure

Add these files to each active project under `10-Projects/<project>/`:

```
10-Projects/<project>/
  project-dashboard.md     ← exists: operational status
  decisions-log.md         ← exists: key decisions + rationale
  literature-map.md        ← NEW: papers organized by theme, with project-specific annotations
  methods.md               ← NEW: software versions, parameters, settings changelog
  results-log.md           ← NEW: chronological results + interpretation
  open-questions.md        ← NEW: hypotheses, open questions, ideas in flight
  manuscript-context.md    ← NEW: created at paper-writing stage; feeds peer-review --expert
```

### `literature-map.md` structure
```markdown
# Literature Map — <project>

## Theme: [e.g., Baseline methods]
- [rogers2010-ecfp](../../20-Sources/papers/rogers2010-ecfp.md) — used as fingerprint baseline in §3.2; main limitation: fixed radius
- ...

## Theme: [e.g., Dataset construction]
- ...
```

### `methods.md` structure
```markdown
# Methods — <project>

## Computational setup
| Date | Software | Version | Key parameters | Notes |
|------|----------|---------|----------------|-------|
| 2026-04-15 | VASP | 6.4.2 | PBE-D3(BJ), 520 eV, 3×3×1 k-mesh, SCF 1e-6 eV | Initial setup |
| 2026-05-10 | VASP | 6.4.2 | PBE-D3(BJ), 520 eV, 5×5×1 k-mesh | Denser k-mesh after convergence test |

## Scripts
| Script | Purpose | Location |
|--------|---------|----------|
| build_extxyz.py | Build extxyz dataset | ~/PhD/scripts/04-extxyz/ |
```

### `results-log.md` structure
```markdown
# Results Log — <project>

## 2026-05-14 — Sensitivity analysis
**What:** 5 variants of sqrt-prop global model (different hyperparameters)
**Result:** sqrt-prop global broken at all settings; 1-3% accuracy across variants
**Interpretation:** Confirm fixed-fraction split as next step
**Files:** ~/PhD/results/2026-05-14-sensitivity/

## 2026-05-03 — Phase 1 QM40 pipeline
...
```

### `manuscript-context.md` structure (for peer-review --expert)
```markdown
# Manuscript Context — <project>

## Target manuscript
- **Title:** [working title]
- **Target journal:** JCTC / JACS / etc.
- **Submission date:** [planned]

## Claims
- [What the paper claims to show — one bullet per major claim]

## Key methods (as used in this manuscript)
- Software: VASP 6.4.2, PBE-D3(BJ), 520 eV cutoff
- Key threshold: SCF 1e-6 eV, ionic relaxation 0.02 eV/Å

## Known weaknesses / open issues
- [Reviewer concerns you anticipate]
- [Limitations you acknowledge]

## Prior review context
- [Notes from previous submission rounds, if any]
```

---

## Proposed new skills

### 1. `/update-project` (vault skill — highest priority)

**Purpose:** End-of-session capture. Updates project files with what happened today.

**Invocation:**
```
/update-project --project <id> [--session-summary "brief text"]
```

**Workflow:**
1. Read today's daily note from `00-Inbox/YYYY-MM-DD.md` (if exists) OR use `--session-summary`
2. Read current `project-dashboard.md`, `decisions-log.md`, `results-log.md`, `methods.md`, `open-questions.md`
3. Claude pass: extract from session content:
   - New decisions → append to `decisions-log.md`
   - New results (numbers, outcomes) → append to `results-log.md`
   - New methods/parameters → append to `methods.md`
   - Resolved questions + new questions → update `open-questions.md`
   - Dashboard status update → update `project-dashboard.md`
   - Galaxy note candidates → list (do not create; ask user)
4. Show diff preview (approval gate)
5. Write on approval
6. Update `memory/project_<id>.md` with session insights

**Design notes:**
- Single Claude pass: reads all context, outputs structured JSON of updates
- Scripts handle diff generation and file patching
- Never creates Galaxy notes without approval

---

### 2. `/project-lit-map` (vault skill)

**Purpose:** Generate or update `literature-map.md` for a project by querying paper notes.

**Invocation:**
```
/project-lit-map --project <id> [--update]
```

**Workflow:**
1. Script: find all `20-Sources/papers/*.md` where frontmatter `project:` contains `<id>`
2. Script: extract title, authors, year, `subject`, `Key points` snippet per paper
3. Claude pass: group papers into 3-8 themes based on content; generate `literature-map.md`
4. With `--update`: diff against existing `literature-map.md`, show changes, ask approval

**Design notes:**
- Exploits existing `project:` frontmatter field — no new tagging needed
- Can be run after a batch of `/lit-vault` runs to synthesize the backlog
- Themes are generated by Claude, not pre-defined

---

### 3. `/open-manuscript` (vault skill)

**Purpose:** Create `manuscript-context.md` for a project, enabling peer-review `--expert` mode.

**Invocation:**
```
/open-manuscript --project <id>
```

**Workflow:**
1. Read `project-dashboard.md`, `methods.md`, `results-log.md`
2. Ask user: target journal, working title, key claims, anticipated reviewer concerns
3. Claude pass: draft `manuscript-context.md` from inputs
4. Approval gate → write

**Design notes:**
- Should be run before `/peer-review --expert` for first time on a manuscript
- `manuscript-context.md` is the primary context source for `--expert` mode
- Takes ~5 min; high leverage for review quality

---

### 4. Enhance `/lit-vault` (modify existing)

**Purpose:** When run with `--project`, also update `literature-map.md` with new papers.

**Change:** After creating paper notes, run a mini `/project-lit-map --update` pass to insert new papers into the existing map under the most relevant theme.

**Priority:** Lower — `/project-lit-map` covers the backlog; this is an incremental improvement for ongoing use.

---

## Peer-review `--expert` mode: improved context loading

Current behavior reads:
- `memory/project_<id>.md` (too operational: scripts, cluster paths)
- `memory/research_interests.md` (too generic)

Proposed behavior (after above files exist):
1. `manuscript-context.md` → primary source (claims, journal, weaknesses)
2. `methods.md` → software and parameters actually used
3. `open-questions.md` → known unresolved issues the author is aware of
4. `memory/research_interests.md` → field context (keep)
5. `memory/project_<id>.md` → fallback if manuscript-context absent

SKILL.md Step 4 should be updated to load in this priority order.

---

## Memory file fixes (separate from above)

- MEMORY.md index uses wrong filenames: `project_chiroptical.md` → actual: `project_cerezo_collab.md`; `project_phd_ch1_aim4ml.md` → actual: `project_phd.md`; `project_zeolites.md` → actual: `project_nanoplastic_zeolites.md`
- Project memory files lack `## Review context` sections (methodological standards, journal targets, anticipated reviewer concerns)
- Fix: rename files to match MEMORY.md OR update MEMORY.md to match actual filenames, then add Review context sections

---

## Implementation order

| Priority | Item | Effort | Value |
|---|---|---|---|
| 1 | Add `methods.md` + `results-log.md` templates to active projects | Low | Immediate; fills the biggest daily gap |
| 2 | `/update-project` skill | Medium | Closes the session-capture loop |
| 3 | Fix MEMORY.md naming + add Review context sections | Low | Unblocks --expert mode now |
| 4 | `/project-lit-map` skill | Medium | Synthesizes 69 orphaned paper notes |
| 5 | `/open-manuscript` skill | Low | Clean --expert setup for paper-writing stage |
| 6 | Update peer-review SKILL.md Step 4 context loading | Low | Uses new files once they exist |
| 7 | Enhance `/lit-vault` with --project lit-map update | Medium | Quality-of-life for ongoing use |
