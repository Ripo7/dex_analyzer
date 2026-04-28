import time
from datetime import datetime, timezone

import requests

_BASE = "https://api.geckoterminal.com/api/v2"
_TIMEOUT = 15


def fetch_pair_swaps(pair_address: str, hours: int = 6, limit: int = 500) -> list[dict]:
    """Return buy trades for a BSC pool from GeckoTerminal (free, no key needed)."""
    cutoff = int(time.time()) - hours * 3600
    url = f"{_BASE}/networks/bsc/pools/{pair_address}/trades"
    print(f"[gecko] querying pool={pair_address[:10]}… cutoff={cutoff}", flush=True)

    try:
        resp = requests.get(
            url,
            params={"trade_volume_in_usd_greater_than": 0},
            headers={"Accept": "application/json;version=20230302"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[gecko] request error: {e}", flush=True)
        return []

    trades = data.get("data", [])
    print(f"[gecko] got {len(trades)} trades for {pair_address[:10]}…", flush=True)

    # Normalise to the dict shape whale.py expects: to, amountUSD, timestamp
    result: list[dict] = []
    for trade in trades:
        attrs = trade.get("attributes", {})
        if attrs.get("kind") != "buy":
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
        })

    return result
