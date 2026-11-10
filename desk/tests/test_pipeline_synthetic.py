"""SYNTHETIC end-to-end PAPER buy. Not from live raw samples — those never cleared the analyst gate
in the Nov 5 night (6 rejects: chase/alive/organic/score). This builds a deterministic candidate
that must reach executor and open a PAPER position without placing any real order."""
from common import *
from agents.auditor import Auditor
from agents.analyst import Analyst
from agents.executor import Executor
from telegram import NullNotifier

M = "SYNTHBUY" + str(time.time_ns())
now = time.time()
db.x("insert into coins(mint,name,symbol,pool,creator,creator_bal,migrated_at,state,liq0,night) values(?,?,?,?,?,?,?,?,?,?)",
     M, "SynthPass", "SYN", "POOLX", "CREATOR1", 100.0, now - 15 * 60, "passed", 80000, db.night_id())
scan = {"agent": "scanner", "mint": M, "name": "SynthPass", "symbol": "SYN", "pool": "POOLX",
        "liquidityUsd": 80000, "top10Pct": 12, "h1ChangePct": 5, "ageMin": 15, "verdict": "pass", "reason": None}
db.x("insert into scans(ts,mint,json) values(?,?,?)", now, M, json.dumps(scan))

async def ai(m):
    return {"value": {"data": {"parsed": {"info": {
        "mintAuthority": None, "freezeAuthority": None, "supply": "1000000000000000", "decimals": 6}}}}}
async def bal(owner, mint): return 100.0
async def top10(mint, pool, sup=None): return 12.0
async def report(mint, which="report"):
    return {"markets": [{"pubkey": "POOLX", "lp": {"lpLockedPct": 100}}], "creator": "CREATOR1"}
async def graph(mint, which="graph"): return []
async def gpa(mint): return []
async def dex_tokens(mints):
    return {mints[0]: {
        "pairAddress": "POOLX", "dexId": "pumpswap",
        "baseToken": {"address": mints[0], "name": "SynthPass", "symbol": "SYN"},
        "priceUsd": "0.001", "liquidity": {"usd": 80000}, "marketCap": 100000,
        "volume": {"m5": 5000, "h1": 40000, "h24": 40000},
        "txns": {"m5": {"buys": 40, "sells": 10}, "h1": {"buys": 200, "sells": 80}},
        "priceChange": {"m5": -6, "h1": 10, "h24": 10},
        "pairCreatedAt": int((now - 15 * 60) * 1000)}}

au_q, an_q, ex_q = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
src = {"account_info": ai, "owner_balance": bal, "top10": top10, "report": report, "graph": graph,
       "program_accounts": gpa, "dex": dex_tokens}
au = Auditor(an_q, src=src)
o_au = asyncio.run(au.audit(scan))
check("SYNTHETIC auditor 8/8 pass", o_au and o_au["passed"] and o_au["layersChecked"] == 8, o_au and o_au.get("reason"))

pair = {"pairAddress": "POOLX", "dexId": "pumpswap", "name": "SynthPass", "symbol": "SYN", "priceUsd": 0.001,
        "liq": 80000, "mcap": 100000, "v5": 5000, "v1": 40000, "v24": 40000, "b5": 40, "s5": 10, "b1": 200, "s1": 80,
        "p5": -6, "p1": 10, "p24": 10, "created": (now - 15 * 60) * 1000}
an = Analyst(ex_q)
item = an_q.get_nowait()
o_an = asyncio.run(an.analyse(item[0], item[1], pair))
check("SYNTHETIC analyst pass", o_an and o_an["passed"] and o_an["score"] >= 70, o_an)

N = NullNotifier()
ex = Executor(N, dex=dex_tokens)
item2 = ex_q.get_nowait()
db.kv_set("paper_balance", 200)
o_ex = asyncio.run(ex.execute(item2[0], item2[1], item2[2]))
check("SYNTHETIC PAPER buy (no real order)", o_ex and o_ex["status"] == "bought" and o_ex["mode"] == "PAPER", o_ex)
check("SYNTHETIC position open", db.q1("select status from positions where mint=?", M)["status"] == "open")
check("SYNTHETIC telegram buy text", N.sent and N.sent[0]["text"].startswith("PAPER · Buy SynthPass"),
      (N.sent[0]["text"][:80] if N.sent else None))
summary("test_pipeline_synthetic")
