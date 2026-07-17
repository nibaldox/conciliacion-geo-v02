#!/usr/bin/env bash
# Start backend (FastAPI) + frontend (Vite) + Electron for local Electron dev.
#
# Usage: ./dev-electron.sh
# Stop:  Ctrl+C (kills all three processes cleanly)
#
# Requirements:
#   - .venv/ at repo root
#   - web/node_modules/ installed
#   - electron/node_modules/ installed

set -uo pipefail

# Resolve script directory so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Dev mode: Electron will skip spawning the sidecar and load the Vite URL.
export CONCILIACION_ELECTRON_DEV=1

# API port must match Vite's proxy target in web/vite.config.ts (default 8000).
API_PORT="${CONCILIACION_API_PORT:-8000}"
export CONCILIACION_API_PORT

# --- Preflight checks -------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "❌ .venv/ not found. Run: uv sync"
  exit 1
fi

if [[ ! -d web/node_modules ]]; then
  echo "❌ web/node_modules/ not found. Run: cd web && npm install"
  exit 1
fi

if [[ ! -d electron/node_modules ]]; then
  echo "❌ electron/node_modules/ not found. Run: cd electron && npm install"
  exit 1
fi

# --- Start backend -----------------------------------------------------------
echo "📡 Starting API server on :${API_PORT}..."
.venv/bin/uvicorn api.main:app --reload --port "${API_PORT}" --host localhost \
  > /tmp/conciliacion-api-electron.log 2>&1 &
API_PID=$!

# --- Start frontend ----------------------------------------------------------
echo "🎨 Starting web app (Vite dev server)..."
setsid bash -c "cd web && exec npm run dev" </dev/null \
  > /tmp/conciliacion-web-electron.log 2>&1 &
WEB_PID=$!

# --- Cleanup on exit ---------------------------------------------------------
CLEANED_UP=0
cleanup() {
  if [[ $CLEANED_UP -eq 1 ]]; then return; fi
  CLEANED_UP=1
  echo ""
  echo "🛑 Stopping dev environment..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  if [[ -n ${ELECTRON_PID:-} ]]; then
    kill "$ELECTRON_PID" 2>/dev/null || true
  fi
  sleep 0.5
  kill -9 "$API_PID" "$WEB_PID" 2>/dev/null || true
  if [[ -n ${ELECTRON_PID:-} ]]; then
    kill -9 "$ELECTRON_PID" 2>/dev/null || true
  fi
  echo "   API log:      /tmp/conciliacion-api-electron.log"
  echo "   Web log:      /tmp/conciliacion-web-electron.log"
  echo "✅ Stopped"
}
trap cleanup INT TERM EXIT

# --- Wait until both dev servers are responding ------------------------------
api_ready=0
web_port=""
web_ready=0

for i in {1..30}; do
  if [[ $api_ready -eq 0 ]] && curl -sf -o /dev/null --max-time 1 "http://localhost:${API_PORT}/api/v1/health"; then
    api_ready=1
  fi

  if [[ -z $web_port ]]; then
    web_port=$(grep -oE 'http://localhost:[0-9]+' /tmp/conciliacion-web-electron.log 2>/dev/null | head -1 | grep -oE '[0-9]+$') || true
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
  echo "❌ API never came up. Check /tmp/conciliacion-api-electron.log"
  cleanup
  exit 1
fi
if [[ $web_ready -eq 0 ]]; then
  echo "❌ Web never came up. Check /tmp/conciliacion-web-electron.log"
  cleanup
  exit 1
fi

echo ""
echo "✅ Dev servers ready!"
echo "   API:    http://localhost:${API_PORT}/docs"
echo "   Web:    http://localhost:${web_port}/"
echo ""
echo "🖥️  Starting Electron in dev mode..."

# --- Start Electron ----------------------------------------------------------
export CONCILIACION_DEV_URL="http://localhost:${web_port}"
cd electron

# Use Xvfb if available (needed when there's no real X11/Wayland display,
# e.g. over SSH or in a headless container). xvfb-run allocates a virtual
# display on-the-fly, runs electron inside it, and tears it down on exit.
if command -v xvfb-run >/dev/null 2>&1; then
  ELECTRON_DISPLAY_OPTS=(-a --server-args="-screen 0 1400x900x24")
  echo "   (using Xvfb virtual display)"
else
  ELECTRON_DISPLAY_OPTS=()
fi

xvfb-run "${ELECTRON_DISPLAY_OPTS[@]}" npm run dev &
ELECTRON_PID=$!
cd ..

# Block until any child dies. The trap cleans up the rest.
wait "$API_PID" "$WEB_PID" "$ELECTRON_PID" 2>/dev/null
echo ""
echo "⚠️  One of the processes stopped. Cleaning up."
