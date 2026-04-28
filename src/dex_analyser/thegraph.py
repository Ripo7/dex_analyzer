import time

import requests

_ENDPOINT = "https://api.thegraph.com/subgraphs/name/pancakeswap/exchange-v2"
_TIMEOUT = 15

_QUERY = """
query($pair: String!, $cutoff: Int!, $first: Int!) {
  swaps(
    first: $first
    orderBy: timestamp
    orderDirection: desc
    where: { pair: $pair, timestamp_gte: $cutoff }
  ) {
    to
    amountUSD
    timestamp
  }
}
"""


def fetch_pair_swaps(pair_address: str, hours: int = 6, limit: int = 500) -> list[dict]:
    """Return swap events for a PancakeSwap v2 pair in the last `hours` hours."""
    cutoff = int(time.time()) - hours * 3600
    print(f"[thegraph] querying pair={pair_address.lower()} cutoff={cutoff}", flush=True)
    try:
        resp = requests.post(
            _ENDPOINT,
            json={
                "query": _QUERY,
                "variables": {
                    "pair": pair_address.lower(),
                    "cutoff": cutoff,
                    "first": limit,
                },
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[thegraph] request error: {e}", flush=True)
        return []

    errors = data.get("errors")
    if errors:
        print(f"[thegraph] errors: {errors}", flush=True)
        return []

    swaps = data.get("data", {}).get("swaps", [])
    print(f"[thegraph] got {len(swaps)} swaps for {pair_address[:10]}…", flush=True)
    return swaps
