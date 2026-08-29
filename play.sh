#!/usr/bin/env bash
# ===========================================================================
#  Space Harvest - one-click launcher for Linux / macOS.
#
#  ./play.sh            first run creates .venv, installs deps, then launches
#  ./play.sh --test     pass any setup.py flags through
#
#  Nothing is installed system-wide; dependencies land in ./.venv and later
#  runs start instantly with no downloads.
# ===========================================================================
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "[Space Harvest] Python 3.11+ required; found: $("$PY" --version 2>&1 || echo none)"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[Space Harvest] First run - creating a private environment in .venv ..."
  "$PY" -m venv .venv
  echo "[Space Harvest] Installing game dependencies (one-time, needs internet)..."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

exec .venv/bin/python setup.py "$@"
