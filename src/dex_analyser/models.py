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
class WhaleEntry:
    wallet: str
    total_bought_usd: float
    tx_count: int
    last_buy_ago_minutes: int
    first_buy_ago_minutes: int = 0
    portfolio_usd: float = 0.0
    flags: list = field(default_factory=list)
    bsc_bag: list = field(default_factory=list)   # [{"symbol": "CAKE", "usd_value": 8000}]
    token_holding_usd: float = 0.0               # current value of the pool's token in their wallet


@dataclass
class RankedToken:
    token: Token
    score: float
    status: str        # "NEW" | "RESURGENT" | "TRENDING"
    volume_spike: bool = False

    @property
    def symbol(self) -> str:
        return self.token.symbol
