#!/usr/bin/env bash
# Sets up a Python environment when needed, then runs a command:
#   ./start.sh menubar            menu bar app (from Terminal)
#   ./start.sh scan               find Hue lights nearby
#   ./start.sh pair <ADDRESS> [--name "Study Light"]
#   ./start.sh run                Apple Home bridge only, no menu bar
#   ./start.sh setup              just install / update dependencies
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && \
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -n "$PY" ]; then
    echo "Creating environment with $PY ..."
    "$PY" -m venv .venv
  elif command -v uv >/dev/null 2>&1; then
    echo "Creating environment with uv (Python 3.12) ..."
    uv venv --python 3.12 .venv
  else
    echo "Python 3.10+ is needed (macOS ships 3.9). Install it with:"
    echo "  brew install python@3.12"
    exit 1
  fi
fi

# (Re)install dependencies whenever requirements.txt changes.
REQ_HASH="$(shasum requirements.txt | cut -d' ' -f1)"
if [ "$(cat .venv/.req-hash 2>/dev/null || true)" != "$REQ_HASH" ]; then
  echo "Installing dependencies (first run takes a minute) ..."
  if [ -x .venv/bin/pip ]; then
    .venv/bin/python -m pip install -q --upgrade pip 2>/dev/null || true
    .venv/bin/pip install -q -r requirements.txt
  else
    uv pip install -q --python .venv/bin/python -r requirements.txt
  fi
  echo "$REQ_HASH" > .venv/.req-hash
fi

case "${1:-}" in
  setup)   exit 0 ;;
  menubar) shift; exec .venv/bin/python hue_menubar.py "$@" ;;
  run)     exec caffeinate -i .venv/bin/python hue_homekit.py "$@" ;;
  "")      echo "Usage: ./start.sh menubar | scan | pair <ADDRESS> | run"; exit 1 ;;
  *)       exec .venv/bin/python hue_homekit.py "$@" ;;
esac
