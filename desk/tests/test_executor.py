from common import *
import links
from agents.executor import size_for, Executor
from commands import Desk
from telegram import NullNotifier
S = settings.all_settings()
s, cap, why = size_for(200, 1e6, S); check("stack $200 -> $16 -> under $47.50 -> bump (free covers) = $47.50", s == 47.5 and cap == "bumped", (s, cap))
s, cap, why = size_for(200, 1e6, S, free=30); check("bump but free $30 < $47.50 -> skip 'under $47.50'", s == 0 and why == "under $47.50", why)
check("raw size is $16", 200 * S["executor.stack_pct"] / 100 == 16)
settings.set_value("executor.below_min", "skip"); S2 = settings.all_settings()
s, cap, why = size_for(200, 1e6, S2); check("below_min=skip -> 'under $47.50'", s == 0 and why == "under $47.50", why)
d = Desk({}, NullNotifier()); w = d.ticket_check()
check('PAPER start $200 with skip -> "every coin will be skipped"', w and w.startswith("every coin will be skipped, stack under $593.75"), w)
settings.set_value("executor.below_min", "bump"); w = d.ticket_check(); check("bump warning text", w == "tickets bumped to $47.50 = 23.8% of stack", w)
s, cap, why = size_for(1e6, 40000, settings.all_settings()); check("pool liquidity $40,000 caps size at max_pool_pct = $800", s == 800 and cap == "pool", (s, cap))
def dex(price=1, liq=1e6):
    async def f(m): return {m[0]: {"baseToken": {"address": m[0], "name": "E", "symbol": "E"}, "dexId": "pumpswap", "priceUsd": str(price), "liquidity": {"usd": liq}, "volume": {}, "txns": {}, "priceChange": {}}} if price else {}
    return f
N = NullNotifier(); ex = Executor(N, dex=dex())
o = asyncio.run(ex.execute({"mint": "EXM", "name": "E"}, {}, {"score": 80, "_pair": {"liq": 1e6, "priceUsd": 1}}))
m = N.sent[0]; kb = m["reply_markup"]["inline_keyboard"]
exp = f"PAPER · Buy E · $47.50 · 23.8% of stack\nAuditor 8/8 · Analyst 80 · stop -{S['risk.stop_pct']:g}% · trail {S['risk.trail_pct']:g}%"
check("push text exact", m["text"] == exp, m["text"])
check("buttons [Buy on FOMO]=coin_url, [Bought], [Skip]", kb[0][0]["text"] == "Buy on FOMO" and kb[0][0]["url"] == links.coin_url("EXM") and [b["text"] for b in kb[1]] == ["Bought", "Skip"], kb)
check("PAPER fill", o["status"] == "bought")
o2 = asyncio.run(ex.execute({"mint": "EXM", "name": "E"}, {}, {"score": 80})); check("1 push per coin per night", o2 is None)
def run(mint, d, an):
    return asyncio.run(Executor(NullNotifier(), dex=d).execute({"mint": mint, "name": mint}, {}, an))
check("no price -> 'no price'", run("NP", dex(price=0), {"score": 80})["reason"] == "no price")
check("liq down >20% -> 'liquidity dropping'", run("LQ", dex(liq=7e5), {"score": 80, "_pair": {"liq": 1e6, "priceUsd": 1}})["reason"] == "liquidity dropping")
check("price up >15% -> 'ran before the push'", run("RN", dex(price=1.2), {"score": 80, "_pair": {"liq": 1e6, "priceUsd": 1}})["reason"] == "ran before the push")
db.kv_set("paper_balance", 100)  # stack 100, EXM open $47.50 -> free 52.5; mint new with bump -> 47.5 ok; then free 5 -> skip
o3 = run("F1", dex(), {"score": 80}); o4 = run("F2", dex(), {"score": 80})
check("size > free -> skip (under $47.50 when bump can't be covered / 'no free stack')", o3["status"] == "bought" and o4["status"] == "skipped" and o4["reason"] in ("under $47.50", "no free stack"), (o3["status"], o4["reason"]))
check("skips written to db.skips", db.q1("select count(*) n from skips where agent='executor'")["n"] >= 4)
class Fail(NullNotifier):
    async def send(self, *a, **k): return False
o5 = asyncio.run(Executor(Fail(), dex=dex()).execute({"mint": "PF", "name": "PF"}, {}, {"score": 80})) if db.kv_set("paper_balance", 1000) or True else None
check("Telegram failure: PAPER fills anyway, logs 'push failed'", o5["status"] == "bought" and o5["reason"] == "push failed", o5)
summary("test_executor")
