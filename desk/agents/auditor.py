"""Agent 2 · Auditor. 8 layers, in order, first red kills. No data is never a pass."""
import asyncio, json, time, logging
import db, net, chain, fields, config as settings
flog = logging.getLogger("auditor.file")
NAMES = ["Mint authority", "Freeze authority", "Dev wallet", "Top 10 holders", "Liquidity", "Pool age", "Bundled wallets", "Delegations"]
SRC = ["rpc", "rpc", "rpc", "rpc", "rugcheck", "rpc", "rugcheck", "rpc"]
class NoData(Exception): pass
class Auditor:
    def __init__(self, out_q, notify=None, src=None):
        self.out = out_q; self.notify = notify; self.paused = False
        self.src = src or {}   # injectable sources for tests
        self.l8_down_alerted = False
    async def _get(self, key, fn, *a):
        f = self.src.get(key, fn)
        n = settings.get("auditor.retries")
        try: return await net.retry(f, *a, tries=n, gap=2)
        except Exception as e: raise NoData(str(e))
    async def audit(self, scan):
        mint, pool = scan["mint"], scan["pool"]
        coin = db.q1("select * from coins where mint=?", mint) or {}
        S = settings.all_settings()
        if db.q1("select 1 from audits where mint=?", mint): return None   # never re-audit
        layers, cache = [], {}
        async def info():
            if "ai" not in cache:
                cache["ai"] = await self._get("account_info", lambda m: net.rpc("getAccountInfo", [m, {"encoding": "jsonParsed"}]), mint)
            v = (cache["ai"] or {}).get("value")
            if not v: raise NoData("no account")
            return v["data"]["parsed"]["info"]
        async def report():
            if "rep" not in cache: cache["rep"] = await self._get("report", net.rugcheck, mint, "report")
            return cache["rep"]
        holders = None
        async def L1():
            i = await info(); return (i.get("mintAuthority") is None, "Revoked" if i.get("mintAuthority") is None else "mint not revoked")
        async def L2():
            i = await info(); return (i.get("freezeAuthority") is None, "Revoked" if i.get("freezeAuthority") is None else "freeze not revoked")
        async def L3():
            i = await info()
            sup = float(i.get("supply") or 0) / 10 ** int(i.get("decimals") or 0)
            if not sup: return False, "no supply"
            cache["sup"] = sup
            cr = coin.get("creator")
            if not cr: return False, "no data: dev"
            bal = await self._get("owner_balance", chain.owner_balance, cr, mint)
            pct = 100 * bal / sup
            b0 = coin.get("creator_bal")
            if b0 is None: return False, "no data: dev"
            if bal < b0 - 1e-9: return False, "dev sold"
            if pct >= S["auditor.max_dev_pct"]: return False, f"dev holds {pct:.0f}%"
            cache["dev"] = pct
            return True, f"{pct:.1f}% · sold 0"
        async def L4():
            t = await self._get("top10", chain.top10, mint, pool, cache.get("sup"))
            cache["top10"] = t
            return (t < S["auditor.max_top10_pct"], f"{t:.1f}%" if t < S["auditor.max_top10_pct"] else f"top 10 hold {t:.0f}%")
        async def L5():
            rep = await report()
            mk = next((m for m in (rep.get("markets") or []) if m.get("pubkey") == pool), None)
            pct = ((mk or {}).get("lp") or {}).get("lpLockedPct")
            if pct is None: return False, "no data: liquidity"
            if pct < S["auditor.min_lp_locked_pct"]: return False, "liquidity unlocked"
            fresh = scan.get("_fresh_liq")
            if fresh is None:
                p = net.pair_fields((await self._get("dex", net.Dex.tokens, [mint])).get(mint))
                fresh = (p or {}).get("liq")
            l0 = scan.get("liquidityUsd") or coin.get("liq0")
            if fresh is None or not l0: return False, "no data: liquidity"
            if fresh < l0 * 0.5: return False, "liquidity pulled"
            cache["lp"] = f"{pct:.0f}% locked"
            return True, f"{pct:.0f}% locked/burned"
        async def L6():
            age = (time.time() - coin.get("migrated_at", time.time())) / 60
            return (age >= S["auditor.min_pool_age_min"], f"{int(age)}m" if age >= S["auditor.min_pool_age_min"] else "pool too young")
        async def L7():
            g = await self._get("graph", net.rugcheck, mint, "graph")
            big = bundled_size(g)
            if big is None: return False, "no data: bundles"
            cache["bund"] = big
            if big >= S["auditor.max_bundled"]: return False, f"{big} bundled wallets"
            return True, "None" if big < 2 else f"{big} linked"
        async def L8():
            nonlocal holders
            try: accs = await self._get("program_accounts", chain.program_accounts, mint)
            except NoData:
                await self.layer8_down(); return False, "no data: delegations"
            by = {}
            holders = 0
            for a in accs:
                inf = a["account"]["data"]["parsed"]["info"]
                if float(inf["tokenAmount"]["uiAmountString"] or 0) > 0: holders += 1
                d = inf.get("delegate")
                if d: by[d] = by.get(d, 0) + 1
            worst = max(by.items(), key=lambda kv: kv[1]) if by else None
            cache["del"] = worst[1] if worst else 0
            if worst and worst[1] > S["auditor.max_delegated_accounts"]:
                return False, f"{worst[1]} wallets → {worst[0][:4]}...{worst[0][-3:]}"
            return True, "None"
        fns = [L1, L2, L3, L4, L5, L6, L7, L8]
        passed, reason = True, None
        for n, fn in enumerate(fns, 1):
            t0 = time.time()
            try: ok, val = await fn()
            except NoData: ok, val = False, f"no data: {NAMES[n-1].lower()}"
            except Exception as e: ok, val = False, f"no data: {NAMES[n-1].lower()}"
            ms = int((time.time() - t0) * 1000)
            L = {"n": n, "name": NAMES[n-1], "pass": ok, "value": val, "source": SRC[n-1]}
            layers.append(L)
            db.event("audit_layer", {"mint": mint, **L})
            flog.info("%s layer %d %s %s %dms", mint, n, ok, val, ms)
            if not ok:
                passed, reason = False, val
                for m in range(n + 1, 9):
                    layers.append({"n": m, "name": NAMES[m-1], "pass": None, "value": "not checked", "source": SRC[m-1]})
                break
        o = {"agent": "auditor", "mint": mint, "ts": db.iso(), "passed": passed, "layersChecked": len([l for l in layers if l["pass"] is not None]),
             "layers": layers, "holders": holders, "reason": reason,
             "_ctx": {k: cache.get(k) for k in ("dev", "top10", "lp", "bund", "del")}}
        db.x("insert into audits(ts,mint,json) values(?,?,?)", time.time(), mint, json.dumps(o))
        if holders is not None: db.x("update coins set holders=? where mint=?", holders, mint)
        flog.info("%s verdict %s %s", mint, passed, reason)
        name = scan.get("name") or mint[:6]
        if passed: self.out.put_nowait((scan, o))
        else:
            db.activity("auditor", "reject", mint, name, f"Rejected {name}", f"Auditor · {reason}", "Skipped", "red")
            db.x("insert into skips(ts,mint,agent,reason) values(?,?,?,?)", time.time(), mint, "auditor", f"L{len(layers) and o['layersChecked']} {reason}")
        return o
    async def layer8_down(self):
        n = db.kv_get("l8_killed", 0) + 1; db.kv_set("l8_killed", n)
        if not self.l8_down_alerted and self.notify:
            self.l8_down_alerted = True
            await self.notify.send("layer 8 down, every coin is red until rpc_url changes")
def bundled_size(g):
    """Biggest connected group of holders in the insiders graph (approved: key 'links', [] = None)."""
    if not isinstance(g, list): return None
    best = 0
    for net_ in g:
        if not isinstance(net_, dict) or "links" not in net_ or "nodes" not in net_: return None
        hold = {n["id"] for n in net_["nodes"] if (n.get("holdings") or 0) > 0}
        par = {h: h for h in hold}
        def f(a):
            while par[a] != a: par[a] = par[par[a]]; a = par[a]
            return a
        for e in net_["links"]:
            a, b = e.get("source"), e.get("target")
            if a in hold and b in hold: par[f(a)] = f(b)
        sizes = {}
        for h in hold: r = f(h); sizes[r] = sizes.get(r, 0) + 1
        # a lone holder is not a group
        best = max([best] + [s for s in sizes.values() if s >= 2])
    return best
