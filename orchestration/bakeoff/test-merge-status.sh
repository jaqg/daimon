#!/usr/bin/env bash
# test-merge-status — the delta *contract*: names, placement, and the integration note.
#
# Written 2026-10-26 after four defects came out of one trial run: the hyphen join could not tell a
# hyphenated part from a hyphenate agent (a delta for part `structure` rolled up as `structure-vault`),
# --force refused the very .processed files the script itself renames, a worker's delta stranded in its
# own worktree because `.agent/status` is per-worktree, and /merge-status asked the brain to run
# `git branch --list`, which its own tier denies. Every case here is deterministic: no model, no network.
#
#   bash orchestration/bakeoff/test-merge-status.sh          # M1..M25
set -euo pipefail

S="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
M="${PI_MERGE_STATUS:-$HOME/.pi/agent/scripts/merge-status.py}"
ROOT=/tmp/test-merge-status
for f in "$S" "$M"; do [ -f "$f" ] || { echo "missing $f — run deploy.sh"; exit 1; }; done
rm -rf "$ROOT"; mkdir -p "$ROOT/vault"
R="$ROOT/repo"; SRC="$ROOT/repo/.agent/status"; git init -q -b main "$R"
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

# M7 — `integrate` PREPARES the integration branch; merging the agent branches is the integrator session's
# job (prepare-only role), so the honest state right after it is EXISTS with nothing merged yet.
bash "$S" add --repo "$R" --part vault-structure --agent init --role worker >/dev/null
# The agent branch needs a commit main does not have, otherwise integrating it is a no-op and the
# rollup correctly reports the part as already landed — which is not the state M12/M14 assert on.
printf 'x = 2  # slice work\n' >> "$R/.worktrees/vault-structure-init/a.py"
git -C "$R/.worktrees/vault-structure-init" commit -qam "vault-structure: slice work"
printf 'DONE: worker output ready to integrate\n' > "$R/.agent/status/$DATE-vault-structure.init.md"
# Re-rollup first: the file on disk was written when this part had no branch at all.
python3 "$M" --repo "$R" --force >/dev/null 2>&1 || true

# M6 — the integration note has to answer existence, because the brain cannot run git. The branch name
# is derived per part (`integration/<part>`), which is what worktree.sh integrate itself creates.
grep -q 'integration/vault-structure (MISSING' "$ROOT/vault/status/vault-structure.md" \
  && ok "M6 rollup reports the integration branch as MISSING" \
  || bad "M6 rollup reports MISSING — got: $(grep -o 'integration:.*' "$ROOT/vault/status/vault-structure.md")"

# M11 — and it prints the command that fixes it, with real paths, so nobody has to remember syntax.
out=$(python3 "$M" --repo "$R" --force --dry-run 2>&1)
echo "$out" | grep -q 'next-command\[brain\]: bash .*worktree.sh integrate --repo .*/repo --part vault-structure' \
  && ok "M11 next-command names worktree.sh integrate with real paths" \
  || bad "M11 next-command names integrate — got: $(echo "$out" | grep -o 'next-command.*' | head -1)"

bash "$S" integrate --repo "$R" --part vault-structure >/dev/null 2>&1 || true
python3 "$M" --repo "$R" --force >/dev/null 2>&1 || true
grep -q 'integration/vault-structure (EXISTS, 0/1' "$ROOT/vault/status/vault-structure.md" \
  && ok "M7 integrate prepares the branch without merging (0/1, integrator's job)" \
  || bad "M7 integrate prepares the branch without merging — got: $(grep -o 'integration:.*' "$ROOT/vault/status/vault-structure.md")"
out=$(python3 "$M" --repo "$R" --force --dry-run 2>&1)
echo "$out" | grep -q 'not yet in it: agent/vault-structure-init' \
  && ok "M13 unmerged branches are named, not counted vaguely" || bad "M13 unmerged branches are named"

# Now let the integrator do its merge, and check the rollup moves to verify-then-land.
git -C "$R/.worktrees/integrate-vault-structure" merge --no-ff -q agent/vault-structure-init -m "integrate vault-structure"
python3 "$M" --repo "$R" --force >/dev/null 2>&1 || true
out=$(python3 "$M" --repo "$R" --force --dry-run 2>&1)
grep -q 'integration/vault-structure (EXISTS, 1/1' "$ROOT/vault/status/vault-structure.md" \
  && ok "M7b tally reaches 1/1 after the integrator merges" \
  || bad "M7b tally after merge — got: $(grep -o 'integration:.*' "$ROOT/vault/status/vault-structure.md")"
echo "$out" | grep -q 'merge --no-ff integration/vault-structure' \
  && ok "M12 landing command targets the part's integration branch" \
  || bad "M12 landing command — got: $(echo "$out" | grep -o 'next-command.*' | head -2 | tr '\n' '|')"
echo "$out" | grep -q 'worktree.sh lab --repo .*/repo --part vault-structure' \
  && ok "M14 verify-before-landing prints the lab command" \
  || bad "M14 lab command printed — got: $(echo "$out" | grep -o 'next-command.*' | head -3 | tr '\n' '|')"
grep -q 'note\[drift\]' <<<"$out" \
  && ok "M13b contract/part mismatch is reported as drift, not applied blindly" \
  || bad "M13b contract/part mismatch reported as drift"

# M21 — the prune line has to be pasteable. `prune` dies without --part, and this command exists precisely
# so nobody has to remember that.
echo "$out" | grep -q 'prune --repo .*/repo --part vault-structure' \
  && ok "M21 prune command carries --part" || bad "M21 prune command carries --part"

# M22/M23 — before landing, prune cleans the slices but must REFUSE to touch the integration worktree or
# the lab: the verdict is still open, and deleting the thing under review is how you lose an integration.
bash "$S" lab --repo "$R" --part vault-structure >/dev/null 2>&1 || true
po=$(bash "$S" prune --repo "$R" --part vault-structure 2>&1)
[ ! -e "$R/.worktrees/vault-structure-init" ] && grep -q 'dropped vault-structure-init' <<<"$po" \
  && ok "M22 prune removes a slice worktree once it is inside the integration branch" \
  || bad "M22 prune removes merged slice worktree" "$(tail -2 <<<"$po")"
grep -q 'integrate-vault-structure kept' <<<"$po" && grep -q '.labs/vault-structure kept' <<<"$po" \
  && [ -e "$R/.worktrees/integrate-vault-structure" ] && [ -e "$R/.labs/vault-structure" ] \
  && ok "M23 prune keeps integration worktree + lab while the part is not in main" \
  || bad "M23 prune keeps unlanded workspaces" "$(tail -2 <<<"$po")"

# M15 — landing changes the answer: the part is in main, so stop telling people to merge it.
git -C "$R" merge --no-ff -q integration/vault-structure -m "land vault-structure" 2>/dev/null || true
out=$(python3 "$M" --repo "$R" --force --dry-run 2>&1)
echo "$out" | grep -q 'is already in main' \
  && ok "M15 landed part reports prune, not merge" \
  || bad "M15 landed part reports prune — got: $(echo "$out" | grep -o 'next-command.*' | head -1)"

# M16 — the bug that froze the brain. A plain run with a fully consumed queue must STILL report the part:
# the old version returned early on "0 unprocessed deltas", so the file kept saying 0/2 after the
# integrator merged both slices, and the brain recommended work that was already finished.
rc=0; python3 "$M" --repo "$R" >/tmp/m16a 2>&1 || rc=$?
[ $rc -eq 0 ] && grep -q 'is already in main' /tmp/m16a \
  && ok "M16a consumed queue still reports live git state (wrote: exit 0)" \
  || bad "M16a consumed queue reports live state" "rc=$rc $(tail -1 /tmp/m16a)"
rc=0; python3 "$M" --repo "$R" >/tmp/m16b 2>&1 || rc=$?
[ $rc -eq 3 ] && grep -q 'note: rollup already matches git state' /tmp/m16b \
  && ok "M16b second run is a no-op (exit 3 = unchanged), commands still printed" \
  || bad "M16b unchanged run exits 3" "rc=$rc $(tail -1 /tmp/m16b)"

# M24/M25 — after landing the whole scaffold is dead weight: integration worktree, its branch, the lab.
po=$(bash "$S" prune --repo "$R" --part vault-structure 2>&1)
grep -q 'dropped integrate-vault-structure' <<<"$po" && [ ! -e "$R/.worktrees/integrate-vault-structure" ] \
  && ! git -C "$R" show-ref --verify --quiet refs/heads/integration/vault-structure \
  && ok "M24 prune removes the integration worktree and branch after landing" \
  || bad "M24 prune removes integration scaffold after landing" "$(tail -2 <<<"$po")"
grep -q 'dropped lab .labs/vault-structure' <<<"$po" && [ ! -e "$R/.labs/vault-structure" ] \
  && ok "M25 prune removes the checker lab once the part landed" \
  || bad "M25 prune removes the lab" "$(tail -2 <<<"$po")"

# M26 — a pruned part must not be reported as "integration branch MISSING, go integrate". The branch is
# gone because the work is in main; telling the brain to recreate it would resurrect a finished part.
rc=0; python3 "$M" --repo "$R" --part vault-structure >/tmp/m26 2>&1 || rc=$?
grep -q 'landed and pruned, or never started; main is the record' /tmp/m26 \
  && ! grep -q 'next-command' /tmp/m26 \
  && ok "M26 pruned part reports the finished state and prints no commands" \
  || bad "M26 pruned part is not re-suggested for integration" "rc=$rc $(grep -o 'next-command.*' /tmp/m26 | head -1)"

# M17 — a git-side change alone rewrites the file, no --force, and the exit code says so.
git -C "$R" branch -q agent/vault-structure-late c60e16e 2>/dev/null || git -C "$R" branch -q agent/vault-structure-late main
rc=0; python3 "$M" --repo "$R" >/tmp/m17 2>&1 || rc=$?
grep -q 'agent/vault-structure-late' "$ROOT/vault/status/vault-structure.md" && [ $rc -eq 0 ] \
  && ok "M17 new branch alone refreshes the rollup (exit 0)" \
  || bad "M17 git change alone refreshes the rollup" "rc=$rc $(grep branches "$ROOT/vault/status/vault-structure.md" | head -1)"

# M18 — a part with zero delivery records is still reportable, and says it has none.
rc=0; python3 "$M" --repo "$R" --part orphan >/tmp/m18 2>&1 || rc=$?
grep -q 'no delivery records for this part yet' /tmp/m18 \
  && ok "M18 --part with no deltas still answers from git" || bad "M18 --part with no deltas answers" "rc=$rc $(tail -1 /tmp/m18)"

# M19 — a re-delivered slice counts once. The queue is append-only, so a second delivery of the same
# (part, agent, date) sits next to the consumed twin: the fresh text must win and the twin must drop out,
# or the tally would report the slice as done twice. Uses `init-script`, which already has a .processed
# twin here; an earlier draft of this case wrote `init`, a *different* agent, and so proved nothing.
printf 'DONE: second delivery of the same slice\n' > "$SRC/$DATE-vault-structure.init-script.md"
out=$(python3 "$M" --repo "$R" --part vault-structure --dry-run 2>&1)
n=$(grep -c '^- init-script:' <<<"$out")
[ "$n" -eq 1 ] && grep -q 'second delivery of the same slice' <<<"$out" \
  && ! grep -q 'two hyphens in the part name' <<<"$out" \
  && ok "M19 re-delivery replaces its consumed twin instead of doubling the tally" \
  || bad "M19 re-delivery counted once" "n=$n fresh-text=$(grep -c 'second delivery' <<<"$out")"

# M20 — asking about one part must not consume another part's deltas (data loss class).
printf 'DONE: other part ready\n' > "$SRC/$DATE-other.again.md"
python3 "$M" --repo "$R" --part vault-structure >/dev/null 2>&1
[ -f "$SRC/$DATE-other.again.md" ] && ok "M20 --part consumes only that part's queue entries" \
  || bad "M20 --part consumed an unrelated delta"

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
