"""Agent 1 · Scanner. Counts and cuts. Never judges quality."""
import asyncio, json, time, logging, re, unicodedata, websockets
import db, net, chain, fields, backfill, config as settings
log = logging.getLogger("scanner")
flog = logging.getLogger("scanner.file")
WS = "wss://pumpportal.fun/api/data"
def norm(s):
    s = (s or "").lower()
    return "".join(ch for ch in s if ch.isalpha() and ch.isascii())
class Scanner:
    def __init__(self, out_q, notify=None):
        self.out = out_q; self.notify = notify; self.reconnects = []; self.paused = False; self.wake = asyncio.Event()
    # ---------- backfill (missed migrations: ws gaps, box pauses) ----------
    async def backfill_loop(self, every=300):
        while True:
            try: await asyncio.wait_for(self.wake.wait(), every)
            except asyncio.TimeoutError: pass
            self.wake.clear(); db.heartbeat("backfill", "sweeping")
            try:
                win = settings.get("scanner.max_wait_min") * 60   # older coins could only be killed as 'never qualified'
                got = await backfill.sweep(lambda sig: db.q1("select 1 from coins where signature=?", sig), win,
                                           beat=lambda: db.heartbeat("backfill", "sweeping"))
                n = 0
                for mint, sig, bt in got:
                    if not bt or time.time() - bt > win: continue  # past max_wait: can only die as never qualified
                    if db.q1("select 1 from coins where mint=?", mint): continue
                    await self.on_migration({"mint": mint, "signature": sig, "txType": "migrate", "_backfill": True}, at=bt); n += 1
                if n: flog.info("backfill added %d missed migrations", n)
                db.kv_set("backfill", {"ts": time.time(), "added": n, "checked": len(got)})
            except Exception as e: flog.info("backfill failed %s", e)
            db.heartbeat("backfill")
    # ---------- websocket intake ----------
    async def ws_loop(self):
        back = 1
        while True:
            silent = False
            try:
                async with websockets.connect(WS, ping_interval=30) as w:
                    await w.send(json.dumps({"method": "subscribeMigration"}))   # resubscribe on every (re)connect
                    flog.info("ws connected, subscribed to migrations"); self.wake.set()
                    back = 1; last = time.time()
                    while True:
                        try: msg = await asyncio.wait_for(w.recv(), timeout=120)
                        except asyncio.TimeoutError:
                            flog.info("ws silent 120s, reconnect"); silent = True; break
                        db.heartbeat("scanner_ws")
                        try: await self.on_migration(json.loads(msg))
                        except Exception as e: log.exception("migration msg: %s", e)
            except Exception as e:
                flog.info("ws error %s", e)
            if not silent: self.reconnects.append(time.time())
            db.kv_set("ws_silent", db.kv_get("ws_silent", 0) + (1 if silent else 0)); db.kv_set("ws_reconnects", [t for t in self.reconnects if time.time() - t < 3600])
            flog.info("ws reconnect in %ss", back); await asyncio.sleep(back); back = min(back * 2, 60)
    async def on_migration(self, m, at=None):
        F = fields.FIELDS["migration"]
        mint = m.get(F["mint"])
        if not mint or m.get("txType") != "migrate": return
        if db.q1("select 1 from coins where mint=?", mint): return
        db.x("insert into coins(mint,signature,migrated_at,raw,state,night) values(?,?,?,?, 'waiting',?)",
             mint, m.get(F["signature"]), at or time.time(), json.dumps(m), db.night_id(at))
        # creator: not in migration message (approved) -> RugCheck report.creator; balance NOW
        creator = bal = None
        try:
            rep = await net.retry(net.rugcheck, mint, "report")
            creator = rep.get(fields.FIELDS["rugcheck_report"]["creator"])
            if creator: bal = await net.retry(chain.owner_balance, creator, mint)
        except Exception as e: flog.info("%s creator lookup failed: %s", mint, e)
        db.x("update coins set creator=?, creator_bal=? where mint=?", creator, bal, mint)
    # ---------- polling ----------
    async def poll_loop(self):
        while True:
            t0 = time.time()
            try:
                if not self.paused: await self.poll_once()
            except net.RateLimit:
                flog.info("dexscreener 429, wait 30s"); await asyncio.sleep(30)
            except Exception as e: log.exception("poll: %s", e)
            db.heartbeat("scanner")
            await asyncio.sleep(max(1, settings.get("scanner.poll_s") - (time.time() - t0)))
    async def poll_once(self, now=None):
        now = now or time.time()
        room = db.q("select * from coins where state='waiting'")
        if not room: return
        pairs = await net.Dex.tokens([c["mint"] for c in room])
        for c in room:
            p = net.pair_fields(pairs.get(c["mint"]))
            if p and p["priceUsd"] is not None:
                db.x("insert into prices(ts,mint,price,vol_m5) values(?,?,?,?)", now, c["mint"], p["priceUsd"], p["v5"])
                db.x("update coins set name=?,symbol=?,pool=?,last_h24=? where mint=?", p["name"], p["symbol"], p["pairAddress"], p["p24"], c["mint"])
            await self.decide(c, p, now)
    async def decide(self, c, p, now, top10_fn=None):
        S = settings.all_settings()
        wait_min = (now - c["migrated_at"]) / 60
        if not p:   # DexScreener doesn't know it yet: wait in the room
            if wait_min >= S["scanner.max_wait_min"]: return self.emit(c, None, "kill", "never qualified", now)
            return
        # Age from migrated_at only. DexScreener pairCreatedAt is often wrong for new
        # pump mints (DB saw 87k–143k min on coins minutes old) and caused instant passes
        # that auditor L6 then correctly refused as "pool too young".
        age = int(wait_min)
        liq = p["liq"] or 0
        if liq < S["scanner.min_liquidity_usd"]:
            return self.emit(c, p, "kill", f"liq ${liq/1000:.1f}K", now, age=age)
        try: t10 = await (top10_fn or chain.top10)(c["mint"], p["pairAddress"])
        except Exception as e:
            flog.info("%s top10 read failed %s, retry next poll", c["mint"], e); t10 = None
        if t10 is not None and t10 > S["scanner.max_top10_pct"]:
            return self.emit(c, p, "kill", f"top 10 hold {t10:.0f}%", now, t10, age)
        if (p["p1"] or 0) > S["scanner.max_h1_change_pct"]:
            return self.emit(c, p, "kill", f"+{p['p1']:.0f}% in 1h", now, t10, age)
        cc = self.copycat(c["mint"], p["name"], p["symbol"], S)
        if cc: return self.emit(c, p, "kill", f"copycat of {cc}", now, t10, age)
        # Window check before pass: backfill was admitting 61–85 min-old coins with
        # current DexScreener prices (DB: xQCP/NATF/Eq8UZ). Too late = never qualified.
        if wait_min > S["scanner.max_wait_min"]:
            return self.emit(c, p, "kill", "never qualified", now, t10, age)
        if age >= S["scanner.min_pool_age_min"] and t10 is not None:
            return self.emit(c, p, "pass", None, now, t10, age)
    def copycat(self, mint, name, symbol, S):
        runners = db.q("select mint,name,symbol from coins where mint<>? and last_h24>=? and night=?", mint, S["scanner.runner_h24_pct"], db.night_id())
        mine = [x for x in (norm(name), norm(symbol)) if x]
        for r in runners:
            for theirs in (norm(r["name"]), norm(r["symbol"])):
                if not theirs: continue
                for a in mine:
                    if a == theirs or (len(a) >= 3 and len(theirs) >= 3 and (a in theirs or theirs in a)):
                        return r["name"] or r["symbol"]
        return None
    def emit(self, c, p, verdict, reason, now, t10=None, age=None):
        if db.q1("select 1 from scans where mint=?", c["mint"]): return  # 1 decision per mint per night
        o = {"agent": "scanner", "mint": c["mint"], "name": (p or {}).get("name") or c.get("name"), "symbol": (p or {}).get("symbol") or c.get("symbol"),
             "pool": (p or {}).get("pairAddress"), "liquidityUsd": (p or {}).get("liq"), "top10Pct": t10, "h1ChangePct": (p or {}).get("p1"),
             "ageMin": age, "verdict": verdict, "reason": reason, "ts": db.iso(now)}
        db.x("insert into scans(ts,mint,json) values(?,?,?)", now, c["mint"], json.dumps(o))
        db.x("update coins set state=?, passed_at=?, liq0=? where mint=?", "passed" if verdict == "pass" else "killed", now, o["liquidityUsd"], c["mint"])
        flog.info("%s %s %s %s liq=%s top10=%s h1=%s age=%s", o["ts"], c["mint"], verdict, reason, o["liquidityUsd"], t10, o["h1ChangePct"], age)
        if verdict == "kill": db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", now, c["mint"], "scanner", reason)
        else: self.out.put_nowait(o)
        return o
