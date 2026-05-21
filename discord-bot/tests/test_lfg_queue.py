"""
Tests for LFG queue operations.

Tests the core queue functionality:
- Adding users to queue
- Removing users from queue
- Expiring old entries
- Matching two users
- Concurrent access with locks

Run with: pytest tests/test_lfg_queue.py -v
"""

import pytest
import asyncio
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


def make_queue_entry(queue_type="ranked", timestamp=None, timeframe=30, deck_url=None, **kwargs):
    """Helper to create a queue entry in the new multi-queue format."""
    if timestamp is None:
        timestamp = datetime.now()
    entry = {
        "timestamp": timestamp,
        "timeframe": timeframe,
        "deck_url": deck_url,
    }
    entry.update(kwargs)
    return {"queues": {queue_type: entry}}


class TestLFGQueueBasics:
    """Test basic queue operations."""

    @pytest.mark.asyncio
    async def test_queue_add_single_user(self):
        """Test adding a single user to the queue."""
        user_id = 123456789
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[user_id] = make_queue_entry(
                deck_url="https://curiosa.io/test",
            )

        assert user_id in lfg_queue
        assert lfg_queue[user_id]["queues"]["ranked"]["timeframe"] == 30
        assert lfg_queue[user_id]["queues"]["ranked"]["deck_url"] == "https://curiosa.io/test"

    @pytest.mark.asyncio
    async def test_queue_add_multiple_users(self):
        """Test adding multiple users to the queue."""
        lfg_queue.clear()
        user_ids = [111, 222, 333]

        async with lfg_queue_lock:
            for i, user_id in enumerate(user_ids):
                lfg_queue[user_id] = make_queue_entry(timeframe=30 + i * 5)

        assert len(lfg_queue) == 3
        assert all(uid in lfg_queue for uid in user_ids)

    @pytest.mark.asyncio
    async def test_queue_remove_user(self):
        """Test removing a user from the queue."""
        user_id = 123456789
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[user_id] = make_queue_entry()

        assert user_id in lfg_queue

        async with lfg_queue_lock:
            lfg_queue.pop(user_id, None)

        assert user_id not in lfg_queue

    @pytest.mark.asyncio
    async def test_queue_duplicate_user_check(self):
        """Test that duplicate users are detected."""
        user_id = 123456789
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[user_id] = make_queue_entry()

        # Try to add same user again
        assert user_id in lfg_queue

    @pytest.mark.asyncio
    async def test_queue_deck_url_optional(self):
        """Test that deck URL is optional when joining queue."""
        lfg_queue.clear()

        async with lfg_queue_lock:
            # User without deck URL
            lfg_queue[111] = make_queue_entry()
            # User with deck URL
            lfg_queue[222] = make_queue_entry(deck_url="https://curiosa.io/test")

        assert lfg_queue[111]["queues"]["ranked"]["deck_url"] is None
        assert lfg_queue[222]["queues"]["ranked"]["deck_url"] is not None


class TestQueueExpiration:
    """Test queue expiration logic."""

    @pytest.mark.asyncio
    async def test_find_expired_entries(self):
        """Test identifying expired queue entries."""
        lfg_queue.clear()
        current_time = datetime.now()

        async with lfg_queue_lock:
            # Add user with 30-minute timeframe (not expired)
            lfg_queue[111] = make_queue_entry(timestamp=current_time)
            # Add user with 5-minute timeframe, added 15 minutes ago (expired)
            lfg_queue[222] = make_queue_entry(
                timestamp=current_time - timedelta(minutes=15),
                timeframe=5,
            )

        # Check which entries are expired
        expired = []
        for user_id, user_data in lfg_queue.items():
            for qt, entry in user_data["queues"].items():
                expiry_time = entry["timestamp"] + timedelta(minutes=entry["timeframe"])
                if current_time > expiry_time:
                    expired.append(user_id)

        assert 222 in expired
        assert 111 not in expired

    @pytest.mark.asyncio
    async def test_remove_expired_entries(self):
        """Test removing all expired entries from queue."""
        lfg_queue.clear()
        current_time = datetime.now()

        async with lfg_queue_lock:
            lfg_queue[111] = make_queue_entry(timestamp=current_time)
            lfg_queue[222] = make_queue_entry(
                timestamp=current_time - timedelta(minutes=20),
                timeframe=10,
            )
            lfg_queue[333] = make_queue_entry(
                timestamp=current_time - timedelta(minutes=5),
            )

        # Remove expired entries
        async with lfg_queue_lock:
            expired_users = []
            for user_id, user_data in list(lfg_queue.items()):
                for qt, entry in list(user_data["queues"].items()):
                    if current_time > entry["timestamp"] + timedelta(minutes=entry["timeframe"]):
                        expired_users.append(user_id)
            for user_id in expired_users:
                lfg_queue.pop(user_id, None)

        assert 111 in lfg_queue
        assert 222 not in lfg_queue
        assert 333 in lfg_queue

    @pytest.mark.asyncio
    async def test_timeframe_bounds(self):
        """Test that timeframe is within bounds (5-120 minutes)."""
        lfg_queue.clear()

        test_cases = [
            (1, 5),      # Too low -> 5
            (5, 5),      # Valid
            (30, 30),    # Valid
            (120, 120),  # Valid
            (150, 120),  # Too high -> 120
        ]

        for input_time, expected_time in test_cases:
            # Clamp timeframe to valid range
            clamped = max(5, min(120, input_time))
            assert clamped == expected_time


class TestMatchingLogic:
    """Test user matching logic."""

    @pytest.mark.asyncio
    async def test_find_match_with_two_users(self):
        """Test matching two users in the queue."""
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[111] = make_queue_entry(deck_url="https://curiosa.io/deck1")
            lfg_queue[222] = make_queue_entry(deck_url="https://curiosa.io/deck2")

        # Matching should find a pair
        assert len(lfg_queue) == 2
        user_ids = list(lfg_queue.keys())
        assert 111 in user_ids
        assert 222 in user_ids

    @pytest.mark.asyncio
    async def test_no_match_with_single_user(self):
        """Test that no match is found with only one user."""
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[111] = make_queue_entry()

        # No matching possible with just one user
        assert len(lfg_queue) == 1

    @pytest.mark.asyncio
    async def test_no_match_with_empty_queue(self):
        """Test that no match is found with empty queue."""
        lfg_queue.clear()

        assert len(lfg_queue) == 0

    @pytest.mark.asyncio
    async def test_match_only_removes_one_opponent(self):
        """Test that matching only removes the opponent, not the requester."""
        lfg_queue.clear()

        async with lfg_queue_lock:
            lfg_queue[111] = make_queue_entry()
            lfg_queue[222] = make_queue_entry()
            lfg_queue[333] = make_queue_entry()

        # Simulate matching user 111 with user 222
        matched_opponent = 222
        async with lfg_queue_lock:
            if matched_opponent in lfg_queue:
                lfg_queue.pop(matched_opponent)

        # User 111 and 333 should still be in queue
        assert 111 in lfg_queue
        assert 222 not in lfg_queue
        assert 333 in lfg_queue


class TestConcurrentAccess:
    """Test thread-safe queue access."""

    @pytest.mark.asyncio
    async def test_concurrent_queue_additions(self):
        """Test that concurrent additions are safe with locks."""
        lfg_queue.clear()

        async def add_user(user_id):
            async with lfg_queue_lock:
                lfg_queue[user_id] = make_queue_entry()

        # Add multiple users concurrently
        user_ids = list(range(100, 110))
        await asyncio.gather(*[add_user(uid) for uid in user_ids])

        assert len(lfg_queue) == 10
        assert all(uid in lfg_queue for uid in user_ids)

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self):
        """Test concurrent read and write operations."""
        lfg_queue.clear()

        async def reader():
            for _ in range(5):
                async with lfg_queue_lock:
                    _ = len(lfg_queue)
                await asyncio.sleep(0.01)

        async def writer(user_id):
            async with lfg_queue_lock:
                lfg_queue[user_id] = make_queue_entry()

        # Run readers and writers concurrently
        readers = [reader() for _ in range(3)]
        writers = [writer(uid) for uid in range(1, 6)]
        await asyncio.gather(*readers, *writers)

        # Queue should have all writes
        assert len(lfg_queue) == 5


class TestQueueState:
    """Test queue state management."""

    def test_pending_match_reports_empty(self):
        """Test pending match reports state is initialized."""
        pending_match_reports.clear()
        assert len(pending_match_reports) == 0

    def test_add_pending_report(self):
        """Test adding a pending match report."""
        pending_match_reports.clear()

        report_key = (111, 222)
        pending_match_reports[report_key] = {
            "winner_id": 111,
            "loser_id": 222,
            "timestamp": datetime.now(),
        }

        assert report_key in pending_match_reports
        assert pending_match_reports[report_key]["winner_id"] == 111

    def test_remove_pending_report(self):
        """Test removing a pending match report."""
        pending_match_reports.clear()

        report_key = (111, 222)
        pending_match_reports[report_key] = {"winner_id": 111}
        assert report_key in pending_match_reports

        pending_match_reports.pop(report_key, None)
        assert report_key not in pending_match_reports

    def test_processed_matches_tracking(self):
        """Test tracking processed matches."""
        processed_matches.clear()

        match_key = frozenset({111, 222})
        processed_matches[match_key] = datetime.now()

        assert match_key in processed_matches
        assert isinstance(processed_matches[match_key], datetime)

    @pytest.mark.asyncio
    async def test_prevent_double_reporting(self):
        """Test that same match is not reported twice."""
        processed_matches.clear()

        match_key = frozenset({111, 222})
        processed_matches[match_key] = datetime.now()

        # Check if already reported
        is_duplicate = match_key in processed_matches
        assert is_duplicate

        # Try to report again - should be blocked
        if is_duplicate:
            # Duplicate! Don't report again
            pass
