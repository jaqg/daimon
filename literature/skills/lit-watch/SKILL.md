---
name: lit-watch
description: >
  Weekly new-literature monitor. Searches databases for papers published since last run,
  scores relevance against a project or topic list, and writes a digest to the vault inbox.
  Trigger for: "/lit-watch", "check for new papers", "weekly lit update", "what's new in the literature",
  "any new papers on X this week", "monitor new papers for my project", "run lit-watch".
  Designed to run weekly, manually or via /schedule.
tools: Bash, Write
---

# lit-watch

Monitors new literature since last run. Scores papers 1–5 for relevance, deduplicates
against previously seen papers, and writes a digest to vault inbox.

## Config keys (sourced from config.local)

```bash
VAULT_DIR              # path to Obsidian vault (for inbox output)
LIT_WATCH_STATE_DIR    # default: ~/.config/daimon
SEMANTIC_SCHOLAR_API_KEY
NCBI_API_KEY
```

## Flags

```
--project PROJECT_ID   read vault memory for research context (primary mode)
--topics "X, Y"        explicit topic list (alternative to --project)
--threshold N          min relevance score 1-5 to include (default: 4)
--since DATE           override last-run date (ISO-8601 YYYY-MM-DD)
--state PATH           path to state file directory
--output-inbox PATH    vault inbox dir (default: $VAULT_DIR/00-Inbox/)
--dry-run              show what would be written; do not write or update state
--domains DB,...       restrict databases (default: all free DBs)
--results N            papers to scan per topic (default: 50)
```

## Step 0: Gather inputs

Determine mode:
- `--project PROJECT_ID`: read vault memory from `~/.claude/projects/*/memory/project_*.md` matching PROJECT_ID
- `--topics "X, Y"`: use topic list directly

Source config.local:
```bash
CONFIG=$(find -L ~/.claude -name "config.local" -path "*/daimon/config/*" | head -1)
[[ -n "$CONFIG" ]] && source "$CONFIG"
```

Load state:
```bash
STATE_SCRIPT=$(find -L ~/.claude -path "*/lit-watch/scripts/watch_state.py" -type f | head -1)
python3 "$STATE_SCRIPT" --show [--state-dir "$LIT_WATCH_STATE_DIR"]
```

If `last_run` not set: default to 7 days ago (first run).
If `--since` provided: use that date instead of state.

## Step 1: Read project context (if --project)

Find vault memory file:
```bash
MEMORY_DIR=$(find ~/.claude/projects -name "MEMORY.md" | head -1 | xargs dirname)
```

Read `$MEMORY_DIR/project_<PROJECT_ID>.md` (or the file whose name matches PROJECT_ID).
Extract: research topics, keywords, methodology terms.

If no matching memory file found: fall back to `--topics` mode and warn user.

## Step 2: Collect papers (all topics, parallel)

```bash
COLLECT=$(find -L ~/.claude -path "*/lit-watch/scripts/collect.py" -type f | head -1)
python3 "$COLLECT" \
  --topics "TOPIC1, TOPIC2, ..." \
  --results ${RESULTS:-50} \
  [--since "$LAST_RUN"] \
  [--domains "$DOMAINS"] \
  [--project "$PROJECT_ID"] \
  [--state-dir "$LIT_WATCH_STATE_DIR"]
```

Capture the output JSON. Key fields:
- `new_papers[]` — papers not yet in seen_ids (score these)
- `papers[]` — all merged results
- `meta.new_unseen` — count of new papers
- `meta.sources_coverage` — per-DB hit counts
- `meta.errors[]` — any per-topic failures

If `new_papers` is empty: skip Step 3, report "No new papers found since LAST_RUN."

## Step 3: Score relevance

Score each paper in `new_papers[]` on title + abstract relevance to project context:
- **5**: directly addresses a core research question or methodology
- **4**: clearly relevant to research area; likely worth reading
- **3**: tangentially related; might be useful as background
- **2**: shares domain but different focus
- **1**: not relevant

Base scoring on:
- Keywords from project memory (explicit matches = higher score)
- Venue tier (target journals for the field = +1)
- Author overlap with known relevant papers = +0.5 bonus (round up)

**Justification required**: every paper with score ≥ threshold must have a 1–2 sentence
explanation citing specific project keywords it matches.

## Step 4: Write digest

If not `--dry-run`:

Output path: `$VAULT_DIR/00-Inbox/lit-watch-YYYY-MM-DD.md`

```markdown
# New Literature — YYYY-MM-DD
Project: PROJECT_ID | Threshold: N/5 | Period: LAST_RUN → TODAY
Sources searched: arXiv, Semantic Scholar, OpenAlex | New papers scanned: N

## High-relevance papers (score ≥ N)

### 1. [Title](url) — Score: 5/5
Authors | Venue | Year | Citations: N
**Why relevant:** [1–2 sentence justification tied to project keywords]
DOI: ... | arXiv: ...

[...]

## Also found (score N-1) — below threshold, listed for reference
- [Title](url) — Authors (Year) — Score: N-1/5

---
Coverage: Searched: arxiv, semantic_scholar, openalex | Not searched (no key): wos
To act on these: `/lit-review --papers papers-watch-YYYY-MM-DD.json`
```

Also save the combined papers.json as `papers-watch-YYYY-MM-DD.json` in cwd (or output-inbox dir)
so the user can run `lit-review` on it immediately.

## Step 5: Update state

If not `--dry-run`:
```bash
python3 "$STATE_SCRIPT" --update --ids "$(cat new_ids.txt)" [--project PROJECT_ID]
```

The script: extends seen_ids with all scanned paper IDs (from `collect_output["papers"]`),
updates last_run to today.

## Step 6: Report to user

```
lit-watch complete — YYYY-MM-DD
  Period: LAST_RUN → TODAY
  Scanned: N papers | New (not previously seen): M | High-relevance (≥ threshold): K

  Digest: $VAULT_DIR/00-Inbox/lit-watch-YYYY-MM-DD.md
  Papers JSON: papers-watch-YYYY-MM-DD.json

  Coverage: Searched: [...] | Not searched (no key): [...]

  [If dry-run]: Dry run — nothing written. Remove --dry-run to save.
```

If 0 high-relevance papers: "No papers above threshold. K papers scored below threshold.
Consider lowering --threshold or checking back next week."

## Scheduling

User sets up weekly run:
```
/schedule weekly /lit-watch --project PhD-Ch1-AIM4ML
```

## Security: what this skill guarantees

1. Only DOI/arXiv ID papers reported — no orphan entries.
2. Relevance justification required for every included paper (tied to project keywords).
3. State file integrity: if `last_run` is in the future, warn and ask user to confirm `--since`.
4. Dedup against seen_ids — never re-report already-seen papers.
5. Coverage statement in digest — same format as lit-search.
6. Threshold transparency — papers just below threshold listed separately so user can lower it.

## Error handling

| Problem | Action |
|---------|--------|
| No project memory file | Fall back to --topics; warn user |
| State file corrupted | Warn; ask user to set --since manually |
| 0 papers found | Report; suggest broadening topics or checking in more days |
| Vault inbox not found | Warn; write digest to cwd instead |
| API failures | Report in coverage statement; continue with available sources |
