#!/usr/bin/env bash
# test-merge-status — the delta *contract*: names, placement, and the integration note.
#
# Written 2026-10-26 after four defects came out of one trial run: the hyphen join could not tell a
# hyphenated part from a hyphenate agent (a delta for part `structure` rolled up as `structure-vault`),
# --force refused the very .processed files the script itself renames, a worker's delta stranded in its
# own worktree because `.agent/status` is per-worktree, and /merge-status asked the brain to run
# `git branch --list`, which its own tier denies. Every case here is deterministic: no model, no network.
#
#   bash orchestration/bakeoff/test-merge-status.sh          # M1..M10
set -euo pipefail

S="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
M="${PI_MERGE_STATUS:-$HOME/.pi/agent/scripts/merge-status.py}"
ROOT=/tmp/test-merge-status
for f in "$S" "$M"; do [ -f "$f" ] || { echo "missing $f — run deploy.sh"; exit 1; }; done
rm -rf "$ROOT"; mkdir -p "$ROOT/vault"
R="$ROOT/repo"; git init -q -b main "$R"
cd "$R" && git config user.email t@t && git config user.name t && echo 'x=1' > a.py && git add -A && git commit -qm seed
bash "$S" init --repo "$R" --vault "$ROOT/vault" --part structure --test-cmd 'true' >/dev/null

pass=0; fail=0
ok()   { echo "PASS $1"; pass=$((pass+1)); }
bad()  { echo "FAIL $1"; fail=$((fail+1)); }
chk()  { [ "$1" -eq 0 ] && ok "$2" || bad "$2"; }
DATE=$(date +%F)

# M1 — the dot separates part from agent, so both may contain hyphens.
printf 'DONE: two hyphens in the part name\n' > "$R/.agent/status/$DATE-vault-structure.init-script.md"
out=$(python3 "$M" --repo "$R" 2>&1); rc=$?
chk $rc "M1 hyphenated part parses"
echo "$out" | grep -q '^- init-script:' && [ -f "$ROOT/vault/status/vault-structure.md" ] \
  && ok "M2 part=vault-structure, agent=init-script (not part=vault-structure-init)" \
  || bad "M2 part=vault-structure, agent=init-script (not part=vault-structure-init)"

# M3 — the old hyphen convention must be refused loudly, never silently mis-grouped.
printf 'DONE: legacy name\n' > "$R/.agent/status/$DATE-structure-gitignore.md"
set +e; out=$(python3 "$M" --repo "$R" 2>&1); rc=$?; set -e
[ $rc -eq 4 ] && echo "$out" | grep -q '<part>.<agent>' && ok "M3 legacy <date>-<part>-<agent>.md refused (exit 4)" \
  || bad "M3 legacy <date>-<part>-<agent>.md refused (exit 4) — got rc=$rc: ${out##*$'\n'}"
rm -f "$R/.agent/status/$DATE-structure-gitignore.md"

# M4 — --force rebuilds from the .processed files this script created (it used to refuse them by name).
out=$(python3 "$M" --repo "$R" --force 2>&1); chk $? "M4 --force rebuilds from .processed"
echo "$out" | grep -q 'deltas: 1 · agents: init-script' && ok "M5 --force rollup names the consumed delta" \
  || bad "M5 --force rollup names the consumed delta: $(echo "$out" | grep -o 'deltas:.*')"

# M6 — the integration note has to answer existence, because the brain cannot run git.
grep -q 'integration/structure (MISSING' "$ROOT/vault/status/vault-structure.md" \
  && ok "M6 rollup reports the integration branch as MISSING" \
  || bad "M6 rollup reports the integration branch as MISSING"
# M7 — after the branch exists and carries the agent's work, the note must say so with a tally.
bash "$S" add --repo "$R" --part vault-structure --agent init --role worker >/dev/null
git -C "$R" branch -f integration/structure agent/vault-structure-init
python3 "$M" --repo "$R" --force >/dev/null 2>&1 || true
grep -q 'integration/structure (EXISTS, 1/1' "$ROOT/vault/status/vault-structure.md" \
  && ok "M7 rollup reports EXISTS + merged tally after integrate" \
  || bad "M7 rollup reports EXISTS + merged tally (got: $(grep -o 'integration:.*' "$ROOT/vault/status/vault-structure.md"))"

# M8 — one shared queue: a leaf writing the documented relative path from inside its worktree must land
# in the repo queue that merge-status actually reads.
bash "$S" add --repo "$R" --part structure --agent env --role worker >/dev/null
WT="$R/.worktrees/structure-env"
[ -L "$WT/.agent/status" ] && printf 'DONE: from inside the worktree\n' > "$WT/.agent/status/$DATE-structure.env.md" \
  && [ -f "$R/.agent/status/$DATE-structure.env.md" ] \
  && ok "M8 worktree .agent/status is the shared queue (write from worktree is readable by the rollup)" \
  || bad "M8 worktree .agent/status is the shared queue (write from worktree is readable by the rollup)"
python3 "$M" --repo "$R" 2>&1 | grep -q 'agents: env' && ok "M9 that delta is rolled up" || bad "M9 that delta is rolled up"

# M10 — the exact delta path is printed, so no leaf re-derives the convention by hand.
bash "$S" add --repo "$R" --part structure --agent desc --role worker 2>&1 | grep -q "^DELTA=$R/.agent/status/$DATE-structure.desc.md$" \
  && ok "M10 worktree.sh add prints DELTA= with the dot convention" || bad "M10 worktree.sh add prints DELTA= with the dot convention"

echo "---- merge-status contract: $pass passed, $fail failed"
[ $fail -eq 0 ]
