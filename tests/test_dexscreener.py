from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from dex_analyser.dexscreener import discover_tokens, search_token


def _make_pair(symbol="PEPE", volume=500_000, price="0.0000081", created_ms=None, fdv=1_000_000):
    return {
        "baseToken": {"symbol": symbol, "name": symbol + " Token", "address": "0xabc"},
        "pairAddress": "0xpair",
        "chainId": "ethereum",
        "priceUsd": price,
        "volume": {"h24": volume},
        "priceChange": {"h24": 12.5},
        "liquidity": {"usd": 2_000_000},
        "fdv": fdv,
        "pairCreatedAt": created_ms,
    }


@patch("dex_analyser.dexscreener.requests.get")
def test_search_token_returns_best_volume(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "pairs": [_make_pair("PEPE", volume=100_000), _make_pair("PEPE", volume=999_000)]
    }
    mock_get.return_value = mock_resp
    token = search_token("PEPE")
    assert token is not None
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
    assert token.pair_created_at == datetime(2025, 1, 1, tzinfo=timezone.utc)


@patch("dex_analyser.dexscreener.requests.get")
def test_search_token_parses_market_cap(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"pairs": [_make_pair(fdv=2_500_000)]}
    mock_get.return_value = mock_resp
    token = search_token("PEPE")
    assert token.market_cap == 2_500_000


@patch("dex_analyser.dexscreener.requests.get")
def test_discover_tokens_combines_profiles_and_boosts(mock_get):
    profile_resp = MagicMock()
    profile_resp.raise_for_status.return_value = None
    profile_resp.json.return_value = [
        {"chainId": "solana", "tokenAddress": "0xAAA"},
    ]

    boost_resp = MagicMock()
    boost_resp.raise_for_status.return_value = None
    boost_resp.json.return_value = [
        {"chainId": "ethereum", "tokenAddress": "0xBBB"},
    ]

    def _make_pair_addr(symbol, address, volume):
        p = _make_pair(symbol, volume=volume)
        p["baseToken"]["address"] = address
        return p

    batch_resp = MagicMock()
    batch_resp.raise_for_status.return_value = None
    batch_resp.json.return_value = {
        "pairs": [
            _make_pair_addr("AAA", "0xAAA", 200_000),
            _make_pair_addr("BBB", "0xBBB", 300_000),
        ]
    }

    mock_get.side_effect = [profile_resp, boost_resp, batch_resp]
    tokens = discover_tokens()
    symbols = {t.symbol for t in tokens}
    assert "AAA" in symbols
    assert "BBB" in symbols


@patch("dex_analyser.dexscreener.requests.get")
def test_discover_tokens_deduplicates_addresses(mock_get):
    same_entry = {"chainId": "solana", "tokenAddress": "0xAAA"}
    profile_resp = MagicMock()
    profile_resp.raise_for_status.return_value = None
    profile_resp.json.return_value = [same_entry, same_entry]  # duplicate

    boost_resp = MagicMock()
    boost_resp.raise_for_status.return_value = None
    boost_resp.json.return_value = [same_entry]  # same again from boosts

    batch_resp = MagicMock()
    batch_resp.raise_for_status.return_value = None
    batch_resp.json.return_value = {"pairs": [_make_pair("AAA", volume=200_000)]}

    mock_get.side_effect = [profile_resp, boost_resp, batch_resp]
    tokens = discover_tokens()
    # Only one unique token despite multiple appearances
    assert len([t for t in tokens if t.symbol == "AAA"]) == 1
