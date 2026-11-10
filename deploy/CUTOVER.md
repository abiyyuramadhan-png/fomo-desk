# Cutover

**Never run two desks at once.** Two copies both poll Telegram and both push the app. Stop the old one, and the job that restarts it, before starting this one.

The installer leaves `fomo-desk.service` stopped and disabled. The heartbeat timer is enabled, and it will not start a stopped desk.

PAPER stays locked. This build does not place real orders, does not take a wallet key, and does not listen on any port (not 2375 either).

## 1. Validate the new server while it is stopped

On the new server:

```bash
systemctl is-active fomo-desk.service
```

Expect `inactive`.

```bash
systemctl is-enabled fomo-desk.service
```

Expect `disabled` (or `not-found` before the first enable).

```bash
stat -c '%a %U:%G' /etc/fomo-desk/env
sudo -u fomo test ! -r /etc/fomo-desk/env && echo "service user cannot read the secrets file"
/opt/fomo-desk/.venv/bin/python -c 'import sys; sys.path.insert(0,"/opt/fomo-desk/desk"); import commands, links; assert commands.LIVE_LOCKED is True; assert links.SIGNUP_URL=="https://fomo.family/r/savipww"; print("LIVE locked")'
python3.13 --version
readlink -f /etc/localtime
ss -ltn | grep ':2375' || echo "2375 closed"
```

Expect mode `600`, owner `root:root`, `LIVE locked`, Python 3.13, `Asia/Jakarta`, and `2375 closed`.

Do not `cat` the secrets file. Do not start the service in this step.

## 2. Stop the old desk

On the old computer, separately:

1. Stop the desk process (`run.sh` / `main.py`).
2. Disable the routine that runs `health.py` or `run.sh` (cron, a timer, or a loop). If you skip this, it will start the old desk again.
3. Wait a few minutes and confirm it stayed down (`pgrep -af main.py` prints nothing).

## 3. Keep PAPER history

The installer does not copy the database. A new file starts the paper stack over.

While **both** desks are stopped, on the old computer (the db is `data/desk.db` next to `main.py`):

```bash
sqlite3 data/desk.db ".backup 'desk-backup.db'"
```

Copy `desk-backup.db` to the new server by `scp` or the provider console. Do not commit it and do not post it.

On the new server, service still stopped:

```bash
install -o fomo -g fomo -m 600 desk-backup.db /var/lib/fomo-desk/data/desk.db
rm -f desk-backup.db
```

Also copy `-wal` and `-shm` only if you copied the live files instead of using `.backup`. Prefer `.backup`.

## 4. Start the new desk

Only after step 2 shows the old desk stayed down:

```bash
systemctl enable --now fomo-desk.service
systemctl is-active fomo-desk.service
journalctl -u fomo-desk -n 40 --no-pager
```

Expect `active`. `journalctl` and `/var/log/fomo-desk/desk.log` should both contain `mode PAPER`. Then check Telegram and the app. The app reads the same GitHub Pages site; slot branches and `latest` are still published by the desk, not by this installer.

The heartbeat timer replaces the old `health.py` restart routine. It runs the same wake check as the box: if the `loop` heartbeat is stale too, that was a pause, and it waits instead of killing a healthy process. It restarts the service only when that service is already active and a heartbeat is still stale after that wait. It does not call `run.sh`. `run.sh` also refuses to start a second copy, including the venv process systemd uses.

## 5. If you have to go back

Stop this one before starting the old one:

```bash
systemctl disable --now fomo-desk.service
```

Confirm `inactive`, then start the old desk again. Do not enable its health routine until this service is stopped.

Re-running the installer does not start the desk. If the secrets file is already present, the installer leaves it unchanged and does not print it. To type the secrets again, `rm /etc/fomo-desk/env` and run the install command again, while the service is stopped.
