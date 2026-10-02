#!/bin/sh
# Development helper (macOS / Linux). Usage: sh scripts/dev.sh {setup|api|web|test|lint|demo}
# The Windows EXE is built with scripts/dev.ps1 build-exe (PyInstaller cannot cross-compile).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
PY="${PYTHON:-python3}"
vpy() { "$VENV/bin/python" "$@"; }

case "${1:-help}" in
  setup)
    "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ required")'
    [ -d "$VENV" ] || "$PY" -m venv "$VENV"
    vpy -m pip install --upgrade pip
    vpy -m pip install -e "$ROOT/backend[api,dev]"
    (cd "$ROOT/frontend" && npm install)
    ;;
  api)  vpy -m imageaudit serve --reload ;;
  web)  (cd "$ROOT/frontend" && npm run dev) ;;
  test) (cd "$ROOT/backend" && vpy -m pytest -q) ;;
  lint)
    (cd "$ROOT/backend" && vpy -m ruff check .)
    (cd "$ROOT/frontend" && npm run lint && npm run typecheck)
    ;;
  demo)
    DEST="$ROOT/build/demo-dataset"
    [ -d "$DEST" ] || vpy -m imageaudit demo "$DEST"
    vpy -m imageaudit scan "$DEST"
    ;;
  *) echo "usage: sh scripts/dev.sh {setup|api|web|test|lint|demo}"; exit 2 ;;
esac
