from datetime import datetime, timezone

import requests

from .models import Token

_BASE = "https://api.dexscreener.com/latest/dex"
_TIMEOUT = 10


def search_token(symbol: str) -> Token | None:
    """Return the best-matching Token for *symbol* from DexScreener, or None."""
    try:
        resp = requests.get(f"{_BASE}/search", params={"q": symbol}, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    pairs = resp.json().get("pairs") or []
    if not pairs:
        return None

    # Prefer the pair with the highest 24h volume
    pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)
    pair = pairs[0]

    base = pair.get("baseToken", {})
    pair_created_ms = pair.get("pairCreatedAt")
    pair_created_at = (
        datetime.fromtimestamp(pair_created_ms / 1000, tz=timezone.utc)
        if pair_created_ms
        else None
    )

    return Token(
        symbol=base.get("symbol", symbol).upper(),
        name=base.get("name", ""),
        address=base.get("address", ""),
        chain=pair.get("chainId", ""),
        price_usd=float(pair.get("priceUsd") or 0),
        volume_24h=float(pair.get("volume", {}).get("h24") or 0),
        price_change_24h=float(pair.get("priceChange", {}).get("h24") or 0),
        liquidity_usd=float(pair.get("liquidity", {}).get("usd") or 0),
        pair_created_at=pair_created_at,
    )
