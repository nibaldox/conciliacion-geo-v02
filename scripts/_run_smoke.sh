#!/usr/bin/env bash
# Helper: runs the smoke test with the real OpenRouter key.
# The key is read from OPENROUTER_API_KEY env var (set externally).
# Usage: bash scripts/_run_smoke.sh
set -e
cd "$(dirname "$0")/.."
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY is not set." >&2
    echo "Set it first: export OPENROUTER_API_KEY='***' or pass inline" >&2
    exit 1
fi
source /tmp/hermes_test_venv/bin/activate
PYTHONPATH=. python scripts/smoke_ai_v2_openrouter.py