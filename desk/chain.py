"""Solana reads shared by Scanner and Auditor."""
from solders.pubkey import Pubkey
import net
PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
def bonding_curve(mint):
    return str(Pubkey.find_program_address([b"bonding-curve", bytes(Pubkey.from_string(mint))], PUMP_PROGRAM)[0])
async def supply(mint):
    v = (await net.rpc("getTokenSupply", [mint]))["value"]
    return float(v["uiAmountString"] or 0)
async def top10(mint, pool, sup=None):
    """Percent of supply held by top 10 accounts, pool + curve owners excluded."""
    sup = sup if sup is not None else await supply(mint)
    if not sup: raise ValueError("no supply")
    try:
        big = (await net.rpc("getTokenLargestAccounts", [mint]))["value"]
    except Exception:
        # public RPC 429s getTokenLargestAccounts per method: fall back to every token account (owner included)
        excl = {pool, bonding_curve(mint)}
        amts = []
        for a in await program_accounts(mint):
            inf = a["account"]["data"]["parsed"]["info"]
            if inf.get("owner") in excl or a["pubkey"] in excl: continue
            amts.append(float(inf["tokenAmount"]["uiAmountString"] or 0))
        return round(100 * sum(sorted(amts, reverse=True)[:10]) / sup, 2)
    addrs = [b["address"] for b in big]
    accs = (await net.rpc("getMultipleAccounts", [addrs, {"encoding": "jsonParsed"}]))["value"] if addrs else []
    excl = {pool, bonding_curve(mint)}
    amts = []
    for b, a in zip(big, accs):
        owner = (((a or {}).get("data") or {}).get("parsed") or {}).get("info", {}).get("owner") if isinstance((a or {}).get("data"), dict) else None
        if owner in excl or b["address"] in excl: continue
        amts.append(float(b["uiAmountString"] or 0))
    return round(100 * sum(sorted(amts, reverse=True)[:10]) / sup, 2)
async def owner_balance(owner, mint):
    r = await net.rpc("getTokenAccountsByOwner", [owner, {"mint": mint}, {"encoding": "jsonParsed"}])
    return sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"] or 0) for a in r["value"])
async def program_accounts(mint):
    """All token accounts of mint on Token and Token-2022."""
    out = []
    for prog, filt in ((TOKEN, [{"dataSize": 165}, {"memcmp": {"offset": 0, "bytes": mint}}]),
                       (TOKEN22, [{"memcmp": {"offset": 0, "bytes": mint}}])):
        out += await net.rpc("getProgramAccounts", [prog, {"encoding": "jsonParsed", "filters": filt}], timeout=60)
    return out
