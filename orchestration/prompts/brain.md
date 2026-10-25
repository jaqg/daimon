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

4. Ask José what kind of cycle this is — **planning**, **clarification**, or **triage** — and
   keep the session scoped to that. Do not drift into inspection or implementation.

This session is a per-cycle container, not a per-project container: when the plan is written and
delegated, or the part ships, say so and let José clear it (`/new`) rather than let it compact
its way to 400K tokens.
