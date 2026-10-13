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


def test_dm_skips_closed_dms_and_keeps_going(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    import discord
    from services import meta_report_notify

    monkeypatch.setattr(meta_report_notify, "DM_PAUSE_SECONDS", 0)
    open_user = MagicMock(send=AsyncMock())
    closed_user = MagicMock(send=AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "closed")))
    bot = MagicMock(fetch_user=AsyncMock(side_effect=[closed_user, open_user]))
    result = asyncio.run(meta_report_notify.dm_meta_report(
        bot, {"url": "https://x/meta-report/2026-09-a"}, ["1", "2", "not-an-id"]))
    assert result == {"sent": 1, "failed": 2}
    open_user.send.assert_awaited_once()
