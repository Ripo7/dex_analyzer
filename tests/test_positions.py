import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from dex_analyser.models import Token
from dex_analyser.positions import enter, entry_age_days, pnl


def _token(symbol="PEPE", price=0.001):
    return Token(
        symbol=symbol, name=symbol, address="0xabc", pair_address="0xpair", chain="ethereum",
        price_usd=price, volume_24h=500_000, price_change_24h=5.0,
        liquidity_usd=200_000, market_cap=1_000_000,
    )


def test_enter_creates_position():
    p = enter(_token("PEPE", price=0.001), size_usd=100)
    assert p["symbol"] == "PEPE"
    assert p["entry_price"] == 0.001
    assert p["size_usd"] == 100
    assert p["status"] == "open"


def test_pnl_profit():
    pct, usd = pnl(entry_price=0.001, current_price=0.0015, size_usd=100)
    assert pct == pytest.approx(50.0)
    assert usd == pytest.approx(50.0)


def test_pnl_loss():
    pct, usd = pnl(entry_price=0.001, current_price=0.0005, size_usd=100)
    assert pct == pytest.approx(-50.0)
    assert usd == pytest.approx(-50.0)


def test_pnl_zero_entry_safe():
    pct, usd = pnl(entry_price=0.0, current_price=0.001, size_usd=100)
    assert pct == 0.0 and usd == 0.0


def test_entry_age_days():
    three_days_ago = (datetime.now(tz=timezone.utc) - timedelta(days=3)).isoformat()
    assert entry_age_days(three_days_ago) == 3


def test_close_position(tmp_path):
    pos_file = tmp_path / "positions.json"
    pos_file.write_text(json.dumps({
        "PEPE": {"status": "open", "entry_price": 0.001, "entry_time": "2024-01-01T00:00:00+00:00"}
    }))
    with patch("dex_analyser.positions._POSITIONS_PATH", pos_file):
        from dex_analyser.positions import close, load
        result = close("PEPE")
        assert result is True
        assert load()["PEPE"]["status"] == "closed"


def test_close_nonexistent_returns_false(tmp_path):
    pos_file = tmp_path / "positions.json"
    pos_file.write_text(json.dumps({}))
    with patch("dex_analyser.positions._POSITIONS_PATH", pos_file):
        from dex_analyser.positions import close
        assert close("UNKNOWN") is False
