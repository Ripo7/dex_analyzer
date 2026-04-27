from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from dex_analyser.models import Token


def _token(symbol="PEPE", volume=1_000_000, price_change=10.0, created_days_ago=30):
    created_at = datetime.now(tz=timezone.utc) - timedelta(days=created_days_ago)
    return Token(
        symbol=symbol,
        name=symbol + " Token",
        address="0xabc",
        chain="ethereum",
        price_usd=0.001,
        volume_24h=volume,
        price_change_24h=price_change,
        liquidity_usd=500_000,
        pair_created_at=created_at,
    )


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
@patch("dex_analyser.analyser.search_token")
def test_analyse_ranks_by_score(mock_search, _mock_load, _mock_save):
    mock_search.side_effect = lambda sym: _token(sym, volume={"PEPE": 2_000_000, "WIF": 500_000}.get(sym, 0))

    from dex_analyser.analyser import analyse

    ranked = analyse({"PEPE": 100, "WIF": 50}, top_n=2)

    assert len(ranked) == 2
    assert ranked[0].symbol == "PEPE"
    assert ranked[0].score > ranked[1].score


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={})
@patch("dex_analyser.analyser.search_token")
def test_new_token_status(mock_search, _mock_load, _mock_save):
    mock_search.return_value = _token("NEWCOIN", created_days_ago=2)

    from dex_analyser.analyser import analyse

    ranked = analyse({"NEWCOIN": 10}, top_n=1)
    assert ranked[0].status == "NEW"


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={"PEPE": 20})
@patch("dex_analyser.analyser.search_token")
def test_resurgent_token_status(mock_search, _mock_load, _mock_save):
    mock_search.return_value = _token("PEPE", created_days_ago=200)

    from dex_analyser.analyser import analyse

    ranked = analyse({"PEPE": 80}, top_n=1)  # 80 >= 20 * 2 → RESURGENT
    assert ranked[0].status == "RESURGENT"


@patch("dex_analyser.analyser._save_history")
@patch("dex_analyser.analyser._load_history", return_value={"SOL": 70})
@patch("dex_analyser.analyser.search_token")
def test_trending_token_status(mock_search, _mock_load, _mock_save):
    mock_search.return_value = _token("SOL", created_days_ago=500)

    from dex_analyser.analyser import analyse

    ranked = analyse({"SOL": 80}, top_n=1)  # 80 < 70 * 2 → TRENDING
    assert ranked[0].status == "TRENDING"
