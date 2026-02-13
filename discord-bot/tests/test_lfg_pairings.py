"""
Tests for LFG pairing database operations.

Tests the active_pairings table functionality:
- Saving new pairings
- Validating pairings
- Marking pairings as reported
- Preventing invalid match reports

Run with: pytest tests/test_lfg_pairings.py -v
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from repositories.elo_repo import (
    create_active_pairings_table,
    save_pairing,
    get_active_pairing_for_user,
    get_opponent_from_pairing,
    validate_pairing,
    mark_pairing_reported,
    cancel_pairing,
    cleanup_old_pairings,
)


class TestPairingCreation:
    """Test creating new pairings."""

    def test_create_active_pairings_table(self):
        """Test that active_pairings table is created."""
        create_active_pairings_table()
        # If no exception, table was created successfully

    def test_save_single_pairing(self):
        """Test saving a new pairing."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        pairing_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url="https://curiosa.io/deck1",
            player2_deck_url="https://curiosa.io/deck2",
        )

        assert pairing_id is not None
        assert isinstance(pairing_id, int)

    def test_save_pairing_without_deck_urls(self):
        """Test saving pairing without deck URLs (optional)."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        pairing_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url=None,
            player2_deck_url=None,
        )

        assert pairing_id is not None

    def test_save_pairing_with_one_deck_url(self):
        """Test saving pairing with only one player's deck URL."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        pairing_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url="https://curiosa.io/deck1",
            player2_deck_url=None,
        )

        assert pairing_id is not None


class TestPairingRetrieval:
    """Test retrieving pairing information."""

    def test_get_active_pairing_for_player1(self):
        """Test getting active pairing for player 1."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url="https://curiosa.io/deck1",
            player2_deck_url="https://curiosa.io/deck2",
        )

        pairing = get_active_pairing_for_user(guild_id, player1_id)

        assert pairing is not None
        assert pairing["player1_id"] == player1_id
        assert pairing["player2_id"] == player2_id

    def test_get_active_pairing_for_player2(self):
        """Test getting active pairing for player 2."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url="https://curiosa.io/deck1",
            player2_deck_url="https://curiosa.io/deck2",
        )

        pairing = get_active_pairing_for_user(guild_id, player2_id)

        assert pairing is not None
        assert pairing["player1_id"] == player1_id
        assert pairing["player2_id"] == player2_id

    def test_get_pairing_different_guild(self):
        """Test that pairings are guild-specific."""
        guild1_id = 111111111
        guild2_id = 222222222
        player1_id = 123456789
        player2_id = 987654321

        # Save pairing in guild 1
        save_pairing(
            guild_id=guild1_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Check guild 1 - should find pairing
        pairing1 = get_active_pairing_for_user(guild1_id, player1_id)
        assert pairing1 is not None

        # Check guild 2 - should NOT find pairing
        pairing2 = get_active_pairing_for_user(guild2_id, player1_id)
        assert pairing2 is None

    def test_get_pairing_nonexistent_user(self):
        """Test getting pairing for user with no active pairing."""
        guild_id = 111111111

        pairing = get_active_pairing_for_user(guild_id, 999999999)

        assert pairing is None

    def test_get_opponent_from_pairing_player1(self):
        """Test getting opponent ID from player 1 perspective."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        opponent = get_opponent_from_pairing(guild_id, player1_id)

        assert opponent == player2_id

    def test_get_opponent_from_pairing_player2(self):
        """Test getting opponent ID from player 2 perspective."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        opponent = get_opponent_from_pairing(guild_id, player2_id)

        assert opponent == player1_id

    def test_get_opponent_no_pairing(self):
        """Test getting opponent when user has no active pairing."""
        guild_id = 111111111

        opponent = get_opponent_from_pairing(guild_id, 999999999)

        assert opponent is None


class TestPairingValidation:
    """Test pairing validation for match reporting."""

    def test_validate_pairing_valid_player1_reports(self):
        """Test validating pairing when player 1 reports."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        is_valid = validate_pairing(guild_id, player1_id, player2_id)

        assert is_valid is True

    def test_validate_pairing_valid_player2_reports(self):
        """Test validating pairing when player 2 reports."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        is_valid = validate_pairing(guild_id, player2_id, player1_id)

        assert is_valid is True

    def test_validate_pairing_wrong_opponent(self):
        """Test that pairing is invalid with wrong opponent."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321
        wrong_player_id = 555555555

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        is_valid = validate_pairing(guild_id, player1_id, wrong_player_id)

        assert is_valid is False

    def test_validate_pairing_no_active_pairing(self):
        """Test validation fails when no active pairing exists."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        is_valid = validate_pairing(guild_id, player1_id, player2_id)

        assert is_valid is False

    def test_validate_pairing_different_guild(self):
        """Test that pairing validation is guild-specific."""
        guild1_id = 111111111
        guild2_id = 222222222
        player1_id = 123456789
        player2_id = 987654321

        # Save pairing in guild 1
        save_pairing(
            guild_id=guild1_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Try to validate in guild 2
        is_valid = validate_pairing(guild2_id, player1_id, player2_id)

        assert is_valid is False


class TestPairingReporting:
    """Test marking pairings as reported."""

    def test_mark_pairing_reported_success(self):
        """Test marking a pairing as reported."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Mark as reported
        success = mark_pairing_reported(guild_id, player1_id, player2_id)

        assert success is True

    def test_mark_pairing_reported_reverse_order(self):
        """Test marking pairing as reported with players in reverse order."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Mark as reported with players reversed
        success = mark_pairing_reported(guild_id, player2_id, player1_id)

        assert success is True

    def test_mark_nonexistent_pairing_reported(self):
        """Test marking a non-existent pairing as reported."""
        guild_id = 111111111

        success = mark_pairing_reported(guild_id, 999999999, 888888888)

        assert success is False

    def test_pairing_marked_reported_no_longer_active(self):
        """Test that marked pairings are no longer 'active'."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Mark as reported
        mark_pairing_reported(guild_id, player1_id, player2_id)

        # Try to validate as active - should fail
        pairing = get_active_pairing_for_user(guild_id, player1_id)
        assert pairing is None


class TestPairingEdgeCases:
    """Test edge cases in pairing operations."""

    def test_multiple_pairings_same_guild(self):
        """Test handling multiple pairings in same guild."""
        guild_id = 111111111

        # Save two pairings
        pairing1_id = save_pairing(
            guild_id=guild_id,
            player1_id=100,
            player2_id=101,
        )
        pairing2_id = save_pairing(
            guild_id=guild_id,
            player1_id=200,
            player2_id=201,
        )

        # Both should be retrievable
        pairing1 = get_active_pairing_for_user(guild_id, 100)
        pairing2 = get_active_pairing_for_user(guild_id, 200)

        assert pairing1 is not None
        assert pairing2 is not None
        assert pairing1["pairing_id"] != pairing2["pairing_id"]

    def test_deck_url_preservation(self):
        """Test that deck URLs are preserved correctly."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321
        deck1_url = "https://curiosa.io/deck/abc123?color=red"
        deck2_url = "https://curiosa.io/deck/xyz789?color=blue"

        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url=deck1_url,
            player2_deck_url=deck2_url,
        )

        pairing = get_active_pairing_for_user(guild_id, player1_id)

        assert pairing["player1_deck_url"] == deck1_url
        assert pairing["player2_deck_url"] == deck2_url

    def test_large_deck_url(self):
        """Test handling large deck URLs."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # Long deck URL
        long_url = "https://curiosa.io/decks/" + "x" * 1000

        pairing_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url=long_url,
        )

        assert pairing_id is not None

        pairing = get_active_pairing_for_user(guild_id, player1_id)
        assert pairing["player1_deck_url"] == long_url


class TestPairingIntegration:
    """Integration tests for complete pairing flows."""

    def test_match_flow_with_pairing(self):
        """Test complete match flow: save pairing → validate → mark reported."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321

        # 1. Match found - save pairing
        pairing_id = save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
            player1_deck_url="https://curiosa.io/deck1",
            player2_deck_url="https://curiosa.io/deck2",
        )
        assert pairing_id is not None

        # 2. Get opponent
        opponent = get_opponent_from_pairing(guild_id, player1_id)
        assert opponent == player2_id

        # 3. Player 1 reports result - validate pairing
        is_valid = validate_pairing(guild_id, player1_id, player2_id)
        assert is_valid is True

        # 4. Record the result
        # (In real code, winner_report would be called here)

        # 5. Mark pairing as reported
        success = mark_pairing_reported(guild_id, player1_id, player2_id)
        assert success is True

        # 6. Pairing no longer active
        pairing = get_active_pairing_for_user(guild_id, player1_id)
        assert pairing is None

    def test_prevent_false_match_report(self):
        """Test that false match reports are prevented."""
        guild_id = 111111111
        player1_id = 123456789
        player2_id = 987654321
        fake_player_id = 555555555

        # Save real pairing
        save_pairing(
            guild_id=guild_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # Try to report with fake opponent
        is_valid = validate_pairing(guild_id, player1_id, fake_player_id)
        assert is_valid is False

        # Real opponent should still be valid
        is_valid = validate_pairing(guild_id, player1_id, player2_id)
        assert is_valid is True

    def test_cross_guild_isolation(self):
        """Test that pairings are properly isolated by guild."""
        guild1_id = 111111111
        guild2_id = 222222222
        player1_id = 123456789
        player2_id = 987654321

        # Save pairing in guild 1
        save_pairing(
            guild_id=guild1_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )

        # In guild 2, players should have no pairing
        pairing_guild1 = get_active_pairing_for_user(guild1_id, player1_id)
        pairing_guild2 = get_active_pairing_for_user(guild2_id, player1_id)

        assert pairing_guild1 is not None
        assert pairing_guild2 is None
