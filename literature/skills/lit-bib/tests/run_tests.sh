#!/usr/bin/env bash
# lit-bib test runner. Deterministic by default; live-network opt-in:
#   RUN_NET=1 bash tests/run_tests.sh
set -u
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$TESTS_DIR"
PYTHON="${PYTHON:-python3}"

echo "== deterministic (no network) =="
"$PYTHON" test_verify.py || exit 1

if [ "${RUN_NET:-0}" = "1" ]; then
    echo ""
    echo "== live network (Crossref) =="
    "$PYTHON" test_live.py || exit 1
else
    echo ""
    echo "SKIP live-network tests (set RUN_NET=1 to enable)"
fi
