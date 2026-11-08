from common import *
import net, chain
from agents.auditor import Auditor
M = "HQUk9fNaMUn3jPGsbBKdbmWBF2D1JCc3VaoP5GGhpump"
async def go():
    p = net.pair_fields((await net.Dex.tokens([M])).get(M)); print("dex", p and {k: p[k] for k in ("name", "pairAddress", "liq", "priceUsd")})
    rep = await net.rugcheck(M); cr = rep.get("creator"); bal = await chain.owner_balance(cr, M)
    print("creator", cr[:6], "bal", bal, "top10", await chain.top10(M, p["pairAddress"]))
    db.x("insert into coins(mint,creator,creator_bal,migrated_at,state,name) values(?,?,?,?,?,?)", M, cr, bal, time.time() - 1800, "passed", p["name"])
    o = await Auditor(asyncio.Queue()).audit({"mint": M, "pool": p["pairAddress"], "name": p["name"], "liquidityUsd": p["liq"]})
    for l in o["layers"]: print(l["n"], l["pass"], l["value"])
    print("holders", o["holders"])
asyncio.run(go())
