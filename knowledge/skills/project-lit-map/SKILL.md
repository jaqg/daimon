---
name: project-lit-map
description: >
  Generate or update a literature map for a project. Use when the user says /project-lit-map,
  "make a literature map", "create literature-map.md", "map the papers for this project",
  "organize the papers", "which papers are tagged to this project?", or wants to link
  paper notes to a project folder. Reads paper notes tagged with the project's ID via
  their `project:` frontmatter field, groups them into themes, and writes
  `10-Projects/<project>/literature-map.md` with project-situated annotations.
  Invoke after running /lit-vault or whenever new papers have been added to 20-Sources/papers/.
tools: Read, Write, Edit, Bash, Glob, Grep
---

# project-lit-map

Build or refresh `literature-map.md` — a thematic index of papers linked to a project.

Papers in `20-Sources/papers/` carry `project: [ProjectID]` frontmatter. This skill
collects them, groups them by scientific theme, adds project-specific annotations for
each paper, and writes a structured map to the project folder.

## Invocation

```
/project-lit-map --project <id> [--update]
```

| Flag | Meaning |
|------|---------|
| `--project <id>` | Project ID (must match `project:` frontmatter values) |
| `--update` | Diff-only mode: add papers not yet in the existing map; don't reorganise existing themes |

## Step 1 — Locate scripts and paths

```bash
SKILL_DIR=$(dirname "$(readlink -f "$(find -L ~/.claude/skills/project-lit-map -name SKILL.md 2>/dev/null | head -1)")")
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
CONFIG_LOCAL="$DAIMON_ROOT/config/config.local"
VAULT_DIR=$(grep '^VAULT_DIR=' "$CONFIG_LOCAL" | cut -d= -f2-)

COLLECT_SCRIPT=$(find -L ~/.claude -path "*/project-lit-map/scripts/collect_papers.py" -type f | head -1)
PATCH_SCRIPT=$(find -L ~/.claude -path "*/project-lit-map/scripts/patch_litmap.py" -type f | head -1)

PROJECT_DIR="$VAULT_DIR/10-Projects/<project-id>"
PAPERS_DIR="$VAULT_DIR/20-Sources/papers"
```

## Step 2 — Collect papers

```bash
python3 "$COLLECT_SCRIPT" --project <id> --papers-dir "$PAPERS_DIR"
```

Outputs JSON array. Each entry has:
```json
{
  "slug": "author2024-keyword",
  "title": "...",
  "authors": "...",
  "year": 2024,
  "subject_tags": ["tag1", "tag2"],
  "why_included": "...",
  "key_relevance": "first 200 chars of Relevance to project from Key points section",
  "screening_score": 4
}
```

If zero papers found: stop and tell user to check that paper notes have `project: [<id>]` frontmatter.

In `--update` mode, also read the existing `literature-map.md` to identify which slugs are already mapped. Pass `--exclude-slugs <slug1,slug2,...>` to collect_papers.py so only new papers reach Claude.

## Step 3 — Claude grouping pass (single call)

You are doing this step. Given the papers JSON from Step 2, produce themed groupings.

**How to group:**
- Aim for 3-6 themes per map. More papers → more themes.
- Each theme should be a coherent scientific topic relevant to the project.
- A paper can appear in at most one theme (place it where it is most relevant).
- Name themes concisely: "DFT adsorption methods", "Zeolite structural properties", "ML for materials".
- For each paper, write a project-situated annotation (1-2 sentences): why this paper matters *to this specific project*, not just what it says.
- Papers with `screening_score <= 2` get a `(low relevance)` tag in the annotation.

**Output JSON:**
```json
{
  "themes": [
    {
      "name": "Theme label",
      "papers": [
        {
          "slug": "author2024-keyword",
          "annotation": "project-specific note about relevance"
        }
      ]
    }
  ]
}
```

## Step 4 — Preview and apply

Write groupings JSON to a temp file, then dry-run:
```bash
GROUPINGS_FILE=$(mktemp /tmp/project-lit-map-XXXX.json)
cat > "$GROUPINGS_FILE" << 'ENDJSON'
<JSON from Step 3>
ENDJSON

python3 "$PATCH_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --papers-dir "$PAPERS_DIR" \
  --groupings-file "$GROUPINGS_FILE" \
  --project-id "<project-id>" \
  [--update] \
  --dry-run
```

Show the diff to the user. Ask for confirmation.

After approval:
```bash
python3 "$PATCH_SCRIPT" \
  --project-dir "$PROJECT_DIR" \
  --papers-dir "$PAPERS_DIR" \
  --groupings-file "$GROUPINGS_FILE" \
  --project-id "<project-id>" \
  [--update]
rm "$GROUPINGS_FILE"
```

## Edge cases

- **No papers tagged:** stop, tell user to add `project: [<id>]` to paper notes
- **Single theme:** fine — write one theme section
- **`--update` with no new papers:** "No new papers to add" — don't rewrite the map
- **Paper in JSON but not on disk:** skip with a warning in the diff output
