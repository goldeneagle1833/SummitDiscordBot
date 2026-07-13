"""Tests for blocked users feature - repository and LFG matchmaking integration."""

import pytest
import datetime
import os
import sqlite3
from unittest.mock import Mock, MagicMock

from cogs.lfg.cog import LFGCog
from cogs.lfg.state import lfg_queue
from repositories.blocked_users_repo import (
    create_blocked_users_table,
    get_blocked_user_ids,
    is_blocked_pair,
)


def make_queue_entry(queue_type, timestamp, timeframe=30, deck_url=None, **kwargs):
    entry = {
        "timestamp": timestamp,
        "timeframe": timeframe,
        "deck_url": deck_url,
    }
    entry.update(kwargs)
    return {"queues": {queue_type: entry}}


@pytest.fixture(autouse=True)
def clear_queue():
    lfg_queue.clear()
    yield
    lfg_queue.clear()


@pytest.fixture
def mock_bot():
    bot = Mock()
    bot.get_channel = Mock(return_value=Mock())
    return bot


@pytest.fixture
def lfg_cog(mock_bot):
    cog = object.__new__(LFGCog)
    cog.bot = mock_bot
    cog.lfg_channel_id = 222222222
    cog.check_last_match_opponent = MagicMock(return_value=False)
    return cog


@pytest.fixture
def mock_ctx():
    ctx = Mock()
    ctx.author = Mock()
    ctx.author.id = 999
    return ctx


# ── Repository tests ────────────────────────────────────────


class TestBlockedUsersRepo:
    def test_create_table(self):
        create_blocked_users_table()
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blocked_users'")
        assert cur.fetchone() is not None
        conn.close()

    def test_get_blocked_user_ids_empty(self):
        create_blocked_users_table()
        result = get_blocked_user_ids(123)
        assert result == set()

    def test_block_and_retrieve(self):
        create_blocked_users_table()
        conn = sqlite3.connect("match_records.db")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('100', '200')")
        conn.commit()
        conn.close()

        result = get_blocked_user_ids(100)
        assert "200" in result

    def test_is_blocked_pair_forward(self):
        create_blocked_users_table()
        conn = sqlite3.connect("match_records.db")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('100', '200')")
        conn.commit()
        conn.close()

        assert is_blocked_pair(100, 200) is True

    def test_is_blocked_pair_reverse(self):
        """If B blocked A, A should also not be paired with B."""
        create_blocked_users_table()
        conn = sqlite3.connect("match_records.db")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('200', '100')")
        conn.commit()
        conn.close()

        assert is_blocked_pair(100, 200) is True

    def test_is_blocked_pair_no_block(self):
        create_blocked_users_table()
        assert is_blocked_pair(100, 200) is False

    def test_multiple_blocked_users(self):
        create_blocked_users_table()
        conn = sqlite3.connect("match_records.db")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('100', '200')")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('100', '300')")
        conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id) VALUES ('100', '400')")
        conn.commit()
        conn.close()

        result = get_blocked_user_ids(100)
        assert result == {"200", "300", "400"}


# ── LFG matchmaking integration tests ────────────────────────


class TestBlockedUsersMatchmaking:
    def test_blocked_user_skipped_in_ranked(self, lfg_cog, mock_ctx):
        """Blocked player should be skipped in ranked queue."""
        now = datetime.datetime.now()

        lfg_queue[111] = make_queue_entry("ranked", now - datetime.timedelta(minutes=5))
        lfg_queue[222] = make_queue_entry("ranked", now - datetime.timedelta(minutes=3))

        # Mock is_blocked_pair: 999 has blocked 111
        with MagicMock() as mock_blocked:
            mock_blocked.side_effect = lambda a, b: {frozenset([999, 111])}.issuperset({frozenset([a, b])})
            import cogs.lfg.cog as cog_module
            original = cog_module.is_blocked_pair
            cog_module.is_blocked_pair = mock_blocked
            try:
                matched = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")
                assert matched == 222, "Should skip blocked player 111 and match with 222"
            finally:
                cog_module.is_blocked_pair = original

    def test_blocked_user_skipped_in_casual(self, lfg_cog, mock_ctx):
        """Blocked player should be skipped even in casual queue."""
        now = datetime.datetime.now()

        lfg_queue[111] = make_queue_entry("testing", now - datetime.timedelta(minutes=5))
        lfg_queue[222] = make_queue_entry("testing", now - datetime.timedelta(minutes=3))

        import cogs.lfg.cog as cog_module
        original = cog_module.is_blocked_pair
        cog_module.is_blocked_pair = lambda a, b: frozenset([a, b]) == frozenset([999, 111])
        try:
            matched = lfg_cog.check_if_someone_is_lfg(mock_ctx, "testing")
            assert matched == 222
        finally:
            cog_module.is_blocked_pair = original

    def test_no_match_when_all_blocked(self, lfg_cog, mock_ctx):
        """If all queue members are blocked, should return None."""
        now = datetime.datetime.now()

        lfg_queue[111] = make_queue_entry("ranked", now - datetime.timedelta(minutes=5))

        import cogs.lfg.cog as cog_module
        original = cog_module.is_blocked_pair
        cog_module.is_blocked_pair = lambda a, b: True
        try:
            matched = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")
            assert matched is None
        finally:
            cog_module.is_blocked_pair = original

    def test_pair_players_skips_blocked(self, lfg_cog, mock_ctx):
        """pair_players() should also skip blocked users."""
        now = datetime.datetime.now()

        lfg_queue[111] = make_queue_entry("ranked", now - datetime.timedelta(minutes=5))
        lfg_queue[222] = make_queue_entry("ranked", now - datetime.timedelta(minutes=3))

        import cogs.lfg.cog as cog_module
        original = cog_module.is_blocked_pair
        cog_module.is_blocked_pair = lambda a, b: frozenset([a, b]) == frozenset([999, 111])
        try:
            matched = lfg_cog.pair_players(mock_ctx)
            assert matched == 222
        finally:
            cog_module.is_blocked_pair = original

    def test_unblocked_users_match_normally(self, lfg_cog, mock_ctx):
        """Users who are not blocked should match normally."""
        now = datetime.datetime.now()

        lfg_queue[111] = make_queue_entry("ranked", now - datetime.timedelta(minutes=5))

        import cogs.lfg.cog as cog_module
        original = cog_module.is_blocked_pair
        cog_module.is_blocked_pair = lambda a, b: False
        try:
            matched = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")
            assert matched == 111
        finally:
            cog_module.is_blocked_pair = original
