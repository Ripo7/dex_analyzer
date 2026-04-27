from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from dex_analyser.dexscreener import search_token


def _make_pair(symbol="PEPE", volume=500_000, price="0.0000081", created_ms=None):
    return {
        "baseToken": {"symbol": symbol, "name": symbol + " Token", "address": "0xabc"},
        "chainId": "ethereum",
        "priceUsd": price,
        "volume": {"h24": volume},
        "priceChange": {"h24": 12.5},
        "liquidity": {"usd": 2_000_000},
        "pairCreatedAt": created_ms,
    }


@patch("dex_analyser.dexscreener.requests.get")
def test_search_token_returns_best_volume(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "pairs": [
            _make_pair("PEPE", volume=100_000),
            _make_pair("PEPE", volume=999_000),
        ]
    }
    mock_get.return_value = mock_resp

    token = search_token("PEPE")

    assert token is not None
    assert token.symbol == "PEPE"
    assert token.volume_24h == 999_000


@patch("dex_analyser.dexscreener.requests.get")
def test_search_token_no_pairs_returns_none(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"pairs": []}
    mock_get.return_value = mock_resp

    assert search_token("UNKNOWN") is None


@patch("dex_analyser.dexscreener.requests.get")
def test_search_token_parses_created_at(mock_get):
    created_ms = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"pairs": [_make_pair(created_ms=created_ms)]}
    mock_get.return_value = mock_resp

    token = search_token("PEPE")
    assert token is not None
    assert token.pair_created_at == datetime(2025, 1, 1, tzinfo=timezone.utc)
