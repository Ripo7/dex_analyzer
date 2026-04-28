from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TokenSafety:
    is_honeypot: bool = False
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    is_mintable: bool = False
    owner_renounced: bool = False
    lp_locked_pct: float = 0.0   # 0-100
    is_blacklist: bool = False    # freeze/blacklist function present


@dataclass
class Token:
    symbol: str
    name: str
    address: str       # base token contract address
    pair_address: str  # DEX pair/pool contract address (used for price refresh)
    chain: str
    price_usd: float
    volume_24h: float
    price_change_24h: float
    liquidity_usd: float
    market_cap: float = 0.0
    pair_created_at: datetime | None = None
    safety: TokenSafety | None = None
    volume_1h: float = 0.0
    buys_1h: int = 0
    sells_1h: int = 0

    @property
    def age_minutes(self) -> int | None:
        if not self.pair_created_at:
            return None
        return int((datetime.now(tz=timezone.utc) - self.pair_created_at).total_seconds() / 60)

    @property
    def age_days(self) -> int | None:
        if not self.pair_created_at:
            return None
        return (datetime.now(tz=timezone.utc) - self.pair_created_at).days


@dataclass
class WhaleSignal:
    token: Token
    avg_buy_usd: float      # average buy size over the last hour
    buy_sell_ratio: float   # 0-1, closer to 1 = more buys than sells
    vol_spike: float        # h1 vol vs hourly average from h24
    whale_score: float

    @property
    def symbol(self) -> str:
        return self.token.symbol


@dataclass
class RankedToken:
    token: Token
    score: float
    status: str        # "NEW" | "RESURGENT" | "TRENDING"
    volume_spike: bool = False

    @property
    def symbol(self) -> str:
        return self.token.symbol
