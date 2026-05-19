---
name: git-branch
description: >
  Manage git branches and worktrees: create, list, merge, and clean. Use this skill whenever
  the user wants to work with branches or worktrees: "/git-branch", "create a branch",
  "new worktree", "list branches", "merge branch X", "clean stale branches", "what branches
  do I have", "remove merged branches", "create a feature branch", "add a worktree",
  "switch to a new branch", "finish this feature", "delete old branches". Also invoke when
  the user asks about branch status, which branches are merged, or which worktrees exist.
tools: Bash
---

# git-branch

Manage the full lifecycle of git branches and worktrees. Prints commands by default — never
executes them unless `--execute` is passed.

## Subcommands

```
(default)       Show current branch status + suggest what to do next
--new <name>    Create branch + linked worktree in sibling directory
--list          List all branches with status, worktree paths, and age
--merge <name>  Merge a finished branch back to main (strategy choice + cleanup)
--clean         Find and remove merged branches and orphaned worktrees
--execute       Run the printed commands directly (confirms before destructive steps)
```

---

## Step 0: Run branch_info script

For every subcommand, run the script first:

```bash
SCRIPT=$(find -L ~/.claude -path "*/git-branch/scripts/branch_info.py" -type f | head -1)
```

| Subcommand | Script call |
|------------|-------------|
| default | `python3 "$SCRIPT"` |
| --list | `python3 "$SCRIPT" list` |
| --clean | `python3 "$SCRIPT" clean` |
| --merge NAME | `python3 "$SCRIPT" merge NAME` |
| --new NAME | `python3 "$SCRIPT" new NAME` |

If the script returns `{"error": "..."}`: report the error and stop.

---

## Default (no flag): branch status

Script returns: `current_branch`, `uncommitted_changes`, `tracking` (ahead/behind), `linked_worktrees`, `merged_stale`, `recent_log`.

Show:
- Current branch + ahead/behind remote
- Whether working tree has uncommitted changes
- Any linked worktrees

**Suggest** the most relevant next action based on the JSON:
- `ahead > 0` → "N commits not yet pushed — run `/git-sync` to push"
- `merged_stale` non-empty → "Branch(es) X merged — run `/git-branch --clean`"
- `uncommitted_changes` → "Uncommitted changes — run `/git-sync` to commit"
- `linked_worktrees` non-empty → list them

---

## --new \<name\>

Script returns: `branch`, `worktree_path`, `current_branch`, `uncommitted_changes`, `branch_exists`, `path_exists`.

If `path_exists: true`: report path conflict, stop.

Print:
```
New branch: <name>
Worktree:   <worktree_path>
```

If `uncommitted_changes`: prepend warning: "main has uncommitted changes. Consider running /git-sync first."

Commands:
```bash
# if branch_exists: false
git worktree add -b <name> <worktree_path>

# if branch_exists: true (branch already exists without worktree)
git worktree add <worktree_path> <name>
```

Remind user: `cd <worktree_path>` to work there; use `/git-sync` or `/git-commit` inside it.

---

## --list

Script returns: `branches[]` — each has `name`, `current`, `ahead`, `behind`, `upstream`, `worktree_path`, `age`, `merged`.

Format as table:

```
Branch                    Status          Last commit     Worktree
──────────────────────────────────────────────────────────────────────
* main                    up to date      2 hours ago     /home/user/myapp
  feature/task-a          3 ahead         1 day ago       /home/user/myapp-task-a
  feature/old-auth        merged ✓        3 weeks ago     (none)
```

Mark merged branches — candidates for `--clean`.
Mark branches with no worktree that aren't `main` — might be abandoned.

---

## --merge \<name\>

Script returns: `branch`, `target`, `commits[]`, `commit_count`, `diff_stat`, `ff_possible`, `worktree_path`.

If script returns `error`: report branch not found, list available branches with `python3 "$SCRIPT" list`, stop.

Show:
```
Branch '<name>' has N commit(s):
  <sha> <message>
  ...

Files changed:
  <diff_stat>
```

**Choose strategy** (use `commit_count` and `ff_possible` from JSON):

```
Merge strategy:
  [1] merge commit   — preserves full history
  [2] squash merge   — N commits → one commit on main (clean linear history)
  [3] rebase         — replays commits on top of main (linear, no merge commit)

Which strategy? (default: 1 for N>1, 2 for N=1)
```

Wait for user input (or default if `--execute` with pre-chosen strategy).

Generate squash commit message from `commits[]` using conventional commit format.

Print commands per strategy:

**Merge commit:**
```bash
git merge --no-ff <name>
git worktree remove <worktree_path>   # only if worktree_path in JSON
git branch -d <name>
git push
```

**Squash:**
```bash
git merge --squash <name>
git commit -m "<generated conventional commit message>"
git worktree remove <worktree_path>
git branch -d <name>
git push
```

**Rebase:**
```bash
git rebase main <name>
git checkout main
git merge --ff-only <name>
git worktree remove <worktree_path>
git branch -d <name>
git push
```

If `diff_stat` shows same files changed on both branches, prepend conflict note.

---

## --clean

Script returns: `candidates[]` (each has `name`, `age`, `worktree_path`) and `orphaned_worktrees[]`.

If both empty: "Nothing to clean — no merged branches or orphaned worktrees found."

Otherwise print:
```
Merged branches (safe to delete):
  feature/old-auth     merged 3 weeks ago
  fix/bug-123          merged 2 days ago

Orphaned worktrees:
  /home/user/myapp-old-feature

Commands to clean up:

git branch -d feature/old-auth fix/bug-123
git worktree prune
git push origin --delete feature/old-auth fix/bug-123
```

---

## --execute

When `--execute` is passed, run printed commands via Bash. Before any destructive step, confirm:
```
About to run: git branch -d feature/old-auth fix/bug-123
Proceed? (y/n)
```

---

## Guarantees

- Never executes commands unless `--execute` is passed.
- Never deletes `main`, `master`, `develop`, or `staging` (enforced in script).
- Never removes a worktree that is currently checked out.
- Never force-pushes.
- Always shows what will be deleted before deleting.

## Error handling

| Problem | Action |
|---------|--------|
| Not in a git repo | Script returns error; report and stop |
| `path_exists: true` for --new | Report conflict; stop |
| `error` from --merge | List available branches; stop |
| No remote configured | Omit push commands; warn user |
