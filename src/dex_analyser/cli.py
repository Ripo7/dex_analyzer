import argparse
import sys

from rich.console import Console
from rich.rule import Rule
from rich.table import Table

from .analyser import discover_and_rank
from . import positions as pos_store

console = Console()

_STATUS_STYLE = {"NEW": "bold green", "RESURGENT": "bold yellow", "TRENDING": "cyan"}


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


def _build_table(ranked: list) -> Table:
    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Symbol", style="bold")
    table.add_column("Chain", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Price USD", justify="right")
    table.add_column("24h Chg", justify="right")
    table.add_column("Vol 24h", justify="right")
    table.add_column("Liquidity", justify="right")
    table.add_column("Mkt Cap", justify="right")
    table.add_column("Age", justify="right")
    table.add_column("Score", justify="right")

    for i, r in enumerate(ranked, 1):
        tok = r.token
        chg = tok.price_change_24h
        chg_str = f"[green]+{chg:.1f}%[/green]" if chg >= 0 else f"[red]{chg:.1f}%[/red]"
        age = f"{tok.age_days}d" if tok.age_days is not None else "?"
        mkt_cap = _fmt_usd(tok.market_cap) if tok.market_cap else "—"
        s_style = _STATUS_STYLE.get(r.status, "white")
        spike = " ⚡" if r.volume_spike else ""

        table.add_row(
            str(i),
            tok.symbol,
            tok.chain.upper(),
            f"[{s_style}]{r.status}[/{s_style}]",
            f"${tok.price_usd:.4g}",
            chg_str,
            _fmt_usd(tok.volume_24h) + spike,
            _fmt_usd(tok.liquidity_usd),
            mkt_cap,
            age,
            f"{r.score:.3f}",
        )
    return table


def _update_positions(ranked: list, size_usd: float) -> None:
    """Open paper positions for the top 2 ranked tokens if not already open."""
    positions = pos_store.load()
    new_entries: list[str] = []

    for r in ranked[:2]:
        if r.symbol in positions and positions[r.symbol]["status"] == "open":
            continue
        positions[r.symbol] = pos_store.enter(r.token, size_usd)
        new_entries.append(r.symbol)

    if new_entries:
        pos_store.save(positions)
        console.print(
            f"\n[bold green]Paper positions opened:[/bold green] {', '.join(new_entries)} "
            f"([dim]${size_usd:.0f} each[/dim])"
        )


def _print_positions() -> None:
    positions = pos_store.load()
    open_pos = {s: p for s, p in positions.items() if p.get("status") == "open"}
    if not open_pos:
        return

    console.print()
    console.print(Rule("[bold]Paper Positions[/bold]"))
    console.print("[dim]Fetching current prices…[/dim]")
    prices = pos_store.current_prices(open_pos)

    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    table.add_column("Symbol", style="bold")
    table.add_column("Chain", style="dim")
    table.add_column("Entry Price", justify="right")
    table.add_column("Current Price", justify="right")
    table.add_column("Entered", justify="right", style="dim")
    table.add_column("Days", justify="right", style="dim")
    table.add_column("Size", justify="right", style="dim")
    table.add_column("PnL %", justify="right")
    table.add_column("PnL USD", justify="right")

    total_pnl = 0.0
    for sym, p in open_pos.items():
        current = prices.get(sym, 0.0)
        pnl_pct, pnl_usd = pos_store.pnl(p["entry_price"], current, p["size_usd"])
        total_pnl += pnl_usd
        days = pos_store.entry_age_days(p["entry_time"])
        entry_date = p["entry_time"][:10]

        pct_str = f"[green]+{pnl_pct:.1f}%[/green]" if pnl_pct >= 0 else f"[red]{pnl_pct:.1f}%[/red]"
        usd_str = f"[green]+${pnl_usd:.2f}[/green]" if pnl_usd >= 0 else f"[red]-${abs(pnl_usd):.2f}[/red]"

        table.add_row(
            sym,
            p.get("chain", "").upper(),
            f"${p['entry_price']:.4g}",
            f"${current:.4g}" if current else "—",
            entry_date,
            str(days),
            f"${p['size_usd']:.0f}",
            pct_str,
            usd_str,
        )

    console.print(table)
    total_style = "bold green" if total_pnl >= 0 else "bold red"
    sign = "+" if total_pnl >= 0 else "-"
    console.print(
        f"\n[{total_style}]Total PnL: {sign}${abs(total_pnl):.2f}[/{total_style}]"
        f"  [dim]across {len(open_pos)} open position(s)[/dim]"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="dex-analyser",
        description="Rank trending on-chain tokens via DexScreener discovery + metrics.",
    )
    parser.add_argument("-n", "--top", type=int, default=10,
                        help="Number of tokens to show (default: 10)")
    parser.add_argument("--min-liquidity", type=float, default=10_000,
                        help="Minimum liquidity in USD (default: 10000)")
    parser.add_argument("--min-volume", type=float, default=50_000,
                        help="Minimum 24h volume in USD (default: 50000)")
    parser.add_argument("--position-size", type=float, default=pos_store.DEFAULT_SIZE_USD,
                        help=f"Paper position size in USD (default: {pos_store.DEFAULT_SIZE_USD:.0f})")
    parser.add_argument("--close", metavar="SYMBOL",
                        help="Close an open paper position and exit")
    args = parser.parse_args(argv)

    if args.close:
        sym = args.close.upper()
        if pos_store.close(sym):
            console.print(f"[green]Closed position: {sym}[/green]")
        else:
            console.print(f"[yellow]No open position found for {sym}[/yellow]")
        sys.exit(0)

    console.print("\n[bold]Fetching tokens from DexScreener…[/bold]")

    ranked = discover_and_rank(
        top_n=args.top,
        min_liquidity=args.min_liquidity,
        min_volume=args.min_volume,
    )

    if not ranked:
        console.print("[yellow]No tokens passed filters. Try lowering --min-liquidity or --min-volume.[/yellow]")
        sys.exit(0)

    console.print(_build_table(ranked))
    console.print(
        "\n[dim]Status: [green]NEW[/green]=pair<7d  [yellow]RESURGENT[/yellow]=2× vol spike  [cyan]TRENDING[/cyan]=active"
        "  ⚡=volume spike vs last scan[/dim]"
    )

    _update_positions(ranked, args.position_size)
    _print_positions()
