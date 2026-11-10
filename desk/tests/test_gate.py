from common import *
from agents.analyst import gate, rules_answers, Analyst
S = settings.all_settings()
base = {"alive_6h": 0.70, "organic": 0.65, "flush": 0.9, "chase": 0.30}
sc, f = gate(base, S); check("all at threshold pass (jev answers)", not f, f"score {sc}")
for k, v in (("alive_6h", 0.69), ("organic", 0.64), ("chase", 0.31)):
    sc, f = gate(dict(base, **{k: v}), S); check(f"{k} {v} rejects", f and f[0].startswith(k), f)
sc, f = gate({"alive_6h": 0.70, "organic": 0.65, "flush": 0.71, "chase": 0.30}, S); check("score 69 rejects", sc == 69 and f == ["score 69"], (sc, f))
sc, f = gate({"alive_6h": 0.70, "organic": 0.65, "flush": 0.75, "chase": 0.30}, S); check("score 70 passes", sc == 70 and not f, (sc, f))
# rules mode with fake DexScreener numbers
au = {"_ctx": {"bund": 0}}
def run(p):
    q = asyncio.Queue(); a = Analyst(q)
    m = "R" + str(time.time_ns()); o = asyncio.run(a.analyse({"mint": m, "name": "RulesCoin"}, au, p))
    act = db.q1("select sub from activity where mint=?", m); return o, act
o, act = run(pair(v1=17500, b1=97.5, p1=24, p5=-6, b5=20, s5=10))   # alive .70 organic .65 chase .30 flush 1 -> 79
check("rules: all at threshold pass", o["passed"] and o["model"] == "rules" and o["inputTokens"] == 0, o["answers"])
o, act = run(pair(v1=17250, b1=200, p1=10)); check("rules: alive 0.69 rejects, Activity 'Analyst (rules)'", not o["passed"] and act and act["sub"].startswith("Analyst (rules) · alive_6h 0.69"), act)
o, act = run(pair(v1=30000, b1=96, p1=10)); check("rules: organic 0.64 rejects", act and "organic 0.64" in act["sub"], act)
o, act = run(pair(v1=30000, b1=200, p1=24.8)); check("rules: chase 0.31 rejects", act and "chase 0.31" in act["sub"], act)
o, act = run(pair(v1=21750, b1=105, p1=24, p5=-1)); check("rules: score 69 rejects", act and "score 69" in act["sub"], (o["score"], act))
o, act = run(pair(v1=22500, b1=105, p1=24, p5=-1)); check("rules: score 70 passes", o["passed"] and o["score"] == 70, o["score"])
au2 = {"_ctx": {"bund": 3}}; S2 = settings.all_settings()
check("rules: bundled 3+ halves organic", rules_answers(pair(b1=150), au2, S2)["organic"] == 0.5)
summary("test_gate")
