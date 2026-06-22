#!/usr/bin/env bash
# Start backend (FastAPI) and frontend (Vite) together for local dev.
#
# Usage: ./dev.sh
# Stop:  Ctrl+C (kills both servers cleanly)
#
# Requirements: .venv/ at repo root, web/node_modules/ installed.

set -euo pipefail

# Resolve script directory so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Preflight checks -------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "❌ .venv/ not found. Run: uv sync  (or: python -m venv .venv && source .venv/bin/activate && pip install -r requirements-api.txt)"
  exit 1
fi

if [[ ! -d web/node_modules ]]; then
  echo "❌ web/node_modules/ not found. Run: cd web && npm install"
  exit 1
fi

# --- Start backend -----------------------------------------------------------
echo "📡 Starting API server on :8000..."
.venv/bin/uvicorn api.main:app --reload --port 8000 --host 127.0.0.1 \
  > /tmp/conciliacion-api.log 2>&1 &
API_PID=$!

# --- Start frontend ----------------------------------------------------------
echo "🎨 Starting web app on :5173..."
(
  cd web
  npm run dev
) > /tmp/conciliacion-web.log 2>&1 &
WEB_PID=$!

# --- Cleanup on exit ---------------------------------------------------------
cleanup() {
  echo ""
  echo "🛑 Stopping dev environment..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
  echo "   API log:    /tmp/conciliacion-api.log"
  echo "   Web log:    /tmp/conciliacion-web.log"
  echo "✅ Stopped"
}
trap cleanup INT TERM EXIT

# --- Wait until both are ready before printing the banner --------------------
echo ""
echo "⏳ Waiting for both servers to come up..."

for i in {1..30}; do
  api_up=0
  web_up=0
  curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8000/api/v1/health && api_up=1
  curl -sf -o /dev/null --max-time 1 http://127.0.0.1:5173/ && web_up=1
  if [[ $api_up -eq 1 && $web_up -eq 1 ]]; then
    break
  fi
  sleep 1
done

if [[ $api_up -eq 0 ]]; then
  echo "⚠️  API did not come up in 30s. Check /tmp/conciliacion-api.log"
fi
if [[ $web_up -eq 0 ]]; then
  echo "⚠️  Web did not come up in 30s. Check /tmp/conciliacion-web.log"
fi

echo ""
echo "✅ Dev environment running!"
echo "   API:    http://localhost:8000/docs"
echo "   Web:    http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers..."

# Block until either child dies
wait -n "$API_PID" "$WEB_PID"
echo ""
echo "⚠️  One of the servers exited unexpectedly. Stopping the other."
cleanup
