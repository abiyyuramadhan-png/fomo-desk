#!/bin/bash
# PAPER only. Refuses to start if LIVE is unlocked. Never prints secrets.
set -euo pipefail
set +x
umask 0077
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
DESK="$ROOT/desk"
PY="$ROOT/.venv/bin/python"
cd "$DESK"
export PYTHONDONTWRITEBYTECODE=1
if ! "$PY" -c 'import commands; raise SystemExit(0 if commands.LIVE_LOCKED is True else 1)'; then
  echo "refusing to start: LIVE is not locked" >&2
  exit 78
fi
exec "$PY" -u "$DESK/main.py"
