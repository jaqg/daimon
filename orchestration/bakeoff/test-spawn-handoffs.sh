#!/usr/bin/env bash
# test-spawn-handoffs — the batch spawner's promises, checked with a RECORDING herdr shim: no
# Herdr, no model, no worktrees (A5). The contract is the call sequence + argv, so the assertions
# are on both: tab create once → per row split (from the TAB's first pane, never --current) →
# pane run (dual naming: --name through pi-agents) → agent rename (same name). Plus per-row
# errors that never abort the batch, the R6 mapping printout, R1-style next-command lines, and
# the close verb.
#   bash orchestration/bakeoff/test-spawn-handoffs.sh            # S1..S11
# shellcheck disable=SC2015   # the house `A && ok || bad` idiom: ok()/bad() always return 0, so
# `A && B || C` here IS if-then-else — SC2015's caveat (C when A && !B) cannot occur.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P="${PI_SPAWN_HANDOFFS:-$HERE/../scripts/spawn-handoffs.sh}"
[ -f "$P" ] || { echo "missing $P"; exit 1; }
command -v jq >/dev/null || { echo "jq not found"; exit 1; }

R=/tmp/test-spawn-handoffs
rm -rf "$R"; mkdir -p "$R/bin" "$R/prompts" "$R/status" "$R/repo"
export R_REPO="$R/repo" SHIM_LOG="$R/herdr.log"
: > "$SHIM_LOG"
for w in w1 w2 w3; do echo "# handoff $w" > "$R/prompts/$w.md"; done
# .agent-paths carries the batch-size guardrail (brain, 2026-10-26): batch_size=5, 2 pending
# deltas in status_dir → cap 3 = exactly what manifest-demo.tsv holds.
printf 'status_dir: %s/status\nbatch_size: 5\n' "$R" > "$R/repo/.agent-paths"
touch "$R/status/2026-10-20-old.a.md" "$R/status/2026-10-21-old.b.md"

# --- herdr shim: records every argv, serves the JSON envelopes herdr 0.9.1 really returns
# (tab create shape verified live 2026-10-26). FAIL_SPLIT_MATCH makes one split blow up.
cat > "$R/bin/herdr" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$SHIM_LOG"
case "$1 ${2:-}" in
  "tab create") printf '{"id":"cli:tab:create","result":{"root_pane":{"pane_id":"wX:pROOT"},"tab":{"tab_id":"wX:tPART","label":"demo"}}}\n';;
  "pane split")
    if [ -n "${FAIL_SPLIT_MATCH:-}" ] && [[ "$*" == *"$FAIL_SPLIT_MATCH"* ]]; then echo '{"error":"split refused"}' >&2; exit 1; fi
    n=$(grep -c '^pane split' "$SHIM_LOG")
    printf '{"id":"cli:pane:split","result":{"pane":{"pane_id":"wX:p%d"}}}\n' "$n";;
  "pane run") :;;
  "pane close") :;;
  "agent rename") :;;
  "tab list") printf '{"result":{"tabs":[{"tab_id":"wX:tOTHER","label":"other"},{"tab_id":"wX:tPART","label":"demo"}]}}\n';;
  "tab close") :;;
  *) echo "unexpected herdr call: $*" >&2; exit 64;;
esac
EOF
chmod +x "$R/bin/herdr"

# --- worktree.sh shim: records argv, emits the WORKTREE=/DELTA= contract lines; FAIL_ADD_MATCH
# makes one add refuse (worktree.sh refuses with exit 5).
cat > "$R/bin/worktree.sh" <<'EOF'
#!/usr/bin/env bash
echo "wt $*" >> "$SHIM_LOG"
part="" agent=""
args=("$@")
while [ $# -gt 0 ]; do
  case "$1" in --part) part="$2"; shift 2;; --agent) agent="$2"; shift 2;; *) shift;; esac
done
if [ -n "${FAIL_ADD_MATCH:-}" ] && [[ "${args[*]}" == *"$FAIL_ADD_MATCH"* ]]; then echo "worktree: REFUSED boom" >&2; exit 5; fi
echo "WORKTREE=$R_REPO/.worktrees/$part-$agent"
echo "DELTA=$R_REPO/.agent/status/$(date +%F)-$part.$agent.md"
EOF
chmod +x "$R/bin/worktree.sh"

export HERDR_BIN="$R/bin/herdr" PI_WORKTREE_SH="$R/bin/worktree.sh" HERDR_WORKSPACE_ID="wsTEST"

manifest() { sed "s|\$TEST_ROOT|$R|g" "$HERE/fixtures/$1"; }

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
order_ok() {  # every pattern appears in $LOG_TEXT (the full shim log), in the listed order
  local rest="$LOG_TEXT" p
  for p in "$@"; do
    case "$rest" in *"$p"*) rest="${rest#*"$p"}";; *) return 1;; esac
  done
}

# ---------------------------------------------------------------- S1 exit 0 + KEY= printout
manifest manifest-demo.tsv > "$R/m.tsv"
out=$(cd "$R" && bash "$P" --manifest "$R/m.tsv" 2>&1) || { bad "S1 exit 0 on clean manifest — rc=$?"; out=""; }
echo "$out" | grep -q '^TAB=wX:tPART PANE=wX:pROOT label=demo$' \
  && ok "S1 tab created once, first pane taken from tab create JSON" \
  || bad "S1 tab line — got: $(echo "$out" | head -1)"
echo "$out" | grep -q 'MAP slice=w1 TAB=wX:tPART PANE=wX:p1 NAME=demo-w1 INTERCOM=demo-w1 DELTA=' \
  && echo "$out" | grep -q 'MAP slice=w3 TAB=wX:tPART PANE=wX:p3 NAME=demo-w3 INTERCOM=demo-w3 DELTA=' \
  && ok "S1 mapping printout: slice/tab/pane/name/intercom/delta per row" \
  || bad "S1 mapping printout — got: $(echo "$out" | grep '^MAP' | head -2)"
echo "$out" | grep -q '^SPAWNED=3 FAILED=0 ' && ok "S1 SPAWNED=3 FAILED=0" || bad "S1 summary — $(echo "$out" | tail -1)"
echo "$out" | grep -q '^CLOSED ROOT_PANE=wX:pROOT$' \
  && ok "S1 tab root pane closed after the batch (N panes for N workers, not N+1)" \
  || bad "S1 root-pane close line — got: $(echo "$out" | grep CLOSED)"
echo "$out" | grep -q 'MAP slice=w1 .* NOTE=plan step 3 gate$' \
  && echo "$out" | grep -q 'MAP slice=w2 .* NOTE=$' \
  && ok "S1 optional 5th-column note round-trips into MAP (empty note prints NOTE=)" \
  || bad "S1 note round-trip — $(echo "$out" | grep '^MAP slice=w[12]')"
echo "$out" | grep -q '^batch-gate rows=3 batch_size=5 pending_deltas=2 cap=3$' \
  && ok "S1 batch gate: cap = batch_size − pending deltas, exactly at the line spawns" \
  || bad "S1 batch-gate line — $(echo "$out" | grep batch-gate)"

# ---------------------------------------------------------------- S2 call order + argv (the contract)
log=$(cat "$SHIM_LOG"); LOG_TEXT="$log"
order_ok \
  'tab create --workspace wsTEST --label demo' \
  'pane split wX:pROOT --direction right --cwd '"$R"'/repo/.worktrees/demo-w1 --no-focus' \
  'pane run wX:p1' \
  'agent rename wX:p1 demo-w1' \
  'pane split wX:pROOT --direction right --cwd '"$R"'/repo/.worktrees/demo-w2 --no-focus' \
  'pane run wX:p2' \
  'agent rename wX:p2 demo-w2' \
  'pane split wX:pROOT --direction right --cwd '"$R"'/repo/.worktrees/demo-w3 --no-focus' \
  'pane run wX:p3' \
  'agent rename wX:p3 demo-w3' \
  'pane close wX:pROOT' \
  && ok "S2 tab create → (split from tab pane → run → rename) × rows → close the root pane, no --current anywhere" \
  || bad "S2 call order — log: $(echo "$log" | tr '\n' '|')"
case "$log" in *--current*) bad "S2 '--current' used — forbidden (script runs in brain's pane)";; *) ok "S2 no --current";; esac
[ "$(grep -c '^pane close' "$SHIM_LOG")" -eq 1 ] \
  && ok "S2 root pane closed exactly once per batch" \
  || bad "S2 pane close count: $(grep -c '^pane close' "$SHIM_LOG")"

# ---------------------------------------------------------------- S3 pane run argv (dual naming, @file)
run1=$(grep '^pane run wX:p1 ' "$SHIM_LOG")
case "$run1" in
  *"pi-agents worker --repo $R/repo --wt demo/w1 -- --name demo-w1 @$R/prompts/w1.md"*)
    ok "S3 pane run = pi-agents <role> --repo … --wt part/slice -- --name X @prompt (single %q string)";;
  *) bad "S3 pane run argv: $run1";;
esac
calcs3=$(grep '^pane run wX:p3 ' "$SHIM_LOG")
case "$calcs3" in *"pi-agents calcs "*) ok "S3 manifest role column reaches pi-agents (calcs)";; *) bad "S3 role — $calcs3";; esac

# ---------------------------------------------------------------- S4 re-add is safe: worktree.sh add ran BEFORE the pane command
order_ok 'wt add --repo '"$R"'/repo --part demo --agent w1 --role worker' 'pane run wX:p1' \
  && ok "S4 worktree pre-created via worktree.sh add (re-add idempotent — live-verified 2026-10-26)" \
  || bad "S4 add/run order — log: $(echo "$log" | tr '\n' '|')"

# ---------------------------------------------------------------- S5 R1-style next-command lines
echo "$out" | grep -qF "next-command[operator]: pi-agents worker --repo $R/repo --wt demo/w1" \
  && echo "$out" | grep -qF "next-command[operator]: pi-agents calcs --repo $R/repo --wt demo/w3" \
  && ok "S5 per-row launch lines" || bad "S5 per-row next-command lines"
echo "$out" | grep -qF "next-command[operator]: python3 $HOME/.pi/agent/scripts/merge-status.py --repo $R/repo --part demo" \
  && ok "S5 rollup line (merge-status.py real flags: --repo --part)" || bad "S5 rollup line"

# ---------------------------------------------------------------- S6 bad rows swallowed, batch continues
manifest manifest-bad.tsv > "$R/mbad.tsv"
: > "$SHIM_LOG"
set +e; outb=$(cd "$R" && bash "$P" --manifest "$R/mbad.tsv" 2>&1); rcb=$?; set -e
[ $rcb -eq 1 ] && ok "S6 partial batch exits 1" || bad "S6 exit $rcb, want 1"
echo "$outb" | grep -qE 'ERROR .*/mbad.tsv:[0-9]+: want 4 \(or 5 with note\) tab-separated columns' \
  && ok "S6 3-column row reported and skipped" || bad "S6 col-count error — $(echo "$outb" | grep ERROR | head -2)"
echo "$outb" | grep -qE "ERROR .*/mbad.tsv:[0-9]+: 'demo-Bad-Slice' breaks herdr rename constraint" \
  && ok "S6 uppercase slice refused against [a-z][a-z0-9_-]{0,31}" || bad "S6 name-constraint error — $(echo "$outb" | grep ERROR | head -2)"
echo "$outb" | grep -qE 'ERROR .*/mbad.tsv:[0-9]+: want 4 \(or 5 with note\) tab-separated columns' \
  && ok "S6 6-column row refused (note is the last column, period)" || bad "S6 6-col error — $(echo "$outb" | grep ERROR | head -3)"
echo "$outb" | grep -q 'MAP slice=first ' && echo "$outb" | grep -q 'MAP slice=last ' \
  && echo "$outb" | grep -q '^SPAWNED=2 FAILED=3 ' \
  && ok "S6 good rows on both sides of the bad ones still spawn (SPAWNED=2 FAILED=3)" \
  || bad "S6 survivors — $(echo "$outb" | grep -E '^(MAP|SPAWNED)' | tr '\n' '|')"

# ---------------------------------------------------------------- S7 split failure mid-batch
: > "$SHIM_LOG"
set +e; outs=$(FAIL_SPLIT_MATCH=demo-w2 bash "$P" --manifest "$R/m.tsv" 2>&1); rcs=$?; set -e
[ $rcs -eq 1 ] && echo "$outs" | grep -q 'ERROR .*demo-w2: pane split failed' \
  && echo "$outs" | grep -q 'MAP slice=w1 ' && echo "$outs" | grep -q 'MAP slice=w3 ' \
  && echo "$outs" | grep -q '^SPAWNED=2 FAILED=1 ' \
  && ok "S7 split failure on row 2: rows 1+3 spawn, exit 1" \
  || bad "S7 split failure handling — rc=$rcs: $(echo "$outs" | grep -E '^(ERROR|SPAWNED)' | tr '\n' '|')"

# ---------------------------------------------------------------- S8 worktree failure mid-batch
: > "$SHIM_LOG"
set +e; outa=$(FAIL_ADD_MATCH='--agent w3' bash "$P" --manifest "$R/m.tsv" 2>&1); rca=$?; set -e
[ $rca -eq 1 ] && echo "$outa" | grep -q 'ERROR .*demo-w3: worktree.sh add failed' \
  && echo "$outa" | grep -q '^SPAWNED=2 FAILED=1 ' \
  && ! grep -q 'pane run wX:p3' "$SHIM_LOG" \
  && ok "S8 add failure on row 3: no pane spawned for it, batch continues" \
  || bad "S8 add failure handling — rc=$rca: $(echo "$outa" | grep -E '^(ERROR|SPAWNED)' | tr '\n' '|')"

# ---------------------------------------------------------------- S9 close verb targets the part's tab by label
: > "$SHIM_LOG"
set +e; outc=$(cd "$R" && bash "$P" close --part demo 2>&1); rcc=$?; set -e
[ $rcc -eq 0 ] && grep -q '^tab close wX:tPART$' "$SHIM_LOG" \
  && echo "$outc" | grep -q '^CLOSED TAB=wX:tPART label=demo$' \
  && ok "S9 close --part picks the label match (not tab list's first entry) and closes it" \
  || bad "S9 close — rc=$rcc log: $(cat "$SHIM_LOG") out: $outc"
set +e; bash "$P" close --part nothing >/dev/null 2>&1; rcn=$?; set -e
[ $rcn -eq 2 ] && ok "S9 close with no matching tab exits 2" || bad "S9 close no-match rc=$rcn, want 2"

# ---------------------------------------------------------------- S10 usage guards
printf '# only comments\n' > "$R/mempty.tsv"
set +e; bash "$P" --manifest "$R/mempty.tsv" >/dev/null 2>&1; rce=$?; set -e
[ $rce -eq 1 ] && ok "S10 manifest with 0 rows exits 1 (no tab created)" || bad "S10 empty manifest rc=$rce, want 1"
set +e; bash "$P" >/dev/null 2>&1; rcu=$?; set -e
[ $rcu -eq 2 ] && ok "S10 no --manifest exits 2" || bad "S10 no-manifest rc=$rcu, want 2"

# ---------------------------------------------------------------- S11 batch-size guardrail (refuse BEFORE the tab exists)
: > "$SHIM_LOG"
touch "$R/status/2026-10-22-old.c.md"   # 3 pending → cap 2 < 3 rows
set +e; outg=$(cd "$R" && bash "$P" --manifest "$R/m.tsv" 2>&1); rcg=$?; set -e
[ $rcg -eq 2 ] && echo "$outg" | grep -q 'batch_size=5 minus 3 pending delta(s)' \
  && ! grep -q '^tab create' "$SHIM_LOG" \
  && ok "S11 over cap: exit 2, message names the arithmetic, ZERO herdr calls (no tab)" \
  || bad "S11 over-cap refusal — rc=$rcg log: $(cat "$SHIM_LOG") out: $(echo "$outg" | tail -1)"
rm "$R/status/2026-10-22-old.c.md"
# no batch_size key = old repo: loud NOTE, no cap, spawn proceeds
printf 'status_dir: %s/status\n' "$R" > "$R/repo/.agent-paths"
: > "$SHIM_LOG"
set +e; outn=$(cd "$R" && bash "$P" --manifest "$R/m.tsv" 2>&1); rcn2=$?; set -e
[ $rcn2 -eq 0 ] && echo "$outn" | grep -q "batch-gate: NOTE no batch_size in $R/repo/.agent-paths" \
  && grep -q '^tab create' "$SHIM_LOG" \
  && ok "S11 missing batch_size: NOTE + no cap, batch still spawns" \
  || bad "S11 missing-key path — rc=$rcn2: $(echo "$outn" | grep -E 'batch-gate|SPAWNED')"

# ---------------------------------------------------------------- S12 0 spawned: the empty tab goes too
: > "$SHIM_LOG"
set +e; outz=$(FAIL_ADD_MATCH='--repo' bash "$P" --manifest "$R/m.tsv" 2>&1); rcz=$?; set -e
[ $rcz -eq 1 ] && grep -q '^tab close wX:tPART$' "$SHIM_LOG" \
  && echo "$outz" | grep -q '^CLOSED TAB=wX:tPART label=demo (0 spawned)$' \
  && ! grep -q '^pane close' "$SHIM_LOG" \
  && ok "S12 all rows fail: empty tab closed (not just its root), exit 1" \
  || bad "S12 zero-spawned cleanup — rc=$rcz log: $(cat "$SHIM_LOG") out: $(echo "$outz" | tail -2)"

echo "test-spawn-handoffs: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
