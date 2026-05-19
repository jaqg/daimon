---
name: git-sync
description: >
  Commit all working-tree changes (modified + untracked) and push to remote. Use this skill
  whenever the user wants to sync, save, or push their current work without manually staging
  files: "/git-sync", "sync my changes", "commit everything", "update the repo", "push all
  changes", "save my work", "commit and push", "commit all my changes". Also invoke when the
  user says "I'm done working, push it" or "update the branch". Make sure to use this whenever
  the user wants to go from working tree → remote in one step.
tools: Bash
---

# git-sync

Reads the working tree, groups related changes into logical commits, shows the proposed
grouping and messages, then prints the full command sequence to stage, commit, and push.
By default never executes git — only prints commands.

## Flags

```
--no-push     omit the final git push command
--coauthor    add "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" to every commit
--dry-run     show grouping plan without generating commit messages or commands
--execute     run all commands directly (confirms before push)
```

## Step 0: Scan working tree

```bash
SCRIPT=$(find -L ~/.claude -path "*/git-sync/scripts/scan.py" -type f | head -1)
python3 "$SCRIPT"
```

The script outputs JSON with:
- `clean: true` → tell user "Nothing to commit — working tree clean." and stop
- `tracked[]` — modified files with `status`, `diff_stat`, `diff_excerpt`
- `untracked[]` — new files with `ambiguous: bool` and `content_excerpt`
- `already_staged[]` — files already staged (warn user; do not re-stage)
- `log[]` — recent commits for style context

**Handle already-staged files first:** warn for each:
```
Warning: <path> is already staged — run git-commit first, or unstage with `git reset HEAD <path>`
```

**Handle ambiguous untracked files:** for each `untracked` entry where `ambiguous: true`, ask:
```
New file: <path> — extension unrecognised or looks like generated output. Include? (y/n)
```
Files where `ambiguous: false` include automatically.

## Step 1: Group related changes

Receive the scan JSON. Cluster files into logical commits — one coherent purpose per group.

**Group together:**
- Source file + its test file → one commit
- Multiple files in same module/directory for the same concern
- Config file + the code using it (if changed for the same reason)

**Separate into different commits:**
- Documentation-only changes (`.md`, `.rst`) → `docs:` commit
- CI/build files (`.github/`, `Makefile`, `pyproject.toml`) → `ci:` or `build:` commit
- Clearly unrelated modules

**--dry-run output** (stop here if flag is set):
```
Proposed grouping:
  Group 1: src/auth/login.py, tests/test_login.py → (message TBD)
  Group 2: docs/README.md → (message TBD)

Run without --dry-run to generate messages and commands.
```

## Step 2: Generate commit messages

Format: `type(scope): subject`

**Type:** feat / fix / docs / chore / refactor / test / style / perf / ci / build  
**Scope:** derived from file paths (`src/auth/` → `auth`; omit if multi-module)  
**Subject:** imperative mood, ≤50 chars, no trailing period  
**Body:** only if the *why* is non-obvious  
**Footer:** `BREAKING CHANGE: <desc>` if public API/CLI/config changes incompatibly

Use `log[]` from scan output for style context.

## Step 3: Print plan and commands

```
Proposed commits (N groups):

  [1] feat(auth): add OAuth2 login flow
      Files: src/auth/oauth.py, tests/test_oauth.py

  [2] docs: update authentication section in README
      Files: docs/README.md

Run these commands, or ask to adjust grouping or messages:

```bash
# Group 1
git add src/auth/oauth.py tests/test_oauth.py
git commit -m "feat(auth): add OAuth2 login flow"

# Group 2
git add docs/README.md
git commit -m "docs: update authentication section in README"

git push
```

If `--no-push`: omit `git push`.  
If `--coauthor`: append `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` to every commit body.

### With --execute

Show plan (Step 3), wait for confirmation, then run each command via Bash. Before `git push`, confirm:
```
About to run: git push
Proceed? (y/n)
```

## Guarantees

- Never executes git unless `--execute` is passed.
- Never adds Co-Authored-By unless `--coauthor` is passed.
- Gitignored files are never included (filtered by scan.py).
- Already-staged files are warned, never double-staged.

## Error handling

| Problem | Action |
|---------|--------|
| `clean: true` from scan | "Nothing to commit — working tree clean." |
| scan.py exits non-zero | Report error from stderr; stop |
| All untracked files ignored | Inform user; stop if nothing tracked either |
| No remote configured | Omit push command; warn user |
