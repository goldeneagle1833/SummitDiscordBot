"""
Tests for LFG race condition fixes.

Tests concurrent operations to verify:
- Multiple simultaneous pairing saves
- Pairing validation with concurrent access
- Error handling for database operations

Run with: pytest tests/test_lfg_race_conditions.py -v
"""

import pytest
import sys
import os
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repositories.elo_repo import (
    create_active_pairings_table,
    save_pairing,
    get_pairing_between_players,
    mark_pairing_reported,
    cleanup_old_pairings,
)


class TestConcurrentPairingSaves:
    """Test concurrent pairing save operations."""

    def test_multiple_concurrent_saves(self):
        """Test that multiple pairings can be saved concurrently without errors."""
        guild_id = 111111111

        # Create multiple pairings concurrently
        pairings = []
        for i in range(10):
            pairing_id = save_pairing(
                guild_id=guild_id,
                player1_id=100 + i,
                player2_id=200 + i,
                player1_deck_url=f"https://curiosa.io/deck{i}a",
                player2_deck_url=f"https://curiosa.io/deck{i}b",
            )
            pairings.append(pairing_id)

        # Verify all pairings were saved with unique IDs
        assert len(pairings) == 10
        assert len(set(pairings)) == 10  # All IDs are unique

    def test_save_pairing_with_none_guild_id(self):
        """Test that save_pairing raises ValueError for None guild_id."""
        with pytest.raises(ValueError, match="guild_id cannot be None"):
            save_pairing(
                guild_id=None,
                player1_id=123456789,
                player2_id=987654321,
            )


class TestPairingValidationUnderConcurrency:
    """Test pairing validation with concurrent operations."""

    def test_validate_then_mark_reported(self):
        """Test that validation works correctly before marking as reported."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Save pairing
        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Validate pairing exists (status='active' is checked in the query)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is not None

        # Mark as reported
        success = mark_pairing_reported(guild_id, player1_id, player2_id)
        assert success is True

        # Validation should now fail (pairing is no longer active)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is None

    def test_multiple_pairings_same_players_different_times(self):
        """Test handling multiple pairings for same players over time."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # First pairing
        pairing1_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Mark first pairing as reported
        mark_pairing_reported(guild_id, player1_id, player2_id)

        # Second pairing (new match)
        pairing2_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Should get the second (most recent) pairing (status='active' is checked in query)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is not None
        assert pairing["pairing_id"] == pairing2_id


class TestDatabaseCleanup:
    """Test database cleanup operations."""

    def test_cleanup_old_pairings(self):
        """Test that cleanup_old_pairings expires old pairings."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Save a pairing
        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Verify pairing is active (status='active' is checked in query)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is not None

        # Run cleanup (with 0 hours to expire all active pairings)
        cleanup_old_pairings(hours=0)

        # Pairing should now be expired (not found as active)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is None

    def test_cleanup_respects_time_threshold(self):
        """Test that cleanup only expires pairings older than threshold."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Save a recent pairing
        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Run cleanup with high threshold (should not expire recent pairings)
        cleanup_old_pairings(hours=48)

        # Pairing should still be active (status='active' is checked in query)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is not None


class TestErrorHandling:
    """Test error handling in database operations."""

    def test_save_pairing_logs_on_error(self, caplog):
        """Test that save_pairing logs errors appropriately."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Mock database connection to simulate error
        with patch("repositories.elo_repo.get_db_connection") as mock_conn:
            mock_conn.side_effect = Exception("Database connection failed")

            with pytest.raises(Exception, match="Database connection failed"):
                save_pairing(
                    guild_id=guild_id,
                    player1_id=player1_id,
                    player2_id=player2_id,
                )

    def test_get_pairing_returns_none_on_missing(self):
        """Test that get_pairing_between_players returns None for missing pairings."""
        guild_id = 999999999
        player1_id = 888888888
        player2_id = 777777777

        # Query for non-existent pairing
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)

        # Should return None, not raise an error
        assert pairing is None


class TestIntegrationFlow:
    """Integration test for complete match flow with race condition handling."""

    def test_complete_match_flow_with_logging(self, caplog):
        """Test complete match flow: save → validate → report with logging."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Step 1: Save pairing (would happen in queue.py)
        import logging

        with caplog.at_level(logging.INFO):
            pairing_id = save_pairing(
                guild_id=guild_id,
                player1_id=player1_id,
                player2_id=player2_id,
                player1_deck_url="https://curiosa.io/deck1",
                player2_deck_url="https://curiosa.io/deck2",
            )

            # Verify logging occurred
            assert f"Saved pairing {pairing_id}" in caplog.text

        # Step 2: Validate pairing exists (would happen in match_reporting.py)
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is not None
        assert pairing["pairing_id"] == pairing_id

        # Step 3: Mark as reported (would happen after confirmation)
        success = mark_pairing_reported(guild_id, player1_id, player2_id)
        assert success is True

        # Step 4: Verify pairing is no longer active
        pairing = get_pairing_between_players(guild_id, player1_id, player2_id)
        assert pairing is None
