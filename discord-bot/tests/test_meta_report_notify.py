"""Meta Report announcement embed for the content channel."""

from services.meta_report_notify import build_embed


def test_embed_lists_story_and_link():
    embed = build_embed({
        "title": "Meta Report: Sep 1–15, 2026",
        "url": "https://sorcererssummit.com/meta-report/2026-09-a",
        "story": [{"headline": "Sparkmage is the deck to beat.", "detail": "55% win rate."}, "junk"],
        "topTier": ["Sparkmage (Air / Fire)"],
        "rankedGames": 1284,
        "events": 1,
    })
    assert embed.title == "Meta Report: Sep 1–15, 2026"
    assert embed.url.endswith("/meta-report/2026-09-a")
    assert "**1. Sparkmage is the deck to beat.** 55% win rate." in embed.description
    fields = {f.name: f.value for f in embed.fields}
    assert fields["S tier"] == "Sparkmage (Air / Fire)"
    assert "1,284 ranked games" in fields["Based on"] and "1 Top 8 event" in fields["Based on"]


def test_embed_without_story_still_reads():
    embed = build_embed({"url": "https://x/meta-report/2026-09-a"})
    assert embed.description and embed.title == "Meta Report"
