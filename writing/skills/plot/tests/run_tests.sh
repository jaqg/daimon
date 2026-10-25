#!/usr/bin/env bash
# Script-path tests for the plot skill. Usage: PYTHON=python3 bash run_tests.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

"$PYTHON" -c "import matplotlib, numpy" 2>/dev/null || {
    echo "ERROR: matplotlib+numpy required (pip install -r requirements.txt)" >&2
    exit 2
}

exec "$PYTHON" "$HERE/test_render.py"
