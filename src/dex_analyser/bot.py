import asyncio
import os
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from .analyser import analyse, discover_and_rank
from .dexscreener import discover_tokens, discover_bsc_tokens
from .models import RankedToken, TokenSafety, WhaleEntry
from .goplus import fetch_safety
from .thegraph import fetch_pair_swaps, discover_trending_bsc_pools, fetch_wallet_analysis
from .whale import find_whales_from_swaps
from . import positions as pos_store

DISCORD_CHANNEL_ID: int = 0  # set by run()
SCAN_INTERVAL_HOURS = float(os.environ.get("SCAN_INTERVAL_HOURS", "1"))
POSITION_SIZE = float(os.environ.get("POSITION_SIZE", "100"))
TOP_N = int(os.environ.get("TOP_N", "10"))

_STATUS_EMOJI = {"NEW": "🆕", "RESURGENT": "🔄", "TRENDING": "📈"}
_SCORE_COLORS = [
    (0.66, 0x2ECC71),  # green — top tier
    (0.33, 0xF1C40F),  # yellow — mid tier
    (0.0,  0x3498DB),  # blue — lower tier
]


def _fmt_age(tok) -> str:
    mins = tok.age_minutes
    if mins is None:
        return "?"
    if mins < 60:
        return f"{mins}m"
    if mins < 60 * 24:
        return f"{mins // 60}h"
    return f"{mins // (60 * 24)}d"


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


def _fmt_safety(safety: TokenSafety | None) -> str | None:
    if safety is None:
        return None
    parts: list[str] = []

    if safety.lp_locked_pct >= 80:
        parts.append(f"🔒 LP {safety.lp_locked_pct:.0f}%")
    elif safety.lp_locked_pct > 0:
        parts.append(f"⚠️ LP {safety.lp_locked_pct:.0f}%")
    else:
        parts.append("🔓 LP ?")

    if safety.sell_tax > 10:
        parts.append(f"🚨 Tax {safety.buy_tax:.0f}/{safety.sell_tax:.0f}%")
    elif safety.sell_tax > 0 or safety.buy_tax > 0:
        parts.append(f"⚠️ Tax {safety.buy_tax:.0f}/{safety.sell_tax:.0f}%")
    else:
        parts.append("✅ Tax 0/0%")

    parts.append("⚠️ Mintable" if safety.is_mintable else "✅ No mint")

    if safety.is_blacklist:
        parts.append("⚠️ Freeze")

    return "  ·  ".join(parts)


def _score_color(score: float, ranked: list[RankedToken]) -> int:
    if not ranked:
        return 0x3498DB
    top = ranked[0].score or 1
    rel = score / top
    for threshold, color in _SCORE_COLORS:
        if rel >= threshold:
            return color
    return 0x3498DB


def _build_summary_embed(ranked: list[RankedToken], use_goplus: bool = True) -> discord.Embed:
    lines: list[str] = []
    for r in ranked:
        tok = r.token
        chg = tok.price_change_24h
        chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
        status_emoji = _STATUS_EMOJI.get(r.status, "")
        spike = " ⚡" if r.volume_spike else ""
        url = f"https://dexscreener.com/{tok.chain}/{tok.pair_address}"
        entry = (
            f"**[{tok.symbol}]({url})** · {tok.chain.upper()}  `{_fmt_age(tok)}`  {status_emoji}{spike}\n"
            f"Score `{r.score:.3f}` · {chg_str} · Vol {_fmt_usd(tok.volume_24h)} · Liq {_fmt_usd(tok.liquidity_usd)}"
        )
        safety_line = _fmt_safety(tok.safety)
        if safety_line:
            entry += f"\n{safety_line}"
        lines.append(entry)
    top_color = _score_color(ranked[0].score, ranked) if ranked else 0x3498DB
    now = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")
    safety_label = "🛡️ GoPlus verified" if use_goplus else "⚠️ No safety check"
    embed = discord.Embed(
        title=f"🔍 New Tokens — Last Hour  ({len(ranked)} found)",
        description="\n\n".join(lines),
        color=top_color,
    )
    embed.set_footer(text=f"Scanned at {now}  |  {safety_label}  |  Next in ~{SCAN_INTERVAL_HOURS:.0f}h")
    return embed


def _fmt_wallet(addr: str) -> str:
    return f"`{addr[:6]}…{addr[-4:]}`"


def _fmt_ago(minutes: int) -> str:
    return f"{minutes}m ago" if minutes < 60 else f"{minutes // 60}h ago"


def _whale_pattern(w: WhaleEntry) -> str:
    span = w.first_buy_ago_minutes - w.last_buy_ago_minutes
    if w.tx_count == 1:
        return "⚡ Single large buy"
    if span < 30:
        return "🚀 Aggressive (burst)"
    return "🔄 Accumulating"


def _fmt_portfolio(usd: float) -> str:
    if usd <= 0:
        return ""
    if usd >= 1_000_000:
        return f"💼 Portfolio ~${usd/1_000_000:.1f}M"
    if usd >= 1_000:
        return f"💼 Portfolio ~${usd/1_000:.0f}K"
    return f"💼 Portfolio ~${usd:.0f}"


def _build_whale_embed(pool: dict, whales: list[WhaleEntry], rank: int, total: int, swap_count: int = 0) -> discord.Embed:
    symbol = pool["symbol"]
    addr = pool["pool_address"]
    vol = pool["volume_24h"]
    pool_url = f"https://www.geckoterminal.com/bsc/pools/{addr}"
    lines: list[str] = []
    for i, w in enumerate(whales, 1):
        avg = w.total_bought_usd / w.tx_count
        debank = f"https://debank.com/profile/{w.wallet}"
        bscscan = f"https://bscscan.com/address/{w.wallet}"
        portfolio = _fmt_portfolio(w.portfolio_usd)
        flag_parts = []
        if "also_sold" in w.flags:
            flag_parts.append("⚠️ Also sold")
        if "bot_rapid" in w.flags:
            flag_parts.append("🤖 Rapid-fire")
        if "empty_wallet" in w.flags:
            flag_parts.append("👻 Empty wallet")
        flag_str = "  ·  ".join(flag_parts)

        # Unrealized PnL on this token
        pnl_str = ""
        if w.token_holding_usd > 0 and w.total_bought_usd > 0:
            pnl_pct = (w.token_holding_usd - w.total_bought_usd) / w.total_bought_usd * 100
            pnl_sign = "+" if pnl_pct >= 0 else ""
            pnl_str = f"  ·  PnL `{pnl_sign}{pnl_pct:.1f}%` ({_fmt_usd(w.token_holding_usd)} now)"

        # Top bag (exclude the current token to avoid redundancy)
        symbol = pool["symbol"].upper()
        bag_items = [t for t in w.bsc_bag if t["symbol"] != symbol][:4]
        bag_str = "  ".join(f"{t['symbol']} {_fmt_usd(t['usd_value'])}" for t in bag_items)

        line = (
            f"**#{i}** [`{w.wallet[:6]}…{w.wallet[-4:]}`]({bscscan})  "
            f"{_fmt_usd(w.total_bought_usd)} · {w.tx_count} buy{'s' if w.tx_count > 1 else ''} · avg {_fmt_usd(avg)}{pnl_str}\n"
            f"{_whale_pattern(w)} · entered {_fmt_ago(w.first_buy_ago_minutes)} · last {_fmt_ago(w.last_buy_ago_minutes)}\n"
            f"[DeBank]({debank})"
        )
        if portfolio:
            line += f"  ·  {portfolio}"
        if bag_str:
            line += f"\n🎒 {bag_str}"
        if flag_str:
            line += f"\n{flag_str}"
        lines.append(line)
    description = "\n\n".join(lines) if lines else "_No whale buys found_"
    embed = discord.Embed(
        title=f"🐋 [{symbol}]({pool_url}) · BSC",
        description=description,
        color=0x9B59B6,
    )
    embed.set_footer(text=f"Pool {rank}/{total}  ·  Min $500 buy  ·  Last 6h  ·  Vol {_fmt_usd(vol)}  ·  {swap_count} trades scanned")
    return embed


def _build_positions_embed(new_entries: list[str] | None = None) -> discord.Embed | None:
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
    pnl_sign = "+" if total_pnl >= 0 else "-"
    title = "📊 Paper Positions"
    if new_entries:
        title += f"  ·  📌 Opened: {', '.join(new_entries)}"
    embed = discord.Embed(
        title=title,
        description="\n\n".join(lines),
        color=color,
    )
    embed.set_footer(
        text=f"Total PnL: {pnl_sign}${abs(total_pnl):.2f}  |  {len(open_pos)} open position(s)"
    )
    return embed


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


async def _run_scan(channel: discord.abc.Messageable, use_goplus: bool = True) -> None:
    label = "🔍 Scanning DexScreener…" if not use_goplus else "🔍 Scanning DexScreener + GoPlus…"
    status_msg = await channel.send(label)
    loop = asyncio.get_event_loop()

    try:
        ranked: list[RankedToken] = await loop.run_in_executor(
            None, lambda: discover_and_rank(top_n=TOP_N)
        )
    except Exception as exc:
        await status_msg.edit(content=f"❌ Scan failed: {exc}")
        print(f"[scan error] {exc}", flush=True)
        return

    # Keep only tokens launched in the last hour
    fresh = [r for r in ranked if r.token.age_minutes is not None and r.token.age_minutes <= 60]

    if not fresh:
        await status_msg.edit(content="🔎 No tokens under 1h found.")
        return

    if use_goplus:
        # Fetch GoPlus safety data for all fresh tokens in parallel
        safety_results = await asyncio.gather(
            *[loop.run_in_executor(None, lambda r=r: fetch_safety(r.token.chain, r.token.address))
              for r in fresh]
        )
        for r, safety in zip(fresh, safety_results):
            r.token.safety = safety

        # Drop confirmed honeypots
        fresh = [r for r in fresh if not (r.token.safety and r.token.safety.is_honeypot)]
        if not fresh:
            await status_msg.edit(content="🔎 All tokens under 1h flagged as honeypots.")
            return

    # Edit the scanning indicator into the result — one message total
    embed = _build_summary_embed(fresh, use_goplus=use_goplus)
    await status_msg.edit(content="", embed=embed)

    # Auto-open positions for top 2 fresh tokens
    positions = pos_store.load()
    new_entries: list[str] = []
    for r in fresh[:2]:
        if r.symbol not in positions or positions[r.symbol].get("status") != "open":
            positions[r.symbol] = pos_store.enter(r.token, POSITION_SIZE)
            new_entries.append(r.symbol)
    if new_entries:
        pos_store.save(positions)

    # Positions PnL — second and last message (new openings folded into the title)
    pos_embed = await loop.run_in_executor(None, lambda: _build_positions_embed(new_entries or None))
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
    bsc_key = os.environ.get("BSCSCAN_API_KEY", "")
    print(f"BSCSCAN_API_KEY: {'SET (' + str(len(bsc_key)) + ' chars)' if bsc_key else 'NOT SET'}", flush=True)
    print(f"All env var names: {sorted(os.environ.keys())}", flush=True)
    if not _auto_scan.is_running():
        _auto_scan.start()


@bot.command(name="scan")
async def scan_cmd(ctx: commands.Context) -> None:
    """Scan with GoPlus safety check — honeypots filtered, safety line shown."""
    await _run_scan(ctx.channel, use_goplus=True)


@bot.command(name="scanraw")
async def scan_raw_cmd(ctx: commands.Context) -> None:
    """Scan without GoPlus — faster, shows all tokens including unverified ones."""
    await _run_scan(ctx.channel, use_goplus=False)


@bot.command(name="whale")
async def whale_cmd(ctx: commands.Context) -> None:
    """Find whale buyers on top 5 trending BSC pools via GeckoTerminal (min $500, last 6h)."""
    status_msg = await ctx.channel.send("🐋 Fetching trending BSC pools…")
    loop = asyncio.get_event_loop()

    pools = await loop.run_in_executor(None, discover_trending_bsc_pools)
    if not pools:
        await status_msg.edit(content="🐋 Could not fetch trending BSC pools.")
        return

    await status_msg.edit(content=f"🐋 Scanning {len(pools)} pools for whale activity…")

    swap_results = await asyncio.gather(
        *[loop.run_in_executor(None, lambda p=p: fetch_pair_swaps(p["pool_address"]))
          for p in pools]
    )

    await status_msg.delete()
    for i, (pool, swaps) in enumerate(zip(pools, swap_results), 1):
        whales = find_whales_from_swaps(swaps)
        # Enrich all whales with DeBank wallet analysis in parallel
        if whales:
            analyses = await asyncio.gather(
                *[loop.run_in_executor(None, lambda w=w: fetch_wallet_analysis(w.wallet))
                  for w in whales]
            )
            token_symbol = pool["symbol"].upper()
            for w, analysis in zip(whales, analyses):
                w.portfolio_usd = analysis["total_usd"]
                if w.portfolio_usd > 0 and w.portfolio_usd < 1_000:
                    w.flags.append("empty_wallet")
                w.bsc_bag = [
                    {"symbol": t.get("symbol", "?").upper(), "usd_value": float(t.get("usd_value") or 0)}
                    for t in analysis["tokens"]
                    if float(t.get("usd_value") or 0) > 10
                ]
                # Find their current holding of the pool's token for PnL
                for t in analysis["tokens"]:
                    if t.get("symbol", "").upper() == token_symbol:
                        w.token_holding_usd = float(t.get("usd_value") or 0)
                        break
        # Keep only clean wallets — no suspicious flags
        whales = [w for w in whales if not w.flags]
        embed = _build_whale_embed(pool, whales, rank=i, total=len(pools), swap_count=len(swaps))
        await ctx.channel.send(embed=embed)


def run() -> None:
    from dotenv import load_dotenv
    load_dotenv()
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
