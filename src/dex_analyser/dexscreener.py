from datetime import datetime, timezone

import requests

from .models import Token

_BASE = "https://api.dexscreener.com/latest/dex"
_DISC_BASE = "https://api.dexscreener.com"
_TIMEOUT = 10


def _pair_to_token(pair: dict) -> Token | None:
    base = pair.get("baseToken", {})
    if not base.get("symbol"):
        return None
    pair_created_ms = pair.get("pairCreatedAt")
    pair_created_at = (
        datetime.fromtimestamp(pair_created_ms / 1000, tz=timezone.utc)
        if pair_created_ms
        else None
    )
    market_cap = float(pair.get("marketCap") or pair.get("fdv") or 0)
    return Token(
        symbol=base.get("symbol", "").upper(),
        name=base.get("name", ""),
        address=base.get("address", ""),
        pair_address=pair.get("pairAddress", ""),
        chain=pair.get("chainId", ""),
        price_usd=float(pair.get("priceUsd") or 0),
        volume_24h=float(pair.get("volume", {}).get("h24") or 0),
        price_change_24h=float(pair.get("priceChange", {}).get("h24") or 0),
        liquidity_usd=float(pair.get("liquidity", {}).get("usd") or 0),
        market_cap=market_cap,
        pair_created_at=pair_created_at,
    )


def get_pair_address_for_token(chain: str, token_address: str) -> str | None:
    """Return the best pair address for a known token contract address."""
    try:
        resp = requests.get(f"{_BASE}/tokens/{token_address}", timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    pairs = resp.json().get("pairs") or []
    chain_pairs = [p for p in pairs if p.get("chainId", "").lower() == chain.lower()]
    if not chain_pairs:
        chain_pairs = pairs
    if not chain_pairs:
        return None
    chain_pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)
    return chain_pairs[0].get("pairAddress")


def get_price_by_address(chain: str, address: str) -> float | None:
    """Fetch the current price for a known pair address. Returns None on failure."""
    try:
        resp = requests.get(f"{_BASE}/pairs/{chain}/{address}", timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    pairs = resp.json().get("pairs") or []
    if not pairs:
        return None
    return float(pairs[0].get("priceUsd") or 0) or None


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

    pairs.sort(key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0), reverse=True)
    return _pair_to_token(pairs[0])


def _fetch_discovery(path: str) -> list[dict]:
    try:
        resp = requests.get(f"{_DISC_BASE}{path}", timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except requests.RequestException:
        return []


def discover_bsc_tokens(top_n: int = 20) -> list[Token]:
    """Return the top BSC tokens by 24h volume from DexScreener search."""
    tokens: list[Token] = []
    seen: set[str] = set()

    for query in ("WBNB", "USDT BSC", "BUSD"):
        try:
            resp = requests.get(f"{_BASE}/search", params={"q": query}, timeout=_TIMEOUT)
            resp.raise_for_status()
            pairs = resp.json().get("pairs") or []
        except requests.RequestException:
            continue

        for pair in pairs:
            if pair.get("chainId", "").lower() != "bsc":
                continue
            tok = _pair_to_token(pair)
            if tok and tok.address and tok.address not in seen:
                seen.add(tok.address)
                tokens.append(tok)

    tokens.sort(key=lambda t: t.volume_24h, reverse=True)
    return tokens[:top_n]


def discover_tokens() -> list[Token]:
    """
    Fetch recently listed and top-boosted tokens from DexScreener discovery endpoints,
    then batch-enrich each with live pair data.
    """
    seen: set[tuple[str, str]] = set()
    candidates: list[tuple[str, str]] = []  # (chainId, tokenAddress)

    for item in _fetch_discovery("/token-profiles/latest/v1"):
        key = (item.get("chainId", ""), item.get("tokenAddress", ""))
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            candidates.append(key)

    for item in _fetch_discovery("/token-boosts/top/v1"):
        key = (item.get("chainId", ""), item.get("tokenAddress", ""))
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            candidates.append(key)

    # Batch-fetch pair data, 30 token addresses at a time
    addresses = [addr for _, addr in candidates[:60]]
    tokens: list[Token] = []

    for i in range(0, len(addresses), 30):
        batch = ",".join(addresses[i : i + 30])
        try:
            resp = requests.get(f"{_BASE}/tokens/{batch}", timeout=_TIMEOUT)
            resp.raise_for_status()
            pairs = resp.json().get("pairs") or []
        except requests.RequestException:
            continue

        # Per base token address keep only the highest-volume pair
        best: dict[str, dict] = {}
        for pair in pairs:
            base_addr = pair.get("baseToken", {}).get("address", "")
            vol = float(pair.get("volume", {}).get("h24") or 0)
            if base_addr not in best or vol > float(best[base_addr].get("volume", {}).get("h24") or 0):
                best[base_addr] = pair

        for pair in best.values():
            tok = _pair_to_token(pair)
            if tok:
                tokens.append(tok)

    return tokens
