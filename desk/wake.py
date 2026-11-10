"""Box-pause wake handling. The box can freeze the whole process for minutes to hours.
On wake, open positions must be re-priced (Risk) before anything else uses the network.
loop_watch() in main.py drives this; other loops call gate() before doing work."""
import asyncio, time
GAP_S = 60                    # wall-clock jump that counts as a pause
GATE_TIMEOUT_S = 30           # never block other agents longer than this
last_tick = time.time()       # wall time of the last loop_watch tick
risk_done = asyncio.Event(); risk_done.set()
def woke(now=None):
    """True if the loop ticker hasn't run for > GAP_S of wall time (we're the first code to run after a pause)."""
    return (now or time.time()) - last_tick > GAP_S
async def gate():
    """Hold non-Risk work while the post-wake Risk refresh runs (bounded)."""
    if woke(): risk_done.clear()          # loop_watch will refresh Risk and set it
    if risk_done.is_set(): return False
    try: await asyncio.wait_for(risk_done.wait(), GATE_TIMEOUT_S)
    except asyncio.TimeoutError: pass
    return True
async def on_wake(gap_s, risk_refresh, resubscribe, backfill, reset_http, log, timeout=20):
    """Ordered recovery: fresh HTTP pool -> Risk re-prices open positions -> release others -> resubscribe ws -> backfill."""
    global last_tick
    last_tick = time.time(); risk_done.clear()
    t0 = time.monotonic(); steps = {}
    try:
        try: reset_http()
        except Exception as e: log.warning("wake: http reset failed %s", type(e).__name__)
        try:
            r = await asyncio.wait_for(risk_refresh(), timeout); steps["risk"] = f"ok {len(r or [])} exits"
        except Exception as e: steps["risk"] = f"failed {type(e).__name__} {e}"[:120]
    finally:
        risk_done.set()
    steps["risk_s"] = round(time.monotonic() - t0, 1)
    try: resubscribe(); steps["ws"] = "resubscribe"
    except Exception as e: steps["ws"] = f"failed {type(e).__name__}"
    try: backfill(); steps["backfill"] = "started"
    except Exception as e: steps["backfill"] = f"failed {type(e).__name__}"
    log.warning("wake after %.0fs pause: %s", gap_s, steps)
    return steps
