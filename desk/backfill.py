"""Best-effort backfill of pump.fun migrations missed while the websocket was down or the box was paused.
Source: Solana RPC signatures of the pump.fun migration authority (each successful tx = one 'Migrate').
The public mainnet RPC 429s getSignaturesForAddress, so this uses publicnode (read-only, no key)."""
import asyncio, time, logging, httpx
log = logging.getLogger("scanner.file")
RPC = "https://solana-rpc.publicnode.com"
MIGRATOR = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
WSOL = "So11111111111111111111111111111111111111112"
_c = None
async def rpc(method, params):
    global _c
    _c = _c or httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5))
    err = None
    for i in range(3):
        try:
            r = await asyncio.wait_for(_c.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}), 15)
            j = r.json()
            if "result" in j: return j["result"]
            err = str(j.get("error"))[:120]
        except Exception as e: err = f"{type(e).__name__} {e}"[:120]   # timeouts have empty str(); keep the type
        await asyncio.sleep(1 + 2 * i)
    raise RuntimeError(f"{method}: {err}")
async def recent(since_ts, limit=1000):
    """[(signature, blockTime)] successful migrator txs newer than since_ts, newest first."""
    out, before = [], None
    while True:
        o = {"limit": limit}
        if before: o["before"] = before
        r = await rpc("getSignaturesForAddress", [MIGRATOR, o])
        if not r: break
        out += [(x["signature"], x["blockTime"]) for x in r if x["err"] is None and (x["blockTime"] or 0) >= since_ts]
        before = r[-1]["signature"]
        if (r[-1]["blockTime"] or 0) < since_ts or len(r) < limit: break
    return out
async def mint_of(sig):
    t = await rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    if not t or not any("Instruction: Migrate" in l for l in (t["meta"].get("logMessages") or [])): return None
    ms = {b["mint"] for b in t["meta"].get("postTokenBalances") or []} - {WSOL}
    return next((m for m in ms if m.endswith("pump")), None) or (next(iter(ms)) if len(ms) == 1 else None)
async def sweep(known, window_s, cap=200, gap=0.8, beat=None, budget_s=240):
    """Returns [(mint, signature, blockTime)] for migrations in the last window_s not in known(sig).
    beat() is called every tx so the heartbeat stays fresh; the whole sweep stops after budget_s
    (the next sweep picks up the rest, since known() skips what was already added)."""
    found, t0 = [], time.monotonic()
    for sig, bt in (await recent(time.time() - window_s))[:cap]:
        if beat: beat()
        if time.monotonic() - t0 > budget_s: log.info("backfill budget %ss hit, rest next sweep", budget_s); break
        if known(sig): continue
        try: m = await mint_of(sig)
        except Exception as e: log.info("backfill tx %s.. failed %s", sig[:8], e); continue
        if m: found.append((m, sig, bt))
        await asyncio.sleep(gap)
    return found
