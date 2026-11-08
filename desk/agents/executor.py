"""Agent 4 · Executor. Arithmetic + 1 button. Never places an order, never touches funds."""
import asyncio, json, time, logging
import db, net, links, config as settings
flog = logging.getLogger("executor.file")
def stack_now():
    S = settings.all_settings()
    if S["desk.mode"] == "PAPER":
        b = db.kv_get("paper_balance")
        return S["desk.paper_start_stack"] if b is None else b
    return S["desk.live_stack"]
def in_positions():
    return sum(r["size"] for r in db.q("select size from positions where status in ('open','exiting')"))
def size_for(stack, pool_liq, S=None, free=None):
    """Returns (size, cap, reason_if_skip). STEP: size = stack_pct of stack, min(size, max_pool_pct of liquidity),
    below min_ticket: bump (if free covers) or skip 'under $47.50'."""
    S = S or settings.all_settings()
    free = stack if free is None else free
    raw = stack * S["executor.stack_pct"] / 100
    pool_cap = (pool_liq or 0) * S["executor.max_pool_pct"] / 100
    size, cap = raw, "stack_pct"
    if pool_cap < size: size, cap = pool_cap, "pool"
    mn = S["executor.min_ticket_usd"]
    if size < mn:
        if S["executor.below_min"] == "bump" and free >= mn: size, cap = mn, "bumped"
        else: return 0, cap, f"under ${mn:.2f}"
    return round(size, 2), cap, None
def set_balance(v, reason):
    db.kv_set("paper_balance", round(v, 2))
    db.x("insert into balance(ts,mode,balance,reason) values(?,?,?,?)", time.time(), "PAPER", round(v, 2), reason)
class Executor:
    def __init__(self, notify, risk_q=None, dex=None):
        self.notify = notify; self.paused = False; self.dex = dex or net.Dex.tokens; self.risk_q = risk_q
    async def execute(self, scan, audit, an):
        S = settings.all_settings(); mint = scan["mint"]; mode = S["desk.mode"]
        name = scan.get("name") or mint[:6]
        if db.q1("select 1 from signals where mint=?", mint) or db.q1("select 1 from positions where mint=? and status in ('open','exiting')", mint):
            return None
        link = links.coin_url(mint, "solana")
        try: p = net.pair_fields((await net.retry(self.dex, [mint])).get(mint))
        except Exception: p = None
        a = an.get("_pair") or {}
        stack = stack_now(); free = stack - in_positions()
        size, cap, why = size_for(stack, (p or {}).get("liq"), S, free)
        status, reason = "sent", None
        if not p or not p["priceUsd"]: status, reason = "skipped", "no price"
        elif why: status, reason = "skipped", why
        elif size > free: status, reason = "skipped", "no free stack"
        elif a.get("liq") and p["liq"] < a["liq"] * (1 - S["executor.recheck_liq_drop_pct"] / 100): status, reason = "skipped", "liquidity dropping"
        elif a.get("priceUsd") and p["priceUsd"] > a["priceUsd"] * (1 + S["executor.recheck_price_up_pct"] / 100): status, reason = "skipped", "ran before the push"
        pct = round(100 * size / stack, 1) if stack else 0
        o = {"agent": "executor", "mint": mint, "signalPrice": (p or {}).get("priceUsd"), "sizeUsd": size, "stackPct": pct,
             "link": link, "mode": mode, "status": status, "reason": reason}
        if status == "skipped":
            db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", time.time(), mint, "executor", reason)
            db.activity("executor", "skip", mint, name, f"Skipped {name}", f"Executor · {reason}", "Skipped", "grey")
        else:
            pre = "PAPER · " if mode == "PAPER" else ""
            text = (f"{pre}Buy {name} · ${size:.2f} · {pct:g}% of stack\n"
                    f"Auditor 8/8 · Analyst {an.get('score')} · stop -{S['risk.stop_pct']:g}% · trail {S['risk.trail_pct']:g}%")
            btns = [[{"text": "Buy on FOMO", "url": link}], [{"text": "Bought", "callback_data": f"bought:{mint}"}, {"text": "Skip", "callback_data": f"skip:{mint}"}]]
            ok = await self.notify.send(text, btns)
            if not ok:
                flog.info("%s push failed", mint)
                o["reason"] = "push failed"
                if mode == "LIVE": o["status"] = "missed"
            if mode == "PAPER":
                o["status"] = "bought"
                db.x("insert into positions(mint,name,mode,entry,size,peak,stop_pct,opened_at,status,last_price,last_liq,night) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                     mint, name, mode, p["priceUsd"], size, p["priceUsd"], S["risk.stop_pct"], time.time(), "open", p["priceUsd"], p["liq"], db.night_id())
                db.activity("executor", "buy", mint, name, f"Bought {name}", f"Executor · {time.strftime('%H:%M')}", f"${size:.2f} · {pct:g}% of stack", "green")
        db.x("insert into signals(ts,mint,json) values(?,?,?)", time.time(), mint, json.dumps(o))
        flog.info("%s stack=%s cap=%s size=%s mode=%s status=%s %s", mint, stack, cap, size, mode, o["status"], link)
        return o
