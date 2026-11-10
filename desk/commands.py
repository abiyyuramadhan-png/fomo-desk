"""Shared command handler (Telegram and Grok Bot app both call Desk.command)."""
import json, time, re
import db, links, config as settings
from agents.executor import stack_now, in_positions
LIVE_LOCKED = True   # Abi: PAPER only for now
AGENTS = ["scanner", "auditor", "analyst", "executor", "risk"]
class Desk:
    def __init__(self, agents, notify, auditor=None, risk=None):
        self.agents = agents; self.notify = notify; self.auditor = auditor; self.risk = risk
    def find(self, x):
        x = x.strip()
        rows = db.q("select mint,name,symbol from coins where mint=? or lower(name)=lower(?) or lower(symbol)=lower(?) or lower(symbol)=lower(?)", x, x, x, x.lstrip("$"))
        return rows
    def ticket_check(self):
        S = settings.all_settings(); st = stack_now(); ms = settings.min_stack()
        if st >= ms: return None
        if S["executor.below_min"] == "bump":
            return f"tickets bumped to ${S['executor.min_ticket_usd']:.2f} = {100*S['executor.min_ticket_usd']/st:.1f}% of stack"
        return f"every coin will be skipped, stack under ${ms:,.2f}. Switch to bump (set below_min to bump) or raise the stack."
    async def command(self, t):
        low = t.lower().strip()
        pre = "PAPER · " if settings.get("desk.mode") == "PAPER" else ""
        m = re.match(r"^(buy|sell|why)\s+(.+)$", low)
        if m:
            verb, arg = m.group(1), t.split(None, 1)[1]
            rows = self.find(arg)
            if not rows:
                if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", arg.strip()): rows = [{"mint": arg.strip(), "name": arg.strip()[:6], "symbol": None}]
                else: return f"I don't know {arg}. Send me its mint."
            if len(rows) > 1:
                return "Which one?\n" + "\n".join(f"{r['name']} ({r['symbol']}) {links.coin_url(r['mint'])}" for r in rows)
            r = rows[0]; url = links.coin_url(r["mint"])
            return await getattr(self, "c_" + verb)(r, url, pre)
        m = re.match(r"^(pause|resume)\s+(\w+)$", low)
        if m:
            a = m.group(2)
            if a not in AGENTS: return f"No agent {a}. Agents: {', '.join(AGENTS)}"
            if a == "risk" and m.group(1) == "pause" and db.q1("select 1 from positions where status in ('open','exiting')"):
                return "Risk can't be paused while a position is open."
            paused = set(db.kv_get("paused", [])); (paused.add if m.group(1) == "pause" else paused.discard)(a)
            db.kv_set("paused", sorted(paused))
            if a in self.agents: self.agents[a].paused = m.group(1) == "pause"
            return f"{a.capitalize()} {'paused' if m.group(1)=='pause' else 'resumed'}"
        m = re.match(r"^set\s+(.+?)\s+(?:to\s+|=\s*)(.+)$", low)
        if m:
            key = settings.resolve(m.group(1))
            if not key: return f"No setting called {m.group(1)}."
            if key in ("desk.mode",): return "Use paper | live to switch mode."
            ok, msg = settings.set_value(key, m.group(2))
            if ok and key == "risk.stop_pct" and self.risk: self.risk.apply_tighter_stop()
            if ok and key in ("executor.stack_pct", "executor.below_min", "executor.min_ticket_usd", "desk.paper_start_stack"):
                w = self.ticket_check(); msg += ("\n" + w) if w else ""
            return msg
        m = re.match(r"^stack\s+\$?([\d,.]+)$", low)
        if m:
            ok, msg = settings.set_value("desk.live_stack", m.group(1))
            w = self.ticket_check() if settings.get("desk.mode") == "LIVE" else None
            return ("LIVE stack " + msg.split(" ", 1)[1]) + (("\n" + w) if w else "") if ok else msg
        if low == "status": return self.status()
        if low == "paper": return "Already PAPER." if settings.get("desk.mode") == "PAPER" else (settings.set_value("desk.mode", "PAPER")[1])
        if t.strip() == "LIVE":
            nights = db.q1("select count(distinct night) n from positions where mode='PAPER' and night<?", db.night_id())["n"]
            if nights < 1: return "LIVE needs at least 1 full PAPER night in the db. None yet, staying PAPER."
            if LIVE_LOCKED: return "LIVE is locked on this build. Staying PAPER."
            return settings.set_value("desk.mode", "LIVE")[1]
        if low == "live": return "To switch to LIVE, type LIVE (capitals)."
        if low == "invite": return f"New to FOMO? {links.SIGNUP_URL}"
        if low == "report":
            u = db.kv_get("last_report_url"); return f"Last morning Page: {u}" if u else "No morning Page yet."
        return "I didn't get that.\n" + __import__("telegram").HELP
    async def c_buy(self, r, url, pre):
        ex = db.q1("select json from signals where mint=?", r["mint"])
        if ex:
            return (f"{pre}Buy {r['name']} · {url}", [[{"text": "Buy on FOMO", "url": url}]])
        if not self.auditor: return f"Auditor not running. {url}"
        sc = db.q1("select json from scans where mint=?", r["mint"])
        scan = json.loads(sc["json"]) if sc else {"mint": r["mint"], "name": r["name"], "pool": (db.q1("select pool from coins where mint=?", r["mint"]) or {}).get("pool")}
        a = db.q1("select json from audits where mint=?", r["mint"])
        o = json.loads(a["json"]) if a else await self.auditor.audit(dict(scan, _manual=True))
        lines = "\n".join(f"{l['n']} {l['name']}: {'✓' if l['pass'] else ('✗' if l['pass'] is False else '·')} {l['value']}" for l in o["layers"])
        return (f"{pre}{r['name']} · Auditor\n{lines}\nnot sized, not on the desk\n{url}", [[{"text": "Buy on FOMO", "url": url}]])
    async def c_sell(self, r, url, pre):
        p = db.q1("select * from positions where mint=? and status in ('open','exiting')", r["mint"])
        if not p: return f"No open position in {r['name']}. {url}"
        return (f"{pre}Sell {r['name']} · {url}", [[{"text": "Sell on FOMO", "url": url}]])
    async def c_why(self, r, url, pre):
        s = db.q1("select * from skips where mint=? order by ts desc", r["mint"])
        if s: return f"{r['name']}: stopped by {s['agent'].capitalize()} · {s['reason']} · {time.strftime('%H:%M', time.localtime(s['ts']))} (UTC+7)\n{url}"
        p = db.q1("select * from positions where mint=? order by id desc", r["mint"])
        if p: return f"{r['name']}: not stopped, position {p['status']}\n{url}"
        c = db.q1("select state from coins where mint=?", r["mint"])
        return f"{r['name']}: {c['state'] if c else 'not seen'} \n{url}"
    def status(self):
        S = settings.all_settings(); st = stack_now(); ps = db.q("select * from positions where status in ('open','exiting')")
        lines = [f"Mode {S['desk.mode']} · balance ${st:,.2f} · in positions ${in_positions():,.2f}",
                 f"stop -{S['risk.stop_pct']:g}% · trail {S['risk.trail_pct']:g}% · paused: {', '.join(db.kv_get('paused', [])) or 'none'}"]
        btns = []
        for p in ps:
            u = links.coin_url(p["mint"]); chg = 100 * ((p["last_price"] or p["entry"]) / p["entry"] - 1)
            lines.append(f"{p['name']} ${p['size']:.2f} · {chg:+.1f}% · stop -{p['stop_pct']:g}% · {u}")
            btns.append([{"text": f"Sell {p['name']} on FOMO", "url": u}])
        if not ps: lines.append("No open positions.")
        return ("\n".join(lines), btns or None)
    async def callback(self, data):
        kind, _, mint = data.partition(":")
        c = db.q1("select name from coins where mint=?", mint) or {"name": mint[:6]}
        url = links.coin_url(mint)
        if kind == "skip":
            db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", time.time(), mint, "owner", "skipped by you")
            db.activity("executor", "skip", mint, c["name"], f"Skipped {c['name']}", "You · Skip", "Skipped", "grey")
            return f"Skipped {c['name']}. {url}"
        if kind in ("bought", "sold"):
            if settings.get("desk.mode") == "PAPER": return f"PAPER · {c['name']} fills and exits by itself in PAPER. {url}"
        return None
