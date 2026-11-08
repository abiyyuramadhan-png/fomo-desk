"""api.py · Plan B JSON writer: state.json chart.json activity.json coin/{mint}.json under /d/{DATA_PATH}/.
Publisher: snapshot -> d/{DATA_PATH}/state.json on rolling branch s{slot} (slot = unix//15).
raw.githubusercontent caches a branch URL ~5 min, so every slot gets a new branch name = fresh cache key.
The app computes the slot from its clock. Old slot branches are deleted in the same push."""
import json, os, time, asyncio, logging, shutil
import db, links, gitpush, config as settings
from agents.executor import stack_now, in_positions
log = logging.getLogger("publisher")
ROOT = os.path.dirname(os.path.abspath(__file__))
def data_path():
    """Private publish directory name. The systemd env file wins; .secrets is the box fallback."""
    env = os.environ.get("DATA_PATH", "").strip()
    if env:
        return env
    secrets = os.path.join(ROOT, ".secrets")
    if os.path.isfile(secrets):
        for l in open(secrets):
            if l.startswith("DATA_PATH="):
                return l.strip().split("=", 1)[1]
    raise RuntimeError("DATA_PATH is not set")
SLOT = 15
def J(r, k="json"):
    o = json.loads(r[k]); return {a: b for a, b in o.items() if not a.startswith("_")} if isinstance(o, dict) else o
def hb_ok(a, hb, now): return a in hb and now - hb[a] < 120
GROUPS = ["scanner", "auditor", "analyst", "executor", "risk", "desk"]
def agents_cards(S, now):
    hb = {r["agent"]: r["ts"] for r in db.q("select * from heartbeats")}; paused = db.kv_get("paused", [])
    st = lambda a: "paused" if a in paused else ("live" if hb_ok(a, hb, now) else "down")
    night = db.night_id()
    scans = [J(r) for r in db.q("select json from scans order by id desc limit 20")]
    audits = [J(r) for r in db.q("select json from audits order by id desc limit 20")]
    verd = [J(r) for r in db.q("select json from verdicts order by id desc limit 20")]
    sig = [J(r) for r in db.q("select json from signals order by id desc limit 20")]
    for L in (scans, audits, verd, sig):
        for o in L: o["link"] = links.coin_url(o["mint"]); o["name"] = o.get("name") or (db.q1("select name from coins where mint=?", o["mint"]) or {}).get("name")
    exits = db.q("select * from positions where status='closed' order by closed_at desc limit 20")
    open_ = db.q("select * from positions where status in ('open','exiting')")
    n = lambda sql, *a: db.q1(sql, *a)["n"]
    return [
     {"id": "scanner", "n": 1, "title": "Scanner", "status": st("scanner"), "headline": f"{n('select count(*) n from coins where night=?', night)} pools",
      "sub": f"{n('select count(*) n from coins where state=?', 'waiting')} in the waiting room", "decisions": scans},
     {"id": "auditor", "n": 2, "title": "Auditor", "status": st("auditor"), "headline": f"{n('select count(*) n from audits')} taken apart",
      "sub": f"{n('select count(*) n from audits where json like ?', '%\"passed\": false%')} rejected", "running": False, "last": audits[0] if audits else None, "decisions": audits},
     {"id": "analyst", "n": 3, "title": "Analyst (rules)" if S["analyst.mode"] == "rules" else "Analyst", "status": st("analyst"), "headline": "Scoring",
      "score": verd[0]["score"] if verd else None, "minScore": S["analyst.min_score"], "decisions": verd},
     {"id": "executor", "n": 4, "title": "Executor", "status": st("executor"), "headline": f"{n('select count(*) n from positions')} trades",
      "sub": (f"${sig[0]['sizeUsd']:.2f} · {sig[0]['stackPct']:g}% of stack" if sig else f"{S['executor.stack_pct']:g}% of stack"), "last": sig[0] if sig else None, "decisions": sig},
     {"id": "risk", "n": 5, "title": "Risk", "status": st("risk"), "headline": "Guarding" if open_ else "Idle",
      "sub": ("Trailed out" if exits and exits[0]["exit_reason"] == "trail" else "Stopped" if exits and exits[0]["exit_reason"] == "stop" else (exits[0]["exit_reason"] if exits else "No exits yet")),
      "pills": [{"text": f"stop -{S['risk.stop_pct']:g}%", "tone": "red"}, {"text": f"trail {S['risk.trail_pct']:g}%", "tone": "green"}],
      "decisions": [dict(p, link=links.coin_url(p["mint"])) for p in exits]}]
RANGES = {"LIVE": 900, "1H": 3600, "4H": 4 * 3600, "1D": 86400, "1W": 7 * 86400, "ALL": None}
def chart(S, now):
    pts = [[r["ts"], r["balance"]] for r in db.q("select ts,balance from balance order by ts")]
    start = S["desk.paper_start_stack"]
    first = db.q1("select min(migrated_at) t from coins")["t"] or now
    if not pts or pts[0][0] > first: pts.insert(0, [first, start])
    pts.append([now, pts[-1][1]])
    marks = []
    for p in db.q("select * from positions"):
        marks.append({"ts": p["opened_at"], "kind": "buy", "label": f"Bought {p['name']}", "mint": p["mint"], "link": links.coin_url(p["mint"])})
        if p["closed_at"]: marks.append({"ts": p["closed_at"], "kind": "win" if (p["pnl"] or 0) >= 0 else "loss",
                                         "label": f"{p['exit_reason']} {p['name']} {p['pnl']:+.2f}", "mint": p["mint"], "link": links.coin_url(p["mint"])})
    out = {"generatedAt": db.iso(now), "ranges": {}}
    for k, sec in RANGES.items():
        lo = now - sec if sec else 0
        before = [q for q in pts if q[0] < lo]
        series = ([[lo, before[-1][1]]] if before else []) + [q for q in pts if q[0] >= lo]
        out["ranges"][k] = {"points": [[round(t), v] for t, v in series], "marks": [m for m in marks if m["ts"] >= lo]}
    return out
def coin_doc(m, S, now):
    c = db.q1("select * from coins where mint=?", m) or {"mint": m}
    pr = db.q("select ts,price,vol_m5 from prices where mint=? order by ts", m)
    b = {}
    for x in pr:
        k = int(x["ts"] // 60) * 60
        if k in b: b[k][2] = max(b[k][2], x["price"]); b[k][3] = min(b[k][3], x["price"]); b[k][4] = x["price"]; b[k][5] = x["vol_m5"]
        else: b[k] = [k, x["price"], x["price"], x["price"], x["price"], x["vol_m5"]]
    a = db.q1("select json from audits where mint=?", m); v = db.q1("select json from verdicts where mint=?", m)
    sc = db.q1("select json from scans where mint=?", m)
    p = db.q1("select * from positions where mint=? order by id desc", m)
    lines = None
    if p and p["status"] in ("open", "exiting"):
        stop = p["entry"] * (1 - p["stop_pct"] / 100); trail = p["peak"] * (1 - S["risk.trail_pct"] / 100) if p["trail_active"] else None
        lines = {"stop": stop, "trail": trail, "exit": max(stop, trail or 0), "stopPct": p["stop_pct"]}
    vd = J(v) if v else None; pair = json.loads(v["json"]).get("_pair") if v else None
    scn = J(sc) if sc else {}
    return {"mint": m, "name": c.get("name"), "symbol": c.get("symbol"), "coin_url": links.coin_url(m, "solana"),
            "price": pr[-1]["price"] if pr else None, "candles": list(b.values())[-600:],
            "stats": {"liquidityUsd": (pair or {}).get("liq") or scn.get("liquidityUsd"), "marketCap": (pair or {}).get("mcap"),
                      "holders": c.get("holders"), "top10Pct": scn.get("top10Pct"), "volumeH1": (pair or {}).get("v1"),
                      "ageMin": int((now - c["migrated_at"]) / 60) if c.get("migrated_at") else None},
            "position": p, "exitLines": lines, "audit": J(a) if a else None, "verdict": vd, "generatedAt": db.iso(now)}
def shown_mints():
    ms = [r["mint"] for r in db.q("select mint from positions order by id desc limit 30")]
    ms += [r["mint"] for r in db.q("select mint from audits order by id desc limit 20")]
    ms += [r["mint"] for r in db.q("select mint from activity where mint is not null order by id desc limit 30")]
    out = []
    for m in ms:
        if m not in out: out.append(m)
    return out[:40]
def snapshot():
    S = settings.all_settings(); now = time.time()
    bal = stack_now(); start = S["desk.paper_start_stack"]
    day0 = db.q1("select balance from balance where ts<? order by ts desc limit 1", now - 86400)
    ref = day0["balance"] if day0 else start
    act = db.q("select * from activity order by id desc limit 300")
    hb = {r["agent"]: r["ts"] for r in db.q("select * from heartbeats")}
    openp = [dict(p, link=links.coin_url(p["mint"])) for p in db.q("select * from positions where status in ('open','exiting')")]
    rows = [dict(a, link=links.coin_url(a["mint"]) if a["mint"] else None) for a in act]
    state = {"generatedAt": db.iso(now), "ts": now, "mode": S["desk.mode"], "balance": round(bal, 2), "inPositions": round(in_positions(), 2),
             "todayPct": round(100 * (bal / ref - 1), 2) if ref else 0, "multiplier": round(bal / start, 3) if start else 1,
             "agents": agents_cards(S, now), "positions": openp, "lastActivity": rows[:5], "heartbeats": hb,
             "account": {"mode": S["desk.mode"], "stack": round(bal, 2), "liveStack": S["desk.live_stack"], "profileUrl": links.profile_url(S["desk.fomo_handle"]),
                         "fomoHandle": S["desk.fomo_handle"], "signupUrl": links.SIGNUP_URL, "minStack": settings.min_stack(),
                         "notifier": "telegram", "telegram": hb_ok("telegram", hb, now), "webPush": False,
                         "settings": {g: {k.split(".", 1)[1]: v for k, v in S.items() if k.startswith(g + ".") and k not in ("desk.owner_chat_id",)} for g in GROUPS}},
             "coins": {m: {"name": (db.q1("select name from coins where mint=?", m) or {}).get("name"), "coin_url": links.coin_url(m)} for m in shown_mints()}}
    return state, chart(S, now), {"generatedAt": db.iso(now), "perPage": 30, "rows": rows}
async def price_other_coins():
    """db.prices writer #3: every 60s, coins shown in the app that Scanner/Risk don't poll."""
    import net
    while True:
        try:
            busy = {r["mint"] for r in db.q("select mint from coins where state='waiting'")} | {r["mint"] for r in db.q("select mint from positions where status='open'")}
            ms = [m for m in shown_mints() if m not in busy]
            if ms:
                pairs = await net.Dex.tokens(ms)
                for m in ms:
                    p = net.pair_fields(pairs.get(m))
                    if p and p["priceUsd"] is not None: db.x("insert into prices(ts,mint,price,vol_m5) values(?,?,?,?)", time.time(), m, p["priceUsd"], p["v5"])
        except Exception as e: log.warning("price_other_coins %s", e)
        db.heartbeat("api_prices"); await asyncio.sleep(60)
STUB = "<!doctype html><title>404</title><meta name=robots content=noindex><p>Not found.</p>"
class Publisher:
    def __init__(self, workdir=None):
        self.dir = workdir or os.path.join(ROOT, "publish", "data"); self.slots = []; self.last_ok = None; self.fails = 0
        gitpush.init(self.dir, "data")
    def write(self):
        dp = data_path(); d = os.path.join(self.dir, "d", dp); os.makedirs(d, exist_ok=True)
        open(os.path.join(self.dir, "d", "index.html"), "w").write(STUB)
        open(os.path.join(self.dir, "index.html"), "w").write(STUB)
        st, ch, ac = snapshot(); S = settings.all_settings(); now = time.time()
        os.makedirs(os.path.join(d, "coin"), exist_ok=True)
        def w(name, obj):
            tmp = os.path.join(d, name + ".tmp"); json.dump(obj, open(tmp, "w"), separators=(",", ":"), default=str); os.replace(tmp, os.path.join(d, name))
        w("state.json", st); w("chart.json", ch); w("activity.json", ac)
        keep = set()
        for m in shown_mints():
            w(f"coin/{m}.json", coin_doc(m, S, now)); keep.add(m + ".json")
        for f in os.listdir(os.path.join(d, "coin")):
            if f.endswith(".json") and f not in keep: os.remove(os.path.join(d, "coin", f))
    async def push(self):
        await asyncio.to_thread(self.write)
        g = lambda *a, **k: gitpush.agit(self.dir, *a, **k)
        await g("add", "-A")
        # single orphan commit, amended every time: no history growth
        if (await g("rev-parse", "--verify", "-q", "HEAD", check=False)).strip(): await g("commit", "-q", "--amend", "--allow-empty", "-m", "state")
        else: await g("commit", "-q", "--allow-empty", "-m", "state")
        slot = int(time.time() // SLOT)
        dels = [f":refs/heads/s{s}" for s in self.slots if s < slot - 14]
        await g("push", "-q", "-f", "origin", f"HEAD:refs/heads/s{slot}", "HEAD:refs/heads/latest", *dels)
        self.slots = [s for s in self.slots if s >= slot - 14] + [slot]; self.last_ok = time.time()
        db.kv_set("publish", {"slot": slot, "ts": self.last_ok, "fails": self.fails})
    def cleanup_remote(self):
        out = gitpush.git(self.dir, "ls-remote", "--heads", "origin")
        old = [l.split("refs/heads/")[1] for l in out.splitlines() if "refs/heads/s" in l]
        old = [b for b in old if b[1:].isdigit() and int(b[1:]) < int(time.time() // SLOT) - 14]  # keep recent slots: app stays online across restarts
        for i in range(0, len(old), 50):
            gitpush.git(self.dir, "push", "-q", "origin", *[":refs/heads/" + b for b in old[i:i+50]], check=False)
    async def loop(self):
        try: await asyncio.wait_for(asyncio.to_thread(self.cleanup_remote), 60)
        except Exception as e: log.warning("cleanup %s", e)
        while True:
            try: await self.push(); self.fails = 0
            except Exception as e:
                self.fails += 1; log.warning("push failed (%d), skipping slot: %s", self.fails, str(e)[-200:])
                lk = os.path.join(self.dir, ".git", "index.lock")
                if os.path.exists(lk): os.remove(lk)   # a killed git can leave its lock behind
            db.heartbeat("publisher")
            nxt = (int(time.time() // SLOT) + 1) * SLOT + 1   # next slot boundary; a missed slot is skipped, never queued
            await asyncio.sleep(max(0.5, nxt - time.time()))
