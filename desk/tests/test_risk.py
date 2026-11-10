from common import *
from agents.risk import Risk
from agents.executor import Executor
from telegram import NullNotifier
import links
N = NullNotifier(); clock = [time.time()]
def mkpos(mint, entry=1.0, size=47.5, stop=None):
    db.x("insert into positions(mint,name,mode,entry,size,peak,stop_pct,opened_at,status,last_price,last_liq,night) values(?,?,?,?,?,?,?,?,?,?,?,?)",
         mint, mint, "PAPER", entry, size, entry, stop if stop is not None else settings.get("risk.stop_pct"), clock[0], "open", entry, 1e5, "n")
    return db.q1("select * from positions where mint=? order by id desc", mint)
rk = Risk(N, clock=lambda: clock[0])
async def feed(mint, prices):
    out = None
    for p in prices:
        pos = db.q1("select * from positions where mint=? and status='open'", mint)
        if not pos: break
        out = await rk.step(pos, {"priceUsd": p, "liq": 1e5, "v5": 1})
    return out
o = asyncio.run(feed("TRAIL", [mkpos("TRAIL")["entry"], 1.25, 1.25 * 0.87]))
check("+25% then 13% off top = trail exit", o and o["reason"] == "trail", o and o["reason"])
mkpos("STOP"); o = asyncio.run(feed("STOP", [0.939])); check("-6.1% = stop", o and o["reason"] == "stop", o and o["reason"])
mkpos("TIME"); clock[0] += 3 * 3600; o = asyncio.run(feed("TIME", [1.04])); check("3h at +4% = timeout", o and o["reason"] == "timeout", o and o["reason"])
clock[0] = time.time()
mkpos("OLD")   # opened at -6%
ok, msg = settings.set_value("risk.stop_pct", "-8%"); check('"set stop to -8%" reply', msg == "stop -6% -> -8%", msg)
rk.apply_tighter_stop()
check("loosening never moves an open stop down", db.q1("select stop_pct from positions where mint='OLD'")["stop_pct"] == 6)
new = mkpos("NEW"); check("new position takes -8%", new["stop_pct"] == 8)
o = asyncio.run(feed("NEW", [0.919]))
act = db.q1("select * from activity where mint='NEW'")
check("NEW drop 8.1% -> push reads -8%", o and o["reason"] == "stop" and "hit the -8% stop" in o["_text"], o and o["_text"])
check("Activity row reads -8%", act and act["sub"] == "Risk · -8% stop", act and act["sub"])
check("exit mark stopPct 8", o and o["stopPct"] == 8)
import api as publisher; st, _ch, _ac = publisher.snapshot()
check("Risk pill reads stop -8%", [a for a in st["agents"] if a["id"]=="risk"][0]["pills"][0]["text"] == "stop -8%")
check("position opened at -6% still shows -6%", [p for p in st["positions"] if p["mint"] == "OLD"][0]["stop_pct"] == 6)
check("PAPER pushes start 'PAPER · ' and carry coin_url", all(m["text"].startswith("PAPER · ") for m in N.sent) and all(links.coin_url(m["text"].split("address=")[1].split("&")[0]) in m["text"] for m in N.sent), [m["text"] for m in N.sent])
settings.set_value("risk.stop_pct", 5); rk.apply_tighter_stop()
check("tighter stop applies to open positions", db.q1("select stop_pct from positions where mint='OLD'")["stop_pct"] == 5)
summary("test_risk")
