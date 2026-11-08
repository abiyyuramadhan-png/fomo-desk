"""Regression: scanner age uses migrated_at; max_wait blocks late/backfill passes."""
from common import *
from agents.scanner import Scanner

async def t10_ok(mint, pool): return 10.0
async def t10_fail(mint, pool): raise RuntimeError("rpc down")

def coin(mint, age_min):
    return {"mint": mint, "name": "C", "symbol": "C", "migrated_at": time.time() - age_min * 60,
            "creator": "X", "creator_bal": 0, "state": "waiting"}

def dex_pair(created_ms=None, liq=50000, p1=10):
    # created_ms defaults to "87k minutes ago" — the DexScreener lie that used to force a pass
    if created_ms is None: created_ms = (time.time() - 87567 * 60) * 1000
    return {"pairAddress": "POOL", "dexId": "pumpswap", "name": "C", "symbol": "C", "priceUsd": 1.0,
            "liq": liq, "mcap": 1e6, "v5": 1, "v1": 1, "v24": 1, "b5": 1, "s5": 1, "b1": 1, "s1": 1,
            "p5": 0, "p1": p1, "p24": 0, "created": created_ms}

sc = Scanner(asyncio.Queue())

# Bug 1: bogus pairCreatedAt must NOT age the coin; migrated_at=5 min < min_pool_age 10 → keep waiting
o = asyncio.run(sc.decide(coin("AGE1", 5), dex_pair(), time.time(), top10_fn=t10_ok))
check("bogus pairCreatedAt does not instant-pass a 5m coin", o is None, o)

# at 10 min with good top10 → pass, ageMin reflects migrated_at not Dex age
o = asyncio.run(sc.decide(coin("AGE2", 10), dex_pair(), time.time(), top10_fn=t10_ok))
check("10m migrated_at passes with ageMin≈10", o and o["verdict"] == "pass" and 9 <= o["ageMin"] <= 11, o)

# Bug 2: past max_wait (60) must kill even when liq/top10/h1 look fine (backfill late path)
o = asyncio.run(sc.decide(coin("LATE1", 84), dex_pair(p1=-1), time.time(), top10_fn=t10_ok))
check("84m coin killed never qualified (not pass)", o and o["verdict"] == "kill" and o["reason"] == "never qualified", o)

o = asyncio.run(sc.decide(coin("LATE2", 61), dex_pair(), time.time(), top10_fn=t10_ok))
check("61m coin killed never qualified", o and o["verdict"] == "kill" and o["reason"] == "never qualified", o)

# exactly 60 min still allowed to pass (same `now` so wait_min is not 60.00x from clock drift)
now = time.time()
c = {"mint": "EDGE1", "name": "C", "symbol": "C", "migrated_at": now - 60 * 60, "state": "waiting"}
o = asyncio.run(sc.decide(c, dex_pair(), now, top10_fn=t10_ok))
check("60m coin may still pass", o and o["verdict"] == "pass", o)

# low liq still kills before window logic
o = asyncio.run(sc.decide(coin("LIQ1", 15), dex_pair(liq=1000), time.time(), top10_fn=t10_ok))
check("low liq still kills", o and o["verdict"] == "kill" and o["reason"].startswith("liq"), o)

summary("test_scanner_window")
