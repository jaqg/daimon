#!/usr/bin/env bash
# test-worktree-base — D22: `add` cuts slice branches from a REF (integration/<part> else main),
# never from the main worktree's checked-out HEAD. The main worktree may sit on any branch with
# dirty WIP; inheriting it drifted bases off integration/<part> and produced add/add conflicts at
# integrate (2 observed in maehtro). Every case asserts the new branch's TIP equals the expected
# ref's tip — a slice branch starts with no commits of its own, so tip equality IS base equality.
#
#   bash orchestration/bakeoff/test-worktree-base.sh     # B1..B5
set -euo pipefail

S="${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}"
ROOT=/tmp/test-worktree-base
[ -f "$S" ] || { echo "missing $S — run deploy.sh"; exit 1; }
rm -rf "$ROOT"; mkdir -p "$ROOT/vault"
R="$ROOT/repo"; git init -q -b main "$R"
cd "$R" && git config user.email t@t && git config user.name t && echo 'x=1' > a.py && git add -A && git commit -qm seed

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1${2:+ — $2}"; fail=$((fail+1)); }

# The three refs the cases discriminate: main (seed), integration/demo (its own commit), and the
# branch the MAIN WORKTREE sits on (foreign tip + dirty file). All three tips must differ or the
# assertions cannot tell which one `add` picked.
git -C "$R" checkout -q -b integration/demo main
echo 'i=1' > "$R/integ.py" && git -C "$R" add integ.py && git -C "$R" commit -qm "integration/demo: part work"
git -C "$R" checkout -q -b feat/wip main
echo 'wip=1' >> "$R/a.py"                 # dirty, uncommitted — must stay invisible to add
echo 'y=2' > "$R/b.py" && git -C "$R" add b.py && git -C "$R" commit -qm "feat/wip: foreign tip"
# main worktree now ON feat/wip with a.py dirty — exactly the state D22 says add must not see
TIP_MAIN="$(git -C "$R" rev-parse main)"
TIP_INTEG="$(git -C "$R" rev-parse integration/demo)"
TIP_WIP="$(git -C "$R" rev-parse feat/wip)"
[ "$TIP_MAIN" != "$TIP_INTEG" ] && [ "$TIP_MAIN" != "$TIP_WIP" ] && [ "$TIP_INTEG" != "$TIP_WIP" ] \
  && ok "B0 fixture: three distinct tips" || bad "B0 fixture" "tips not distinct"

bash "$S" init --repo "$R" --vault "$ROOT/vault" --part demo --test-cmd 'true' >/dev/null

# B1 — integration/<part> exists → the slice branch cuts from it, despite HEAD being feat/wip.
bash "$S" add --repo "$R" --part demo --agent alpha >/dev/null
T="$(git -C "$R" rev-parse agent/demo-alpha)"
[ "$T" = "$TIP_INTEG" ] \
  && ok "B1 add cuts from integration/<part> when it exists" \
  || bad "B1 base" "got $T want $TIP_INTEG (HEAD was feat/wip)"

# B2 — and the main worktree's dirty WIP is untouched: still on feat/wip, a.py still dirty.
[ "$(git -C "$R" rev-parse --abbrev-ref HEAD)" = "feat/wip" ] \
  && ok "B2 main worktree still on its own branch after add" \
  || bad "B2 HEAD" "$(git -C "$R" rev-parse --abbrev-ref HEAD)"
[ -n "$(git -C "$R" status --porcelain -- a.py)" ] \
  && ok "B2 dirty WIP still dirty (invisible to add)" \
  || bad "B2 WIP" "a.py no longer dirty"

# B3 — no integration/<part> ref → falls back to main, still not HEAD.
git -C "$R" branch -D integration/demo >/dev/null
bash "$S" add --repo "$R" --part demo --agent beta >/dev/null
T="$(git -C "$R" rev-parse agent/demo-beta)"
[ "$T" = "$TIP_MAIN" ] \
  && ok "B3 add falls back to main when no integration ref" \
  || bad "B3 base" "got $T want $TIP_MAIN (HEAD was feat/wip)"

# B4 — an explicit --base overrides the resolver (contract: user-supplied base wins).
bash "$S" add --repo "$R" --part demo --agent gamma --base feat/wip >/dev/null
T="$(git -C "$R" rev-parse agent/demo-gamma)"
[ "$T" = "$TIP_WIP" ] \
  && ok "B4 explicit --base overrides resolver" \
  || bad "B4 base" "got $T want $TIP_WIP"

# B5 — `integrate` creates integration/demo from main (its ref cannot exist at create time, so
# resolve_base returns main) — the pre-D22 default, now from the shared resolver.
out="$(bash "$S" integrate --repo "$R" --part demo)"
T="$(git -C "$R" rev-parse integration/demo)"
[ "$T" = "$TIP_MAIN" ] \
  && ok "B5 integrate creates its branch from main" \
  || bad "B5 base" "got $T want $TIP_MAIN"

echo "---- worktree base contract: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
