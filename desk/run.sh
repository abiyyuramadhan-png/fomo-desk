#!/bin/sh
# start the desk in the background (no systemd on the box)
cd "$(dirname "$0")"
if [ -f desk.pid ] && kill -0 "$(cat desk.pid)" 2>/dev/null; then echo "running $(cat desk.pid)"; exit 0; fi
nohup python3 main.py >> logs/stdout.log 2>&1 &
echo $! > desk.pid; echo "started $!"
