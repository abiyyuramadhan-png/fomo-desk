from common import *
import api as publisher, links
from agents.auditor import Auditor
from agents.analyst import Analyst
from agents.risk import Risk
from telegram import NullNotifier
out = sys.argv[1]
def dump(name, mints=()):
    d = os.path.join(out, name); os.makedirs(d + "/coin", exist_ok=True)
    for f, o in zip(("state", "chart", "activity"), publisher.snapshot()): json.dump(o, open(f"{d}/{f}.json", "w"), default=str)
    for m in mints: json.dump(publisher.coin_doc(m, settings.all_settings(), time.time()), open(f"{d}/coin/{m}.json", "w"), default=str)
dump("empty")
now = time.time(); M1, M2, M3 = "HQUk9fNaMUn3jPGsbBKdbmWBF2D1JCc3VaoP5GGhpump", "E8wkr6QdcopbpEXqgYNFUuAwN7AiiyvbrhRtaadapump", "3bJoG3fTVxfFW6ukgNkBQHHtYxim2gXhMvw2TtJLpump"
for m, n, s in ((M1, "Graft Model", "GRAFT"), (M2, "Laughing Monkey Coin", "LMC"), (M3, "Moon Cat", "MCAT")):
    db.x("insert into coins(mint,name,symbol,pool,migrated_at,state,night,holders) values(?,?,?,?,?,?,?,?)", m, n, s, "POOL", now - 3000, "passed", db.night_id(), 161)
for m, n, v, r, liq in ((M1, "Graft Model", "pass", None, 52000), (M2, "Laughing Monkey Coin", "kill", "liq $3.7K", 3.67), (M3, "Moon Cat", "kill", "top 10 hold 38%", 61000)):
    db.x("insert into scans(ts,mint,json) values(?,?,?)", now, m, json.dumps({"agent": "scanner", "mint": m, "name": n, "verdict": v, "reason": r, "liquidityUsd": liq}))
L = [{"n": i, "name": nm, "pass": True, "value": vv, "source": "rpc"} for i, (nm, vv) in enumerate([("Mint authority", "Revoked"), ("Freeze authority", "Revoked"), ("Dev wallet", "1.1% · sold 0"), ("Top 10 holders", "24.4%"), ("Liquidity", "100% locked/burned"), ("Pool age", "30m"), ("Bundled wallets", "4 linked"), ("Delegations", "None")], 1)]
db.x("insert into audits(ts,mint,json) values(?,?,?)", now, M3, json.dumps({"mint": M3, "passed": False, "reason": "freeze not revoked", "layers": L[:1] + [dict(L[1], **{"pass": False, "value": "freeze not revoked"})] + [dict(l, **{"pass": None, "value": "not checked"}) for l in L[2:]]}))
db.x("insert into audits(ts,mint,json) values(?,?,?)", now, M1, json.dumps({"mint": M1, "passed": True, "reason": None, "layers": L, "holders": 161}))
db.x("insert into verdicts(ts,mint,json) values(?,?,?)", now, M1, json.dumps({"mint": M1, "answers": {"alive_6h": 0.92, "organic": 0.81, "flush": 0.5, "chase": 0.12}, "score": 78, "passed": True, "failed": [], "model": "rules"}))
db.x("insert into signals(ts,mint,json) values(?,?,?)", now, M1, json.dumps({"mint": M1, "sizeUsd": 47.5, "stackPct": 23.8, "status": "bought", "link": links.coin_url(M1)}))
import random; random.seed(3); p = 1.0e-5
for i in range(240):
    p *= 1 + random.uniform(-0.03, 0.035); db.x("insert into prices(ts,mint,price,vol_m5) values(?,?,?,?)", now - (240 - i) * 15, M1, p, 1000)
db.x("insert into positions(mint,name,mode,entry,size,peak,stop_pct,trail_active,opened_at,status,last_price,last_liq,night) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
     M1, "Graft Model", "PAPER", 1.0e-5, 47.5, p * 1.05, 6, 1, now - 3600, "open", p, 52000, db.night_id())
db.activity("executor", "buy", M1, "Graft Model", "Bought Graft Model", "Executor · 12:31", "$47.50 · 23.8% of stack", "cyan")
db.activity("auditor", "reject", M3, "Moon Cat", "Rejected Moon Cat", "Auditor · freeze not revoked", "Skipped", "red")
db.activity("risk", "stop", M2, "Laughing Monkey Coin", "Stopped Laughing Monkey Coin", "Risk · -6% stop", "-$3.61", "red")
for a in ("scanner", "auditor", "analyst", "executor", "risk"): db.heartbeat(a)
dump("full", [M1])
print(M1)
