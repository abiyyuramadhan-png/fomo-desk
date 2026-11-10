"""FOMO desk: 5 agents + Telegram + publisher in one process. PAPER only. Never places orders."""
import asyncio, logging, os, sys, time, json
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT); os.chdir(ROOT)
import db, links, config as settings
from agents.scanner import Scanner
from agents.auditor import Auditor
from agents.analyst import Analyst
from agents.executor import Executor
from agents.risk import Risk
from telegram import Telegram
import bus, wake, net
from commands import Desk, LIVE_LOCKED
from api import Publisher, price_other_coins
def setup_logs():
    os.makedirs("logs", exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s")
    root = logging.getLogger(); root.setLevel(logging.INFO)
    h = logging.FileHandler("logs/desk.log"); h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")); root.addHandler(h)
    err = logging.StreamHandler(); err.setFormatter(h.formatter); root.addHandler(err)
    for a in ("scanner", "auditor", "analyst", "executor", "risk"):
        l = logging.getLogger(a + ".file"); fh = logging.FileHandler(f"logs/{a}.log"); fh.setFormatter(fmt); l.addHandler(fh)
    for noisy in ("httpx", "httpcore", "websockets"): logging.getLogger(noisy).setLevel(logging.WARNING)
async def worker(name, q, fn, obj):
    while True:
        try: item = await asyncio.wait_for(q.get(), timeout=30)
        except asyncio.TimeoutError: db.heartbeat(name); continue
        await wake.gate()   # after a box pause, Risk re-prices open positions first
        while obj.paused: db.heartbeat(name, "paused"); await asyncio.sleep(5)
        try: await fn(*item) if isinstance(item, tuple) else await fn(item)
        except Exception as e: logging.getLogger(name).exception("%s: %s", name, e)
        db.heartbeat(name)
async def night_watch(desk, tg):
    while True:
        n = db.night_id()
        if db.kv_get("night") != n:
            db.kv_set("night", n)
            w = desk.ticket_check()
            if w: await tg.send(("PAPER · " if settings.get("desk.mode") == "PAPER" else "") + w)
        db.heartbeat("desk"); await asyncio.sleep(60)
WAKE = None
RISK = None; SCANNER = None
async def loop_watch():
    """Tick every 5s. A wall-clock jump means the whole box was paused (process frozen, not crashed)."""
    import threading, faulthandler
    st = {"mono": time.monotonic()}
    def guard():   # real event-loop hang (monotonic time passes, loop doesn't tick): dump all stacks once
        dumped = False; grace_until = 0
        while True:
            w0 = time.time(); time.sleep(10); w1 = time.time()
            if w1 - w0 > 30: grace_until = time.monotonic() + 60   # this thread was frozen too: box pause, not a hang
            lag = time.monotonic() - st["mono"]
            if lag > 60 and not dumped and time.monotonic() > grace_until:
                with open("logs/stall.log", "a") as f:
                    f.write(f"{db.iso()} event loop stuck {lag:.0f}s\n"); faulthandler.dump_traceback(file=f, all_threads=True)
                dumped = True
            elif lag < 60: dumped = False
    threading.Thread(target=guard, daemon=True, name="loop-guard").start()
    lg = logging.getLogger("desk"); wall = time.time()
    while True:
        await asyncio.sleep(5); now = time.time(); st["mono"] = time.monotonic()
        if now - wall > wake.GAP_S:
            lg.warning("box paused/frozen %.0fs (wall-clock gap), resuming", now - wall); db.event("box_pause", {"gap_s": round(now - wall)})
            steps = await wake.on_wake(now - wall,
                risk_refresh=RISK.poll_once if RISK else (lambda: asyncio.sleep(0)),
                resubscribe=SCANNER.force_reconnect if SCANNER else (lambda: None),
                backfill=(WAKE.set if WAKE else (lambda: None)),   # backfill migrations missed while frozen
                reset_http=net.reset_client, log=lg)
            db.event("wake", steps)
        wall = time.time(); wake.last_tick = wall; db.heartbeat("loop")
async def main():
    if LIVE_LOCKED is not True:
        raise SystemExit("refusing to start: LIVE is not locked")
    setup_logs()
    if settings.get("desk.mode") != "PAPER":
        ok, _msg = settings.set_value("desk.mode", "PAPER")
        if not ok or settings.get("desk.mode") != "PAPER":
            raise SystemExit("refusing to start: mode is not PAPER")
    open(os.environ.get("DESK_PID", "desk.pid"), "w").write(str(os.getpid()))
    tg = Telegram()
    qa, qn, qe = bus.auditor, bus.analyst, bus.executor
    sc = Scanner(qa, tg); au = Auditor(qn, tg); an = Analyst(qe); ex = Executor(tg); rk = Risk(tg)
    agents = {"scanner": sc, "auditor": au, "analyst": an, "executor": ex, "risk": rk}
    for a in db.kv_get("paused", []):
        if a in agents: agents[a].paused = True
    global WAKE, RISK, SCANNER; WAKE = sc.wake; RISK = rk; SCANNER = sc
    desk = Desk(agents, tg, au, rk); tg.desk = desk
    # re-queue coins that passed a stage before a restart
    for r in db.q("select s.json from scans s where json like '%\"pass\"%' and mint not in (select mint from audits)"): qa.put_nowait(json.loads(r["json"]))
    pub = Publisher()
    logging.getLogger("desk").info("desk up pid %s mode %s", os.getpid(), settings.get("desk.mode"))
    await asyncio.gather(sc.ws_loop(), sc.poll_loop(), sc.backfill_loop(), worker("auditor", qa, au.audit, au), worker("analyst", qn, an.analyse, an),
                         worker("executor", qe, ex.execute, ex), rk.loop(), tg.poll(), pub.loop(), price_other_coins(), night_watch(desk, tg), loop_watch())
if __name__ == "__main__":
    asyncio.run(main())
