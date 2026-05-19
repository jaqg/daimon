---
name: git-sync
description: >
  Commit all working-tree changes (modified + untracked) and push to remote. Use this skill
  whenever the user wants to sync, save, or push their current work without manually staging
  files: "/git-sync", "sync my changes", "commit everything", "update the repo", "push all
  changes", "save my work", "commit and push", "commit all my changes". Also invoke when the
  user says "I'm done working, push it" or "update the branch". Make sure to use this whenever
  the user wants to go from working tree → remote in one step.
tools: Bash, Read
---

# git-sync

Reads the working tree, groups related changes into logical commits, shows you the proposed
grouping and messages, then prints the full command sequence to stage, commit, and push.
By default it never executes git — it only prints the commands.

## Flags

```
--no-push     omit the final git push command
--coauthor    add "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" to every commit
--dry-run     show grouping plan without generating commit messages or commands
--execute     run all commands directly (confirms before push)
```

## Step 0: Read the working tree

```bash
git status --short
```

Parse the output. Each line has a two-character status code + filename:
- ` M` / `M ` / `MM` — modified tracked file
- `??` — untracked file
- `A ` — already staged (warn user; do not re-stage)
- `D ` / ` D` — deleted

If the working tree is clean (no output), tell the user and stop:
```
Nothing to commit — working tree clean.
```

## Step 1: Handle untracked files

For each `??` file:
1. Run `git check-ignore -q <file>` — if exit code 0, it is gitignored; skip it silently.
2. If not ignored, include it in the sync. If the file has an ambiguous extension (`.log`, `.tmp`,
   `.pyc`, binary detected) ask the user before including:
   ```
   New file: build/output.log — looks like generated output. Include? (y/n)
   ```
3. Common source files (`.py`, `.js`, `.ts`, `.md`, `.yaml`, `.toml`, `.sh`, etc.) include
   automatically without asking.

## Step 2: Read diffs

For modified tracked files, read their diffs:
```bash
git diff <file1> <file2> ...
```

For untracked files that will be included, read their content:
```bash
cat <new-file>
```

For very large diffs (>200 lines per file), use `--stat` + the first 40 lines of that file's diff.

Also read recent history for style context:
```bash
git log --oneline -10
```

## Step 3: Group related changes

Cluster files into logical commits. A good group has a single coherent purpose — one reason to
revert it. Use these signals:

**Group together:**
- Source file + its test file (`src/foo.py` + `tests/test_foo.py` → one commit)
- Multiple files in the same module/directory that address the same concern
- Config file + the code that uses it, if changed together for the same reason

**Separate into different commits:**
- Documentation-only changes (`.md`, `.rst`, docstrings) → `docs:` commit
- CI/build file changes (`.github/`, `Makefile`, `pyproject.toml`) → `ci:` or `build:` commit
- Changes in clearly unrelated modules, even if small

If the grouping is ambiguous, default to one commit per logical concern. It's better to have
two well-named commits than one vague `chore: update files`.

**--dry-run output** (stop here if flag is set):
```
Proposed grouping:
  Group 1: src/auth/login.py, tests/test_login.py → (message TBD)
  Group 2: docs/README.md → (message TBD)

Run without --dry-run to generate messages and commands.
```

## Step 4: Generate commit messages

For each group, generate a conventional commit message using the same rules as git-commit:

Format: `type(scope): subject`

**Type:** feat / fix / docs / chore / refactor / test / style / perf / ci / build  
**Scope:** derived from file paths (e.g. `src/auth/` → `auth`; omit if multi-module)  
**Subject:** imperative mood, ≤50 chars, no trailing period  
**Body:** add only if the *why* is non-obvious  
**Footer:** `BREAKING CHANGE: <desc>` if public API/CLI/config changes incompatibly  

## Step 5: Print plan and commands together

Show the grouping plan and the full command sequence in the same response. The user can
immediately run the commands, or ask you to adjust the grouping or messages.

```
Proposed commits (3 groups):

  [1] feat(auth): add OAuth2 login flow
      Files: src/auth/oauth.py, tests/test_oauth.py

  [2] fix(api): return 404 instead of 500 for missing resource
      Files: src/api/handlers.py

  [3] docs: update authentication section in README
      Files: docs/README.md

Run these commands, or ask me to adjust the grouping or messages:

```bash
# Group 1
git add src/auth/oauth.py tests/test_oauth.py
git commit -m "feat(auth): add OAuth2 login flow"

# Group 2
git add src/api/handlers.py
git commit -m "fix(api): return 404 instead of 500 for missing resource"

# Group 3
git add docs/README.md
git commit -m "docs: update authentication section in README"

git push
```

For multi-line commit messages (with body), format the `-m` value correctly:
```bash
git commit -m "feat(users): add pagination to list endpoint

Results capped at 100 per page. Use ?page=N to navigate.
Prevents OOM on large datasets."
```

If `--no-push` is set, omit the final `git push` line.  
If `--coauthor` is set, append to the body of every commit:
```
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### With --execute

Show the plan (Step 5), wait for confirmation, then run each command in sequence via Bash
and display git's output. Before running `git push`, pause and confirm:
```
About to run: git push
Proceed? (y/n)
```

## Guarantees

- Never executes git unless `--execute` is passed explicitly.
- Never adds Co-Authored-By unless `--coauthor` is passed.
- Always shows the full plan before printing or executing commands.
- Gitignored files are never included.
- Already-staged files are flagged, not double-staged.

## Error handling

| Problem | Action |
|---------|--------|
| Working tree clean | Inform user; stop |
| Not in a git repo | Report git error; stop |
| All changes gitignored | Inform user; stop |
| Ambiguous untracked file | Ask before including |
| Already-staged files exist | Warn: "X is already staged — run git-commit first, or unstage with `git reset HEAD X`" |
| Diff too large | Use `--stat` + first 40 lines per file |
| No remote configured | Omit push command; warn user |
