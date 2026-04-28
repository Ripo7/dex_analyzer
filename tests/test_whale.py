import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from dex_analyser.models import Token


def _token(symbol="PEPE", price_usd=0.001, pair_address="0xpair"):
    return Token(
        symbol=symbol, name=symbol, address="0xtoken", pair_address=pair_address,
        chain="bsc", price_usd=price_usd, volume_24h=500_000,
        price_change_24h=10.0, liquidity_usd=100_000,
        pair_created_at=datetime.now(tz=timezone.utc) - timedelta(hours=2),
    )


def _transfer(from_addr, to_addr, value_tokens, ago_seconds=60):
    from dex_analyser.bscscan import Transfer
    return Transfer(
        from_addr=from_addr.lower(),
        to_addr=to_addr.lower(),
        value_tokens=value_tokens,
        timestamp=int(time.time()) - ago_seconds,
    )


def test_find_whales_basic():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [_transfer("0xpair", "0xwhale", value_tokens=10_000)]
    whales = find_whales(tok, transfers)
    assert len(whales) == 1
    assert whales[0].wallet == "0xwhale"
    assert whales[0].total_bought_usd == pytest.approx(10_000.0)
    assert whales[0].tx_count == 1


def test_only_buys_counted():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [
        _transfer("0xpair", "0xwhale", value_tokens=10_000),   # buy
        _transfer("0xwhale", "0xpair", value_tokens=5_000),    # sell — ignored
    ]
    whales = find_whales(tok, transfers)
    assert len(whales) == 1
    assert whales[0].total_bought_usd == pytest.approx(10_000.0)


def test_below_min_buy_filtered():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [_transfer("0xpair", "0xsmall", value_tokens=100)]  # $100 < $5K
    whales = find_whales(tok, transfers)
    assert whales == []


def test_multiple_buys_same_wallet_aggregated():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [
        _transfer("0xpair", "0xwhale", value_tokens=3_000, ago_seconds=300),
        _transfer("0xpair", "0xwhale", value_tokens=3_000, ago_seconds=100),
    ]
    whales = find_whales(tok, transfers)
    assert len(whales) == 1
    assert whales[0].total_bought_usd == pytest.approx(6_000.0)
    assert whales[0].tx_count == 2


def test_ranked_by_total_bought():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [
        _transfer("0xpair", "0xbig", value_tokens=20_000),
        _transfer("0xpair", "0xsmall", value_tokens=6_000),
    ]
    whales = find_whales(tok, transfers)
    assert whales[0].wallet == "0xbig"
    assert whales[1].wallet == "0xsmall"


def test_top_n_respected():
    from dex_analyser.whale import find_whales
    tok = _token(price_usd=1.0, pair_address="0xpair")
    transfers = [_transfer("0xpair", f"0xwhale{i}", value_tokens=10_000) for i in range(20)]
    whales = find_whales(tok, transfers, top_n=10)
    assert len(whales) == 10


def test_fetch_transfers_no_api_key():
    from dex_analyser.bscscan import fetch_token_transfers
    with patch.dict("os.environ", {}, clear=True):
        result = fetch_token_transfers("0xtoken")
    assert result == []


def test_fetch_transfers_parses_response():
    from dex_analyser.bscscan import fetch_token_transfers
    from unittest.mock import MagicMock
    now = int(time.time())
    payload = {"status": "1", "result": [
        {"from": "0xpair", "to": "0xbuyer", "value": "1000000000000000000",
         "tokenDecimal": "18", "timeStamp": str(now - 60)},
    ]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    with patch("dex_analyser.bscscan.requests.get", return_value=mock_resp), \
         patch.dict("os.environ", {"BSCSCAN_API_KEY": "testkey"}):
        transfers = fetch_token_transfers("0xtoken")
    assert len(transfers) == 1
    assert transfers[0].value_tokens == pytest.approx(1.0)
    assert transfers[0].from_addr == "0xpair"


def test_fetch_transfers_stops_at_cutoff():
    from dex_analyser.bscscan import fetch_token_transfers
    from unittest.mock import MagicMock
    now = int(time.time())
    payload = {"status": "1", "result": [
        {"from": "0xa", "to": "0xb", "value": "1000", "tokenDecimal": "0",
         "timeStamp": str(now - 100)},        # recent — included
        {"from": "0xa", "to": "0xb", "value": "1000", "tokenDecimal": "0",
         "timeStamp": str(now - 999_999)},    # too old — stops here
    ]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    with patch("dex_analyser.bscscan.requests.get", return_value=mock_resp), \
         patch.dict("os.environ", {"BSCSCAN_API_KEY": "testkey"}):
        transfers = fetch_token_transfers("0xtoken", hours=6)
    assert len(transfers) == 1
