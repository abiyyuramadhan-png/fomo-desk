"""For the desk-health routine: restart if the process is gone or an agent heartbeat is stale.
Box pauses freeze the whole process; that is not a crash. The 'loop' heartbeat ticks every 5s, so if it is
stale too, the box was paused: wait for the wake recovery instead of killing a healthy process.

On the VPS (DESK_SYSTEMD=1, or the fomo-desk unit installed) this never calls run.sh. A dead process is
left to systemd Restart=always. A live process that is still stale after the wake wait is restarted
only while the unit is already active, so a desk left stopped for cutover stays stopped.
"""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); os.chdir(os.path.dirname(os.path.abspath(__file__)))
import db
LIMIT = {"scanner_ws": 300, "backfill": 900}
def pid_path():
    return os.environ.get("DESK_PID", "desk.pid")
def pid():
    try: return int(open(pid_path()).read().strip())
    except Exception: return None
def alive(p=None):
    """True if the desk process exists. PermissionError (other user / sandbox) still means it exists:
    treating it as dead made health report a 'full-desk restart' that never happened (Nov 8 14:33)."""
    p = p or pid()
    if not p: return False
    try: os.kill(p, 0)
    except ProcessLookupError: return False
    except PermissionError: pass
    except Exception: return False
    try: return b"main.py" in open(f"/proc/{p}/cmdline", "rb").read()
    except FileNotFoundError: return False
    except Exception: return True
def systemd_mode():
    return os.environ.get("DESK_SYSTEMD") == "1" or os.path.isfile("/etc/systemd/system/fomo-desk.service")
def service_active():
    r = subprocess.run(["systemctl", "is-active", "--quiet", "fomo-desk.service"])
    return r.returncode == 0
def stale_now():
    now = time.time(); hb = {r["agent"]: r["ts"] for r in db.q("select * from heartbeats")}
    return {a: int((now - t) / 60) for a, t in hb.items() if now - t > LIMIT.get(a, 120)}
def check(wait_s=75, extra_wait_s=60):
    p0 = pid(); out = {"alive": alive(p0), "pid": p0, "stale": stale_now(), "restarted": None}
    now = time.time()
    out["ws_reconnects_1h"] = len([t for t in db.kv_get("ws_reconnects", []) if now - t < 3600])
    if out["alive"] and out["stale"]:
        # box may just have woken from a pause: a live loop refreshes heartbeats within ~60s. Recheck before killing.
        whole = "loop" in out["stale"]
        time.sleep(wait_s); s = stale_now()
        if s and whole and "loop" not in s:   # process is ticking again, give agents one more window
            time.sleep(extra_wait_s); s = stale_now()
        out["stale"] = s; out["recovered_after_wake"] = not s; out["box_pause"] = whole
    if not out["alive"] or out["stale"]:
        if systemd_mode():
            # Never fork a second desk. Restart the unit only when it is already active.
            if out["alive"] and out["stale"] and service_active():
                subprocess.run(["systemctl", "restart", "fomo-desk.service"], check=False)
                out["restarted"] = sorted(out["stale"]) or ["desk"]
        else:
            if out["alive"]:
                try: os.kill(p0, 15)
                except Exception: pass
                for _ in range(20):
                    if not alive(p0): break
                    time.sleep(0.5)
            r = subprocess.run(["sh", "run.sh"], capture_output=True, text=True)
            p1 = pid(); time.sleep(3)
            up = p1 != p0 and alive(p1)
            out["restarted"] = (sorted(out["stale"]) or ["desk"]) if up else None
            out["new_pid"] = p1 if up else None
            if not up: out["restart_failed"] = (r.stdout + r.stderr).strip()[-200:]
    return out
if __name__ == "__main__":
    print(json.dumps(check()))
