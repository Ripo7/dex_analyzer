import time

from .bscscan import Transfer
from .models import Token, WhaleEntry

_MIN_BUY_USD = 500.0
_WHALE_HOURS = 6


def find_whales_from_swaps(swaps: list[dict], top_n: int = 10, min_buy_usd: float = _MIN_BUY_USD) -> list[WhaleEntry]:
    """Build WhaleEntry list from GeckoTerminal trade dicts (buys + sells)."""
    now = int(time.time())
    buy_buckets: dict[str, dict] = {}
    sellers: set[str] = set()

    for swap in swaps:
        wallet = swap.get("to", "").lower()
        if not wallet:
            continue
        kind = swap.get("kind", "buy")
        usd = float(swap.get("amountUSD") or 0)
        ts = int(swap.get("timestamp") or 0)

        if kind == "sell":
            sellers.add(wallet)
            continue

        if wallet not in buy_buckets:
            buy_buckets[wallet] = {"total_usd": 0.0, "tx_count": 0, "last_ts": 0, "first_ts": ts, "timestamps": []}
        buy_buckets[wallet]["total_usd"] += usd
        buy_buckets[wallet]["tx_count"] += 1
        buy_buckets[wallet]["last_ts"] = max(buy_buckets[wallet]["last_ts"], ts)
        buy_buckets[wallet]["first_ts"] = min(buy_buckets[wallet]["first_ts"], ts)
        buy_buckets[wallet]["timestamps"].append(ts)

    whales: list[WhaleEntry] = []
    for wallet, b in buy_buckets.items():
        if b["total_usd"] < min_buy_usd:
            continue

        flags: list[str] = []
        if wallet in sellers:
            flags.append("also_sold")
        # Rapid-fire: any two consecutive buys within 5 minutes
        sorted_ts = sorted(b["timestamps"])
        if any(sorted_ts[i+1] - sorted_ts[i] < 300 for i in range(len(sorted_ts) - 1)):
            flags.append("bot_rapid")

        whales.append(WhaleEntry(
            wallet=wallet,
            total_bought_usd=b["total_usd"],
            tx_count=b["tx_count"],
            last_buy_ago_minutes=(now - b["last_ts"]) // 60,
            first_buy_ago_minutes=(now - b["first_ts"]) // 60,
            flags=flags,
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
