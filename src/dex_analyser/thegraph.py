import time
from datetime import datetime, timezone

import requests

_BASE = "https://api.geckoterminal.com/api/v2"
_HEADERS = {"Accept": "application/json;version=20230302"}
_TIMEOUT = 15

_SKIP_SYMBOLS = {"WBNB", "BNB", "USDT", "BUSD", "USDC", "DAI", "WETH", "ETH", "BTCB"}
_DEBANK = "https://openapi.debank.com/v1"


def fetch_wallet_portfolio_usd(address: str) -> float:
    """Return total portfolio value in USD from DeBank. Returns 0.0 on failure."""
    try:
        resp = requests.get(
            f"{_DEBANK}/user/total_balance",
            params={"id": address},
            timeout=8,
        )
        if resp.status_code == 200:
            return float(resp.json().get("usd_value") or 0)
    except Exception:
        pass
    return 0.0


def discover_trending_bsc_pools(top_n: int = 5) -> list[dict]:
    """Return top trending BSC pools from GeckoTerminal, excluding stables/majors."""
    try:
        resp = requests.get(
            f"{_BASE}/networks/bsc/trending_pools",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        pools = resp.json().get("data", [])
    except requests.RequestException as e:
        print(f"[gecko] trending pools error: {e}", flush=True)
        return []

    result = []
    for pool in pools:
        attrs = pool.get("attributes", {})
        name = attrs.get("name", "")
        # name is like "CAKE / WBNB" — base token is before the slash
        base_symbol = name.split("/")[0].strip().upper()
        if base_symbol in _SKIP_SYMBOLS:
            continue
        result.append({
            "pool_address": attrs.get("address", ""),
            "symbol": base_symbol,
            "volume_24h": float((attrs.get("volume_usd") or {}).get("h24") or 0),
        })
        if len(result) >= top_n:
            break

    print(f"[gecko] found {len(result)} trending BSC pools: {[r['symbol'] for r in result]}", flush=True)
    return result


def fetch_pair_swaps(pair_address: str, hours: int = 6, limit: int = 500) -> list[dict]:
    """Return buy trades for a BSC pool from GeckoTerminal (free, no key needed)."""
    cutoff = int(time.time()) - hours * 3600
    url = f"{_BASE}/networks/bsc/pools/{pair_address}/trades"
    print(f"[gecko] querying pool={pair_address[:10]}… cutoff={cutoff}", flush=True)

    try:
        resp = requests.get(
            url,
            params={"trade_volume_in_usd_greater_than": 0},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[gecko] request error: {e}", flush=True)
        return []

    trades = data.get("data", [])
    print(f"[gecko] got {len(trades)} trades for {pair_address[:10]}…", flush=True)

    result: list[dict] = []
    for trade in trades:
        attrs = trade.get("attributes", {})
        kind = attrs.get("kind")
        if kind not in ("buy", "sell"):
            continue
        ts_str = attrs.get("block_timestamp", "")
        try:
            ts = int(datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
        except (ValueError, AttributeError):
            continue
        if ts < cutoff:
            continue
        result.append({
            "to": attrs.get("tx_from_address", "").lower(),
            "amountUSD": attrs.get("volume_in_usd", "0"),
            "timestamp": ts,
            "kind": kind,
        })

    return result
