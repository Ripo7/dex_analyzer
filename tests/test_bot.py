"""Tests for bot embed builders — no live Discord connection needed."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from dex_analyser.models import RankedToken, Token


def _token(symbol="PEPE", price=0.001, volume=1_000_000, price_change=10.0, liquidity=500_000):
    return Token(
        symbol=symbol, name=symbol, address="0xabc", pair_address="0xpair", chain="solana",
        price_usd=price, volume_24h=volume, price_change_24h=price_change,
        liquidity_usd=liquidity, market_cap=5_000_000,
        pair_created_at=datetime.now(tz=timezone.utc) - timedelta(days=10),
    )


def _ranked(symbol="PEPE", score=0.8, status="TRENDING", volume_spike=False):
    return RankedToken(token=_token(symbol), score=score, status=status, volume_spike=volume_spike)


def test_fmt_usd_millions():
    from dex_analyser.bot import _fmt_usd
    assert _fmt_usd(2_500_000) == "$2.50M"


def test_fmt_usd_thousands():
    from dex_analyser.bot import _fmt_usd
    assert _fmt_usd(75_000) == "$75.0K"


def test_fmt_usd_small():
    from dex_analyser.bot import _fmt_usd
    assert _fmt_usd(500) == "$500"


def test_score_color_top_tier():
    from dex_analyser.bot import _score_color
    ranked = [_ranked(score=1.0), _ranked(score=0.5), _ranked(score=0.2)]
    assert _score_color(1.0, ranked) == 0x2ECC71


def test_score_color_mid_tier():
    from dex_analyser.bot import _score_color
    ranked = [_ranked(score=1.0), _ranked(score=0.5), _ranked(score=0.2)]
    assert _score_color(0.5, ranked) == 0xF1C40F


def test_score_color_low_tier():
    from dex_analyser.bot import _score_color
    ranked = [_ranked(score=1.0), _ranked(score=0.5), _ranked(score=0.2)]
    assert _score_color(0.2, ranked) == 0x3498DB


def test_build_summary_embed_contains_symbol():
    import discord
    from dex_analyser.bot import _build_summary_embed
    ranked = [_ranked("PIPPIN", score=0.9, status="NEW")]
    embed = _build_summary_embed(ranked)
    assert isinstance(embed, discord.Embed)
    assert "PIPPIN" in embed.description
    assert "🆕" in embed.description
    assert "0.900" in embed.description


def test_build_summary_embed_volume_spike_marker():
    import discord
    from dex_analyser.bot import _build_summary_embed
    ranked = [_ranked("BONK", score=0.7, volume_spike=True)]
    embed = _build_summary_embed(ranked)
    assert "⚡" in embed.description


def test_build_summary_embed_title_shows_count():
    import discord
    from dex_analyser.bot import _build_summary_embed
    ranked = [_ranked("A"), _ranked("B"), _ranked("C")]
    embed = _build_summary_embed(ranked)
    assert "3" in embed.title


def test_build_positions_embed_shows_new_entries():
    import discord
    from dex_analyser.bot import _build_positions_embed
    positions = {
        "PEPE": {
            "status": "open", "chain": "ethereum",
            "entry_price": 0.001, "entry_time": "2024-01-01T00:00:00+00:00",
            "size_usd": 100, "pair_address": "0xpair",
        }
    }
    with patch("dex_analyser.bot.pos_store.load", return_value=positions), \
         patch("dex_analyser.bot.pos_store.current_prices", return_value={"PEPE": 0.0015}):
        embed = _build_positions_embed(new_entries=["PEPE"])
    assert "Opened" in embed.title
    assert "PEPE" in embed.title


def test_build_positions_embed_no_positions():
    from dex_analyser.bot import _build_positions_embed
    with patch("dex_analyser.bot.pos_store.load", return_value={}):
        assert _build_positions_embed() is None


def test_build_positions_embed_with_open_position():
    import discord
    from dex_analyser.bot import _build_positions_embed
    positions = {
        "PEPE": {
            "status": "open",
            "chain": "ethereum",
            "entry_price": 0.001,
            "entry_time": "2024-01-01T00:00:00+00:00",
            "size_usd": 100,
            "pair_address": "0xpair",
        }
    }
    with patch("dex_analyser.bot.pos_store.load", return_value=positions), \
         patch("dex_analyser.bot.pos_store.current_prices", return_value={"PEPE": 0.0015}):
        embed = _build_positions_embed()
    assert isinstance(embed, discord.Embed)
    assert "PEPE" in embed.description
