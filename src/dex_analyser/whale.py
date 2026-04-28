import time

from .bscscan import Transfer
from .models import Token, WhaleEntry

_MIN_BUY_USD = 500.0
_WHALE_HOURS = 6


def find_whales_from_swaps(swaps: list[dict], top_n: int = 10, min_buy_usd: float = _MIN_BUY_USD) -> list[WhaleEntry]:
    """Build WhaleEntry list from PancakeSwap subgraph swap dicts."""
    now = int(time.time())
    buckets: dict[str, dict] = {}

    for swap in swaps:
        wallet = swap.get("to", "").lower()
        if not wallet:
            continue
        usd = float(swap.get("amountUSD") or 0)
        ts = int(swap.get("timestamp") or 0)
        if wallet not in buckets:
            buckets[wallet] = {"total_usd": 0.0, "tx_count": 0, "last_ts": 0, "first_ts": ts}
        buckets[wallet]["total_usd"] += usd
        buckets[wallet]["tx_count"] += 1
        buckets[wallet]["last_ts"] = max(buckets[wallet]["last_ts"], ts)
        buckets[wallet]["first_ts"] = min(buckets[wallet]["first_ts"], ts)

    whales: list[WhaleEntry] = []
    for wallet, b in buckets.items():
        if b["total_usd"] < min_buy_usd:
            continue
        whales.append(WhaleEntry(
            wallet=wallet,
            total_bought_usd=b["total_usd"],
            tx_count=b["tx_count"],
            last_buy_ago_minutes=(now - b["last_ts"]) // 60,
            first_buy_ago_minutes=(now - b["first_ts"]) // 60,
        ))

    whales.sort(key=lambda w: w.total_bought_usd, reverse=True)
    return whales[:top_n]


def find_whales(token: Token, transfers: list[Transfer], top_n: int = 10, min_buy_usd: float = _MIN_BUY_USD) -> list[WhaleEntry]:
    pair_addr = token.pair_address.lower()
    now = int(time.time())

    # A buy = tokens flowing OUT of the pair TO a wallet
    buckets: dict[str, dict] = {}
    for tx in transfers:
        if tx.from_addr != pair_addr:
            continue
        usd = tx.value_tokens * token.price_usd
        wallet = tx.to_addr
        if wallet not in buckets:
            buckets[wallet] = {"total_usd": 0.0, "tx_count": 0, "last_ts": 0}
        buckets[wallet]["total_usd"] += usd
        buckets[wallet]["tx_count"] += 1
        buckets[wallet]["last_ts"] = max(buckets[wallet]["last_ts"], tx.timestamp)

    whales: list[WhaleEntry] = []
    for wallet, b in buckets.items():
        if b["total_usd"] < min_buy_usd:
            continue
        whales.append(WhaleEntry(
            wallet=wallet,
            total_bought_usd=b["total_usd"],
            tx_count=b["tx_count"],
            last_buy_ago_minutes=(now - b["last_ts"]) // 60,
        ))

    whales.sort(key=lambda w: w.total_bought_usd, reverse=True)
    return whales[:top_n]
