---
name: update-memory
disable-model-invocation: true
description: End-of-session memory capture. Reviews the current conversation for durable insights — user corrections, feedback rules, user-type facts — and writes them to the memory system following the vault memory contract. Use whenever the user says "update memory", "save session", "end session", "/update-memory", "capture what we learned", or "save the session". Also trigger proactively at natural session end points when significant corrections or feedback emerged.
tools: Read, Write, Edit, Glob, Grep
---

# Update Memory

Capture durable knowledge from the current session and persist it — strictly to the files this skill owns.

## Ownership (single-writer rule)

Vault contract: `AGENTS.md § Memory contract`. This skill writes ONLY:

| File | Owner |
|---|---|
| `memory/feedback_*.md` | **this skill** |
| `memory/user_*.md` | **this skill** |
| `memory/MEMORY.md` (index lines only) | **this skill** |
| `memory/project_*.md` | `/update-project` — do NOT touch |
| `10-Projects/<X>/history.md`, `decisions-log.md`, `results-log.md`, `methods.md`, `open-questions.md`, dashboards | `/update-project` — do NOT touch |

Project-state insights discovered here → report them at the end as "belongs in project_X.md — run /update-project". Never write them yourself.

## Role guard: only an operator pane may write memory

The input to this skill is **the conversation that just happened**, and the durable thing in that
conversation is usually a correction to how the fleet should work. A correction delivered into one leaf
pane is cold input for that pane only: its siblings and the brain's next planning cycle never see it, so
memory written from a leaf fragments the contract it is supposed to record. Only the operator's pane sees
corrections across all of them.

Detect first, with `Read` (every tier keeps it, including the brain, whose `bash` is denied):

1. `Read` `./.pi-role`, then each parent up to the vault root (8 hops).
2. Found and non-empty ⇒ gated tier ⇒ **STOP**, write nothing. Print the hand-off instead:

```
next-command[operator]: cd "$VAULT_DIR" && pi   # unroled pane, then /update-memory
```

| Role found | What that pane does instead |
|---|---|
| none / empty | continue — this is an operator pane |
| `worker`, `calcs` | put the rule you were corrected on in your `.agent/status/` delta as a `feedback:` line, so the operator captures it where it generalises. `role-gate` denies any write/edit under a `memory/` path component for your tier — a refusal there is this rule, not a bug |
| `scout`, `verifier`, `integrator` | no write tools by design; state it in your report |
| `brain` | bash is denied and `memory/` writes are denied; you may quote the rule into `plans/` for the operator to capture |
| `writer` (the writer tier) | prose for humans; `memory/` is denied for your tier |

Unroled means **operator**: no `.pi-role` up the tree ⇒ `role-gate` fails open ⇒ full tools. The human's
own pane, not an agent file — see `USAGE.md § 1`.

## Memory directory resolution

```bash
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)   # $SKILL_DIR = dir of this SKILL.md
VAULT_DIR=$(grep '^VAULT_DIR=' "$DAIMON_ROOT/config/config.local" | cut -d= -f2- | sed "s|~|$HOME|")
```

- CWD under `$VAULT_DIR` → `MEMORY_DIR="$VAULT_DIR/memory"` (vault mode).
- Otherwise (non-vault project) → `MEMORY_DIR="$HOME/.claude/projects/$(pwd | sed 's|^/||; s|/|-|g')/memory"`.

If `$VAULT_DIR` unset in config.local → stop and tell the user to fill `config/config.local` (machine-local, gitignored).

## File formats (vault contract)

**`feedback_*.md` / `user_*.md` frontmatter** — top level, no `metadata:` nesting:
```yaml
---
name: feedback-kebab-slug
description: one-line summary — used to decide relevance
type: feedback   # or: user
---
```

**Body structure** (feedback type):
```
[The rule, stated directly]

**Why:** [constraint, incident, preference]
**How to apply:** [when this kicks in]
```

**`MEMORY.md`** — index only:
```
- [Descriptive title](filename.md) — one-line hook
```
Cap ~60 lines. If index approaches the cap: consolidate related entries, don't just truncate.

**project_*.md contract** (enforced by /update-project; shown here so you route correctly):
CURRENT (≤5 date-stamped bullets) + CONSTRAINTS + POINTERS, ≤80 lines total.

## What NOT to save

- Dated session narrative → `history.md` (/update-project)
- Decisions with rationale → `decisions-log.md`
- Numerical results / run records → `results-log.md`
- Methods/parameter changes → `methods.md`
- Work-log entries → dashboard (30-day window)
- Code patterns derivable from reading current files; git history; debugging solutions in commit messages
- Anything already in AGENTS.md files — that IS the persistence layer for it
- Ephemeral task state; vague impressions — concrete facts only

## Step 1: Review the conversation

For each candidate: *Would a fresh agent starting tomorrow benefit from knowing this?*

- User corrected an approach ("no, don't do X") or confirmed one emphatically → `feedback`
- User revealed background, preferences, working style → `user`
- New external system (cluster, tool, service) → candidate `reference`/`user` entry — but check AGENTS.md first, pointers there usually suffice

## Step 2: Check existing files before writing

Read `$MEMORY_DIR/MEMORY.md` index first. Matching file exists → update in place (never duplicate). No match → create new file named lowercase-hyphen, topic-first: `feedback_compact_discipline.md`.

## Step 3: Write or update

Keep entries tight — read in 20 seconds beats 2 minutes. Convert relative dates to absolute (2026-05-15).

## Step 4: Update MEMORY.md index

One line per new file; refresh hook text if an updated file's description drifted.

## Step 5: Hygiene check (report step, always)

After writing, run the deterministic checker on your domain:

```bash
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
VAULT_DIR=$(grep '^VAULT_DIR=' "$SKILL_DIR/../../../config/config.local" | cut -d= -f2- | sed "s|~|$HOME|")
python3 "$SKILL_DIR/../vault-hygiene/scripts/vault_hygiene.py" --vault-dir "$VAULT_DIR" --check
```

Report memory-domain violations in your output: index lines missing hooks (you write them — index is yours), over-cap memory files (route compression to `/update-project` — it owns project files). Stale index lines: rerun with `--fix`. Non-memory violations: mention in one line, full pass = `/vault-hygiene`.

## Step 6: Report

```
## Memory update — YYYY-MM-DD

**Added:** / **Updated:** — files + what changed
**Skipped:** — anything considered, one word (duplicate / ephemeral / in-AGENTS.md / belongs-to-update-project)
**Route to /update-project:** — project-state insights found this session (if any)
```

If nothing worth saving: say so plainly — never write trivial memories to justify a run.
