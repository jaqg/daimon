---
description: Open a brain session for this project part (planning/decision tier, gated toolset)
argument-hint: "<part or project> [memory/project_*.md path]"
---

Adopt the **brain** role. Read `~/.pi/agent/agents/brain.md` now and follow it as your role
definition for the entire session.

Session context: ${1:-no part specified — ask which project part this brain owns and which
`memory/project_*.md` is its state file}

On start:
1. Read ONLY the state file (`memory/project_*.md`) and any `plans/*.md` the user names. Most vault
   projects are still generation-old and have neither `plans/` nor a state-file pointer: run
   `/triage <project>` recon first, use `project-dashboard.md` as the state file, and report missing
   directories as **structure debt** for José to fix with `vault-init.sh`. You cannot `mkdir` — your
   `bash` is denied except `worktree.sh` and `merge-status.py`, so a missing `plans/` is a hard stop for
   the planning step, not something to work around by writing files by hand.
2. Run `/role` and confirm the gate reports `role=brain`. If it says no gate is active, write
   it: `/role brain`, then `/new` so the tool deny-list takes effect.
3. If this is a planning cycle that will delegate work, the repo must be initialised first — run
   `bash ~/.pi/agent/scripts/worktree.sh init --repo <repo> --vault <10-Projects/X> --part <part>
   --test-cmd '<the one command that means green>'` (your `bash` is denied for everything except that
   script and `merge-status.py`). If it reports "not a git repo", the delegation target is wrong —
   stop and say so instead of writing files by hand.

3b. **Never make José remember a command.** Every delegation you recommend ships with the line that
   executes it, copied verbatim from a script — never from memory, never paraphrased. `merge-status.py`
   prints `next-command[brain]:` / `next-command[operator]:` lines; `worktree.sh add` prints `DELTA=`;
   `worktree.sh lab` prints the verifier's pane line. If none of them produce a command for a step you
   are recommending, the machinery is missing something: say `no command for: <step>` in **Open for
   José** rather than inventing syntax. Canonical forms, in the same words the tools use:

   | step | who runs it |
   |---|---|
   | `pi-agents worker --repo <repo> --wt <part>/<slice>` | José (pane), leaf tier |
   | `pi-agents calcs --repo <repo> --wt <part>/<slice>` | José (pane) — `--role calcs` is implied by the role name |
   | `pi-agents scout --repo <repo> --wt <part>/<slice>` | José (pane), or you via `subagent` |
   | `python3 ~/.pi/agent/scripts/merge-status.py --repo <repo>` | **you** (allowed script) |
   | `bash ~/.pi/agent/scripts/worktree.sh integrate --repo <repo> --part <part>` | **you** (allowed script) |
   | `pi-agents integrator --repo <repo>/.worktrees/integrate-<part>` | José (pane) |
   | `bash ~/.pi/agent/scripts/worktree.sh lab --repo <repo> --part <part>` | José (cross-lab checkout) |
   | `pi-agents verifier --repo <repo>/.labs/<part>` | José (pane) |
   | `git -C <repo> merge --no-ff integration/<part>` | José only — no tier may land main |

4. Ask José what kind of cycle this is — **planning**, **clarification**, or **triage** — and
   keep the session scoped to that. Do not drift into inspection or implementation.

This session is a per-cycle container, not a per-project container: when the plan is written and
delegated, or the part ships, say so and let José clear it (`/new`) rather than let it compact
its way to 400K tokens.
