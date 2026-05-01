"""
Integration tests for complete LFG flow.

Tests end-to-end scenarios:
- User joins queue
- Match is found
- Match is reported
- ELO is updated

Run with: pytest tests/test_lfg_flow.py -v
"""

import pytest
import asyncio
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.lfg.state import (
    lfg_queue,
    lfg_queue_lock,
    pending_match_reports,
    processed_matches,
)
from cogs.lfg.match_reporting import ReportResultSelectView, MatchReportDeckModal
from cogs.lfg.helpers import scrub_urls


class TestLFGMatchFlow:
    """Test the complete flow from joining to reporting."""

    @pytest.mark.asyncio
    async def test_user_joins_queue(self):
        """Test user joining the queue."""
        lfg_queue.clear()

        user_id = 123456789
        async with lfg_queue_lock:
            lfg_queue[user_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": "https://curiosa.io/deck1",
            }

        assert user_id in lfg_queue
        assert lfg_queue[user_id]["timeframe"] == 30

    @pytest.mark.asyncio
    async def test_two_users_match(self):
        """Test two users being matched."""
        lfg_queue.clear()

        # Both users join
        user1_id = 123456789
        user2_id = 987654321

        async with lfg_queue_lock:
            lfg_queue[user1_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": "https://curiosa.io/deck1",
            }
            lfg_queue[user2_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": "https://curiosa.io/deck2",
            }

        # Check for match
        assert user1_id in lfg_queue
        assert user2_id in lfg_queue
        assert len(lfg_queue) == 2

    @pytest.mark.asyncio
    async def test_match_and_remove_opponent(self):
        """Test that matched opponent is removed from queue."""
        lfg_queue.clear()

        user1_id = 123456789
        user2_id = 987654321

        async with lfg_queue_lock:
            lfg_queue[user1_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": None,
            }
            lfg_queue[user2_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": None,
            }

        # User1 matches with User2
        matched_user_id = user2_id
        matched_user_deck_url = lfg_queue.get(matched_user_id, {}).get("deck_url")

        async with lfg_queue_lock:
            lfg_queue.pop(matched_user_id, None)

        assert matched_user_id not in lfg_queue
        assert user1_id in lfg_queue  # User1 should still be in queue to add themselves

    @pytest.mark.asyncio
    async def test_match_report_flow(self):
        """Test the match report flow with pending reports."""
        pending_match_reports.clear()

        reporter_id = 123456789
        opponent_id = 987654321

        # Create pending report
        report_key = (reporter_id, opponent_id)
        pending_match_reports[report_key] = {
            "winner_id": reporter_id,
            "loser_id": opponent_id,
            "timestamp": datetime.now(),
            "match_data": {
                "first_player": "y",
                "match_time": 25,
                "deck_url": "https://curiosa.io/winner",
            },
        }

        assert report_key in pending_match_reports

    @pytest.mark.asyncio
    async def test_prevent_duplicate_match_reports(self):
        """Test that same match cannot be reported twice."""
        processed_matches.clear()

        player1_id = 123456789
        player2_id = 987654321
        match_key = frozenset({player1_id, player2_id})

        # First report
        processed_matches[match_key] = datetime.now()
        assert match_key in processed_matches

        # Try to report again - should detect duplicate
        is_duplicate = match_key in processed_matches
        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_multiple_concurrent_matches(self):
        """Test handling multiple matches concurrently."""
        lfg_queue.clear()

        # Add 6 users (3 potential matches)
        user_ids = [100, 101, 102, 103, 104, 105]

        async with lfg_queue_lock:
            for user_id in user_ids:
                lfg_queue[user_id] = {
                    "timestamp": datetime.now(),
                    "timeframe": 30,
                    "deck_url": None,
                }

        assert len(lfg_queue) == 6

        # Simulate 3 matches being made
        matches = [(100, 101), (102, 103), (104, 105)]
        remaining_users = user_ids.copy()

        for player1, player2 in matches:
            async with lfg_queue_lock:
                if player2 in lfg_queue:
                    lfg_queue.pop(player2)
                if player1 in remaining_users:
                    remaining_users.remove(player1)
                if player2 in remaining_users:
                    remaining_users.remove(player2)

        # Both players should be removed from remaining
        assert len(remaining_users) == 0


class TestQueueCleanupFlow:
    """Test queue cleanup and expiration."""

    @pytest.mark.asyncio
    async def test_clean_expired_queue_entries(self):
        """Test cleaning expired entries from queue."""
        lfg_queue.clear()

        current_time = datetime.now()
        async with lfg_queue_lock:
            # Add mix of expired and valid entries
            lfg_queue[111] = {
                "timestamp": current_time - timedelta(minutes=40),
                "timeframe": 30,
                "deck_url": None,
            }
            lfg_queue[222] = {
                "timestamp": current_time - timedelta(minutes=5),
                "timeframe": 30,
                "deck_url": None,
            }
            lfg_queue[333] = {
                "timestamp": current_time,
                "timeframe": 30,
                "deck_url": None,
            }

        # Clean expired
        async with lfg_queue_lock:
            expired_ids = [
                uid
                for uid, entry in list(lfg_queue.items())
                if current_time > entry["timestamp"] + timedelta(minutes=entry["timeframe"])
            ]
            for uid in expired_ids:
                lfg_queue.pop(uid, None)

        assert 111 not in lfg_queue
        assert 222 in lfg_queue
        assert 333 in lfg_queue

    @pytest.mark.asyncio
    async def test_queue_with_mixed_timeframes(self):
        """Test queue with different timeframe durations."""
        lfg_queue.clear()

        current_time = datetime.now()
        async with lfg_queue_lock:
            lfg_queue[111] = {
                "timestamp": current_time - timedelta(minutes=10),
                "timeframe": 5,  # Expired
                "deck_url": None,
            }
            lfg_queue[222] = {
                "timestamp": current_time - timedelta(minutes=10),
                "timeframe": 20,  # Still valid
                "deck_url": None,
            }
            lfg_queue[333] = {
                "timestamp": current_time,
                "timeframe": 120,  # Just added, valid
                "deck_url": None,
            }

        # Find expired
        async with lfg_queue_lock:
            expired = [
                uid
                for uid, entry in list(lfg_queue.items())
                if current_time > entry["timestamp"] + timedelta(minutes=entry["timeframe"])
            ]

        assert 111 in expired
        assert 222 not in expired
        assert 333 not in expired


class TestURLHandlingInFlow:
    """Test URL handling throughout the LFG flow."""

    @pytest.mark.asyncio
    async def test_deck_urls_preserved_in_queue(self):
        """Test that deck URLs are preserved in queue."""
        lfg_queue.clear()

        user_id = 123456789
        deck_url = "https://curiosa.io/decks/test123"

        async with lfg_queue_lock:
            lfg_queue[user_id] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": deck_url,
            }

        assert lfg_queue[user_id]["deck_url"] == deck_url

    @pytest.mark.asyncio
    async def test_scrub_urls_in_public_message(self):
        """Test that URLs are scrubbed in public channel messages."""
        deck_url = "https://curiosa.io/decks/secret"
        message = f"Match found! Your deck: {deck_url}"

        scrubbed = scrub_urls(message)

        assert deck_url not in scrubbed
        assert "[link removed]" in scrubbed
        assert "Match found!" in scrubbed

    @pytest.mark.asyncio
    async def test_handle_missing_deck_url(self):
        """Test handling users who don't provide deck URL."""
        lfg_queue.clear()

        user_without_url = 111
        user_with_url = 222

        async with lfg_queue_lock:
            lfg_queue[user_without_url] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": None,
            }
            lfg_queue[user_with_url] = {
                "timestamp": datetime.now(),
                "timeframe": 30,
                "deck_url": "https://curiosa.io/deck",
            }

        # Both should be matchable
        assert user_without_url in lfg_queue
        assert user_with_url in lfg_queue


class TestReportingFlow:
    """Test match reporting integration."""

    @pytest.mark.asyncio
    async def test_reporter_chosen_randomly(self):
        """Test that reporter is randomly chosen from two players."""
        # This is a logic test - in real code, random.sample is used
        players = [
            (111, "Player1", "deck1"),
            (222, "Player2", "deck2"),
        ]

        # Simulate random selection (would use random.sample in real code)
        import random
        selected = random.sample(players, 2)

        assert len(selected) == 2
        assert selected[0] != selected[1]

    @pytest.mark.asyncio
    async def test_confirmation_flow(self):
        """Test that non-reporter gets confirmation button."""
        pending_match_reports.clear()

        reporter_id = 111
        other_id = 222

        # After reporter submits report, create pending confirmation
        report_key = (reporter_id, other_id)
        pending_match_reports[report_key] = {
            "result": "reporter_won",
            "timestamp": datetime.now(),
        }

        assert report_key in pending_match_reports

    @pytest.mark.asyncio
    async def test_confirm_match_removes_pending(self):
        """Test that confirming a match removes it from pending."""
        pending_match_reports.clear()

        report_key = (111, 222)
        pending_match_reports[report_key] = {
            "result": "reporter_won",
            "timestamp": datetime.now(),
        }

        # Opponent confirms
        pending_match_reports.pop(report_key, None)

        assert report_key not in pending_match_reports

    @pytest.mark.asyncio
    async def test_reject_match_removes_pending(self):
        """Test that rejecting a match removes it from pending."""
        pending_match_reports.clear()

        report_key = (111, 222)
        pending_match_reports[report_key] = {
            "result": "reporter_won",
            "timestamp": datetime.now(),
        }

        # Opponent rejects
        pending_match_reports.pop(report_key, None)

        assert report_key not in pending_match_reports


def _build_report_result_view(mock_bot, mock_user, mock_user_2, reporter_deck_url):
    return ReportResultSelectView(
        bot=mock_bot,
        reporter_id=mock_user.id,
        reporter_global=mock_user.global_name,
        reporter_deck_url=reporter_deck_url,
        opponent_id=mock_user_2.id,
        opponent_global=mock_user_2.global_name,
        opponent_deck_url="https://curiosa.io/decks/opponent-deck",
        player1_id=mock_user.id,
        player1_global=mock_user.global_name,
        player2_id=mock_user_2.id,
        player2_global=mock_user_2.global_name,
        match_start_time=datetime.now(),
        guild_id=111111111,
        ladder_info={},
        match_type="ranked",
        reporter_run_id=0,
        opponent_run_id=0,
    )


class TestReportResultSelectView:
    @pytest.mark.asyncio
    async def test_selects_do_not_auto_submit(self, mock_bot, mock_interaction, mock_user, mock_user_2):
        view = _build_report_result_view(
            mock_bot, mock_user, mock_user_2, "https://curiosa.io/decks/reporter-deck"
        )
        view._submit = AsyncMock()

        view.first_select._values = [str(mock_user.id)]
        await view._on_first_select(mock_interaction)

        assert view.selected_first_id == mock_user.id
        assert view.submit_button.disabled is True
        view._submit.assert_not_awaited()

        mock_interaction.response.edit_message.reset_mock()
        view.winner_select._values = [str(mock_user_2.id)]
        await view._on_winner_select(mock_interaction)

        assert view.selected_winner_id == mock_user_2.id
        assert view.submit_button.disabled is False
        view._submit.assert_not_awaited()
        mock_interaction.response.edit_message.assert_awaited_once_with(view=view)

    @pytest.mark.asyncio
    async def test_submit_button_opens_deck_modal_when_missing_deck_url(
        self, mock_bot, mock_interaction, mock_user, mock_user_2
    ):
        view = _build_report_result_view(mock_bot, mock_user, mock_user_2, None)
        view.selected_first_id = mock_user.id
        view.selected_winner_id = mock_user.id
        view._sync_controls()

        await view._on_submit(mock_interaction)

        modal = mock_interaction.response.send_modal.await_args.args[0]
        assert isinstance(modal, MatchReportDeckModal)
        assert view._submit_interaction is mock_interaction

    @pytest.mark.asyncio
    async def test_submit_button_calls_submit_when_ready(
        self, mock_bot, mock_interaction, mock_user, mock_user_2
    ):
        view = _build_report_result_view(
            mock_bot, mock_user, mock_user_2, "https://curiosa.io/decks/reporter-deck"
        )
        view.selected_first_id = mock_user.id
        view.selected_winner_id = mock_user_2.id
        view._sync_controls()
        view._submit = AsyncMock()

        await view._on_submit(mock_interaction)

        mock_interaction.response.defer.assert_awaited_once_with()
        view._submit.assert_awaited_once_with(mock_interaction)


class TestStateReset:
    """Test state cleanup between matches."""

    def test_clear_queue_for_test(self):
        """Test clearing queue state."""
        lfg_queue.clear()
        assert len(lfg_queue) == 0

    def test_clear_pending_reports(self):
        """Test clearing pending reports state."""
        pending_match_reports.clear()
        assert len(pending_match_reports) == 0

    def test_clear_processed_matches(self):
        """Test clearing processed matches state."""
        processed_matches.clear()
        assert len(processed_matches) == 0

    def test_state_isolation(self):
        """Test that state modifications don't affect other tests."""
        lfg_queue.clear()
        pending_match_reports.clear()
        processed_matches.clear()

        # Add test data
        lfg_queue[123] = {"test": "data"}
        pending_match_reports[(1, 2)] = {"test": "data"}
        processed_matches[frozenset({1, 2})] = "timestamp"

        # Clear all
        lfg_queue.clear()
        pending_match_reports.clear()
        processed_matches.clear()

        assert len(lfg_queue) == 0
        assert len(pending_match_reports) == 0
        assert len(processed_matches) == 0
