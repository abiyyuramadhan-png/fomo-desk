#!/bin/bash
# Install the FOMO paper desk on Ubuntu 24.04. Does not start it.
# One command, from the provider console or Termius:
#   curl -fsSL https://raw.githubusercontent.com/abiyyuramadhan-png/fomo-desk/main/deploy/install.sh | sudo bash
set -euo pipefail
set +x
umask 022
export DEBIAN_FRONTEND=noninteractive
export GIT_TERMINAL_PROMPT=0
export PYTHONDONTWRITEBYTECODE=1

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root. Paste the install command again; it uses sudo." >&2
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
fi
if [[ "${VERSION_ID:-}" != "24.04" ]]; then
  echo "This installer supports Ubuntu 24.04 only (found ${VERSION_ID:-unknown})." >&2
  exit 1
fi

REPO="${FOMO_DESK_REPO:-https://github.com/abiyyuramadhan-png/fomo-desk.git}"
REF="${FOMO_DESK_REF:-main}"
if [[ "$REPO" == *"@"* ]]; then
  echo "Refusing a repository URL that contains credentials." >&2
  exit 1
fi
RESET="${FOMO_DESK_RESET_SECRETS:-0}"
DEST=/opt/fomo-desk
ENV_FILE=/etc/fomo-desk/env

say() { printf '%s\n' "$*" >/dev/tty 2>/dev/null || printf '%s\n' "$*"; }

need_tty() {
  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    echo "A terminal is required so secrets stay hidden. Open the provider web console or Termius and run the command there." >&2
    exit 1
  fi
}

ask_secret() {
  local __var="$1" __label="$2" __re="$3"
  local __v=""
  need_tty
  while true; do
    printf '%s' "$__label" >/dev/tty
    IFS= read -rs __v </dev/tty || exit 1
    printf '\n' >/dev/tty
    __v=${__v%$'\r'}
    __v="${__v%"${__v##*[![:space:]]}"}"
    __v="${__v#"${__v%%[![:space:]]*}"}"
    if [[ ${#__v} -le 256 && "$__v" =~ $__re ]]; then
      printf -v "$__var" '%s' "$__v"
      unset __v
      printf 'accepted\n' >/dev/tty
      return 0
    fi
    unset __v
    printf 'That value was not accepted. Check it and try again.\n' >/dev/tty
  done
}

write_env() {
  local tmp
  install -d -m 700 -o root -g root /etc/fomo-desk
  umask 077
  tmp=$(mktemp /etc/fomo-desk/.write.XXXXXX)
  printf 'TG_TOKEN=%s\nGH_PAGES_TOKEN=%s\nDATA_PATH=%s\n' "$TG_TOKEN" "$GH_PAGES_TOKEN" "$DATA_PATH" >"$tmp"
  chown root:root "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  chown root:root "$ENV_FILE"
  unset TG_TOKEN GH_PAGES_TOKEN DATA_PATH tmp
}

check_env_file() {
  "$DEST/.venv/bin/python" - <<'PY'
import os, stat
p = "/etc/fomo-desk/env"
st = os.stat(p)
mode = stat.S_IMODE(st.st_mode)
if mode != 0o600 or st.st_uid != 0:
    raise SystemExit("secrets file permissions are wrong")
keys = {}
for line in open(p):
    line = line.rstrip("\n")
    if not line or line.startswith("#") or "=" not in line:
        raise SystemExit("secrets file is not valid")
    k, v = line.split("=", 1)
    keys[k] = v
need = ("TG_TOKEN", "GH_PAGES_TOKEN", "DATA_PATH")
if tuple(keys) != need or any(not keys[k] for k in need):
    raise SystemExit("secrets file is not valid")
print("secrets file ok")
PY
}

echo "Installing packages. This takes a few minutes."
apt-get update
apt-get install -y ca-certificates curl gnupg software-properties-common git tzdata rsync iproute2 logrotate sqlite3
if ! command -v python3.13 >/dev/null 2>&1; then
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update
fi
apt-get install -y python3.13 python3.13-venv
python3.13 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 13) else "python is not 3.13")
PY

ln -sfn /usr/share/zoneinfo/Asia/Jakarta /etc/localtime
printf 'Asia/Jakarta\n' >/etc/timezone
if [[ -d /run/systemd/system ]] && command -v timedatectl >/dev/null 2>&1; then
  timedatectl set-timezone Asia/Jakarta || true
fi

if ! id -u fomo >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/fomo-desk --create-home --shell /usr/sbin/nologin fomo
fi
install -d -m 750 -o fomo -g fomo /var/lib/fomo-desk /var/lib/fomo-desk/data /var/lib/fomo-desk/publish /var/log/fomo-desk

SRC=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  _here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  if [[ -f "$_here/install.sh" && -f "$_here/../desk/main.py" ]]; then
    SRC=$(cd "$_here/.." && pwd)
  fi
fi

echo "Installing desk code."
if [[ -n "$SRC" ]]; then
  mkdir -p "$DEST"
  rsync -a --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'desk/logs' \
    --exclude 'desk/data' \
    --exclude 'desk/publish' \
    --exclude 'desk/.secrets' \
    --exclude '.env' \
    --exclude '.secrets' \
    --exclude '*.db' \
    --exclude '*.db-wal' \
    --exclude '*.db-shm' \
    --exclude '*.pid' \
    "$SRC"/ "$DEST"/
elif [[ -d "$DEST/.git" ]]; then
  git -C "$DEST" fetch --depth 1 origin "$REF"
  git -C "$DEST" checkout -f -B "$REF" "origin/$REF"
  git -C "$DEST" reset --hard "origin/$REF"
else
  rm -rf "$DEST"
  git clone --depth 1 --branch "$REF" "$REPO" "$DEST"
fi

if [[ ! -x "$DEST/.venv/bin/python" ]]; then
  python3.13 -m venv "$DEST/.venv"
fi
"$DEST/.venv/bin/pip" install --upgrade pip
"$DEST/.venv/bin/pip" install -r "$DEST/desk/requirements.txt"
PYTHONPATH="$DEST/desk" "$DEST/.venv/bin/python" - <<'PY'
import sys, commands, links, httpx, websockets
from solders.pubkey import Pubkey
assert sys.version_info[:2] == (3, 13)
assert commands.LIVE_LOCKED is True
assert links.SIGNUP_URL == "https://fomo.family/r/savipww"
assert callable(websockets.connect) and httpx.Client and Pubkey
print("PAPER lock ok")
PY

chown -R root:root "$DEST"
chmod -R a+rX "$DEST"
chmod 755 "$DEST/deploy/install.sh" "$DEST/deploy/run-paper.sh" "$DEST/deploy/health-timer.sh"
install -d -m 750 -o fomo -g fomo /var/lib/fomo-desk/data /var/lib/fomo-desk/publish /var/log/fomo-desk
ln -sfn /var/log/fomo-desk "$DEST/desk/logs"
ln -sfn /var/lib/fomo-desk/data "$DEST/desk/data"
ln -sfn /var/lib/fomo-desk/publish "$DEST/desk/publish"
# code stays root-owned; the service user writes only state, logs, and the publish checkout
chown -h root:root "$DEST/desk/logs" "$DEST/desk/data" "$DEST/desk/publish" || true
if ! git config --system --get-all safe.directory 2>/dev/null | grep -qx /var/lib/fomo-desk/publish; then
  git config --system --add safe.directory /var/lib/fomo-desk/publish
fi
if ! git config --system --get-all safe.directory 2>/dev/null | grep -qx "$DEST"; then
  git config --system --add safe.directory "$DEST"
fi

if [[ -f "$ENV_FILE" && "$RESET" != "1" ]]; then
  chown root:root "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  say "Secrets file already on the server. Left it unchanged."
else
  say "Enter three secrets. Nothing you type is shown. Press return after each."
  ask_secret TG_TOKEN "Telegram bot token: " '^[0-9]+:[A-Za-z0-9_-]{20,}$'
  ask_secret GH_PAGES_TOKEN "GitHub token: " '^[A-Za-z0-9_-]{8,}$'
  ask_secret DATA_PATH "DATA_PATH: " '^[A-Za-z0-9_-]{16,128}$'
  write_env
  say "Secrets saved. They were not shown."
fi
check_env_file

install -m 644 "$DEST/deploy/fomo-desk.service" /etc/systemd/system/fomo-desk.service
install -m 644 "$DEST/deploy/fomo-desk-health.service" /etc/systemd/system/fomo-desk-health.service
install -m 644 "$DEST/deploy/fomo-desk-health.timer" /etc/systemd/system/fomo-desk-health.timer
install -m 644 "$DEST/deploy/logrotate-fomo-desk" /etc/logrotate.d/fomo-desk

if command -v ss >/dev/null 2>&1; then
  if ss -ltn | awk 'NR>1 && $4 ~ /:2375$/ {found=1} END {exit !found}'; then
    echo "Port 2375 is in use. This installer did not open it. Close it before using this server." >&2
    exit 1
  fi
fi

if [[ -d /run/systemd/system ]]; then
  systemctl daemon-reload
  systemctl enable fomo-desk-health.timer
  systemctl start fomo-desk-health.timer || true
  if systemctl is-active --quiet fomo-desk.service; then
    say "Desk service was already running. This installer did not restart it."
  else
    systemctl disable fomo-desk.service >/dev/null 2>&1 || true
    say "Desk service is installed and stopped."
  fi
else
  say "systemd is not running here. Unit files are installed. The desk was not started."
fi

say "Installed. The desk is STOPPED."
say "Leave it stopped until the old desk is off."
say "Open Telegram only after this desk is started. You want a PAPER message."
