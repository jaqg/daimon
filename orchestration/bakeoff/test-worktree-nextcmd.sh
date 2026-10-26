#!/usr/bin/env bash
# test-worktree-nextcmd — R1: `add`/`integrate` EMIT the next-command lines, so nobody (brain or
# José) ever composes a launch/rollup command from memory (rule 3c). Every assertion is against
# stdout of the real script; the rollup line is additionally EXECUTED against the repo's own
# merge-status.py, because a line whose flags argparse rejects is worse than no line at all — the
# brief and the brain's contract literally disagreed on whether `--part` exists.
#
#   bash orchestration/bakeoff/test-worktree-nextcmd.sh     # X1..X9
# shellcheck disable=SC2015   # the ok/bad `cond && ok || bad` idiom is every bakeoff test's pattern
set -euo pipefail

S="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
M="${PI_MERGE_STATUS:-$HOME/.pi/agent/scripts/merge-status.py}"
ROOT=/tmp/test-worktree-nextcmd
for f in "$S" "$M"; do [ -f "$f" ] || { echo "missing $f — run deploy.sh"; exit 1; }; done
rm -rf "$ROOT"; mkdir -p "$ROOT/vault"
R="$ROOT/repo"; git init -q -b main "$R"
cd "$R" && git config user.email t@t && git config user.name t && echo 'x=1' > a.py && git add -A && git commit -qm seed
bash "$S" init --repo "$R" --vault "$ROOT/vault" --part demo --test-cmd 'true' >/dev/null

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1${2:+ — $2}"; fail=$((fail+1)); }

# X1/X2 — `add` tail: the per-row launch line carries role, repo, and wt part/slice as passed.
out=$(bash "$S" add --repo "$R" --part demo --agent desc --role worker)
# The slice must hold a commit main does not have: an agent branch sitting AT main makes the part
# report as landed, and X8's integrator line would never be printed (same trap as test-merge-status M7).
printf 'x = 2  # slice work\n' >> "$R/.worktrees/demo-desc/a.py"
git -C "$R/.worktrees/demo-desc" commit -qam "demo: slice work"
echo "$out" | grep -qx "next-command\[operator\]: pi-agents worker --repo $R --wt demo/desc" \
  && ok "X1 add emits the pi-agents launch line for its own row" \
  || bad "X1 launch line" "$(echo "$out" | grep -o 'next-command.*' | tail -1)"

# X3 — and the rollup line invokes merge-status with flags its argparse really has.
echo "$out" | grep -qx "next-command\[operator\]: python3 \$HOME/.pi/agent/scripts/merge-status.py --repo $R --part demo" \
  && ok "X3 add emits the post-completion rollup line" || bad "X3 rollup line" "$(echo "$out" | grep -o 'next-command.*' | tail -1)"

# X4 — the emitted lines come AFTER DELTA=, so a consumer reading the tail sees state then next step.
echo "$out" | awk '/^DELTA=/{d=NR} /^next-command/{n=NR} END{exit !(d && n && d<n)}' \
  && ok "X4 next-command lines follow DELTA= in the tail" || bad "X4 tail ordering"

# X5 — the rollup line must be RUNNABLE: execute it (repo copy of merge-status.py swapped in for the
# deployed path) and require success — this is the flag-truth assertion, not a string match.
printf 'DONE: slice desc ready\n' > "$R/.agent/status/$(date +%F)-demo.desc.md"
cmd=$(echo "$out" | sed -n 's/^next-command\[operator\]: //p' | grep '^python3 ' | tail -1)
cmd="${cmd/\$HOME\/.pi\/agent\/scripts\/merge-status.py/$M}"
rc=0; eval "$cmd" >/tmp/x5 2>&1 || rc=$?
[ "$rc" -eq 0 ] && grep -q 'demo' /tmp/x5 \
  && ok "X5 emitted rollup line runs against merge-status.py argparse (rc=0)" \
  || bad "X5 rollup line not runnable" "rc=$rc $(tail -2 /tmp/x5 | tr '\n' '|')"

# X6 — a non-worker role emits its own role, not a hardcoded `worker`.
out=$(bash "$S" add --repo "$R" --part demo --agent spectra --role calcs 2>&1)
echo "$out" | grep -qx "next-command\[operator\]: pi-agents calcs --repo $R --wt demo/spectra" \
  && ok "X6 launch line reflects --role" || bad "X6 role in launch line" "$(echo "$out" | grep -o 'next-command.*pi-agents.*' | head -1)"

# X7/X8 — `integrate` emits the integrator launch line, BYTE-IDENTICAL to what merge-status.py prints
# in its own rollup (the two emitters must not drift).
out=$(bash "$S" integrate --repo "$R" --part demo 2>&1)
line="next-command[operator]: pi-agents integrator --repo $R/.worktrees/integrate-demo"
echo "$out" | grep -qxF "$line" && ok "X7 integrate emits the integrator launch line" \
  || bad "X7 integrator line" "$(echo "$out" | grep -o 'next-command.*' | tail -1)"
ms=$(python3 "$M" --repo "$R" --part demo --dry-run 2>&1 || true)
echo "$ms" | grep -qxF "$line" \
  && ok "X8 integrate's line is byte-identical to merge-status.py's rollup line" \
  || bad "X8 emitter drift" "merge-status says: $(echo "$ms" | grep -o 'pi-agents integrator.*' | head -1)"

# X9 — integration worktrees are not the only consumer: `lab` already emitted its line; make sure the
# new `add` lines did not displace it (the verifier flow depends on it).
lab=$(bash "$S" lab --repo "$R" --part demo 2>&1)
echo "$lab" | grep -q '^next-command\[operator\]: pi-agents verifier --repo ' \
  && ok "X9 lab verifier line still emitted" || bad "X9 lab line missing"

echo "---- worktree next-command emitter: $pass passed, $fail failed"
[ $fail -eq 0 ]
