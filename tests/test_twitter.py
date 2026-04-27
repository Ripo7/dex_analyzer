from unittest.mock import MagicMock, patch

from dex_analyser.twitter import get_mention_counts


def _mock_scraper(tweets):
    scraper = MagicMock()
    scraper.get_tweets.return_value = {"tweets": tweets}
    return scraper


@patch("dex_analyser.twitter._scraper")
def test_counts_cashtags(mock_factory):
    mock_factory.return_value = _mock_scraper([
        {"text": "Loving $PEPE and $WIF today!"},
        {"text": "$PEPE is mooning again $PEPE"},
        {"text": "No cashtags here"},
    ])

    counts = get_mention_counts("meme coins")

    assert counts["PEPE"] == 3
    assert counts["WIF"] == 1


@patch("dex_analyser.twitter._scraper")
def test_blocklist_filtered(mock_factory):
    mock_factory.return_value = _mock_scraper([
        {"text": "$USD is not a token, $BTC is"},
    ])

    counts = get_mention_counts("crypto")

    assert "USD" not in counts
    assert counts.get("BTC", 0) == 1


@patch("dex_analyser.twitter._scraper")
def test_returns_empty_on_exception(mock_factory):
    scraper = MagicMock()
    scraper.get_tweets.side_effect = Exception("network error")
    mock_factory.return_value = scraper

    assert get_mention_counts("anything") == {}
