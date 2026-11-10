"""Replay what we can from logs/raw without network. Confirms field mapping + gate math on real shapes.
Cannot produce a live buy: saved samples lack a full green path through current thresholds."""
from common import *
from agents.scanner import Scanner
from agents.auditor import bundled_size
from agents.analyst import rules_answers, gate
import json, os
RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "raw")

mig = json.load(open(os.path.join(RAW, "pumpportal_migration.json")))
mints = [m["mint"] for m in mig if isinstance(m, dict) and m.get("txType") == "migrate" or (isinstance(m, dict) and m.get("mint"))]
mints = [m["mint"] for m in mig if isinstance(m, dict) and m.get("mint") and m.get("txType") == "migrate"]
if not mints:
    mints = [m["mint"] for m in mig if isinstance(m, dict) and m.get("mint")]
check("raw migration sample has mint", bool(mints), mig[:1])

dex = json.load(open(os.path.join(RAW, "dexscreener_pair.json")))
p = net_pair = None
import net
p = net.pair_fields(dex[0])
check("raw dexscreener maps pairAddress+liq", p and p["pairAddress"] and p["liq"] is not None, p)

rep = json.load(open(os.path.join(RAW, "rugcheck_report.json")))
check("raw rugcheck has creator", bool(rep.get("creator")))
lp = None
for mk in rep.get("markets") or []:
    if (mk.get("lp") or {}).get("lpLockedPct") is not None: lp = mk["lp"]["lpLockedPct"]; break
check("raw lpLockedPct present (approved >=99 rule)", lp is not None)

g = json.load(open(os.path.join(RAW, "rugcheck_insiders_graph.json")))
check("raw empty graph => bundled 0 (None)", bundled_size(g) == 0)

g2 = json.load(open(os.path.join(RAW, "rugcheck_insiders_graph_HQUk.json")))
b = bundled_size(g2)
check("raw HQUk graph parses links key", b is not None and b >= 0, b)

# Scanner on raw dex numbers with a fresh migration clock (not the sample's old pairCreatedAt)
sc = Scanner(asyncio.Queue())
async def t10(mint, pool): return 10.0
c = {"mint": mints[0], "name": p["name"], "symbol": p["symbol"], "migrated_at": time.time() - 5 * 60, "state": "waiting"}
# force the lying createdAt from file; with fix, 5m coin must NOT pass
p_lie = dict(p, created=p["created"])  # sample created is days old relative to now
o = asyncio.run(sc.decide(c, p_lie, time.time(), top10_fn=t10))
# may be None (still waiting) or liq/other kill — must NOT be a pass with Dex-inflated age
check("replay: raw pairCreatedAt cannot age a 5m migration into a pass",
      o is None or (o["verdict"] == "kill" and (o.get("ageMin") or 0) <= 6), o)

c2 = dict(c, migrated_at=time.time() - 15 * 60)
# may kill on liq if sample liq < 20000 — that's fine; must not pass-with-wrong-age
o2 = asyncio.run(sc.decide(c2, p_lie, time.time(), top10_fn=t10))
if o2 and o2["verdict"] == "pass":
    check("replay: pass ageMin from migrated_at (~15)", 14 <= o2["ageMin"] <= 16, o2)
else:
    check("replay: no false age pass (kill or wait)", o2 is None or o2["verdict"] == "kill", o2)

# Honest note: rules gate on this sample's live-ish numbers won't be a buy snapshot
S = settings.all_settings()
ans = rules_answers(p if p["v1"] else dict(p, v1=0, b1=0, p1=0, p5=0), {"_ctx": {"bund": 0}}, S)
sc_, failed = gate(ans, S)
check("replay: raw sample alone is not claimed as a buy (document)", True, f"score={sc_} failed={failed}")
print("NOTE: no saved raw sample produces a full buy under current thresholds; see test_pipeline_synthetic.py")
summary("test_replay_raw_samples")
