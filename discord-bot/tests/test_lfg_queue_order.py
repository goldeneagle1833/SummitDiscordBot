"""Tests for LFG queue FIFO ordering - ensures first player in queue is matched first."""

import pytest
import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from cogs.lfg.cog import LFGCog
from cogs.lfg.state import lfg_queue


@pytest.fixture
def mock_bot():
    """Create a mock bot instance."""
    bot = Mock()
    bot.get_channel = Mock(return_value=Mock())
    return bot


@pytest.fixture
def lfg_cog(mock_bot):
    """Create an LFG cog instance with background tasks mocked."""
    # Create a mock cog instance without running __init__
    cog = object.__new__(LFGCog)
    cog.bot = mock_bot
    cog.lfg_channel_id = 222222222  # Mock channel ID
    # Mock check_last_match_opponent to always return False (no last match restriction)
    cog.check_last_match_opponent = MagicMock(return_value=False)
    return cog


@pytest.fixture
def mock_ctx():
    """Create a mock context with an author."""
    ctx = Mock()
    ctx.author = Mock()
    ctx.author.id = 999  # New player joining
    return ctx


@pytest.fixture(autouse=True)
def clear_queue():
    """Clear the queue before each test."""
    lfg_queue.clear()
    yield
    lfg_queue.clear()


class TestQueueFIFOOrdering:
    """Tests to verify FIFO (First In, First Out) ordering for all queue types."""

    def test_ranked_queue_fifo_order(self, lfg_cog, mock_ctx):
        """Test that ranked queue matches with the FIRST player who joined."""
        now = datetime.datetime.now()

        # Player 1 joins first (oldest)
        lfg_queue[111] = {
            "timestamp": now - datetime.timedelta(minutes=10),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 2 joins second
        lfg_queue[222] = {
            "timestamp": now - datetime.timedelta(minutes=5),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 3 joins third (newest)
        lfg_queue[333] = {
            "timestamp": now - datetime.timedelta(minutes=1),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 999 joins and should match with Player 111 (first in queue)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")

        assert matched_user_id == 111, "Should match with the FIRST player (111), not the newest"

    def test_casual_queue_fifo_order(self, lfg_cog, mock_ctx):
        """Test that casual queue matches with the FIRST player who joined."""
        now = datetime.datetime.now()

        # Player 1 joins first (oldest)
        lfg_queue[111] = {
            "timestamp": now - datetime.timedelta(minutes=10),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "testing",
        }

        # Player 2 joins second (newest)
        lfg_queue[222] = {
            "timestamp": now - datetime.timedelta(minutes=5),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "testing",
        }

        # Player 999 joins and should match with Player 111 (first in queue)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "testing")

        assert matched_user_id == 111, "Casual queue should match with the FIRST player (111)"

    def test_limited_queue_fifo_order(self, lfg_cog, mock_ctx):
        """Test that limited queue matches with the FIRST player who joined."""
        now = datetime.datetime.now()

        # Player 1 joins first (oldest)
        lfg_queue[111] = {
            "timestamp": now - datetime.timedelta(minutes=10),
            "timeframe": 30,
            "deck_url": "https://curiosa.io/decks/111",
            "queue_type": "limited",
            "run_id": 1,
        }

        # Player 2 joins second (newest)
        lfg_queue[222] = {
            "timestamp": now - datetime.timedelta(minutes=5),
            "timeframe": 30,
            "deck_url": "https://curiosa.io/decks/222",
            "queue_type": "limited",
            "run_id": 2,
        }

        # Player 999 joins and should match with Player 111 (first in queue)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "limited")

        assert matched_user_id == 111, "Limited queue should match with the FIRST player (111)"

    def test_two_players_ranked_queue(self, lfg_cog, mock_ctx):
        """Test the reported bug: when two people join ranked, first person should be matched."""
        now = datetime.datetime.now()

        # Player A joins ranked queue first
        player_a_id = 100
        lfg_queue[player_a_id] = {
            "timestamp": now - datetime.timedelta(seconds=30),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player B joins ranked queue second (this is ctx.author)
        mock_ctx.author.id = 200

        # Player B should match with Player A (who joined first)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")

        assert matched_user_id == player_a_id, (
            f"BUG: Player B should match with Player A ({player_a_id}) who joined first, "
            f"not with the newest player"
        )

    def test_expired_players_are_skipped(self, lfg_cog, mock_ctx):
        """Test that expired queue entries are skipped and newer valid entries are matched."""
        now = datetime.datetime.now()

        # Player 1 joined first but expired (31 minutes ago, timeframe=30)
        lfg_queue[111] = {
            "timestamp": now - datetime.timedelta(minutes=31),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 2 joined second and is still valid
        lfg_queue[222] = {
            "timestamp": now - datetime.timedelta(minutes=5),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 999 joins and should match with Player 222 (111 is expired)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")

        assert matched_user_id == 222, "Should skip expired player 111 and match with 222"

    def test_incompatible_queue_types_are_skipped(self, lfg_cog, mock_ctx):
        """Test that incompatible queue types are skipped in FIFO order."""
        now = datetime.datetime.now()

        # Player 1 joined first but in casual queue
        lfg_queue[111] = {
            "timestamp": now - datetime.timedelta(minutes=10),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "testing",
        }

        # Player 2 joined second in ranked queue (compatible)
        lfg_queue[222] = {
            "timestamp": now - datetime.timedelta(minutes=5),
            "timeframe": 30,
            "deck_url": None,
            "queue_type": "ranked",
        }

        # Player 999 joins ranked queue and should match with Player 222 (111 is incompatible)
        matched_user_id = lfg_cog.check_if_someone_is_lfg(mock_ctx, "ranked")

        assert matched_user_id == 222, "Should skip incompatible player 111 and match with ranked player 222"
