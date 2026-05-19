---
name: git-branch
description: >
  Manage git branches and worktrees: create, list, merge, and clean. Use this skill whenever
  the user wants to work with branches or worktrees: "/git-branch", "create a branch",
  "new worktree", "list branches", "merge branch X", "clean stale branches", "what branches
  do I have", "remove merged branches", "create a feature branch", "add a worktree",
  "switch to a new branch", "finish this feature", "delete old branches". Also invoke when
  the user asks about branch status, which branches are merged, or which worktrees exist.
tools: Bash, Read
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

## Default (no flag): branch status

Run:
```bash
git branch --show-current
git status --short
git log --oneline -5
git branch -vv
git worktree list
```

Show:
- Current branch name + how many commits ahead/behind remote
- Whether working tree has uncommitted changes
- Any linked worktrees

Suggest the most relevant next action (e.g., "You have 3 commits not yet pushed — run
`/git-sync` to push them" or "Branch `feature/auth` has been merged — run `/git-branch --clean`
to remove it").

---

## --new \<name\>

Create a new branch and a linked worktree in a sibling directory so work can proceed in
parallel without switching branches.

### Step 1: Gather context

```bash
git rev-parse --show-toplevel   # repo root (e.g. /home/user/repos/myapp)
git branch --show-current       # current branch (usually main)
git status --short              # warn if uncommitted changes in main
```

### Step 2: Compute paths

- Repo root: `<root>` (e.g. `/home/user/repos/myapp`)
- Worktree path: `<root>/../myapp-<name>/` (sibling directory)
  - Strip `feature/` / `fix/` prefixes for the directory name:
    `feature/task-a` → `myapp-task-a`
  - If the computed path already exists, inform the user and stop.

### Step 3: Print commands

```
New branch: <name>
Worktree:   <computed-path>

git worktree add -b <name> <computed-path>
```

If main has uncommitted changes, prepend a warning:
```
Warning: main has uncommitted changes. Consider running /git-sync first.
```

If the branch already exists (without a worktree):
```bash
git worktree add <computed-path> <name>
```

After creating the worktree, the user can `cd <computed-path>` and work there independently.
Remind them: run `/git-sync` or `/git-commit` inside the worktree to commit work there.

---

## --list

Show all branches with actionable status information.

### Step 1: Gather data

```bash
git branch -vv                          # local branches + upstream tracking info
git worktree list --porcelain           # all linked worktrees
git for-each-ref --format='%(refname:short) %(committerdate:relative)' refs/heads
```

Also check which branches are merged into main:
```bash
git branch --merged main
git branch --no-merged main
```

### Step 2: Format output

Print a table. For each branch:

```
Branch                    Status          Last commit     Worktree
──────────────────────────────────────────────────────────────────────────
* main                    up to date      2 hours ago     /home/user/myapp
  feature/task-a          3 ahead         1 day ago       /home/user/myapp-task-a
  feature/old-auth        merged ✓        3 weeks ago     (none)
  fix/bug-123             2 behind main   4 days ago      (none)
```

Mark merged branches clearly — they're candidates for `--clean`.
Mark branches with no worktree that aren't `main` — might be abandoned.

---

## --merge \<name\>

Merge a finished feature branch back to the current branch (usually `main`), then clean up.

### Step 1: Validate

```bash
git branch --show-current            # must be main (or target branch)
git log main..<name> --oneline       # commits that will be merged
git diff main...<name> --stat        # files changed
```

If `<name>` does not exist, report and stop.

Count commits: if exactly 1 commit on the branch, squash is natural. If multiple, offer choice.

### Step 2: Choose strategy

Present the options:

```
Branch '<name>' has N commit(s):
  <sha> <message>
  ...

Merge strategy:
  [1] merge commit   — preserves full history, always an explicit merge commit
  [2] squash merge   — squashes N commits into one commit on main (clean linear history)
  [3] rebase         — replays commits on top of main (linear, no merge commit)

Which strategy? (default: 1 for N>1, 2 for N=1)
```

Wait for user input (or use default if `--execute` with a pre-chosen strategy).

### Step 3: Print commands

**Merge commit (strategy 1):**
```bash
git merge --no-ff <name>
git worktree remove <worktree-path>   # if worktree exists
git branch -d <name>
git push
```

**Squash (strategy 2):**
```bash
git merge --squash <name>
git commit -m "<generated conventional commit message>"
git worktree remove <worktree-path>
git branch -d <name>
git push
```
Generate the squash commit message by summarising the branch's commits using conventional
commit format (`type(scope): subject`).

**Rebase (strategy 3):**
```bash
git rebase main <name>
git checkout main
git merge --ff-only <name>
git worktree remove <worktree-path>
git branch -d <name>
git push
```

Always include `git push` unless `--no-push` is set.

### Conflict guidance

If there is likely to be conflicts (diverged history, same files changed on both branches), add
a note before the commands:
```
Note: <name> and main both modified <files>. If conflicts occur during merge:
  1. git status          → shows conflicted files
  2. Edit files to resolve (look for <<<<<<< markers)
  3. git add <resolved>
  4. git commit          → completes the merge
  Or: git merge --abort  → cancel and start over
```

---

## --clean

Find and remove branches that are safe to delete: merged into main and not currently checked out.

### Step 1: Find candidates

```bash
git branch --merged main              # merged local branches (excluding main itself)
git worktree list --porcelain         # check which branches have worktrees
git for-each-ref --format='%(refname:short) %(committerdate:relative)' refs/heads
```

Exclude:
- `main` (and `master`, `develop`, `staging` — protected branch names)
- Branches with an active worktree currently checked out

Also find orphaned worktrees — directories listed in `git worktree list` whose path no longer
exists on disk:
```bash
git worktree prune --dry-run
```

### Step 2: Print candidates + commands

```
Merged branches (safe to delete):
  feature/old-auth     merged 3 weeks ago
  fix/bug-123          merged 2 days ago

Orphaned worktrees:
  /home/user/myapp-old-feature  (path no longer exists)

Commands to clean up:

git branch -d feature/old-auth fix/bug-123
git worktree prune
git push origin --delete feature/old-auth fix/bug-123   # remove remote tracking branches
```

If there are no candidates:
```
Nothing to clean — no merged branches or orphaned worktrees found.
```

---

## --execute

When `--execute` is passed, run the printed commands via Bash instead of just printing them.

Before any destructive step (branch delete, worktree remove, push), pause and confirm:
```
About to run: git branch -d feature/old-auth fix/bug-123
Proceed? (y/n)
```

If the user says n, skip that step and continue with the rest.

---

## Guarantees

- Never executes commands unless `--execute` is passed.
- Never deletes `main`, `master`, `develop`, or `staging` branches.
- Never removes a worktree that is currently checked out.
- Never force-pushes — always uses `git push` with normal tracking.
- Always shows what will be deleted before deleting.

## Error handling

| Problem | Action |
|---------|--------|
| Not in a git repo | Report git error; stop |
| Branch name already exists | Report + suggest `git worktree add <path> <existing-branch>` |
| Target worktree path already exists | Report path conflict; stop |
| Branch `<name>` not found for --merge | List existing branches; stop |
| Branch has unmerged commits for --clean | Skip it (only delete `--merged` branches) |
| No remote configured | Omit push/remote-delete commands; warn user |
| Worktree path still exists after `prune` | Note it; user may need to `rm -rf` manually |
