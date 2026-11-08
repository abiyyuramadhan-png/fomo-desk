"""HTTP helpers: RPC, DexScreener (rate-limited), RugCheck."""
import asyncio, time, json, logging, httpx, config as settings
log = logging.getLogger("net")
_client = None
def client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20, headers={"User-Agent": "fomo-desk/1.0"})
    return _client
class RateLimit(Exception): pass
class Dex:
    calls = []
    backoff_until = 0
    @classmethod
    async def tokens(cls, mints):
        """Batched /tokens/v1/solana (30 per call). Returns {mint: best pumpswap pair or None}."""
        out = {}
        for i in range(0, len(mints), 30):
            chunk = mints[i:i+30]
            while True:
                now = time.time()
                if now < cls.backoff_until:
                    await asyncio.sleep(cls.backoff_until - now); continue
                cls.calls = [t for t in cls.calls if now - t < 60]
                if len(cls.calls) >= settings.get("scanner.max_dex_rpm"):
                    await asyncio.sleep(1); continue
                break
            cls.calls.append(time.time())
            r = await client().get("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk))
            if r.status_code == 429:
                cls.backoff_until = time.time() + 30
                raise RateLimit()
            r.raise_for_status()
            for p in r.json() or []:
                m = (p.get("baseToken") or {}).get("address")
                if m not in chunk or p.get("dexId") != "pumpswap": continue
                if m not in out or ((p.get("liquidity") or {}).get("usd") or 0) > ((out[m].get("liquidity") or {}).get("usd") or 0):
                    out[m] = p
        return out
async def rpc(method, params, timeout=30):
    r = await client().post(settings.get("desk.rpc_url"), json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
    if r.status_code == 429: raise RateLimit()
    r.raise_for_status()
    j = r.json()
    if "error" in j: raise RuntimeError(f"rpc {method}: {j['error']}")
    return j["result"]
async def rugcheck(mint, which="report"):
    path = "report" if which == "report" else "insiders/graph"
    r = await client().get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/{path}")
    if r.status_code == 429: raise RateLimit()
    r.raise_for_status()
    return r.json()
async def retry(fn, *a, tries=3, gap=2):
    last = None
    for i in range(tries):
        try: return await fn(*a)
        except Exception as e:
            last = e
            if i < tries - 1: await asyncio.sleep(gap)
    raise last
def pair_fields(p):
    """DexScreener pair -> flat dict via fields.py paths."""
    if not p: return None
    g = lambda *ks: _dig(p, ks)
    return {"pairAddress": g("pairAddress"), "dexId": g("dexId"), "name": g("baseToken", "name"), "symbol": g("baseToken", "symbol"),
      "priceUsd": float(g("priceUsd")) if g("priceUsd") else None, "liq": g("liquidity", "usd"), "mcap": g("marketCap"),
      "v5": g("volume", "m5"), "v1": g("volume", "h1"), "v24": g("volume", "h24"),
      "b5": g("txns", "m5", "buys"), "s5": g("txns", "m5", "sells"), "b1": g("txns", "h1", "buys"), "s1": g("txns", "h1", "sells"),
      "p5": g("priceChange", "m5"), "p1": g("priceChange", "h1"), "p24": g("priceChange", "h24"), "created": g("pairCreatedAt")}
def _dig(o, ks):
    for k in ks:
        if not isinstance(o, dict) or k not in o: return None
        o = o[k]
    return o
