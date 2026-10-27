#!/usr/bin/env bash
# test-role-gate — the gate-brain slice's contract (plan spawn-handoffs step 3, R2+R4):
#   1. role-gate.ts lets the brain run `spawn-handoffs.sh` — the SPAWN? execution route — and ONLY
#      it: every other shell command stays denied, and shell composition around an allowlisted
#      script stays refused (SHELL_SMUGGLE_RE), so the allowlist is never an escape hatch.
#   2. brain.md carries the SPAWN? hard rule (stop under "### Open for José", one confirmation per
#      batch) with rules 3c/3d intact, and 3c has the emitter-copy sentence.
#   3. evals/evals.json holds the one SPAWN? judgment entry.
# The assertions run the REAL gate: the driver imports orchestration/extensions/role-gate.ts and
# drives its `tool_call` handler against a temp dir with `.pi-role: brain` — not a re-implementation
# of the regex logic, which could drift from the extension.
#
#   bash orchestration/bakeoff/test-role-gate.sh     # G1..G6 allow, G7..G13 deny, D1..D5 docs
# shellcheck disable=SC2015   # the ok/bad `cond && ok || bad` idiom is every bakeoff test's pattern
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RG="$ROOT/orchestration/extensions/role-gate.ts"
BRAIN="$ROOT/orchestration/agents/brain.md"
EVALS="$ROOT/evals/evals.json"
for f in "$RG" "$BRAIN" "$EVALS"; do [ -f "$f" ] || { echo "missing $f"; exit 1; }; done

TMP="$(mktemp -d /tmp/test-role-gate.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
printf 'brain\n' > "$TMP/.pi-role"

pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1${2:+ — $2}"; fail=$((fail+1)); }

# Driver: import the extension (type-strip), fake just enough ExtensionAPI to capture its handlers,
# feed each command from argv through the real `tool_call` gate, print one verdict per line.
cat > "$TMP/driver.mjs" <<'EOF'
const handlers = {};
const pi = {
	on: (name, cb) => { handlers[name] = cb; },
	registerCommand: () => {},
};
const { default: ext } = await import(process.env.ROLE_GATE);
ext(pi);
if (typeof handlers.tool_call !== "function") {
	console.error("driver: role-gate.ts registered no tool_call handler");
	process.exit(2);
}
for (const cmd of process.argv.slice(2)) {
	const r = await handlers.tool_call(
		{ toolName: "bash", input: { command: cmd } },
		{ cwd: process.env.GATE_CWD, ui: { notify() {} } },
	);
	console.log(r ? `BLOCK\t${String(r.reason ?? "")}` : "ALLOW\t");
}
EOF

run_gate() {   # run_gate <cmd...> → "<VERDICT>\t<reason>" per invocation
	ROLE_GATE="$RG" GATE_CWD="$TMP" NODE_NO_WARNINGS=1 \
	  node --experimental-strip-types "$TMP/driver.mjs" "$@"
}

S=~/.pi/agent/scripts   # the deployed path form the gate matches on (no expansion in the command)

# label = "<expected> <name>", then the command — `|`-separated so commands keep their own pipes.
CASES=(
  "allow|G1 spawn-handoffs bare|$S/spawn-handoffs.sh --manifest $S/m.tsv --part spawn-handoffs"
  "allow|G2 spawn-handoffs \$HOME form|bash \$HOME/.pi/agent/scripts/spawn-handoffs.sh --manifest /tmp/m.tsv --part p"
  "allow|G3 spawn-handoffs absolute path|bash /home/someone/.pi/agent/scripts/spawn-handoffs.sh --manifest /tmp/m.tsv"
  "allow|G4 worktree.sh add|bash $S/worktree.sh add --repo /r --part p --agent a"
  "allow|G5 merge-status.py|python3 $S/merge-status.py --repo /r --part p"
  "allow|G6 triage.sh|bash $S/triage.sh"
  "deny|G7 plain shell|cat /etc/passwd"
  "smug|G8 semicolon composition|$S/spawn-handoffs.sh --manifest m.tsv; cat /etc/passwd"
  "smug|G9 pipe composition|bash $S/spawn-handoffs.sh --manifest m.tsv | tee /tmp/out"
  "smug|G10 substitution composition|bash $S/spawn-handoffs.sh --manifest \$(cat m.tsv)"
  "deny|G11 typosquat spawn-handoffs-extra.sh|bash $S/spawn-handoffs-extra.sh"
  "deny|G12 suffix spawn-handoffs.sh.bak|bash $S/spawn-handoffs.sh.bak"
  "deny|G13 typed herdr command|herdr pane split abc123 --direction right"
)

# One driver run for all cases (one node process, one extension import). Strip the first two
# `|`-separated fields (expected, name); whatever follows is the command verbatim — commands keep
# their own `|` (G9).
cmds=()
for c in "${CASES[@]}"; do r="${c#*|}"; cmds+=("${r#*|}"); done
mapfile -t verdicts < <(run_gate "${cmds[@]}")

i=0
for c in "${CASES[@]}"; do
  want="${c%%|*}"; rest="${c#*|}"; name="${rest%%|*}"   # rest still holds name|command
  line="${verdicts[$i]:-MISSING}"
  got="${line%%$'\t'*}"; reason="${line#*$'\t'}"
  if [ "$got" = MISSING ]; then
    bad "$name" "driver produced no verdict for: ${cmds[$i]}"
  else
    case "$want" in
      allow) [ "$got" = ALLOW ] && ok "$name allowed" || bad "$name" "expected ALLOW, got $got" ;;
      smug)  [ "$got" = BLOCK ] && case "$reason" in
               *"allowlisted script may be run"*) ok "$name refused by smuggle guard" ;;
               *) bad "$name smuggle guard" "reason: $reason" ;;
             esac || bad "$name" "expected BLOCK, got ALLOW" ;;
      deny)  [ "$got" = BLOCK ] && case "$reason" in
               *"is denied"*) ok "$name denied" ;;
               *) bad "$name deny reason" "reason: $reason" ;;
             esac || bad "$name" "expected BLOCK, got ALLOW" ;;
    esac
  fi
  i=$((i+1))
done

# D1/D2 — the SPAWN? hard rule: gate under "### Open for José", stop, one confirm per batch,
# never per worker, never re-asked mid-batch; execution only through spawn-handoffs.sh.
grep -q 'SPAWN?.*one confirmation per batch, before anything launches' "$BRAIN" \
  && ok "D1 rule 7 = SPAWN? hard rule" || bad "D1 rule 7 heading"
grep -q 'never one per worker, and never re-asked mid-batch' "$BRAIN" \
  && ok "D2 never per worker / never re-asked" || bad "D2 batch-once semantics"
grep -q '### Open for José' "$BRAIN" && grep -q 'only\*\* via `bash ~/.pi/agent/scripts/spawn-handoffs.sh`' "$BRAIN" \
  && ok "D2b stop under Open for José; exec via spawn-handoffs.sh only" || bad "D2b gate location / exec route"

# D3/D4 — rules 3c/3d semantics intact, 3c carries the ONE added sentence (emitter-copy).
grep -q '3c\. \*\*Every recommendation carries the command that executes it\.\*\*' "$BRAIN" \
  && ok "D3 rule 3c intact" || bad "D3 rule 3c"
grep -q 'Launch and rollup lines in `### Run next` are copied from the `worktree.sh add` /' "$BRAIN" \
  && ok "D3b 3c emitter-copy sentence present" || bad "D3b emitter-copy sentence"
grep -q '3d\. \*\*Every pane-based worker delegation is a runnable handoff\.\*\*' "$BRAIN" \
  && ok "D4 rule 3d intact" || bad "D4 rule 3d"

# D5 — the evals entry: valid JSON, the SPAWN? judgment exists, pins stop-then-spawn.
rc=0
python3 - "$EVALS" <<'EOF' || rc=$?
import json, sys
entries = json.load(open(sys.argv[1]))
e = next((x for x in entries if x.get("id") == "spawn_gate_batch_stop"), None)
assert e, "no id=spawn_gate_batch_stop entry"
assert e.get("role") == "brain"
assert "SPAWN?" in e.get("expected_behavior", "") and "SPAWN?" in e.get("must_contain", [])
assert "spawn-handoffs.sh" in e.get("expected_behavior", "")
EOF
[ "$rc" -eq 0 ] && ok "D5 evals entry spawn_gate_batch_stop present" || bad "D5 evals entry" "rc=$rc"

echo "---- test-role-gate: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
