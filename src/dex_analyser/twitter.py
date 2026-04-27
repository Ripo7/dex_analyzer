import re
from collections import defaultdict

from ntscraper import Nitter

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{2,10})\b")
_SCRAPER: Nitter | None = None

# Symbols too generic to be token tickers
_BLOCKLIST = {"USD", "EUR", "GBP", "JPY", "THE", "FOR", "ARE", "YOU", "NOT", "ALL"}


def _scraper() -> Nitter:
    global _SCRAPER
    if _SCRAPER is None:
        _SCRAPER = Nitter(log_level=0, skip_instance_check=False)
    return _SCRAPER


def get_mention_counts(query: str, limit: int = 100) -> dict[str, int]:
    """
    Scrape tweets matching *query* and return a mapping of
    cashtag symbol → mention count.
    """
    counts: dict[str, int] = defaultdict(int)
    try:
        results = _scraper().get_tweets(query, mode="term", number=limit)
    except Exception:
        return {}

    tweets = results.get("tweets", [])
    for tweet in tweets:
        text = tweet.get("text", "") or ""
        for match in _CASHTAG_RE.finditer(text):
            symbol = match.group(1).upper()
            if symbol not in _BLOCKLIST:
                counts[symbol] += 1

    return dict(counts)
