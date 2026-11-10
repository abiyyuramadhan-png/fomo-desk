"""Regression: box-pause wake recovery, Risk-first ordering, no double exits, health liveness, 4xx no-retry,
ws resubscribe on wake, creator re-lookup before a pass, stall guard ignores pauses."""
from common import *
import httpx, logging, importlib
import wake, net
from agents.risk import Risk
from agents.scanner import Scanner
from telegram import NullNotifier
lg = logging.getLogger("t")
def mkpos(mint, entry=1.0):
    db.x("insert into positions(mint,name,mode,entry,size,peak,stop_pct,opened_at,status,last_price,last_liq,night) values(?,?,?,?,?,?,?,?,?,?,?,?)",
         mint, mint, "PAPER", entry, 47.5, entry, 6, time.time(), "open", entry, 1e5, "n")
async def t_order():
    order = []; mkpos("W1")
    async def dex(mints):
        order.append("risk_dex"); await asyncio.sleep(0.2)
        return {m: {"baseToken": {"address": m}, "dexId": "pumpswap", "priceUsd": "0.5", "liquidity": {"usd": 1e5}, "volume": {"m5": 1}} for m in mints}
    rk = Risk(NullNotifier(), dex=dex)
    wake.last_tick = time.time() - 3600          # box was frozen for an hour
    async def other():                           # e.g. scanner poll firing first after the pause
        await wake.gate(); order.append("other")
    o = asyncio.create_task(other()); await asyncio.sleep(0.01)
    check("other agent held while box just woke", "other" not in order)
    steps = await wake.on_wake(3600, rk.poll_once, lambda: order.append("ws"), lambda: order.append("backfill"),
                               lambda: order.append("http_reset"), lg)
    await o
    check("wake order: http reset -> risk -> ws -> backfill", order[:2] == ["http_reset", "risk_dex"] and order.index("ws") < order.index("backfill"), order)
    check("risk refresh ran before other work", order.index("risk_dex") < order.index("other"), order)
    check("stop re-evaluated on wake (exit at -50%)", "1 exits" in steps["risk"] and db.q1("select status from positions where mint='W1'")["status"] == "closed", steps)
    check("gate open after wake", wake.risk_done.is_set() and not wake.woke())
async def t_hang():
    async def hang(): await asyncio.sleep(3600)
    t = time.monotonic()
    steps = await wake.on_wake(100, hang, lambda: None, lambda: None, lambda: None, lg, timeout=0.2)
    check("hung risk refresh can't block the desk", time.monotonic() - t < 2 and "TimeoutError" in steps["risk"] and wake.risk_done.is_set(), steps)
async def t_double():
    mkpos("D1"); calls = []
    async def dex(mints):
        calls.append(1); await asyncio.sleep(0.1)
        return {m: {"baseToken": {"address": m}, "dexId": "pumpswap", "priceUsd": "0.5", "liquidity": {"usd": 1e5}, "volume": {"m5": 1}} for m in mints}
    rk = Risk(NullNotifier(), dex=dex)
    bal0 = db.q("select count(*) n from balance")[0]["n"]
    r = await asyncio.gather(rk.poll_once(), rk.poll_once())
    exits = sum(len(x or []) for x in r)
    check("wake refresh + regular loop never exit the same position twice", exits == 1 and db.q("select count(*) n from balance")[0]["n"] - bal0 == 1, exits)
async def t_retry():
    n = {"c": 0}
    def mk(code):
        async def f():
            n["c"] += 1; req = httpx.Request("GET", "https://x"); raise httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, request=req))
        return f
    for code, want in ((400, 1), (500, 3), (429, 3)):
        n["c"] = 0
        try: await net.retry(mk(code), gap=0)
        except httpx.HTTPStatusError: pass
        check(f"net.retry: HTTP {code} tried {want}x", n["c"] == want, n["c"])
async def t_ws():
    sc = Scanner(asyncio.Queue()); closed = []
    class W:
        async def close(self): closed.append(1)
    sc._ws = W(); sc.force_reconnect(); await asyncio.sleep(0.01)
    check("wake closes the dead socket so ws resubscribes now", closed == [1] and sc._back_reset)
    sc._ws = None; sc.force_reconnect(); check("force_reconnect with no socket is safe", True)
async def t_creator():
    sc = Scanner(asyncio.Queue()); seen = []
    async def look(m): seen.append(m); db.x("update coins set creator='C' where mint=?", m); return "C"
    sc.lookup_creator = look
    db.x("insert into coins(mint,migrated_at,state,night) values('CR1',?, 'waiting','n')", time.time() - 15 * 60)
    c = db.q1("select * from coins where mint='CR1'")
    async def t10(m, p): return 10.0
    o = await sc.decide(c, pair(liq=50000, p1=10, mint="CR1"), time.time(), top10_fn=t10)
    check("missing creator re-looked-up before pass", seen == ["CR1"] and o and o["verdict"] == "pass", o)
def t_health():
    import health
    real_kill = os.kill
    def perm(p, s): raise PermissionError()
    def gone(p, s): raise ProcessLookupError()
    import subprocess as sp
    dummy = sp.Popen([sys.executable, "-c", "import time; time.sleep(30)", "main.py"])   # cmdline looks like the desk
    os.kill = perm; a = health.alive(dummy.pid); os.kill = real_kill; dummy.kill(); dummy.wait()
    check("health: PermissionError = process exists (no fake restart)", a is True)
    os.kill = gone; a = health.alive(os.getpid()); os.kill = real_kill
    check("health: ProcessLookupError = dead", a is False)
    check("health: non-desk pid not mistaken for desk", health.alive(1) is False or b"main.py" in open("/proc/1/cmdline", "rb").read())
    # paused box: every heartbeat incl. loop stale; the process wakes during the recheck -> no restart
    for a in ("loop", "scanner", "risk"): db.heartbeat(a); db.x("update heartbeats set ts=? where agent=?", time.time() - 3000, a)
    health.pid = lambda: os.getpid(); health.alive = lambda p=None: True
    orig = time.sleep
    def sl(s):
        for a in ("loop", "scanner", "risk"): db.heartbeat(a)
    time.sleep = sl; ran = []
    import subprocess; orig_run = subprocess.run; subprocess.run = lambda *a, **k: ran.append(a)
    out = health.check(); time.sleep = orig; subprocess.run = orig_run
    check("health: paused box that wakes is not restarted", out["restarted"] is None and out.get("box_pause") and out.get("recovered_after_wake") and not ran, out)
def t_guard_source():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")).read()
    check("stall guard skips box pauses (grace after own sleep jumps)", "grace_until" in src and "w1 - w0 > 30" in src)
    sc_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents", "scanner.py")).read()
    check("ws close on wake doesn't wait 10s for a dead peer", "close_timeout=2" in sc_src)
    check("loop_watch runs ordered wake recovery", "wake.on_wake(" in src and "RISK.poll_once" in src and "SCANNER.force_reconnect" in src)
async def main():
    await t_order(); await t_hang(); await t_double(); await t_retry(); await t_ws(); await t_creator()
asyncio.run(main()); t_health(); t_guard_source()
sys.exit(0 if summary("test_wake_recovery") else 1)
