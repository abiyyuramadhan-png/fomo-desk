"""Settings: defaults, ranges, aliases. Persisted in data/settings.json. Agents never write here."""
import json, os, threading
"""STEP 10 settings, stored in db.settings; every change in db.change_log."""
_lock = threading.Lock()
# key: (default, min, max)  -- str/bool settings use None ranges
SPEC = {
 "scanner.min_liquidity_usd": (40000, 1000, 5_000_000), "scanner.max_top10_pct": (25, 1, 100),
 "scanner.max_h1_change_pct": (80, 1, 10000), "scanner.poll_s": (60, 15, 600),
 "scanner.min_pool_age_min": (10, 0, 240), "scanner.max_wait_min": (60, 5, 720),
 "scanner.runner_h24_pct": (300, 10, 100000), "scanner.max_dex_rpm": (250, 10, 290),
 "auditor.enabled": (True, None, None), "auditor.max_dev_pct": (5, 0, 100),
 "auditor.max_top10_pct": (25, 1, 100), "auditor.min_lp_locked_pct": (99, 0, 100),
 "auditor.min_pool_age_min": (10, 0, 240), "auditor.max_bundled": (5, 1, 1000),
 "auditor.max_delegated_accounts": (10, 1, 100000), "auditor.retries": (3, 1, 10),
 "analyst.mode": ("rules", None, None), "analyst.min_alive_6h": (0.70, 0, 1),
 "analyst.min_organic": (0.65, 0, 1), "analyst.max_chase": (0.30, 0, 1),
 "analyst.min_score": (70, 0, 100), "analyst.timeout_s": (10, 1, 60),
 "analyst.alive_volume_h1": (25000, 100, 10_000_000), "analyst.organic_buys_h1": (150, 1, 100000),
 "analyst.bundled_penalty": (0.5, 0, 1), "analyst.bundled_from": (3, 1, 1000),
 "analyst.flush_drop_m5_pct": (5, 0.1, 100), "analyst.chase_h1_pct": (80, 1, 10000),
 "executor.stack_pct": (8, 0.1, 100), "executor.max_pool_pct": (2, 0.01, 100),
 "executor.min_ticket_usd": (47.50, 5, 100000), "executor.below_min": ("bump", None, None),
 "executor.recheck_liq_drop_pct": (20, 1, 100), "executor.recheck_price_up_pct": (15, 1, 1000),
 "executor.confirm_window_min": (5, 1, 60),
 "risk.poll_s": (15, 5, 300), "risk.stop_pct": (6, 0.5, 90), "risk.trail_start_pct": (20, 1, 1000),
 "risk.trail_pct": (12, 0.5, 90), "risk.timeout_h": (3, 0.25, 72), "risk.timeout_min_gain_pct": (5, 0, 1000),
 "risk.confirm_window_min": (2, 1, 60),
 "desk.mode": ("PAPER", None, None), "desk.paper_start_stack": (200, 10, 10_000_000),
 "desk.live_stack": (0, 0, 100_000_000), "desk.report_time": ("08:00", None, None),
 "desk.notifier": ("telegram", None, None), "desk.rpc_url": ("https://api.mainnet-beta.solana.com", None, None),
 "desk.push_rejects": (False, None, None), "desk.fees_ref_discount": (0.10, 0, 1),
 "desk.fomo_handle": ("13ckngMad", None, None), "desk.owner_chat_id": (1254205679, None, None),
}
CHOICES = {"analyst.mode": ("rules", "jev"), "executor.below_min": ("bump", "skip"), "desk.mode": ("PAPER", "LIVE")}
ALIASES = {"stop": "risk.stop_pct", "trail": "risk.trail_pct", "trail start": "risk.trail_start_pct",
 "timeout": "risk.timeout_h", "stack pct": "executor.stack_pct", "ticket": "executor.min_ticket_usd",
 "min ticket": "executor.min_ticket_usd", "below min": "executor.below_min", "min liquidity": "scanner.min_liquidity_usd",
 "liquidity": "scanner.min_liquidity_usd", "top10": "scanner.max_top10_pct", "top 10": "scanner.max_top10_pct",
 "min score": "analyst.min_score", "score": "analyst.min_score", "pool pct": "executor.max_pool_pct",
 "report time": "desk.report_time", "rpc": "desk.rpc_url", "push rejects": "desk.push_rejects"}
LABEL = {"risk.stop_pct": ("stop", "-{}%"), "risk.trail_pct": ("trail", "{}%"), "executor.stack_pct": ("stack pct", "{}%")}

def _load():
    import db
    return {r["k"]: json.loads(r["v"]) for r in db.q("select k,v from settings")}

def all_settings():
    cur = _load()
    return {k: cur.get(k, v[0]) for k, v in SPEC.items()}

def get(key):
    return all_settings()[key]

def resolve(name):
    n = name.strip().lower().replace("_", " ")
    if n in ALIASES: return ALIASES[n]
    for k in SPEC:
        if n == k.replace("_", " ") or n == k.split(".", 1)[1].replace("_", " "): return k
    return None

def fmt(key, val):
    lab, f = LABEL.get(key, (key.split(".", 1)[1], "{}"))
    return lab, f.format(val)

def set_value(key, raw, src="telegram"):
    """Returns (ok, message). Out of range = refuse with the range."""
    d, lo, hi = SPEC[key]
    if key in CHOICES:
        v = next((c for c in CHOICES[key] if c.lower() == str(raw).strip().lower()), None)
        if v is None: return False, f"{key} must be one of {', '.join(CHOICES[key])}"
    elif isinstance(d, bool):
        s = str(raw).strip().lower()
        if s not in ("true", "false", "on", "off", "1", "0", "yes", "no"): return False, f"{key} must be true or false"
        v = s in ("true", "on", "1", "yes")
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        try: v = float(str(raw).replace("%", "").replace("$", "").replace(",", "").strip().lstrip("-"))
        except ValueError: return False, f"{key} needs a number"
        if lo is not None and not (lo <= v <= hi): return False, f"{key} must be between {lo} and {hi}"
        if isinstance(d, int) and v.is_integer(): v = int(v)
    else:
        v = str(raw).strip()
    old = get(key)
    import db, time
    db.x("insert or replace into settings(k,v) values(?,?)", key, json.dumps(v))
    db.x("insert into change_log(ts,k,old,new,src) values(?,?,?,?,?)", time.time(), key, json.dumps(old), json.dumps(v), src)
    lab, a = fmt(key, old); _, b = fmt(key, v)
    return True, f"{lab} {a} -> {b}"

def min_stack():
    s = all_settings()
    return round(s["executor.min_ticket_usd"] / (s["executor.stack_pct"] / 100), 2)
