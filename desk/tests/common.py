import os, sys, tempfile
T = tempfile.mkdtemp(prefix="desktest_")
os.environ["DESK_DB"] = os.path.join(T, "t.db"); os.environ["DESK_SETTINGS"] = os.path.join(T, "s.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio, json, time
import db, config as settings
R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
def summary(t):
    bad = [n for n, ok in R if not ok]; print(f"== {t}: {len(R)-len(bad)}/{len(R)} pass" + (f" FAILED: {bad}" if bad else "")); return not bad
def pair(price=1.0, liq=100000, v1=30000, b1=200, s1=100, b5=20, s5=10, p5=-1, p1=10, mint="M"):
    return {"pairAddress": "POOL", "dexId": "pumpswap", "name": "Test", "symbol": "TST", "priceUsd": price, "liq": liq, "mcap": 1e6,
            "v5": 1000, "v1": v1, "v24": v1, "b5": b5, "s5": s5, "b1": b1, "s1": s1, "p5": p5, "p1": p1, "p24": p1, "created": None}
