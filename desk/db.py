"""SQLite store. One file: data/desk.db"""
import sqlite3, json, os, time, threading, datetime as dt
PATH = os.environ.get("DESK_DB", os.path.join(os.path.dirname(__file__), "data", "desk.db"))
_local = threading.local()
SCHEMA = """
create table if not exists coins(mint text primary key, name text, symbol text, pool text, signature text,
  creator text, creator_bal real, migrated_at real, raw text, state text default 'waiting', passed_at real,
  liq0 real, holders integer, last_h24 real, night text);
create table if not exists scans(id integer primary key, ts real, mint text, json text);
create table if not exists audits(id integer primary key, ts real, mint text, json text);
create table if not exists verdicts(id integer primary key, ts real, mint text, json text);
create table if not exists signals(id integer primary key, ts real, mint text, json text);
create table if not exists positions(id integer primary key, mint text, name text, mode text, entry real, size real,
  peak real, stop_pct real, trail_active integer default 0, opened_at real, status text, exit_price real,
  exit_reason text, closed_at real, pnl real, pct real, fees real, nopx integer default 0, last_price real, last_liq real,
  pushed_at real, night text);
create table if not exists activity(id integer primary key, ts real, agent text, kind text, mint text, name text,
  title text, sub text, value text, tone text, mode text);
create table if not exists prices(id integer primary key, ts real, mint text, price real, vol_m5 real);
create table if not exists skips(id integer primary key, ts real, mint text, agent text, reason text);
create table if not exists heartbeats(agent text primary key, ts real, note text);
create table if not exists balance(id integer primary key, ts real, mode text, balance real, reason text);
create table if not exists settings(k text primary key, v text);
create table if not exists change_log(id integer primary key, ts real, k text, old text, new text, src text);
create table if not exists push_subs(id integer primary key, ts real, endpoint text, json text);
create table if not exists kv(k text primary key, v text);
create table if not exists events(id integer primary key, ts real, kind text, json text);
create index if not exists ip on prices(mint, ts);
"""
def conn():
    c = getattr(_local, "c", None)
    if c is None:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        c = sqlite3.connect(PATH, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("pragma journal_mode=wal")
        c.executescript(SCHEMA)
        _local.c = c
    return c
def q(sql, *a): return [dict(r) for r in conn().execute(sql, a).fetchall()]
def q1(sql, *a):
    r = q(sql, *a); return r[0] if r else None
def x(sql, *a): return conn().execute(sql, a).lastrowid
def kv_get(k, d=None):
    r = q1("select v from kv where k=?", k); return json.loads(r["v"]) if r else d
def kv_set(k, v): x("insert or replace into kv(k,v) values(?,?)", k, json.dumps(v))
def iso(t=None): return dt.datetime.fromtimestamp(t or time.time(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def night_id(t=None):
    # night = local (UTC+7) date the evening started; rolls at report time 08:00
    lt = dt.datetime.fromtimestamp(t or time.time(), dt.timezone(dt.timedelta(hours=7)))
    if lt.hour < 8: lt -= dt.timedelta(days=1)
    return lt.strftime("%Y-%m-%d")
def heartbeat(agent, note=""): x("insert or replace into heartbeats values(?,?,?)", agent, time.time(), note)
def activity(agent, kind, mint, name, title, sub, value="", tone="", mode=None):
    import config as settings
    x("insert into activity(ts,agent,kind,mint,name,title,sub,value,tone,mode) values(?,?,?,?,?,?,?,?,?,?)",
      time.time(), agent, kind, mint, name, title, sub, value, tone, mode or settings.get("desk.mode"))
def event(kind, obj): x("insert into events(ts,kind,json) values(?,?,?)", time.time(), kind, json.dumps(obj))
