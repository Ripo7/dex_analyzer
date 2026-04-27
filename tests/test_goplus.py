from unittest.mock import MagicMock, patch

import pytest
import requests as req


def _mock_resp(data: dict, raise_for: Exception | None = None):
    m = MagicMock()
    m.json.return_value = data
    if raise_for:
        m.raise_for_status.side_effect = raise_for
    return m


def test_evm_honeypot_detected():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 1, "result": {"0xabc": {
        "is_honeypot": "1", "buy_tax": "0", "sell_tax": "0",
        "is_mintable": "0", "owner_address": "",
        "lp_total_supply": "0", "lp_holders": [], "is_blacklisted": "0",
    }}}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("ethereum", "0xabc")
    assert safety is not None
    assert safety.is_honeypot is True


def test_evm_clean_token_lp_locked():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 1, "result": {"0xdef": {
        "is_honeypot": "0", "buy_tax": "0", "sell_tax": "0",
        "is_mintable": "0", "owner_address": "",
        "lp_total_supply": "1000",
        "lp_holders": [{"balance": "950", "is_locked": 1}],
        "is_blacklisted": "0",
    }}}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("bsc", "0xDEF")
    assert safety is not None
    assert safety.is_honeypot is False
    assert safety.lp_locked_pct == pytest.approx(95.0)
    assert safety.owner_renounced is True


def test_evm_high_sell_tax():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 1, "result": {"0x111": {
        "is_honeypot": "0", "buy_tax": "5", "sell_tax": "20",
        "is_mintable": "0", "owner_address": "0xdev",
        "lp_total_supply": "0", "lp_holders": [], "is_blacklisted": "0",
    }}}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("ethereum", "0x111")
    assert safety is not None
    assert safety.sell_tax == pytest.approx(20.0)
    assert safety.owner_renounced is False


def test_solana_mint_authority_present():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 1, "result": {"SOLaddr": {
        "mint_authority": "DevWalletXYZ",
        "freeze_authority": None,
        "transfer_fee_rate": None,
    }}}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("solana", "SOLaddr")
    assert safety is not None
    assert safety.is_mintable is True
    assert safety.is_blacklist is False


def test_solana_clean():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 1, "result": {"SOLclean": {
        "mint_authority": None,
        "freeze_authority": None,
        "transfer_fee_rate": None,
    }}}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("solana", "SOLclean")
    assert safety is not None
    assert safety.is_mintable is False
    assert safety.is_blacklist is False


def test_unknown_chain_returns_none():
    from dex_analyser.goplus import fetch_safety
    safety = fetch_safety("unknownchain", "0xabc")
    assert safety is None


def test_network_error_returns_none():
    from dex_analyser.goplus import fetch_safety
    with patch("dex_analyser.goplus.requests.get", side_effect=req.RequestException("timeout")):
        safety = fetch_safety("ethereum", "0xabc")
    assert safety is None


def test_goplus_bad_code_returns_none():
    from dex_analyser.goplus import fetch_safety
    payload = {"code": 0, "message": "rate limit"}
    with patch("dex_analyser.goplus.requests.get", return_value=_mock_resp(payload)):
        safety = fetch_safety("ethereum", "0xabc")
    assert safety is None
