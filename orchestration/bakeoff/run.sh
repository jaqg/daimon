#!/usr/bin/env bash
# run.sh — the single GREEN command for this repo (`test_cmd:` in .agent-paths points here).
# Runs every bakeoff contract test `test-*.sh`; exit 0 iff all green.
#
# Why the env vars: test-merge-status.sh and test-pi-agents.sh default to the DEPLOYED copies under
# ~/.pi/agent/scripts (deploy.sh symlinks), which means "green" would silently test whatever was last
# deployed rather than the tree under review. Pointing them at the repo copies makes a fresh clone
# green without deploy.sh having run — and makes a red test mean THIS checkout broke something.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PI_WORKTREE_SH="$ROOT/orchestration/scripts/worktree.sh"
export PI_MERGE_STATUS="$ROOT/orchestration/scripts/merge-status.py"
export PI_AGENTS_BIN="$ROOT/orchestration/scripts/pi-agents.sh"

pass=0; fail=0
for t in "$ROOT"/orchestration/bakeoff/test-*.sh; do
  name="$(basename "$t")"
  if bash "$t"; then
    pass=$((pass+1))
  else
    echo "==== FAILED: $name (rc=$?)"
    fail=$((fail+1))
  fi
done

echo "---- bakeoff suites: $pass suite(s) green, $fail red"
[ "$fail" -eq 0 ]
