#!/usr/bin/env bash
# Starts the compute backend, the administrative interface, and the GUI server.
#
#   ./run.sh          build the SPA if needed, then run all three services
#   ./run.sh --dev     backend + admin + Vite dev server (hot reload, HTTP only)
#   ./run.sh --build   rebuild the SPA and exit
#
# Ports (override with PMW_* env vars):
#   compute backend   8000
#   admin interface   8090
#   GUI (HTTP)        8080     GUI (HTTPS)  8443   — TLS mode is set in the admin UI

set -euo pipefail
cd "$(dirname "$0")"

VENV="./.venv/bin"
WEB="frontend/web"

if [[ ! -x "$VENV/python" ]]; then
  echo "error: virtualenv missing — create it with:" >&2
  echo "  python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

build_web() {
  if [[ ! -d "$WEB/node_modules" ]]; then
    echo "→ installing frontend dependencies"
    (cd "$WEB" && npm install)
  fi
  echo "→ building the SPA"
  (cd "$WEB" && npm run build)
}

case "${1:-}" in
  --build)
    build_web
    exit 0
    ;;
esac

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "→ compute backend on http://127.0.0.1:${PMW_BACKEND_PORT:-8000}"
"$VENV/uvicorn" app.main:app \
  --app-dir backend \
  --host "${PMW_BACKEND_HOST:-127.0.0.1}" \
  --port "${PMW_BACKEND_PORT:-8000}" &
pids+=($!)

echo "→ admin interface on http://127.0.0.1:${PMW_ADMIN_PORT:-8090}"
"$VENV/uvicorn" server:app \
  --app-dir admin \
  --host "${PMW_ADMIN_HOST:-127.0.0.1}" \
  --port "${PMW_ADMIN_PORT:-8090}" &
pids+=($!)

if [[ "${1:-}" == "--dev" ]]; then
  if [[ ! -d "$WEB/node_modules" ]]; then
    (cd "$WEB" && npm install)
  fi
  echo "→ Vite dev server on http://localhost:5173"
  (cd "$WEB" && npm run dev) &
  pids+=($!)
else
  if [[ ! -f "$WEB/dist/index.html" ]]; then
    build_web
  fi
  # The launcher reads the TLS plan from the admin store and binds HTTP and/or HTTPS.
  echo "→ GUI server (HTTP ${PMW_FRONTEND_PORT:-8080} / HTTPS ${PMW_FRONTEND_HTTPS_PORT:-8443}, per TLS mode)"
  "$VENV/python" frontend/launch.py &
  pids+=($!)
fi

wait
