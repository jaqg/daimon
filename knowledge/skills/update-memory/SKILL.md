---
name: update-memory
description: End-of-session memory capture for any project. Reviews the current conversation for insights worth persisting across sessions — project facts, user corrections, validated approaches, reference pointers — and writes or updates memory files in the project memory directory. Use this skill whenever the user says "update memory", "save session", "end session", "/update-memory", "capture what we learned", or "save the session". Also trigger proactively at natural session end points when significant new facts, decisions, or corrections emerged that aren't yet in memory files.
tools: Read, Write, Edit, Glob, Grep
---

# Update Memory

Capture durable knowledge from the current session and write it to the memory system so future sessions start with full context.

## Memory system layout

Derive the memory directory from the current working directory:

```bash
MEMORY_DIR="$HOME/.claude/projects/$(pwd | sed 's|^/||; s|/|-|g')/memory"
```

- **Index**: `$MEMORY_DIR/MEMORY.md`
  - One line per memory: `- [Title](filename.md) — one-line hook`
  - Truncated after ~200 lines — keep entries concise
- **Memory files**: same directory, one `.md` file per topic
- **Required frontmatter** in every memory file:
  ```yaml
  ---
  name: short-kebab-case-slug
  description: one-line summary — used to decide relevance in future conversations
  metadata:
    type: user | feedback | project | reference
  ---
  ```

## Memory types

| Type | What goes here |
|------|---------------|
| `user` | José's role, background, preferences, knowledge level |
| `feedback` | Corrections to Claude's approach; validated non-obvious approaches |
| `project` | Project facts, decisions, constraints, deadlines, open questions |
| `reference` | Pointers to external systems (clusters, dashboards, Slack, Linear) |

## What NOT to save

- Code patterns derivable by reading the current files
- Git history — `git log` covers this
- Debugging solutions already in the codebase or commit messages
- Anything already documented in CLAUDE.md files
- Ephemeral task state that only matters this session
- Vague impressions — only concrete, specific facts

## Step 1: Review the conversation

Scan back through the session. For each candidate ask: *Would a fresh Claude instance starting a new session tomorrow benefit from knowing this?* 

Look for:
- User corrected an approach ("no, don't do X") or confirmed one ("yes, exactly") → `feedback`
- A project deadline, decision, or constraint was stated → `project`
- A new tool, cluster, or external system was mentioned → `reference`
- User revealed background, preferences, or working style → `user`

## Step 2: Check existing memories before writing

Read `MEMORY.md` index first. For each candidate:
- Matching file exists → update in place (never duplicate)
- No match → create new file

File naming: lowercase, hyphens, topic-first.
- `feedback_compact_discipline.md`
- `project_phd_chapter1_status.md`  
- `reference_cluster_sops.md`

## Step 3: Write or update memory files

For **feedback** and **project** types, structure the body as:

```
[The rule or fact, stated directly]

**Why:** [The reason — constraint, incident, preference, deadline]
**How to apply:** [When this kicks in; how it shapes future behavior]
```

For **user** and **reference** types, plain prose or a short list works fine.

Keep entries tight — a memory read in 20 seconds beats one that takes 2 minutes.

Dates: always convert relative dates ("next Thursday", "last week") to absolute dates (2026-05-15) — memories must be interpretable after time passes.

## Step 4: Update MEMORY.md index

For each new file:
```
- [Descriptive title](filename.md) — one-line hook explaining relevance
```

For updated files: check if the existing index line still describes the content accurately. Update if not.

## Step 5: Report what changed

```
## Memory update — YYYY-MM-DD

**Added:**
- `filename.md` — what it captures

**Updated:**
- `filename.md` — what changed

**Skipped:**
- [anything considered but not saved, with one-word reason: duplicate / ephemeral / already-in-CLAUDE.md]
```

If nothing worth saving was found, say so plainly — don't write trivial memories to justify the run.
