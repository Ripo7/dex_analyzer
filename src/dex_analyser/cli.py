import argparse
import sys

from rich.console import Console
from rich.table import Table

from .analyser import analyse
from .twitter import get_mention_counts

console = Console()

_STATUS_STYLE = {
    "NEW": "bold green",
    "RESURGENT": "bold yellow",
    "TRENDING": "cyan",
}


def _parse_weights(raw: str) -> tuple[float, float, float]:
    mapping: dict[str, float] = {}
    for part in raw.split(","):
        key, _, val = part.partition("=")
        mapping[key.strip()] = float(val.strip())
    tweet = mapping.get("tweet", 0.4)
    vol = mapping.get("vol", 0.4)
    chg = mapping.get("chg", 0.2)
    total = tweet + vol + chg
    return tweet / total, vol / total, chg / total


def _build_table(ranked: list) -> Table:
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Symbol", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Tweets", justify="right")
    table.add_column("Price USD", justify="right")
    table.add_column("24h Chg", justify="right")
    table.add_column("Vol 24h", justify="right")
    table.add_column("Liquidity", justify="right")
    table.add_column("Score", justify="right")

    for i, r in enumerate(ranked, 1):
        tok = r.token
        chg = tok.price_change_24h
        chg_str = f"[green]+{chg:.1f}%[/green]" if chg >= 0 else f"[red]{chg:.1f}%[/red]"
        status_style = _STATUS_STYLE.get(r.status, "white")

        table.add_row(
            str(i),
            tok.symbol,
            f"[{status_style}]{r.status}[/{status_style}]",
            str(r.tweet_count),
            f"${tok.price_usd:.6g}",
            chg_str,
            f"${tok.volume_24h:,.0f}",
            f"${tok.liquidity_usd:,.0f}",
            f"{r.score:.3f}",
        )
    return table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="dex-analyser",
        description="Rank trending crypto tokens by Twitter mentions + DexScreener metrics.",
    )
    parser.add_argument("-q", "--query", default="crypto memecoin altcoin", help="Twitter search query")
    parser.add_argument("-n", "--top", type=int, default=10, help="Number of tokens to show")
    parser.add_argument(
        "--tweet-limit",
        type=int,
        default=200,
        help="Max tweets to scrape (default 200)",
    )
    parser.add_argument(
        "--weights",
        default="tweet=0.4,vol=0.4,chg=0.2",
        help="Scoring weights, e.g. tweet=0.4,vol=0.4,chg=0.2",
    )
    args = parser.parse_args(argv)

    try:
        w_tweet, w_vol, w_chg = _parse_weights(args.weights)
    except (ValueError, ZeroDivisionError):
        console.print("[red]Invalid --weights format. Use e.g. tweet=0.4,vol=0.4,chg=0.2[/red]")
        sys.exit(1)

    console.print(f"\n[bold]Scraping tweets for:[/bold] {args.query!r}")
    mention_counts = get_mention_counts(args.query, limit=args.tweet_limit)

    if not mention_counts:
        console.print("[yellow]No cashtags found in tweets. Try a different query.[/yellow]")
        sys.exit(0)

    console.print(f"Found [bold]{len(mention_counts)}[/bold] unique ticker(s). Looking up DexScreener...\n")

    ranked = analyse(
        mention_counts,
        top_n=args.top,
        weight_tweet=w_tweet,
        weight_vol=w_vol,
        weight_chg=w_chg,
    )

    if not ranked:
        console.print("[yellow]No tokens matched on DexScreener.[/yellow]")
        sys.exit(0)

    console.print(_build_table(ranked))
    console.print(
        "\n[dim]Status: [green]NEW[/green] = pair < 7 days old  "
        "[yellow]RESURGENT[/yellow] = 2× spike vs last run  "
        "[cyan]TRENDING[/cyan] = active[/dim]"
    )
