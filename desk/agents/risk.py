"""Agent 5 · Risk. Exits by rule, sends the Sell button. Never moves a stop down."""
import asyncio, json, time, logging
import db, net, links, fees, config as settings
flog = logging.getLogger("risk.file")
class Risk:
    def __init__(self, notify, dex=None, clock=time.time):
        self.notify = notify; self.dex = dex or net.Dex.tokens; self.clock = clock
        self.lock = asyncio.Lock()   # wake refresh and the regular loop must never exit the same position twice
    def apply_tighter_stop(self):
        s = settings.get("risk.stop_pct")
        db.x("update positions set stop_pct=? where status='open' and stop_pct>?", s, s)
    async def loop(self):
        while True:
            try: await self.poll_once()
            except net.RateLimit:
                flog.info("429, back off 30s, polls missed"); await asyncio.sleep(30)
            except Exception as e: logging.getLogger("risk").exception("poll %s", e)
            db.heartbeat("risk")
            await asyncio.sleep(settings.get("risk.poll_s"))
    async def poll_once(self):
        async with self.lock: return await self._poll_once()
    async def _poll_once(self):
        ps = db.q("select * from positions where status='open'")
        if not ps: return []
        self.apply_tighter_stop(); ps = db.q("select * from positions where status='open'")
        pairs = await self.dex([p["mint"] for p in ps])
        out = []
        for pos in ps:
            pr = net.pair_fields(pairs.get(pos["mint"]))
            r = await self.step(pos, pr)
            if r: out.append(r)
        return out
    async def step(self, pos, pr):
        S = settings.all_settings(); now = self.clock()
        mint, name = pos["mint"], pos["name"]; link = links.coin_url(mint, "solana")
        if not pr or pr["priceUsd"] is None:
            n = pos["nopx"] + 1; db.x("update positions set nopx=? where id=?", n, pos["id"])
            if n == 4: await self.notify.send(f"{'PAPER · ' if pos['mode']=='PAPER' else ''}{name}: no price for 1 min", [[{"text": "Sell on FOMO", "url": link}]])
            flog.info("%s no price (%d)", mint, n); return None
        price, liq = pr["priceUsd"], pr["liq"]
        db.x("insert into prices(ts,mint,price,vol_m5) values(?,?,?,?)", now, mint, price, pr["v5"])
        peak = max(pos["peak"], price); entry = pos["entry"]
        trail = bool(pos["trail_active"]) or price >= entry * (1 + S["risk.trail_start_pct"] / 100)
        stop_line = entry * (1 - pos["stop_pct"] / 100); trail_line = peak * (1 - S["risk.trail_pct"] / 100)
        reason = None
        if not liq: reason, price = "pulled", pos["last_price"] or price
        elif price <= stop_line: reason = "stop"
        elif trail and price <= trail_line: reason = "trail"
        elif now - pos["opened_at"] >= S["risk.timeout_h"] * 3600 and price < entry * (1 + S["risk.timeout_min_gain_pct"] / 100): reason = "timeout"
        db.x("update positions set peak=?, trail_active=?, nopx=0, last_price=?, last_liq=? where id=?", peak, int(trail), price, liq, pos["id"])
        flog.info("%s price=%s peak=%s stop=%s trail=%s action=%s", mint, price, peak, stop_line, trail_line if trail else None, reason)
        if reason: return await self.exit(dict(pos, peak=peak), price, reason, S)
        return None
    async def exit(self, pos, price, reason, S):
        units = pos["size"] / pos["entry"]; out_usd = units * price
        fee = fees.round_trip(pos["size"], out_usd, S["desk.fees_ref_discount"])
        pnl = round(out_usd - pos["size"] - fee, 2); pct = round(100 * pnl / pos["size"], 2)
        mode = pos["mode"]; status = "closed" if mode == "PAPER" else "exiting"
        link = links.coin_url(pos["mint"], "solana"); name = pos["name"]; sp = pos["stop_pct"]
        db.x("update positions set status=?, exit_price=?, exit_reason=?, closed_at=?, pnl=?, pct=?, fees=?, pushed_at=? where id=?",
             status, price, reason, time.time(), pnl, pct, fee, time.time(), pos["id"])
        if mode == "PAPER":
            from agents.executor import stack_now, set_balance
            set_balance(stack_now() + pnl, f"{reason} {name}")
        pre = "PAPER · " if mode == "PAPER" else ""
        fmt_sp = f"{sp:g}"
        if reason == "trail": text = f"{pre}Sold {name} · {'+' if pnl>=0 else '-'}${abs(pnl):.2f} ({pct:+.1f}%)"
        elif reason == "stop":
            gap = f" (price gapped past the stop: {pct:+.1f}%)" if pct < -(sp + 5) else ""
            text = f"{pre}{name} hit the -{fmt_sp}% stop · -${abs(pnl):.2f}{gap}"
        elif reason == "timeout": text = f"{pre}Sell {name}, dead money · {pct:+.1f}% in {S['risk.timeout_h']:g}h"
        else: text = f"{pre}Sell {name} now, liquidity pulled · {pct:+.1f}%"
        btn = [[{"text": "Sell on FOMO", "url": link}]] + ([[{"text": "Sold", "callback_data": f"sold:{pos['mint']}"}]] if mode == "LIVE" else [])
        await self.notify.send(text + f"\n{link}", btn)
        if reason == "trail": db.activity("risk", "sell", pos["mint"], name, f"Sold {name}", "Risk · trailing stop", f"{'+' if pnl>=0 else '-'}${abs(pnl):.2f} / {pct:+.1f}%", "green" if pnl >= 0 else "red")
        elif reason == "stop": db.activity("risk", "stop", pos["mint"], name, f"Stopped {name}", f"Risk · -{fmt_sp}% stop", f"-${abs(pnl):.2f}", "red")
        else: db.activity("risk", reason, pos["mint"], name, f"Sold {name}", f"Risk · {reason}", f"{pnl:+.2f} / {pct:+.1f}%", "red" if pnl < 0 else "green")
        o = {"agent": "risk", "mint": pos["mint"], "name": name, "ts": db.iso(), "reason": reason, "entryPrice": pos["entry"], "exitPrice": price,
             "peakPrice": pos["peak"], "pnlUsd": pnl, "pct": pct, "feesUsd": fee, "stopPct": sp, "mode": mode, "status": status, "link": link, "_text": text}
        db.event("exit", o)
        return o
