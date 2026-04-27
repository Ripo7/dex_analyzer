import json
from datetime import datetime, timezone
from pathlib import Path

from .dexscreener import get_pair_address_for_token, get_price_by_address, search_token
from .models import Token

_POSITIONS_PATH = Path.home() / ".dex-analyser" / "positions.json"
DEFAULT_SIZE_USD = 100.0


def load() -> dict:
    if _POSITIONS_PATH.exists():
        try:
            return json.loads(_POSITIONS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save(positions: dict) -> None:
    _POSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _POSITIONS_PATH.write_text(json.dumps(positions, indent=2))


def enter(token: Token, size_usd: float = DEFAULT_SIZE_USD) -> dict:
    return {
        "symbol": token.symbol,
        "name": token.name,
        "chain": token.chain,
        "address": token.address,
        "pair_address": token.pair_address,   # pool address for deterministic price refresh
        "entry_price": token.price_usd,
        "entry_time": datetime.now(tz=timezone.utc).isoformat(),
        "size_usd": size_usd,
        "status": "open",
    }


def close(symbol: str) -> bool:
    positions = load()
    if symbol in positions and positions[symbol]["status"] == "open":
        positions[symbol]["status"] = "closed"
        positions[symbol]["close_time"] = datetime.now(tz=timezone.utc).isoformat()
        save(positions)
        return True
    return False


def current_prices(positions: dict) -> dict[str, float]:
    """
    Fetch latest price for every open position from DexScreener.
    Uses the saved pair address for a deterministic lookup so we always
    price the *exact* pair that was entered, not whichever one DexScreener
    returns first for the symbol on a fresh search.
    """
    prices: dict[str, float] = {}
    for sym, pos in positions.items():
        if pos.get("status") != "open":
            continue
        chain = pos.get("chain", "")
        pair_address = pos.get("pair_address", "")
        price = None
        if chain and pair_address:
            price = get_price_by_address(chain, pair_address)
        if price is None:
            # Fallback: symbol search (less reliable)
            token = search_token(sym)
            price = token.price_usd if token else 0.0
        prices[sym] = price or 0.0
    return prices


def pnl(entry_price: float, current_price: float, size_usd: float) -> tuple[float, float]:
    """Return (pnl_pct, pnl_usd)."""
    if entry_price <= 0:
        return 0.0, 0.0
    pct = (current_price - entry_price) / entry_price * 100
    usd = size_usd * pct / 100
    return round(pct, 2), round(usd, 2)


def entry_age_days(entry_time: str) -> int:
    dt = datetime.fromisoformat(entry_time)
    return (datetime.now(tz=timezone.utc) - dt).days
