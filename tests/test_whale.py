from datetime import datetime, timedelta, timezone

import pytest

from dex_analyser.models import Token


def _token(symbol="PEPE", volume_24h=1_000_000, volume_1h=100_000,
           buys_1h=20, sells_1h=10, liquidity=500_000):
    return Token(
        symbol=symbol, name=symbol, address="0xabc", pair_address="0xpair",
        chain="solana", price_usd=0.001, volume_24h=volume_24h,
        price_change_24h=10.0, liquidity_usd=liquidity,
        pair_created_at=datetime.now(tz=timezone.utc) - timedelta(hours=2),
        volume_1h=volume_1h, buys_1h=buys_1h, sells_1h=sells_1h,
    )


def test_find_whale_tokens_basic():
    from dex_analyser.whale import find_whale_tokens
    tokens = [_token("WHALE", volume_1h=50_000, buys_1h=10, sells_1h=5)]
    signals = find_whale_tokens(tokens)
    assert len(signals) == 1
    assert signals[0].symbol == "WHALE"
    assert signals[0].avg_buy_usd == pytest.approx(5_000.0)


def test_filtered_below_min_avg_buy():
    from dex_analyser.whale import find_whale_tokens
    # avg buy = 100 / 10 = $10 → below $500 threshold
    tokens = [_token("SMALL", volume_1h=100, buys_1h=10)]
    assert find_whale_tokens(tokens) == []


def test_filtered_below_min_buys():
    from dex_analyser.whale import find_whale_tokens
    # only 2 buys → below minimum of 3
    tokens = [_token("FEW", volume_1h=10_000, buys_1h=2)]
    assert find_whale_tokens(tokens) == []


def test_buy_sell_ratio_calculation():
    from dex_analyser.whale import find_whale_tokens
    tokens = [_token("RATIO", volume_1h=10_000, buys_1h=9, sells_1h=1)]
    signals = find_whale_tokens(tokens)
    assert signals[0].buy_sell_ratio == pytest.approx(0.9)


def test_vol_spike_calculation():
    from dex_analyser.whale import find_whale_tokens
    # hourly avg = 24_000 / 24 = 1_000. h1 vol = 5_000 → spike = 5×
    tokens = [_token("SPIKE", volume_24h=24_000, volume_1h=5_000, buys_1h=5)]
    signals = find_whale_tokens(tokens)
    assert signals[0].vol_spike == pytest.approx(5.0)


def test_ranked_by_whale_score():
    from dex_analyser.whale import find_whale_tokens
    low = _token("LOW", volume_1h=2_000, buys_1h=4)    # avg $500
    high = _token("HIGH", volume_1h=50_000, buys_1h=5)  # avg $10K
    signals = find_whale_tokens([low, high])
    assert signals[0].symbol == "HIGH"


def test_top_n_respected():
    from dex_analyser.whale import find_whale_tokens
    tokens = [_token(f"T{i}", volume_1h=10_000, buys_1h=5) for i in range(20)]
    signals = find_whale_tokens(tokens, top_n=5)
    assert len(signals) == 5
