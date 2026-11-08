"""Regression: backfill sweep must beat per tx, time out hung RPCs, and respect its time budget."""
import asyncio, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backfill
ok = 0; tot = 0
def check(n, c):
    global ok, tot; tot += 1; ok += bool(c); print(("PASS" if c else "FAIL"), n)
async def main():
    sigs = [(f"sig{i}", time.time()) for i in range(10)]
    async def fake_recent(since): return sigs
    calls = {"m": 0}
    async def fake_mint(sig): calls["m"] += 1; await asyncio.sleep(0.05); return sig + "pump"
    backfill.recent, backfill.mint_of = fake_recent, fake_mint
    beats = []
    got = await backfill.sweep(lambda s: False, 3600, gap=0, beat=lambda: beats.append(1))
    check("beats once per tx", len(beats) == 10)
    check("all found", len(got) == 10)
    t = time.monotonic(); beats.clear()
    got = await backfill.sweep(lambda s: False, 3600, gap=0.1, beat=lambda: beats.append(1), budget_s=0.3)
    check("budget stops sweep early", len(got) < 10 and time.monotonic() - t < 1.5)
    # hung RPC -> rpc() raises within bounded time instead of hanging forever
    class Hang:
        async def post(self, *a, **k): await asyncio.sleep(3600)
    backfill._c = Hang(); orig = asyncio.wait_for
    async def fast_wait(aw, t): return await orig(aw, 0.05)
    asyncio.wait_for = fast_wait
    t = time.monotonic()
    try: await backfill.rpc("x", []); r = False
    except RuntimeError as e: r = "TimeoutError" in str(e)
    asyncio.wait_for = orig
    check("hung RPC raises with error type", r and time.monotonic() - t < 15)
asyncio.run(main()); print(f"{ok}/{tot}"); sys.exit(ok != tot)
