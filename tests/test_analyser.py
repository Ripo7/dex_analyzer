from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from dex_analyser.models import Token


def _token(symbol="PEPE", volume=1_000_000, price_change=10.0, created_days_ago=30, liquidity=500_000):
    return Token(
        symbol=symbol,
        name=symbol + " Token",
        address="0xabc",
        pair_address="0xpair",
        chain="ethereum",
        price_usd=0.001,
        volume_24h=volume,
        price_change_24h=price_change,
        liquidity_usd=liquidity,
        market_cap=5_000_000,
        pair_created_at=datetime.now(tz=timezone.utc) - timedelta(days=created_days_ago),
    )


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
def test_analyse_ranks_by_score(_load, _save):
    from dex_analyser.analyser import analyse
    tokens = [_token("PEPE", volume=2_000_000), _token("WIF", volume=500_000)]
    ranked = analyse(tokens, top_n=2)
    assert len(ranked) == 2
    assert ranked[0].symbol == "PEPE"
    assert ranked[0].score > ranked[1].score


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
def test_new_token_status(_load, _save):
    from dex_analyser.analyser import analyse
    ranked = analyse([_token("NEWCOIN", created_days_ago=2)], top_n=1)
    assert ranked[0].status == "NEW"


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={"PEPE": 20_000})
def test_resurgent_token_status(_load, _save):
    from dex_analyser.analyser import analyse
    # volume 2× previous → RESURGENT
    ranked = analyse([_token("PEPE", volume=80_000, created_days_ago=200)], top_n=1)
    assert ranked[0].status == "RESURGENT"
    assert ranked[0].volume_spike is True


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={"SOL": 70_000})
def test_trending_token_status(_load, _save):
    from dex_analyser.analyser import analyse
    # volume NOT 2× previous → TRENDING
    ranked = analyse([_token("SOL", volume=80_000, created_days_ago=500)], top_n=1)
    assert ranked[0].status == "TRENDING"
    assert ranked[0].volume_spike is False


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
def test_scam_filters(_load, _save):
    from dex_analyser.analyser import analyse
    tokens = [
        _token("LOWLIQ", volume=100_000, liquidity=500),
        _token("C0IN"),
        _token("PUMP", price_change=5_000.0),
        _token("LEGIT"),
    ]
    ranked = analyse(tokens, top_n=10)
    symbols = [r.symbol for r in ranked]
    assert "LEGIT" in symbols
    assert "LOWLIQ" not in symbols
    assert "C0IN" not in symbols
    assert "PUMP" not in symbols


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
def test_deduplicates_by_symbol_keeps_highest_volume(_load, _save):
    from dex_analyser.analyser import analyse
    tokens = [_token("PEPE", volume=200_000), _token("PEPE", volume=900_000)]
    ranked = analyse(tokens, top_n=10)
    assert len(ranked) == 1
    assert ranked[0].token.volume_24h == 900_000


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
def test_empty_token_list_returns_empty(_load, _save):
    from dex_analyser.analyser import analyse
    assert analyse([]) == []
