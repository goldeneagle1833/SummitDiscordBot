"""Tests for the recap copy the daily summary saves for the Match History page."""

import datetime
import json
import sqlite3
from unittest.mock import MagicMock

import config

# config.example.py (used in CI) has no daily summary settings
for _name, _value in (("DAILY_SUMMARY_HOUR", 23), ("DAILY_SUMMARY_MINUTE", 0), ("DAILY_SUMMARY_CHANNEL_ID", 0)):
    if not hasattr(config, _name):
        setattr(config, _name, _value)

from cogs.daily_summary import _period, _recap_url, _save_recap, _build_embed


def _guild(names):
    guild = MagicMock()

    def get_member(user_id):
        if str(user_id) not in names:
            return None
        member = MagicMock()
        member.display_name = names[str(user_id)]
        return member

    guild.get_member.side_effect = get_member
    return guild


def test_recap_link_carries_kind_and_date():
    period = _period("daily", datetime.date(2026, 10, 9))
    assert _recap_url(period).endswith("/match-history?recap=daily&date=2026-10-09")
    embed = _build_embed(period, {"total_matches": 0}, {}, None)
    assert embed.url.endswith("?recap=daily&date=2026-10-09")
    assert "recap=daily&date=2026-10-09" in embed.description


def test_save_recap_stores_stats_and_server_names():
    period = _period("weekly", datetime.date(2026, 10, 11))
    stats = {
        "total_matches": 5,
        "top_gainer": (111, "OldName", 30),
        "hot_streaks": [(222, "Bob", 4)],
        "broken_streaks": [],
    }
    _save_recap(period, stats, {"total_matches": 3}, _guild({"111": "Alice"}))
    # Re-posting the same day replaces the saved copy
    stats["total_matches"] = 6
    _save_recap(period, stats, {"total_matches": 3}, _guild({"111": "Alice"}))

    conn = sqlite3.connect("match_records.db")
    rows = conn.execute("SELECT kind, date, payload FROM daily_summaries").fetchall()
    conn.close()

    assert len(rows) == 1
    kind, date, payload = rows[0]
    assert (kind, date) == ("weekly", "2026-10-11")
    data = json.loads(payload)
    assert data["stats"]["total_matches"] == 6
    assert data["stats"]["top_gainer"] == [111, "OldName", 30]
    assert data["names"] == {"111": "Alice"}
    assert data["previous"] == {"total_matches": 3}
    assert data["start"] == "2026-10-05"
