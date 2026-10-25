---
name: vault-hygiene
disable-model-invocation: false
description: >
  Deterministic vault maintenance: check caps/frontmatter/links and run mechanical
  archival splits (decisions-log, work-log, ai-changes). Use when the user says
  /vault-hygiene, "check the vault", "vault is bloated", "clean up logs",
  "archive old entries", or when any agent notices a hygiene violation while
  working (AGENTS.md § Agent rules). Also runs automatically post-/update-project.
tools: Read, Bash, Glob, Grep
---

# vault-hygiene

Script owns ALL mechanics (thresholds, splits, idempotency). Claude owns judgment
only: interpreting residual violations and directing/composing fixes the script
cannot make. Contract: `vault AGENTS.md § Memory contract`.

## Invocation

```
/vault-hygiene [--project <id>] [--fix]
```

## Step 1 — Locate script + vault

```bash
SKILL_DIR="$(cd "$(dirname "$SKILL_MD")" && pwd)"
DAIMON_ROOT=$(cd "$SKILL_DIR/../../.." && pwd)
VAULT_DIR=$(grep '^VAULT_DIR=' "$DAIMON_ROOT/config/config.local" | cut -d= -f2- | sed "s|~|$HOME|")
SCRIPT="$SKILL_DIR/scripts/vault_hygiene.py"
```

If `VAULT_DIR` unset/template → stop, tell user to fill `config/config.local`.

## Step 2 — Check (always first)

```bash
python3 "$SCRIPT" --vault-dir "$VAULT_DIR" --check [--project <id>] [--fix]
```

Exit 0 = clean. Exit 1 = violations (listed in report). `--fix` auto-applies
zero-judgment fixes (stale MEMORY.md index lines).

## Step 3 — Present + propose

Show the report. Violations needing mechanical archival → propose `--archive`
(preview with `--dry-run` first). **Approval gate:** never run `--archive`
without explicit user confirmation, even though moves are mechanical.

## Step 4 — Archive (on approval)

```bash
python3 "$SCRIPT" --vault-dir "$VAULT_DIR" --archive [--project <id>] [--dry-run]
```

Script is idempotent (re-runs no-op), re-checks post-archive, D-numbers never
reused. Report the moves + post-state to the user.

## Step 5 — Judgment residuals (Claude's job)

Script reports but cannot fix:

| Violation | Claude's action |
|---|---|
| memory/project_*.md >80 lines | Compress: keep CURRENT (≤5 bullets) + CONSTRAINTS + POINTERS; move dated detail to project's `history.md` |
| MEMORY.md >60 lines | Consolidate index entries (merge related hooks) |
| frontmatter missing keys | Fill: `status/type/subject` (notes) or `name/description/type` (memory files) — `subject`/`description` need judgment |
| memory file not in MEMORY.md index | Write one-line hook (needs content judgment) |
| results-log/history over warn threshold | Inform user — archival is manual by design (citable record / overflow valve) |

For memory compression: use `/update-project` (owns memory/project_*.md) —
don't hand-edit during hygiene. Frontmatter/index fixes: small, do inline with
user approval (show diff).

## Thresholds (script constants — do not duplicate here)

`scripts/vault_hygiene.py` header documents all caps. AGENTS.md § Memory contract
is the canonical policy source.

## Edge cases

- **Nothing to report:** say "All clean" plainly
- **--project given:** paper/frontmatter/symlink/ai-changes checks skipped (project-scoped run)
- **Vault path wrong / not found:** exit 2 with message — report to user, don't improvise paths
