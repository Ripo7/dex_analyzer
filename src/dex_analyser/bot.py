import asyncio
import os

import discord
from discord.ext import commands, tasks

from .analyser import discover_and_rank
from .models import RankedToken
from . import positions as pos_store

DISCORD_CHANNEL_ID: int = 0  # set by run()
SCAN_INTERVAL_HOURS = float(os.environ.get("SCAN_INTERVAL_HOURS", "4"))
POSITION_SIZE = float(os.environ.get("POSITION_SIZE", "100"))
TOP_N = int(os.environ.get("TOP_N", "10"))

_STATUS_EMOJI = {"NEW": "🆕", "RESURGENT": "🔄", "TRENDING": "📈"}
_SCORE_COLORS = [
    (0.66, 0x2ECC71),  # green — top tier
    (0.33, 0xF1C40F),  # yellow — mid tier
    (0.0,  0x3498DB),  # blue — lower tier
]


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


def _score_color(score: float, ranked: list[RankedToken]) -> int:
    if not ranked:
        return 0x3498DB
    top = ranked[0].score or 1
    rel = score / top
    for threshold, color in _SCORE_COLORS:
        if rel >= threshold:
            return color
    return 0x3498DB


def _build_summary_embed(ranked: list[RankedToken]) -> discord.Embed:
    lines: list[str] = []
    for i, r in enumerate(ranked, 1):
        tok = r.token
        chg = tok.price_change_24h
        chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
        status_emoji = _STATUS_EMOJI.get(r.status, "")
        spike = " ⚡" if r.volume_spike else ""
        lines.append(
            f"**#{i}** {tok.symbol} · {tok.chain.upper()}  {status_emoji} {r.status}{spike}\n"
            f"`{r.score:.3f}`  {chg_str}  {_fmt_usd(tok.volume_24h)}"
        )
    top_color = _score_color(ranked[0].score, ranked) if ranked else 0x3498DB
    embed = discord.Embed(
        title="📊 Token Dashboard",
        description="\n\n".join(lines),
        color=top_color,
    )
    embed.set_footer(text=f"{len(ranked)} tokens  |  Next scan in ~{SCAN_INTERVAL_HOURS:.0f}h")
    return embed


def _build_token_embed(r: RankedToken, rank: int, total: int, color: int) -> discord.Embed:
    tok = r.token
    status_emoji = _STATUS_EMOJI.get(r.status, "")
    chg = tok.price_change_24h
    chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    age = f"{tok.age_days}d" if tok.age_days is not None else "?"
    status_line = r.status + (" ⚡" if r.volume_spike else "")

    embed = discord.Embed(
        title=f"{status_emoji} #{rank} {tok.symbol} — {tok.chain.upper()}",
        description=f"**{status_line}**  ·  Age {age}",
        color=color,
    )
    embed.add_field(name="Score", value=f"{r.score:.3f}", inline=True)
    embed.add_field(name="Price", value=f"${tok.price_usd:.4g}", inline=True)
    embed.add_field(name="24h Change", value=chg_str, inline=True)
    embed.add_field(name="Vol 24h", value=_fmt_usd(tok.volume_24h), inline=True)
    embed.add_field(name="Mkt Cap", value=_fmt_usd(tok.market_cap) if tok.market_cap else "—", inline=True)
    embed.add_field(name="Liquidity", value=_fmt_usd(tok.liquidity_usd), inline=True)
    embed.set_footer(text=f"Token {rank}/{total}  |  Next scan in ~{SCAN_INTERVAL_HOURS:.0f}h")
    return embed


def _build_positions_embed() -> discord.Embed | None:
    positions = pos_store.load()
    open_pos = {s: p for s, p in positions.items() if p.get("status") == "open"}
    if not open_pos:
        return None

    prices = pos_store.current_prices(open_pos)
    total_pnl = 0.0
    lines: list[str] = []

    for sym, p in open_pos.items():
        current = prices.get(sym, 0.0)
        pct, usd = pos_store.pnl(p["entry_price"], current, p["size_usd"])
        total_pnl += usd
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"**{sym}** · {p.get('chain','').upper()}\n"
            f"${p['entry_price']:.4g} → ${current:.4g}  {sign}{pct:.1f}% ({sign}${usd:.2f})"
        )

    color = 0x2ECC71 if total_pnl >= 0 else 0xE74C3C
    sign = "+" if total_pnl >= 0 else "-"
    embed = discord.Embed(
        title="📊 Paper Positions",
        description="\n".join(lines),
        color=color,
    )
    embed.set_footer(
        text=f"Total PnL: {sign}${abs(total_pnl):.2f}  |  {len(open_pos)} open position(s)"
    )
    return embed


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


async def _run_scan(channel: discord.abc.Messageable) -> None:
    status_msg = await channel.send("🔍 Scanning DexScreener…")
    loop = asyncio.get_event_loop()

    try:
        ranked: list[RankedToken] = await loop.run_in_executor(
            None, lambda: discover_and_rank(top_n=TOP_N)
        )
    except Exception as exc:
        await status_msg.edit(content=f"❌ Scan failed: {exc}")
        print(f"[scan error] {exc}", flush=True)
        return

    if not ranked:
        await status_msg.edit(content="🔎 Scan complete — no tokens passed filters.")
        return

    await status_msg.edit(content=f"✅ Found **{len(ranked)}** token(s) — full dashboard below")

    summary_embed = _build_summary_embed(ranked)
    await channel.send(embed=summary_embed)

    # Detailed embeds for top 3
    for i, r in enumerate(ranked[:3]):
        color = _score_color(r.score, ranked)
        embed = _build_token_embed(r, rank=i + 1, total=len(ranked), color=color)
        await channel.send(embed=embed)

    # Auto-open positions for top 2 (if not already open)
    positions = pos_store.load()
    new_entries: list[str] = []
    for r in ranked[:2]:
        if r.symbol not in positions or positions[r.symbol].get("status") != "open":
            positions[r.symbol] = pos_store.enter(r.token, POSITION_SIZE)
            new_entries.append(r.symbol)
    if new_entries:
        pos_store.save(positions)
        await channel.send(
            f"📌 Paper positions opened: **{', '.join(new_entries)}** (${POSITION_SIZE:.0f} each)"
        )

    # Positions PnL summary
    pos_embed = await loop.run_in_executor(None, _build_positions_embed)
    if pos_embed:
        await channel.send(embed=pos_embed)


@tasks.loop(hours=SCAN_INTERVAL_HOURS)
async def _auto_scan() -> None:
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if channel:
        await _run_scan(channel)


@_auto_scan.before_loop
async def _wait_ready() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}  |  auto-scan every {SCAN_INTERVAL_HOURS:.0f}h", flush=True)
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    print(f"Target channel: {channel} (ID={DISCORD_CHANNEL_ID})", flush=True)
    if not _auto_scan.is_running():
        _auto_scan.start()


@bot.command(name="scan")
async def scan_cmd(ctx: commands.Context) -> None:
    await _run_scan(ctx.channel)


def run() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("DISCORD_CHANNEL_ID environment variable is not set")
    global DISCORD_CHANNEL_ID  # noqa: PLW0603
    # Accept full Discord link or raw ID
    DISCORD_CHANNEL_ID = int(channel_id.rstrip("/").split("/")[-1])
    bot.run(token)
