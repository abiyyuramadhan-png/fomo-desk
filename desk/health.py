"""For the desk-health routine: restart if the process or any heartbeat is older than 2 min.

On the VPS (DESK_SYSTEMD=1, or /etc/systemd/system/fomo-desk.service installed) this never
calls run.sh. A dead process is left to systemd Restart=always. A live process with stale
heartbeats is restarted only while the unit is already active, so a desk left stopped for
cutover stays stopped.
"""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); os.chdir(os.path.dirname(os.path.abspath(__file__)))
import db
PID = os.environ.get("DESK_PID", "desk.pid")
def alive():
    try: os.kill(int(open(PID).read()), 0); return True
    except Exception: return False
def systemd_mode():
    return os.environ.get("DESK_SYSTEMD") == "1" or os.path.isfile("/etc/systemd/system/fomo-desk.service")
def service_active():
    r = subprocess.run(["systemctl", "is-active", "--quiet", "fomo-desk.service"])
    return r.returncode == 0
now = time.time(); hb = {r["agent"]: r["ts"] for r in db.q("select * from heartbeats")}
stale = {a: int((now - t) / 60) for a, t in hb.items() if now - t > (300 if a == 'scanner_ws' else 900 if a == 'backfill' else 120)}
out = {"alive": alive(), "stale": stale, "ws_reconnects_1h": len([t for t in db.kv_get("ws_reconnects", []) if now - t < 3600]), "restarted": None}
if out["alive"] and stale:
    # box may just have woken from a pause: a live loop refreshes heartbeats within ~60s. Recheck before killing.
    time.sleep(75); now = time.time(); hb = {r["agent"]: r["ts"] for r in db.q("select * from heartbeats")}
    stale = {a: int((now - t) / 60) for a, t in hb.items() if now - t > (300 if a == 'scanner_ws' else 900 if a == 'backfill' else 120)}
    out["stale"] = stale; out["recovered_after_wake"] = not stale
if not out["alive"] or stale:
    if systemd_mode():
        # Never fork a second desk. Restart the unit only when it is already active.
        if out["alive"] and stale and service_active():
            subprocess.run(["systemctl", "restart", "fomo-desk.service"], check=False)
            out["restarted"] = sorted(stale) or ["desk"]
    else:
        if out["alive"]:
            try: os.kill(int(open(PID).read()), 15); time.sleep(3)
            except Exception: pass
        subprocess.run(["sh", "run.sh"]); out["restarted"] = sorted(stale) or ["desk"]
print(json.dumps(out))
