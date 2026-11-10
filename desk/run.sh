#!/bin/sh
# start the desk in the background (no systemd on the box). Never starts a second copy.
cd "$(dirname "$0")"
if [ -f desk.pid ]; then
  p="$(cat desk.pid)"
  # /proc check too: kill -0 fails with "not permitted" for a live process owned by another user
  if kill -0 "$p" 2>/dev/null || grep -q main.py "/proc/$p/cmdline" 2>/dev/null; then echo "running $p"; exit 0; fi
fi
if p=$(pgrep -f "python3 main.py" | head -1) && [ -n "$p" ]; then echo "running $p (pidfile stale)"; exit 0; fi
# systemd starts the venv as "python -u .../main.py", which the python3 check above does not see
if p=$(pgrep -f "python.*main\\.py" | head -1) && [ -n "$p" ]; then echo "running $p (pidfile stale)"; exit 0; fi
nohup python3 main.py >> logs/stdout.log 2>&1 &
echo $! > desk.pid; echo "started $!"
