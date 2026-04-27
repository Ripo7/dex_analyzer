from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Token:
    symbol: str
    name: str
    address: str
    chain: str
    price_usd: float
    volume_24h: float
    price_change_24h: float
    liquidity_usd: float
    pair_created_at: datetime | None = None


@dataclass
class RankedToken:
    token: Token
    tweet_count: int
    score: float
    status: str  # "NEW" | "RESURGENT" | "TRENDING"
    previous_tweet_count: int = 0

    @property
    def symbol(self) -> str:
        return self.token.symbol
