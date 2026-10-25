# `.agent-paths` — the delegation contract between a brain and its workers

One file per repo, at the repo root, **gitignored** (`worktree.sh init` adds it to
`.git/info/exclude`, so it never shows up in a diff or a commit). The brain writes it once per
part via `worktree.sh init`; agents only read it. Values are never invented by an agent — that is
the whole point: the integrator is forbidden from guessing where to merge, so the branch name has
to come from somewhere mechanical.

```
repo: $HOME/Documents/Universidad/aac-DOCTORADO/the-dataset-project
vault_project: $VAULT_ROOT/10-Projects/the-dataset-project
status_dir: $VAULT_ROOT/10-Projects/the-dataset-project/status
ai_out: $VAULT_ROOT/10-Projects/the-dataset-project/ai-out
worktrees: $HOME/Documents/Universidad/aac-DOCTORADO/the-dataset-project/.worktrees
integration_branch: integration/partB
test_cmd: .venv/bin/pytest -q
```

| key | who writes | who reads | why it exists |
|---|---|---|---|
| `repo` | `worktree.sh init` | everyone | the shared checkout. **No agent works here.** |
| `vault_project` | brain | `/merge-status`, `/update-project` | where durable state lives (vault, not repo) |
| `status_dir` | `init` | `/merge-status` | receives `status/<part>.md` rollups (≤15 lines, permanent) |
| `ai_out` | `init` | any agent | `ai-out/YYYY-MM-DD-<agent>-<topic>.md`, swept at 14 days |
| `worktrees` | `init` | brain, `worktree.sh` | one directory per agent: `.worktrees/<part>-<agent>` |
| `integration_branch` | brain (`--part`) | **integrator**, `merge-status.py`, `worktree.sh prune` | the merge lock: `role-gate.ts` blocks `git merge` unless HEAD starts with this prefix |
| `test_cmd` | brain | worker, calcs, integrator | the one command that defines "green", so no agent has to guess it |

## Two machines, one file per machine

`.agent-paths` holds **absolute** paths and is gitignored, so it is not shared: `worktree.sh init`
has to be re-run on each machine (different `$HOME`, sometimes different repo roots). Nothing else
in the contract changes, and re-running `init` keeps any key you do not pass.

## Rules this file enforces

1. **The brain runs the two scripts, and nothing else.** `bash` is denied for the brain tier except
   for `worktree.sh` and `merge-status.py` (`bashAllow` in `role-gate.ts`), and the allowance is refused
   if the command contains `;`, `&&`, `|`, backticks or redirection — the allowlist covers the *bare*
   command, so it cannot be used to read a file or chain a shell. Its worktree path comes from `worktrees` + `--part/--agent`;
   `worktree.sh add` also drops a `.pi-role` inside, which is what activates the tool gate for a
   spawned agent (the spawn-time detection gap: subagents inherit cwd, not role).
2. **`integration_branch` is the only legal merge target.** Landing = promoting
   `integration/<part>` to `main`, which is a *decision*, and decisions belong to José or the brain.
   `git checkout main` and `git push` are denied for the integrator by pattern; merges off the
   integration branch are denied by the lock.
3. **`test_cmd` is what "green" means.** The integrator runs it on the integrated tree, not on the
   parts; a branch that was green alone and broke the whole is an integration FAIL.
4. **Re-running `init` is safe and loses nothing**: keys you do not pass are preserved from the
   existing file. `--part` also sets `integration_branch: integration/<part>`.

## Lifecycle

```
/brain partB                      planning cycle
  worktree.sh init  --repo R --vault V --part partB --test-cmd '...'
  worktree.sh add   --repo R --part partB --agent desc            # worker
  worktree.sh add   --repo R --part partB --agent env --role calcs
  … workers append .agent/status/<date>-partB-<agent>.md …
/merge-status partB               roll deltas → status/partB.md (≤15 lines), mark deltas .processed
worktree.sh integrate --repo R --part partB                       # integrator's own worktree
  integrator: merges agent/* into integration/partB, runs test_cmd, reports CONFLICT lines
  worktree.sh prune --repo R --part partB                          # drop worktrees already merged
José: git checkout main && git merge --no-ff integration/partB     # the only irreversible step
```
