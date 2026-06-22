#!/usr/bin/env bash
# Start backend (FastAPI) and frontend (Vite) together for local dev.
#
# Usage: ./dev.sh
# Stop:  Ctrl+C (kills both servers cleanly)
#
# Requirements: .venv/ at repo root, web/node_modules/ installed.

set -uo pipefail  # NOTE: no -e, so wait failures don't kill the script

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
.venv/bin/uvicorn api.main:app --reload --port 8000 --host localhost \
  > /tmp/conciliacion-api.log 2>&1 &
API_PID=$!

# --- Start frontend ----------------------------------------------------------
# Run Vite in its own session (setsid) with stdin redirected to /dev/null
# so it doesn't get killed by SIGPIPE or try to read from a missing TTY.
echo "🎨 Starting web app (Vite picks a port)..."
setsid bash -c "cd web && exec npm run dev" </dev/null \
  > /tmp/conciliacion-web.log 2>&1 &
WEB_PID=$!

# --- Cleanup on exit ---------------------------------------------------------
# IMPORTANT: set a flag so cleanup only runs once. Bash fires EXIT once,
# but if the script is killed mid-flight the trap can run multiple times
# if the script also hits an error path that re-enters.
CLEANED_UP=0
cleanup() {
  if [[ $CLEANED_UP -eq 1 ]]; then return; fi
  CLEANED_UP=1
  echo ""
  echo "🛑 Stopping dev environment..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  # Give them a moment to shut down gracefully
  sleep 0.5
  kill -9 "$API_PID" "$WEB_PID" 2>/dev/null || true
  echo "   API log:    /tmp/conciliacion-api.log"
  echo "   Web log:    /tmp/conciliacion-web.log"
  echo "✅ Stopped"
}
trap cleanup INT TERM EXIT

# --- Wait until both are responding to HTTP ---------------------------------
# We probe by hitting the backend on :8000 (fixed) and parsing Vite's
# stdout to discover which port the frontend bound to (Vite auto-picks
# when :5173 is taken).
echo ""
echo "⏳ Waiting for both servers to come up..."

api_ready=0
web_port=""
web_ready=0

for i in {1..30}; do
  # API ready? Use `localhost` so we hit Vite/uvicorn whether they
  # bound to IPv4, IPv6, or both. `127.0.0.1` doesn't always work
  # because modern Vite (5+) binds to `[::1]` only by default.
  if [[ $api_ready -eq 0 ]] && curl -sf -o /dev/null --max-time 1 http://localhost:8000/api/v1/health; then
    api_ready=1
  fi

  # Discover the Vite port from its log. Vite prints "Local: http://...:NNNN/".
  if [[ -z $web_port ]]; then
    web_port=$(grep -oE 'http://localhost:[0-9]+' /tmp/conciliacion-web.log 2>/dev/null | head -1 | grep -oE '[0-9]+$') || true
  fi
  if [[ $api_ready -eq 1 && -n $web_port && $web_ready -eq 0 ]]; then
    if curl -sf -o /dev/null --max-time 1 "http://localhost:${web_port}/"; then
      web_ready=1
    fi
  fi

  if [[ $api_ready -eq 1 && $web_ready -eq 1 ]]; then
    break
  fi

  sleep 1
done

# --- Report -----------------------------------------------------------------
if [[ $api_ready -eq 0 ]]; then
  echo "❌ API never came up. Check /tmp/conciliacion-api.log"
  cleanup
  exit 1
fi
if [[ $web_ready -eq 0 ]]; then
  echo "❌ Web never came up. Check /tmp/conciliacion-web.log"
  cleanup
  exit 1
fi

echo ""
echo "✅ Dev environment running!"
echo "   API:    http://localhost:8000/docs"
echo "   Web:    http://localhost:${web_port}/conciliacion-geo-v02/"
echo ""
echo "Press Ctrl+C to stop both servers..."

# Block until either child dies. The trap will clean up the other.
# Using `wait -n` (bash 4.3+) with the explicit PIDs. We don't use
# `set -e`, so a missing PID just returns 127 and we still proceed to
# cleanup via the EXIT trap.
wait "$API_PID" "$WEB_PID" 2>/dev/null
echo ""
echo "⚠️  One of the servers stopped. Cleaning up."
