"""Tests for !fart_gift once-per-recipient-per-season tracking."""

import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

# Minimal config stub so fun.py can import without discord-bot/config.py
sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
    ),
)

from cogs.fun import FunCog  # noqa: E402


@pytest.fixture()
def gift_db(tmp_path, monkeypatch):
    """Run gift helpers against a temp fart_scores.db in cwd."""
    monkeypatch.chdir(tmp_path)
    cog = FunCog(MagicMock())
    yield cog
    if os.path.exists("fart_scores.db"):
        os.remove("fart_scores.db")


class TestFartGiftSeasonLimit:
    def test_not_gifted_initially(self, gift_db):
        assert gift_db.has_gifted_to_this_season(111, 222) is False

    def test_mark_and_detect_gift(self, gift_db):
        gift_db.mark_gifted_this_season(111, 222)
        assert gift_db.has_gifted_to_this_season(111, 222) is True

    def test_different_recipient_still_allowed(self, gift_db):
        gift_db.mark_gifted_this_season(111, 222)
        assert gift_db.has_gifted_to_this_season(111, 333) is False

    def test_different_gifter_still_allowed(self, gift_db):
        gift_db.mark_gifted_this_season(111, 222)
        assert gift_db.has_gifted_to_this_season(999, 222) is False

    def test_table_schema(self, gift_db):
        gift_db.mark_gifted_this_season(1, 2)
        conn = sqlite3.connect("fart_scores.db")
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(fart_gift_usage)").fetchall()
        }
        conn.close()
        assert cols == {"gifter_id", "recipient_id", "gifted_at"}
