---
description: Read-only project triage — reconstruct where a project stands and name 2-3 candidate next parts
argument-hint: "[project name under 10-Projects/ (e.g. a-collab-project, the-dataset-project, Collabs/a-collab-project)]"
---

Adopt the **brain** role: read `~/.pi/agent/agents/brain.md` now and follow it for this session.
This is a **triage cycle** — recon and recommendation only. No planning, no file writing, no delegation.
Project: `${1:-ask José which project, then continue}`

## 1. Deterministic recon first (zero tokens per fact, run it before reading anything)

```bash
: "${VAULT_ROOT:=$HOME/Documents/vault}"   # override: export VAULT_ROOT=~/path/to/your/vault
V="$VAULT_ROOT/10-Projects"
P="$V/${1:?}"
[ -d "$P" ] || P=$(find "$V" -maxdepth 2 -type d -iname "*${1}*")
ls "$P"
echo "-- state file:"; grep -m1 -o 'memory/project_[a-z0-9_]*\.md' "$P/AGENTS.md"
echo "-- structure generation:"
for d in plans status ai-out handoffs; do [ -d "$P/$d" ] && echo "   $d/ present ($(ls "$P/$d" | wc -l) entries)" || echo "   $d/ MISSING"; done
echo "-- dashboard head:"; head -20 "$P/project-dashboard.md" 2>/dev/null
echo "-- last history entries:"; grep -n '^##\|^###' "$P/history.md" 2>/dev/null | tail -6
echo "-- open questions:"; grep -c '^\s*-\s*\[ \]' "$P/open-questions.md" 2>/dev/null || echo "   none"
echo "-- linked repos:"; cat "$P/status/repos.txt" 2>/dev/null; grep -m2 -o '/home/[^ )`]*' "$P/AGENTS.md"
echo "-- recent commits per linked repo:"
for r in $(cat "$P/status/repos.txt" 2>/dev/null); do echo "  $r: $(git -C "$r" log --oneline -3 2>/dev/null | tr '\n' ' | ')"; done
echo "-- part rollups:"; for f in "$P"/status/*.md; do [ -f "$f" ] && echo "  $(basename "$f"): $(head -3 "$f" | tr '\n' ' ')"; done
```

Never substitute an `ls` for a `read` of a file you intend to summarise — this block exists so you do
not burn cache on directory listing. Read files *after* it, and only the ones it points at.

## 2. Then read, in this order, and stop when you can answer

1. `memory/project_*.md` if the pointer exists (current state + constraints).
2. `project-dashboard.md` (status + 30-day work log) — **this is the real state file for most projects.**
3. The newest 2–4 sections of `history.md`, or `handoffs/next-session-context.md` if present.
4. `plans/*.md` if present (planned-but-unstarted parts).

If a project has no `memory/project_*.md`, say so and use the dashboard — do not create a state file,
and do not invent a path. Missing directory ≠ missing knowledge.

## 3. Report in ≤20 lines, exactly these four blocks

**WHERE IT STANDS** — 3–5 lines: last landed thing, what's mid-flight, what's blocked, date of the newest evidence.

**STRUCTURE DEBT** — one line per generation-old element, with the fix being *always* the same script, never you:
```
plans/ missing → bash <repo>/orchestration/scripts/vault-init.sh --project <X>   (José runs it — your bash is denied)
no memory/project_*.md pointer in AGENTS.md → same script
```
You cannot `mkdir`: the gate denies it. Reporting the debt is your whole job for this block.

**CANDIDATE NEXT PARTS** — 2–3, each as `<part-name>: one sentence of what lands — <N> worker panes, model tier, rough cost`.
Recommend the cheapest one that unblocks the most. Part names become branches, so lowercase, hyphenated,
no verbs (`selection-pipeline`, not `do-selection`).

**ASK** — one question that only José can answer. If the answer is obvious, there is nothing to triage;
say "run `/brain <part>`" and stop.

Do not paste file bodies into chat, do not draft specs, do not open a scout. Triage ends when José picks a part.
