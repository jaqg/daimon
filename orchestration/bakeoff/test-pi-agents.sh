#!/usr/bin/env bash
# test-pi-agents — the launcher's promises, checked without starting a model.
#
# Written 2026-10-26 after `/merge-status` started printing commands for José to paste. A printed
# command that does not do what it says is worse than none, so every assertion here is against --dry
# output: the launcher's decision, not the model's behaviour.
#   bash orchestration/bakeoff/test-pi-agents.sh            # P1..P9
set -euo pipefail
P="${PI_AGENTS_BIN:-$HOME/.pi/agent/scripts/pi-agents.sh}"
[ -f "$P" ] || { echo "missing $P — run deploy.sh"; exit 1; }
R=/tmp/test-pi-agents
rm -rf "$R"; mkdir -p "$R/repo"
cd "$R/repo" && git init -q -b main && git config user.email t@t && git config user.name t && echo x > a.py && git add -A && git commit -qm seed
bash "${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}" init --repo "$R/repo" --vault "$R/vault" --part demo --test-cmd 'true' >/dev/null

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }

# P1 — --repo without --wt has to POSITION the session. It used to be ignored, so the printed
# `pi-agents integrator --repo <worktree>` launched in the caller's directory and inherited the parent
# checkout's role.
mkdir -p "$R/repo/wt"; echo integrator > "$R/repo/wt/.pi-role"
out=$(cd "$R" && bash "$P" integrator --repo "$R/repo/wt" --dry 2>&1)
echo "$out" | grep -q "dir=$R/repo/wt" && ok "P1 --repo positions the pane (dir=<repo>)" \
  || bad "P1 --repo positions the pane — got: $(echo "$out" | grep -o 'dir=[^ ]*')"

# P2 — a role that disagrees with the directory gate is refused, not silently mixed.
echo brain > "$R/repo/wt/.pi-role"
set +e; out=$(cd "$R" && bash "$P" integrator --repo "$R/repo/wt" --dry 2>&1); rc=$?; set -e
[ $rc -ne 0 ] && echo "$out" | grep -q 'mixed tier' && ok "P2 mixed tier refused (exit $rc)" || bad "P2 mixed tier refused — rc=$rc: ${out:0:90}"

# P3 — a workspace that does not exist must name the command that creates it, and must not interpolate
# the missing path as though it were the project root.
set +e; out=$(cd "$R" && bash "$P" integrator --repo "$R/repo/.worktrees/integrate-nothing" --dry 2>&1); rc=$?; set -e
[ $rc -ne 0 ] && echo "$out" | grep -q 'integrate --repo <project-root>' && ok "P3 missing workspace prints the creating command" \
  || bad "P3 missing workspace prints the creating command — ${out:0:120}"

# P4 — leaf roles get a real worktree, a role file, and the DELTA path in the documented dot convention.
out=$(cd "$R" && bash "$P" worker --repo "$R/repo" --wt demo/desc --dry 2>&1)
echo "$out" | grep -q "DELTA=$R/repo/.agent/status/$(date +%F)-demo.desc.md" \
  && ok "P4 --wt prints DELTA=<date>-<part>.<agent>.md" || bad "P4 --wt prints DELTA — $(echo "$out" | grep -o 'DELTA=.*' | head -1)"
[ -f "$R/repo/.worktrees/demo-desc/.pi-role" ] && [ "$(cat "$R/repo/.worktrees/demo-desc/.pi-role")" = worker ] \
  && ok "P5 worktree carries its own role" || bad "P5 worktree carries its own role"
[ -L "$R/repo/.worktrees/demo-desc/.agent/status" ] \
  && ok "P6 worktree shares the repo status queue" || bad "P6 worktree shares the repo status queue"

# P7 — every role the launcher can offer must resolve to a tier the gate knows, or the pane opens
# ungated. (CONTEXT.md #19: three definitions have no PROFILES entry — this asserts the *known* set.)
for role in brain worker calcs scout verifier integrator; do
  echo "$role" > "$R/repo/.pi-role"
  o=$(cd "$R/repo" && bash "$P" "$role" --dry 2>&1)
  echo "$o" | grep -q "role=$role" && echo "$o" | grep -q 'model=opencode-go/' || { bad "P7 $role launches with a pin"; continue; }
done
ok "P7 six tiers launch pinned"

# P8 — the verify step has to be launchable, not just recommendable: `worktree.sh lab` makes a detached
# cross-lab checkout, tags it `verifier`, and the printed pane command must actually resolve to that tier.
LABOUT=$(bash "${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}" lab --repo "$R/repo" --part demo 2>&1)
LABP=$(echo "$LABOUT" | sed -n 's/^LAB=//p')
[ -n "$LABP" ] && [ -f "$LABP/.pi-role" ] && [ "$(cat "$LABP/.pi-role")" = verifier ] \
  && ok "P8 lab creates a detached checker workspace tagged verifier" || bad "P8 lab workspace — ${LABOUT:0:120}"
o=$(bash "$P" verifier --repo "$LABP" --dry 2>&1)
echo "$o" | grep -q "role=verifier" && echo "$o" | grep -q "dir=$LABP" \
  && ok "P9 the printed verifier command opens the lab as its own tier" \
  || bad "P9 verifier command works — ${o:0:120}"

# P10 — re-verification is a normal second pass: `lab` on an existing lab reuses it and says so, instead of
# refusing (which pushed people to delete a workspace that may still hold an open session).
again=$(bash "${PI_WORKTREE_SH:-$HOME/.pi/agent/scripts/worktree.sh}" lab --repo "$R/repo" --part demo 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q 'LAB=.* (existing)' <<<"$again" && grep -q 'already checked out' <<<"$again" \
  && ok "P10 lab reuses an existing workspace and reports the ref match" \
  || bad "P10 lab reuse" "${again:0:120}"

# P11 — `operator` is the one launchable role that is SUPPOSED to open ungated: it is defined by the
# absence of a `.pi-role` (role-gate fails open ⇒ full tools), and it is the tier every
# `next-command[operator]:` line names. The launcher must call that "by design", not the generic
# "gate is INACTIVE" warning a leaf pane would deserve.
rm -f "$R/repo/.pi-role"
o=$(cd "$R/repo" && bash "$P" operator --dry 2>&1)
{ echo "$o" | grep -q 'role=operator' && echo "$o" | grep -q 'gate=none' \
  && echo "$o" | grep -q 'no .pi-role anywhere, which is the POINT' \
  && echo "$o" | grep -q 'model=opencode-go/'; } \
  && ok "P11 operator launches ungated, pinned, and says why" || bad "P11 operator launch" "${o:0:140}"

# P12 — and it refuses --claim. Claiming `operator` writes a role name no profile knows: the gate stays
# off (harmless) but a later `pi-agents worker` in that directory is refused as a mixed tier, which reads
# like a config bug and is really a stray file from three weeks ago.
set +e
o=$(cd "$R/repo" && bash "$P" operator --claim --dry 2>&1); rc=$?
set -e
[ $rc -ne 0 ] && grep -q 'needs no --claim' <<<"$o" && [ ! -f "$R/repo/.pi-role" ] \
  && ok "P12 operator refuses --claim and writes nothing" || bad "P12 operator --claim" "${o:0:140}"

# P13 — the mismatch hint for `operator` must not offer --claim (the launcher refuses it) and must not say
# "launch brain instead". José hit exactly this in 10-Projects/IQARIS-extension/, a directory the documented
# rhythm claims for the brain: the refusal was correct, the advice in it was unusable. It must print the
# path that has no tag, and warn that deleting the tag would strip the gate from a live pane.
set +e
echo brain > "$R/repo/wt/.pi-role"          # deterministic: the seat the daily rhythm claims for the brain
rm -f "$R/repo/.pi-role"                    # its parent stays unclaimed
o=$(cd "$R/repo/wt" && bash "$P" operator --dry 2>&1); rc=$?
set -e
{ [ $rc -ne 0 ] && echo "$o" | grep -q 'operator has no tag' \
  && echo "$o" | grep -qF "cd $R/repo && pi-agents operator" \
  && ! echo "$o" | grep -q -- '--claim to overwrite' \
  && echo "$o" | grep -q 'every tool call'; } \
  && ok "P13 operator hint gives the unclaimed seat + live-pane warning (exit $rc)" \
  || bad "P13 operator hint" "${o:0:200}"

# P14 — and for a real role the hint keeps --claim but names its blast radius.
set +e
o=$(cd "$R/repo/wt" && bash "$P" worker --dry 2>&1); rc=$?
set -e
[ $rc -ne 0 ] && echo "$o" | grep -q 'Caveat on --claim' && echo "$o" | grep -q 'LIVE brain pane' \
  && ok "P14 leaf mismatch hint warns --claim re-gates live panes" \
  || bad "P14 leaf mismatch hint" "${o:0:160}"

# P15 — the launcher must forward the agent file's `thinking:` as a flag. pi has no such frontmatter field,
# so if this passthrough breaks the pin is silently dead and every tier falls back to
# settings.json defaultThinkingLevel — which is exactly how all 7 tiers ended up on `high` in the first
# place without anyone deciding it.
o=$(cd "$R/repo" && bash "$P" worker --dry 2>&1)
# (the dry line is printed with `printf %q`, which double-spaces arguments, so a literal
# "--thinking medium" substring can never match — a test that can only fail is not a test.)
{ echo "$o" | grep -q 'thinking=medium' && echo "$o" | grep -qE -- '--thinking[[:space:]]+medium'; } \
  && ok "P15 worker.md thinking pin reaches the pi command line" || bad "P15 thinking passthrough" "${o:0:200}"

# P16 — and a role with NO thinking line says so out loud instead of pretending it decided.
mkdir -p "$R/defs"
sed '/^thinking:/d' "$HOME/.pi/agent/agents/worker.md" > "$R/defs/naive.md"
sed -i 's/^name:.*/name: naive/; s/^model:.*/model: opencode-go\/mimo-v2.6-flash/' "$R/defs/naive.md"
o=$(cd "$R/repo" && PI_AGENTS_DIR="$R/defs" bash "$P" naive --dry 2>&1)
{ echo "$o" | grep -q 'thinking=settings-default' && ! echo "$o" | grep -q -- '--thinking'; } \
  && ok "P16 unpinned role inherits + reports the global default" || bad "P16 unpinned role" "${o:0:200}"

echo "---- pi-agents launcher: $pass passed, $fail failed"
[ $fail -eq 0 ]
