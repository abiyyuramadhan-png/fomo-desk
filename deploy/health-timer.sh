#!/bin/bash
# Heartbeat check for the VPS desk.
# If the service is stopped (install, cutover, or an operator stop), do nothing.
# health.py then uses systemctl, not run.sh. run.sh also refuses to start a second copy.
set -euo pipefail
set +x
umask 0077
if ! systemctl is-active --quiet fomo-desk.service; then
  exit 0
fi
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
export DESK_SYSTEMD=1
export DESK_DB="${DESK_DB:-/var/lib/fomo-desk/data/desk.db}"
export DESK_PID="${DESK_PID:-/var/lib/fomo-desk/data/desk.pid}"
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT/desk"
exec "$ROOT/.venv/bin/python" "$ROOT/desk/health.py"
