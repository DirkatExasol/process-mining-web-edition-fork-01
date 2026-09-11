#!/usr/bin/env bash
# Runs the full test suite: backend (pytest) + frontend (vitest).
#
#   ./test.sh            run everything
#   ./test.sh backend    backend pytest only
#   ./test.sh frontend   frontend vitest only

set -euo pipefail
cd "$(dirname "$0")"

VENV="./.venv/bin"
WEB="frontend/web"
target="${1:-all}"

run_backend() {
  echo "══ Backend tests (pytest) ═══════════════════════════════════════════"
  if [[ ! -x "$VENV/pytest" ]]; then
    echo "installing test dependencies…"
    "$VENV/pip" install -q -r requirements-dev.txt
  fi
  (cd backend && "../$VENV/python" -m pytest)
}

run_frontend() {
  echo "══ Frontend tests (vitest) ══════════════════════════════════════════"
  if [[ ! -d "$WEB/node_modules" ]]; then
    (cd "$WEB" && npm install)
  fi
  (cd "$WEB" && npm test)
}

case "$target" in
  backend)  run_backend ;;
  frontend) run_frontend ;;
  all)      run_backend; echo; run_frontend ;;
  *) echo "usage: ./test.sh [all|backend|frontend]" >&2; exit 1 ;;
esac
