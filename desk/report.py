"""For the night-report routine: prints the night as markdown (every coin linked via links.coin_url).
python3 report.py [--clear]  (--clear empties db.skips after the Page is made)"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); os.chdir(os.path.dirname(os.path.abspath(__file__)))
import db, links
L = lambda m, n: f"[{n or m[:6]}]({links.coin_url(m)})"
import datetime as dt
# one window for everything: the night that just ended (08:00 -> 08:00 WIB); verdicts counted per coin seen in it
_n = db.night_id(time.time() - 3600)
since = dt.datetime.strptime(_n + " 08:00 +0700", "%Y-%m-%d %H:%M %z").timestamp(); until = since + 86400
out = []
l8 = db.kv_get("l8_killed", 0)
if l8: out.append(f"**Layer 8 was down: {l8} coins killed by 'no data: delegations'**\n")
ps = db.q("select * from positions where closed_at>=? and closed_at<? order by pnl", since, until)
for title, rows in (("Red trades", [p for p in ps if (p["pnl"] or 0) < 0]), ("Green trades", [p for p in ps if (p["pnl"] or 0) >= 0])):
    out.append(f"## {title}")
    out += [f"- {L(p['mint'], p['name'])} entry {p['entry']:.10g} → exit {p['exit_price']:.10g} · ${p['pnl']:+.2f} ({p['pct']:+.1f}%) · {p['exit_reason']} · fees ${p['fees']:.2f}" for p in rows] or ["- none"]
coins = db.q("select mint,name,state,raw from coins where migrated_at>=? and migrated_at<?", since, until)
pend = [c for c in coins if c["state"] == "waiting"]
bf = sum(1 for c in coins if '"_backfill"' in (c["raw"] or ""))
pz = db.q("select json from events where kind='box_pause' and ts>=? and ts<?", since, until)
out.append(f"## Coins seen: {len(coins)} (backfilled {bf}, still waiting {len(pend)})")
if pz: out.append(f"Box paused {len(pz)}x, {sum(json.loads(p['json'])['gap_s'] for p in pz)//60} min total: coins during pauses arrive late via backfill or are missed.")
for ag in ("scanner", "auditor", "analyst", "executor"):
    if ag == "scanner":   # from scans (kept forever), not skips (cleared each morning)
        rows = [dict(r, reason=json.loads(r["json"]).get("reason") or "") for r in db.q("select s.ts,s.mint,s.json from scans s join coins c using(mint) where c.migrated_at>=? and c.migrated_at<? order by s.ts", since, until) if json.loads(r["json"]).get("verdict") == "kill"]
    else:
        rows = db.q("select * from skips where agent=? and mint in (select mint from coins where migrated_at>=? and migrated_at<?) order by ts", ag, since, until)
    out.append(f"## {ag.capitalize()} {'kills' if ag=='scanner' else 'refusals' if ag=='auditor' else 'rejects' if ag=='analyst' else 'skips'}: {len(rows)}")
    by = {}
    for r in rows: by.setdefault(r["reason"].split(" ")[0] if ag == "scanner" else r["reason"], []).append(r)
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        names = ", ".join(L(r["mint"], (db.q1("select name from coins where mint=?", r["mint"]) or {}).get("name")) + (" " + time.strftime("%H:%M", time.localtime(r["ts"])) if ag == "auditor" else "") for r in v[:20])
        out.append(f"- {k} ({len(v)}): {names}")
toks = sum(json.loads(r["json"]).get("inputTokens") or 0 for r in db.q("select json from verdicts where ts>=? and ts<?", since, until))
out.append(f"## Jev tokens: {toks} (rules mode, cost $0)")
out.append(f"## Fees paid: ${sum(p['fees'] or 0 for p in ps):.2f}")
out.append(f"\nNew to FOMO? {links.SIGNUP_URL}")
print("\n".join(out))
if "--clear" in sys.argv: db.x("delete from skips where mint in (select mint from coins where migrated_at<?)", until)   # keep next night's early verdicts
