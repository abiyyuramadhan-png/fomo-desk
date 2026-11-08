from common import *
from agents.auditor import Auditor
async def ai(m): return {"value": {"data": {"parsed": {"info": {"mintAuthority": None, "freezeAuthority": "FrzAuth1111111111111111111111111111111111", "supply": "1000000000000000", "decimals": 6}}}}}
db.x("insert into coins(mint,creator,creator_bal,migrated_at,state) values('FRZ','C',0,?, 'passed')", time.time() - 3600)
a = Auditor(asyncio.Queue(), src={"account_info": ai})
o = asyncio.run(a.audit({"mint": "FRZ", "pool": "P", "name": "Frozen", "liquidityUsd": 50000}))
L = o["layers"]
check("red at layer 2", not o["passed"] and L[1]["pass"] is False and L[1]["value"] == "freeze not revoked", L[1])
check("layer 1 ok Revoked", L[0]["pass"] and L[0]["value"] == "Revoked")
check("layers 3-8 not checked", all(l["pass"] is None and l["value"] == "not checked" for l in L[2:]) and len(L) == 8)
act = db.q1("select * from activity where mint='FRZ'"); check("Activity 'Rejected Frozen / Auditor · freeze not revoked / Skipped'", act["title"] == "Rejected Frozen" and act["sub"] == "Auditor · freeze not revoked" and act["value"] == "Skipped")
print(json.dumps({k: v for k, v in o.items() if not k.startswith("_")}, indent=0)[:900])
summary("test_auditor (layer 2)")
