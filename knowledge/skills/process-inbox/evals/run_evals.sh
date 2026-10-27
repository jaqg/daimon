#!/usr/bin/env bash
# Script-path tests for process-inbox event ingest (mode B).
# Deterministic, zero network. Usage: PYTHON=python3 bash evals/run_evals.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" "$HERE/test_event_ingest.py"
