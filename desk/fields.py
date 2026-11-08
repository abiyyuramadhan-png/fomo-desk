# APPROVED by Abi 2026-11-03:
#  - Layer 5: lpLockedPct >= 99 covers locked AND burned.
#  - Layer 7: graph edges key is 'links'; empty list [] = 'None' (pass), missing links key = red 'no data: bundles'.
#  - Scanner: pool = DexScreener pairAddress; creator = RugCheck report.creator.
# Field mapping from raw samples in logs/raw/ (2026-11-03). None = not present in source.
FIELDS = {
 "migration": {  # PumpPortal subscribeMigration message (top-level dict)
  "mint": "mint", "signature": "signature", "txType": "txType",
  "pool": None,      # 'pool' key holds the venue string "pump-amm", NOT a pool address -> use DexScreener pairAddress
  "creator": None,   # not in message -> RugCheck report.creator
 },
 "dexscreener": {  # response is a list; pick item with dexId=="pumpswap", max liquidity.usd
  "pairAddress": "[i].pairAddress", "dexId": "[i].dexId", "priceUsd": "[i].priceUsd",  # string
  "liquidity_usd": "[i].liquidity.usd", "marketCap": "[i].marketCap",
  "volume_m5": "[i].volume.m5", "volume_h1": "[i].volume.h1", "volume_h24": "[i].volume.h24",
  "buys_m5": "[i].txns.m5.buys", "sells_m5": "[i].txns.m5.sells",
  "buys_h1": "[i].txns.h1.buys", "sells_h1": "[i].txns.h1.sells",
  "priceChange_m5": "[i].priceChange.m5", "priceChange_h1": "[i].priceChange.h1", "priceChange_h24": "[i].priceChange.h24",
  "pairCreatedAt": "[i].pairCreatedAt",  # ms epoch
 },
 "rugcheck_report": {
  "creator": "creator", "creatorBalance": "creatorBalance",
  "markets_pool_key": "markets[].pubkey",  # == DexScreener pairAddress (marketType pump_fun_amm)
  "lp_locked_pct": "markets[].lp.lpLockedPct",
  "lp_burned_pct": None,  # no burn key in sample; lpLockedPct covers locked+burned
 },
 "rugcheck_graph": {  # response is a list of networks; [] when none found
  "nodes": "[n].nodes[]", "node_wallet": "[n].nodes[].id",
  "edges": "[n].links[]", "edge_from": "[n].links[].source", "edge_to": "[n].links[].target",
  "holder_flag": "[n].nodes[].holdings",  # raw amount; holder = holdings > 0 (no boolean flag)
 },
 "rpc_getaccountinfo": {
  "mintAuthority": "result.value.data.parsed.info.mintAuthority",
  "freezeAuthority": "result.value.data.parsed.info.freezeAuthority",
  "supply": "result.value.data.parsed.info.supply",  # string, raw units
  "decimals": "result.value.data.parsed.info.decimals",
  "program": "result.value.data.program",
 },
}
