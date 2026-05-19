---
name: git-commit
description: >
  Generate a conventional commit message from currently staged git changes and print the
  git commit command to run. Use this skill whenever the user wants to commit staged files:
  "/git-commit", "generate commit message", "commit this", "write a commit for staged changes",
  "what should I commit", "conventional commit for staged files", "help me write a commit",
  "commit message for my changes", "I staged X, now commit". Also invoke when the user says
  "staged my fix, need a message" or similar. Make sure to use this whenever the user has
  staged changes and wants a well-formatted commit message.
tools: Bash, Read
---

# git-commit

Reads the staged diff, infers a conventional commit message, and prints the `git commit`
command for you to run. By default it never executes git — it only prints the command.

## Flags

```
--coauthor    add "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>" trailer
--amend       use git commit --amend instead of a new commit
--execute     run the commit command directly (shows message first, confirms before running)
```

## Step 0: Check for staged changes

```bash
git diff --cached --stat
```

If the output is empty, nothing is staged. Tell the user and stop — suggest what to do:
```
Nothing staged. Try:
  git add <file>     # stage a specific file
  git add -p         # stage hunks interactively
```

## Step 1: Read the staged diff and recent history

```bash
git diff --cached
git log --oneline -10
```

The diff tells you *what* changed. The log tells you the style and type of commits already in
this repo, so you can stay consistent. For very large diffs (>300 lines), use `--stat` only
plus the first 50 lines of the full diff — enough to understand the shape of the change.

## Step 2: Generate the conventional commit message

Format: `type(scope): subject`

**Type** — pick the best fit:

| type | when to use |
|------|-------------|
| feat | new feature or user-visible capability |
| fix | bug fix |
| docs | documentation only (md, rst, docstrings) |
| chore | maintenance, config, deps, scripts |
| refactor | restructure without behaviour change |
| test | add or fix tests |
| style | whitespace, formatting (no logic change) |
| perf | performance improvement |
| ci | CI/CD configuration |
| build | build system or tooling |

**Scope** — derive from the file paths that changed:
- `src/auth/login.py` → scope `auth`
- `src/utils/parser.py` → scope `utils`
- `tests/test_foo.py` alongside `src/foo.py` → use `foo` (tests are implied by the type)
- Changes span many unrelated modules → omit scope: `feat: subject`

**Subject** — imperative mood ("add X", not "added X"), ≤50 chars, no trailing period.

**Body** (optional) — add only when the *why* is non-obvious from the diff alone. Separate
from subject with a blank line. Keep each line ≤72 chars.

**Footer** — add `BREAKING CHANGE: <description>` when a public API, CLI interface, or
config schema changes in a way that forces callers to update their code.

### Spotting multiple unrelated changes

If the staged diff contains clearly unrelated concerns (e.g. a bug fix in one module and a
new feature in another), warn the user before generating the message:

```
Warning: staged changes span multiple unrelated concerns.
Consider splitting with:
  git reset HEAD <file>    # unstage a specific file
  git stash -p             # interactively stash hunks
```
Then generate the best single message you can for the combined diff, with a note that it
covers multiple changes.

## Step 3: Output

### Default (print command only)

Present the message clearly, then the exact command:

```
Commit message:
  fix(auth): reject empty credentials before password check

Run:
  git commit -m "fix(auth): reject empty credentials before password check"
```

For multi-line messages (with body), format the `-m` value with proper newlines:
```
  git commit -m "feat(api): add pagination to list endpoints

Results are now limited to 100 items per page. Pass ?page=N to
navigate. Prevents OOM on large datasets."
```

If `--amend` is set, replace `git commit` with `git commit --amend`.
If `--coauthor` is set, append to the body (after a blank line):
```
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### With --execute

Show the message and command as above, then run the command via Bash and display git's output.

## Guarantees

- Never executes git unless `--execute` is passed explicitly.
- Never adds Co-Authored-By unless `--coauthor` is passed.
- Always uses conventional commits format (`type(scope): subject`).
- Always checks for staged content before generating a message.

## Error handling

| Problem | Action |
|---------|--------|
| Nothing staged | Inform user; suggest `git add`; stop |
| Not in a git repo | Report the error from git; stop |
| Diff too large (>300 lines) | Use `--stat` + first 50 diff lines |
| Merge/rebase in progress | Warn; proceed with diff-based message |
| Amend on empty history | Report git error; stop |
