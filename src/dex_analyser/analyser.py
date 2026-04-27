import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dexscreener import discover_tokens
from .models import RankedToken, Token

_CACHE_PATH = Path.home() / ".dex-analyser" / "history.json"
_NEW_TOKEN_DAYS = 7
_RESURGENT_SPIKE_RATIO = 2.0

_MIN_LIQUIDITY = 25_000
_MIN_VOLUME = 50_000
_MAX_PRICE_CHANGE = 500
_MAX_VOL_LIQ_RATIO = 50
_MIN_SCORE = 0.30
_DIGIT_RE = re.compile(r"\d")


def _load_history() -> dict[str, float]:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_history(volumes: dict[str, float]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_history()
    existing.update(volumes)
    _CACHE_PATH.write_text(json.dumps(existing, indent=2))


def _is_scam(
    token: Token,
    min_liquidity: float,
    min_volume: float,
    max_price_change: float,
    max_vol_liq_ratio: float,
) -> bool:
    if _DIGIT_RE.search(token.symbol):
        return True
    if token.liquidity_usd < min_liquidity:
        return True
    if token.volume_24h < min_volume:
        return True
    if abs(token.price_change_24h) > max_price_change:
        return True
    if token.liquidity_usd > 0 and token.volume_24h / token.liquidity_usd > max_vol_liq_ratio:
        return True
    return False


def _classify(token: Token, current_vol: float, prev_vol: float) -> str:
    now = datetime.now(tz=timezone.utc)
    if token.pair_created_at and (now - token.pair_created_at) < timedelta(days=_NEW_TOKEN_DAYS):
        return "NEW"
    if prev_vol > 0 and current_vol >= prev_vol * _RESURGENT_SPIKE_RATIO:
        return "RESURGENT"
    return "TRENDING"


def _normalize(values: list[float]) -> list[float]:
    max_v = max(values, default=1) or 1
    return [v / max_v for v in values]


def analyse(
    tokens: list[Token],
    top_n: int = 10,
    weight_vol: float = 0.5,
    weight_chg: float = 0.3,
    weight_liq: float = 0.2,
    min_liquidity: float = _MIN_LIQUIDITY,
    min_volume: float = _MIN_VOLUME,
    max_price_change: float = _MAX_PRICE_CHANGE,
    max_vol_liq_ratio: float = _MAX_VOL_LIQ_RATIO,
) -> list[RankedToken]:
    history = _load_history()

    # Deduplicate by symbol — keep highest-volume pair per symbol
    by_symbol: dict[str, Token] = {}
    for tok in tokens:
        if tok.symbol not in by_symbol or tok.volume_24h > by_symbol[tok.symbol].volume_24h:
            by_symbol[tok.symbol] = tok

    clean = [
        tok for tok in by_symbol.values()
        if not _is_scam(tok, min_liquidity, min_volume, max_price_change, max_vol_liq_ratio)
    ]

    if not clean:
        return []

    volumes = [tok.volume_24h for tok in clean]
    changes = [tok.price_change_24h for tok in clean]
    liqs = [tok.liquidity_usd for tok in clean]

    norm_vols = _normalize(volumes)
    norm_chgs = _normalize([max(c, 0) for c in changes])
    norm_liqs = _normalize(liqs)

    ranked: list[RankedToken] = []
    for i, tok in enumerate(clean):
        score = (
            weight_vol * norm_vols[i]
            + weight_chg * norm_chgs[i]
            + weight_liq * norm_liqs[i]
        )
        prev_vol = history.get(tok.symbol, 0.0)
        ranked.append(
            RankedToken(
                token=tok,
                score=round(score, 4),
                status=_classify(tok, tok.volume_24h, prev_vol),
                volume_spike=prev_vol > 0 and tok.volume_24h >= prev_vol * _RESURGENT_SPIKE_RATIO,
            )
        )

    ranked.sort(key=lambda r: r.score, reverse=True)
    result = [r for r in ranked[:top_n] if r.score >= _MIN_SCORE]

    _save_history({tok.symbol: tok.volume_24h for tok in clean})
    return result


def discover_and_rank(**kwargs) -> list[RankedToken]:
    """Fetch tokens from DexScreener discovery endpoints and rank them."""
    tokens = discover_tokens()
    return analyse(tokens, **kwargs)
