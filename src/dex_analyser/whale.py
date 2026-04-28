from .models import Token, WhaleSignal

_MIN_AVG_BUY = 500.0   # $500 minimum average buy to qualify
_MIN_BUYS = 3           # at least 3 buys in the hour to filter noise


def _whale_score(avg_buy: float, buy_ratio: float, vol_spike: float) -> float:
    # avg buy normalised against $10K ceiling, buy ratio 0-1, spike normalised against 5× ceiling
    return round(
        0.5 * min(avg_buy / 10_000, 1.0)
        + 0.3 * buy_ratio
        + 0.2 * min(vol_spike / 5.0, 1.0),
        4,
    )


def find_whale_tokens(tokens: list[Token], top_n: int = 10) -> list[WhaleSignal]:
    signals: list[WhaleSignal] = []

    for tok in tokens:
        if tok.buys_1h < _MIN_BUYS or tok.volume_1h <= 0:
            continue

        avg_buy = tok.volume_1h / tok.buys_1h
        if avg_buy < _MIN_AVG_BUY:
            continue

        total_txns = tok.buys_1h + tok.sells_1h
        buy_ratio = tok.buys_1h / total_txns if total_txns > 0 else 0.5

        hourly_avg = tok.volume_24h / 24 if tok.volume_24h > 0 else 0
        vol_spike = tok.volume_1h / hourly_avg if hourly_avg > 0 else 1.0

        signals.append(WhaleSignal(
            token=tok,
            avg_buy_usd=avg_buy,
            buy_sell_ratio=buy_ratio,
            vol_spike=vol_spike,
            whale_score=_whale_score(avg_buy, buy_ratio, vol_spike),
        ))

    signals.sort(key=lambda s: s.whale_score, reverse=True)
    return signals[:top_n]
