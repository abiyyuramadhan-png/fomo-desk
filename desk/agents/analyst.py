"""Agent 3 · Analyst. Builds a numbers-only state, gets 4 answers in 0-1, code applies the gate."""
import asyncio, json, time, logging, hashlib, os
import db, net, config as settings
flog = logging.getLogger("analyst.file")
clamp = lambda v, a=0.0, b=1.0: max(a, min(b, v))
QUESTIONS = {
 "alive_6h": {"type": "noul", "instructions": "This coin is still actively traded 6 hours from now"},
 "organic": {"type": "noul", "instructions": "Most buyers in the last 30 minutes are separate real wallets"},
 "flush": {"type": "noul", "instructions": "Price just flushed down and buyers are absorbing it"},
 "chase": {"type": "noul", "instructions": "This entry is chasing a green candle that already ran"}}
def build_state(scan, audit, p):
    c = audit.get("_ctx", {})
    s = (f"Coin {scan.get('name')} on Solana, graduated {scan.get('ageMin')} min ago. Liquidity ${p['liq']:,.0f}. Market cap ${(p['mcap'] or 0):,.0f}.\n"
         f"Last 5 min: {p['b5']} buys, {p['s5']} sells, volume ${(p['v5'] or 0):,.0f}, price {p['p5']}%.\n"
         f"Last 1h: {p['b1']} buys, {p['s1']} sells, volume ${(p['v1'] or 0):,.0f}, price {p['p1']}%.\n"
         f"Top 10 hold {c.get('top10')}%. Dev holds {round(c.get('dev') or 0, 2)}%, sold 0. LP {c.get('lp')}. Bundled {c.get('bund')}. Delegations {c.get('del')}.")
    return s[:3000]
def rules_answers(p, audit, S):
    alive = clamp((p["v1"] or 0) / S["analyst.alive_volume_h1"])
    org = clamp((p["b1"] or 0) / S["analyst.organic_buys_h1"])
    if (audit.get("_ctx", {}).get("bund") or 0) >= S["analyst.bundled_from"]: org *= S["analyst.bundled_penalty"]
    p5 = p["p5"] or 0
    flush = 1.0 if (p5 <= -S["analyst.flush_drop_m5_pct"] and (p["b5"] or 0) >= (p["s5"] or 0)) else (0.5 if p5 < 0 else 0.0)
    chase = clamp((p["p1"] or 0) / S["analyst.chase_h1_pct"])
    return {"alive_6h": round(alive, 4), "organic": round(org, 4), "flush": flush, "chase": round(chase, 4)}
def gate(a, S):
    failed = []
    if a["alive_6h"] < S["analyst.min_alive_6h"]: failed.append(f"alive_6h {a['alive_6h']:.2f}")
    if a["organic"] < S["analyst.min_organic"]: failed.append(f"organic {a['organic']:.2f}")
    if a["chase"] > S["analyst.max_chase"]: failed.append(f"chase {a['chase']:.2f}")
    score = round(100 * (a["alive_6h"] + a["organic"] + a["flush"] + (1 - a["chase"])) / 4)
    if score < S["analyst.min_score"]: failed.append(f"score {score}")
    return score, failed
class Analyst:
    def __init__(self, out_q, dex=None):
        self.out = out_q; self.paused = False; self.dex = dex or net.Dex.tokens
    async def jev(self, state, S):
        key = os.environ.get("TYPESAFE_API_KEY")
        body = {"model": "jev-latest", "state": state, "questions": QUESTIONS}
        for i in range(2):
            try:
                r = await net.client().post("https://api.typesafe.ai/v1/systemone", json=body, timeout=S["analyst.timeout_s"],
                                            headers={"Authorization": f"Bearer {key}"})
                r.raise_for_status(); j = r.json()
                return {k: j["answers"][k]["noul"] for k in QUESTIONS}, j.get("model"), (j.get("usage") or {}).get("input_tokens", 0)
            except Exception:
                if i == 0: await asyncio.sleep(2)
        return None, None, 0
    async def analyse(self, scan, audit, p=None):
        S = settings.all_settings(); mint = scan["mint"]
        if db.q1("select 1 from verdicts where mint=?", mint): return None
        if p is None: p = net.pair_fields((await net.retry(self.dex, [mint])).get(mint))
        mode = S["analyst.mode"]
        failed, a, model, tok = [], None, "rules", 0
        if not p or p["liq"] is None: failed = ["no answer"]
        elif mode == "rules": a = rules_answers(p, audit, S)
        else:
            a, model, tok = await self.jev(build_state(scan, audit, p), S)
            if a is None: failed = ["no answer"]
            elif any((not isinstance(v, (int, float))) or v < 0 or v > 1 for v in a.values()): failed, a = ["bad answer"], None
        score = None
        if a:
            score, failed = gate(a, S)
        o = {"agent": "analyst", "mint": mint, "answers": a, "score": score, "passed": not failed, "failed": failed,
             "model": model, "inputTokens": tok, "_pair": p}
        db.x("insert into verdicts(ts,mint,json) values(?,?,?)", time.time(), mint, json.dumps(o))
        flog.info("%s state=%s %s score=%s passed=%s tokens=%s", mint, hashlib.sha1(build_state(scan, audit, p).encode()).hexdigest()[:10] if p else None,
                  a, score, o["passed"], tok)
        name = scan.get("name") or mint[:6]
        lab = "Analyst (rules)" if model == "rules" else "Analyst"
        if o["passed"]: self.out.put_nowait((scan, audit, o))
        else:
            db.activity("analyst", "reject", mint, name, f"Rejected {name}", f"{lab} · {failed[0]}", "Skipped", "red")
            db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", time.time(), mint, "analyst", failed[0])
        return o
