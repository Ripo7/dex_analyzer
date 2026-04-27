import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dexscreener import search_token
from .models import RankedToken, Token

_CACHE_PATH = Path.home() / ".dex-analyser" / "history.json"
_NEW_TOKEN_DAYS = 7
_RESURGENT_SPIKE_RATIO = 2.0  # tweet count must be 2× previous to be "RESURGENT"


def _load_history() -> dict[str, int]:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_history(counts: dict[str, int]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_history()
    existing.update(counts)
    _CACHE_PATH.write_text(json.dumps(existing, indent=2))


def _classify(token: Token, tweet_count: int, prev_count: int) -> str:
    now = datetime.now(tz=timezone.utc)
    if token.pair_created_at and (now - token.pair_created_at) < timedelta(days=_NEW_TOKEN_DAYS):
        return "NEW"
    if prev_count > 0 and tweet_count >= prev_count * _RESURGENT_SPIKE_RATIO:
        return "RESURGENT"
    return "TRENDING"


def _normalize(values: list[float]) -> list[float]:
    max_v = max(values, default=1) or 1
    return [v / max_v for v in values]


def analyse(
    mention_counts: dict[str, int],
    top_n: int = 10,
    weight_tweet: float = 0.4,
    weight_vol: float = 0.4,
    weight_chg: float = 0.2,
) -> list[RankedToken]:
    history = _load_history()

    symbols = sorted(mention_counts, key=mention_counts.__getitem__, reverse=True)[:top_n * 3]

    tokens: list[tuple[str, Token, int]] = []
    for sym in symbols:
        token = search_token(sym)
        if token:
            tokens.append((sym, token, mention_counts[sym]))

    if not tokens:
        return []

    tweet_counts = [t for _, _, t in tokens]
    volumes = [tok.volume_24h for _, tok, _ in tokens]
    changes = [tok.price_change_24h for _, tok, _ in tokens]

    norm_tweets = _normalize(tweet_counts)
    norm_vols = _normalize(volumes)
    norm_chgs = _normalize([max(c, 0) for c in changes])

    ranked: list[RankedToken] = []
    for i, (sym, tok, count) in enumerate(tokens):
        score = (
            weight_tweet * norm_tweets[i]
            + weight_vol * norm_vols[i]
            + weight_chg * norm_chgs[i]
        )
        prev = history.get(sym, 0)
        ranked.append(
            RankedToken(
                token=tok,
                tweet_count=count,
                score=round(score, 4),
                status=_classify(tok, count, prev),
                previous_tweet_count=prev,
            )
        )

    ranked.sort(key=lambda r: r.score, reverse=True)
    result = ranked[:top_n]

    _save_history({sym: mention_counts[sym] for sym, _, _ in tokens})
    return result
