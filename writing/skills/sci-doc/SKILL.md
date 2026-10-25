---
name: sci-doc
description: >
  Create or update a scientific document (internal report or manuscript) in the
  project's established voice. Use this skill when the user says "write the report",
  "draft the report/manuscript", "update the report with the new results", "continue
  the report", "integrate the new work into the document", "sci-doc", or when context
  chunks arrive from other agents addressed to a project document. Auto-selects path:
  file does not exist → draft; file exists → incremental update. Delegates scientific
  rigor (claim-evidence binding, consistency checks, lints) to the vendored K-Dense
  scientific-writing workflow. Not for peer review (use /peer-review) or posters.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# sci-doc

Create and maintain project documents (internal report, manuscript) in one voice
across the whole project lifetime. Long-lived writer agent runs this skill repeatedly:
first invocation drafts, every later invocation updates.

## Required context

- `writing/style-guide.md` (repo root, next to this skill's domain dir) — voice rules
  and exemplars. Read once at first invocation, keep for session lifetime.
- Identity: `source config/config.local` → `AUTHOR_NAME`, `AUTHOR_AFFILIATION`,
  `AUTHOR_EMAIL` (same convention as /poster). Manuscripts only.
- Document location: user states it, or find with Glob (`report*.md`, `manuscript*`,
  `*.tex`, project dir). Never create a duplicate if a document already exists.

Resolve the repo root by following this skill's own path (symlink-aware:
`readlink -f` this SKILL.md, then up to `writing/skills/sci-doc/`). Vendored workflow
lives at `vendor/kdense-scientific-writing/` relative to this file.

## Intake (both paths)

Before writing, confirm or infer and state:

1. `doc_type`: `report` (internal, audience = group/self) or `manuscript` (external,
   venue, audience = reviewers/readers).
   `doc_format`: `md` or `tex`. For LaTeX projects (or when the user says "tex",
   ".tex", "LaTeX report"), work directly in `.tex` — same paths, style guide,
   approval gates; rigor pass uses the tex fallback below.

   **`.tex` reports start from the user's template repo**:

   ```bash
   SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
   TPL_ROOT=$(grep '^LATEX_TEMPLATES_DIR=' "$SKILL_DIR/../../../config/config.local" | cut -d= -f2- | sed "s|~|$HOME|")
   # unset or missing dir → skill-bundled fallback: $SKILL_DIR/templates/report.tex
   ```

   If `$TPL_ROOT/report-template/` exists: copy it into the target project dir
   (`main.tex`, `configuration/`, `front-page/`, `mybraket.sty`) — the draft is
   self-contained, never `\input` across repos. Then:

   1. Fill `front-page/info.tex` (or `configuration/style.tex`) metadata from
      `config/config.local` (`AUTHOR_NAME` etc.) — never leave template
      placeholder text (e.g. old thesis title) in the draft.
   2. Ask user which front-page option (plain `maketitle` / minimal / elaborate);
      enable exactly one in `main.tex`, comment rest.
   3. Add `\usepackage{siunitx}` + `\DeclareSIUnit\calorie{cal}` to
      `configuration/packages.tex` if absent (units rule).
   4. Delete unused boilerplate only when user agrees — templates are their
      property, minimize surprise edits.
   5. `\input{text}` → the draft body this skill writes/edits.

   Bundled fallback: copy `templates/report.tex`, fill `%%PLACEHOLDER%%` marks.
   Manuscripts use the venue's own class at submission time — templates are for
   internal reports.
2. Scope of this pass: new sections / revised sections / full pass.
3. Evidence available: which results, notes, intercom chunks, scripts, figures.

If evidence for a claim is missing, write the explicit placeholder state
(`[TODO: needs <X>]`), never plausible filler. This is a hard rule inherited from the
vendored workflow's no-fabrication section.

If `manuscript-context.md` exists in the project (written by `/open-manuscript`),
read it during intake: journal, working title, key claims, anticipated concerns are
authoritative context. For manuscripts without it, suggest the user run
`/open-manuscript` first — but proceed if they decline.

## Path A — draft (target file absent)

1. Load style guide + identity.
2. Structure:
   - `report`: read `vendor/kdense-scientific-writing/assets/REPORT_FORMATTING_GUIDE.md`;
     skip IMRAD unless user asks.
   - `manuscript`: read `vendor/kdense-scientific-writing/references/imrad_structure.md`;
     select reporting guideline with
     `python3 vendor/.../scripts/select_reporting_guidelines.py select --study-design <design>`.
3. Outline first, show to requester, wait for approval (approval gate: a new document is
   a user-facing artifact — see "Approval gates" below).
4. Draft sections in full flowing prose (never bullet skeletons). Two-stage per section:
   outline key points → convert to paragraphs. Apply style guide on every paragraph.
   Note: the vendored `assets/REPORT_FORMATTING_GUIDE.md` may suggest scaffolding via
   `scaffold_manuscript.py` — this Path A (outline → draft) governs; scaffold is only
   used on explicit user request.
5. Evidence binding: assign claim/evidence IDs per
   `vendor/kdense-scientific-writing/references/evidence_workflow.md` for manuscripts.
   For internal reports, a lighter ledger is acceptable: every number cites its source
   script/fig/table inline (`[src: analysis/free-energy.py:out/fe.csv]`).
6. Changelog: create `<doc>.changelog.md` with initial entry (date, scope, sources used).

### Approval gates (user present vs agent-to-agent)

Gates exist to protect user-facing artifacts, not to deadlock autonomous runs.

- Human in session: normal behavior — show outline/diff, wait for yes.
- Agent-to-agent (intercom chunk, no human waiting): the gate may be satisfied by the
  sender's authorization for scratch/intermediate artifacts, but **documents in the
  Obsidian vault (or any user's real project tree) are always user-approved in the
  end** — no agent can authorize a vault write on the user's behalf. For those:
  1. Discrepancies found (wrong numbers, stale claims, contradictions with sources)
     are reported immediately: notify sender + user with section, old value,
     new value, `[src]` evidence;
  2. Draft the diff (temp-copy + `diff -u`), but do NOT apply — stage it: post the
     diff and hold the pending changeset until the user confirms;
  3. Changelog entry is written only after approval.
- If a chunk arrives with `[urgent]` or contradicts an existing claim as its whole
  content (pure correction): same as above — report + staged diff now, apply only on
  user approval. Urgency shortens notification latency, not the approval requirement.

## Path B — update (target file exists)

Never rewrite the document. Integrate incrementally.

Style guide applies to text this update touches, not retroactively: preserve the
local style of untouched paragraphs (legacy tables, old notation) unless the user
asks for a full restyle pass.

1. Read the full existing document + changelog. Note section map and voice.
2. Classify each incoming chunk (intercom message, notes, new results) as:
   new result / correction / removal / restructure request.
3. For each chunk: draft minimal diff touching only affected paragraphs. Preserve
   tense, person, notation, and terminology of the surrounding text (style guide).
   If a correction changes a number, grep the doc for other occurrences of that
   number and update all of them.
4. Produce the diff deterministically: `cp` the doc to a temp file, apply the planned
   edits to the temp copy, then `diff -u <orig> <temp>` — show that. Approval gate:
   updates modify user files (see "Approval gates" under Path A for agent-to-agent).
5. Apply with Edit. Append changelog entry: date, chunks integrated, sections touched,
   claims added/changed (for corrections: old value → new value). If no changelog
   exists yet, create it (same initial-entry convention as Path A, backdated with a
   note that prior history predates the changelog).
6. If >40% of the document would change, stop and propose Path A (restructure pass)
   instead.

## Intercom intake protocol

Other agents hand over context for the document. Expected chunk format (accept
looser input, but ask sender to tighten if ambiguous):

```
[section] target section or "any"
[claim]   the finding, one paragraph max
[numbers] key=value pairs with units
[src]     script/fig/table the numbers came from
[caveats] limitations, known issues, open questions
```

Rules: numbers without `[src]` are not integrated (ask sender). Chunks arriving
mid-draft queue in session; integrate when current section completes.

## Rigor pass (end of every invocation)

Delegates to vendored deterministic tools (scripts own the checks, Claude only
fixes what they flag):

```bash
V=vendor/kdense-scientific-writing/scripts   # resolve relative to this SKILL.md
python3 $V/check_consistency.py <consistency_manifest.json>   # manuscripts
python3 $V/audit_claims.py <doc>.md <claims.csv> <source_manifest.json>
python3 $V/lint_manuscript.py <doc>.md --manifest <manuscript_manifest.json>
```

For internal reports without full manifests, run `lint_manuscript.py` on the doc
alone (works without manifest) and fix flagged issues. Expected noise: findings
matching skill-mandated `[TODO: needs <X>]` placeholders (UNRESOLVED_PLACEHOLDER
etc.) are correct behavior, not errors — no-fabrication outranks lint cleanliness;
suppress by listing the placeholders in the report to the user, not by removing them.
Everything else gets fixed. Report to user: issues found, issues fixed, issues
needing human decision.

**`.tex` fallback**: vendor lint is Markdown-only. For `.tex` docs the rigor pass is
a grep-based substitute:

```bash
# 1. every [TODO: ...] marker left in the doc (report count; honest markers stay)
grep -c '\[TODO:' "$DOC"
# 2. banned words from style-guide.md (Global voice section) — fix hits
BANNED='interestingly|notably|remarkably|curiously|delve|it is worth noting|\bstate-of-the-art\b'
grep -inE "$BANNED" "$DOC" | grep -v '^%'
```

Comment lines (`%`) are excluded — reviewer notes there are fine. In `.tex`, revision
tags (`%CT:`, `%CQ:`) are handled by the review-tags-tex skill, not here.

## Boundaries

- Not peer review: user asks for referee-style critique → /peer-review skill.
- Not LaTeX compilation of manuscripts; user's existing toolchain handles that.
  In `.tex` docs, respect `\input`/`\include` boundaries: read the target file, edit
  it, never restructure across included files without flagging it.
- Vendored files under `vendor/` are read-only; behavior changes go in this SKILL.md.
- No invented citations, numbers, methods, or provenance — ever. (Vendored workflow,
  no-fabrication section, applies in full.)
