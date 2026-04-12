"""Tests for the Resend Last Match button functionality."""

import pytest
import sqlite3
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.lfg.queue import get_last_unreported_pairing
from repositories.elo_repo import save_pairing, create_active_pairings_table
from repositories.limited_repo import save_limited_pairing, create_limited_tables


@pytest.fixture
def setup_databases():
    """Set up test databases with correct schema."""
    # Create active_pairings table
    create_active_pairings_table()

    # Create limited tables
    create_limited_tables()

    yield

    # Cleanup
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM active_pairings")
    cur.execute("DELETE FROM limited_active_pairings")
    conn.commit()
    conn.close()


def test_get_last_unreported_pairing_regular_match(setup_databases):
    """Test getting last unreported regular pairing."""
    guild_id = 123456789
    player1_id = 111111
    player2_id = 222222

    # Save a pairing
    pairing_id = save_pairing(
        guild_id=guild_id,
        player1_id=player1_id,
        player2_id=player2_id,
        player1_deck_url="https://curiosa.io/decks/test1",
        player2_deck_url="https://curiosa.io/decks/test2",
    )

    # Get the pairing for player1
    result = get_last_unreported_pairing(player1_id, guild_id)

    assert result is not None
    assert result['pairing_id'] == pairing_id
    assert result['player1_id'] == player1_id
    assert result['player2_id'] == player2_id
    assert result['player1_deck_url'] == "https://curiosa.io/decks/test1"
    assert result['player2_deck_url'] == "https://curiosa.io/decks/test2"
    assert result['status'] == 'active'

    # Get the pairing for player2
    result = get_last_unreported_pairing(player2_id, guild_id)

    assert result is not None
    assert result['pairing_id'] == pairing_id


def test_get_last_unreported_pairing_limited_match(setup_databases):
    """Test getting last unreported limited pairing."""
    guild_id = 123456789
    player1_id = 111111
    player2_id = 222222

    # Save a limited pairing
    pairing_id = save_limited_pairing(
        guild_id=guild_id,
        player1_id=player1_id,
        player2_id=player2_id,
        player1_deck_url="https://curiosa.io/decks/limited1",
        player2_deck_url="https://curiosa.io/decks/limited2",
        player1_run_id=1001,
        player2_run_id=1002,
    )

    # Get the pairing
    result = get_last_unreported_pairing(player1_id, guild_id)

    assert result is not None
    assert result['pairing_id'] == pairing_id
    assert result['player1_id'] == player1_id
    assert result['player2_id'] == player2_id
    assert result['match_type'] == 'limited'
    assert result['player1_run_id'] == 1001
    assert result['player2_run_id'] == 1002


def test_get_last_unreported_pairing_no_matches(setup_databases):
    """Test getting pairing when there are no unreported matches."""
    guild_id = 123456789
    player_id = 111111

    result = get_last_unreported_pairing(player_id, guild_id)

    assert result is None


def test_get_last_unreported_pairing_only_reported_matches(setup_databases):
    """Test getting pairing when all matches are already reported."""
    guild_id = 123456789
    player1_id = 111111
    player2_id = 222222

    # Save a pairing
    save_pairing(
        guild_id=guild_id,
        player1_id=player1_id,
        player2_id=player2_id,
    )

    # Mark it as reported
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE active_pairings SET status = 'reported' WHERE player1_id = ? AND player2_id = ?",
        (player1_id, player2_id)
    )
    conn.commit()
    conn.close()

    # Should not find any unreported pairings
    result = get_last_unreported_pairing(player1_id, guild_id)

    assert result is None


def test_get_last_unreported_pairing_multiple_guilds(setup_databases):
    """Test that pairings are correctly filtered by guild_id."""
    guild1_id = 111111
    guild2_id = 222222
    player_id = 333333
    opponent_id = 444444

    # Save pairing in guild1
    pairing1_id = save_pairing(
        guild_id=guild1_id,
        player1_id=player_id,
        player2_id=opponent_id,
    )

    # Save pairing in guild2
    pairing2_id = save_pairing(
        guild_id=guild2_id,
        player1_id=player_id,
        player2_id=555555,
    )

    # Get pairing for guild1
    result = get_last_unreported_pairing(player_id, guild1_id)
    assert result is not None
    assert result['pairing_id'] == pairing1_id
    assert result['guild_id'] == guild1_id

    # Get pairing for guild2
    result = get_last_unreported_pairing(player_id, guild2_id)
    assert result is not None
    assert result['pairing_id'] == pairing2_id
    assert result['guild_id'] == guild2_id


def test_get_last_unreported_pairing_prefers_regular_over_limited(setup_databases):
    """Test that regular pairings are checked before limited pairings."""
    guild_id = 123456789
    player_id = 111111

    # Save a limited pairing (older)
    limited_pairing_id = save_limited_pairing(
        guild_id=guild_id,
        player1_id=player_id,
        player2_id=222222,
        player1_deck_url="https://curiosa.io/decks/limited",
        player2_deck_url="https://curiosa.io/decks/limited2",
        player1_run_id=1001,
        player2_run_id=1002,
    )

    # Save a regular pairing (newer)
    regular_pairing_id = save_pairing(
        guild_id=guild_id,
        player1_id=player_id,
        player2_id=333333,
    )

    # Should get the regular pairing (checked first in the function)
    result = get_last_unreported_pairing(player_id, guild_id)

    assert result is not None
    assert result['pairing_id'] == regular_pairing_id
    assert 'match_type' not in result  # Regular pairings don't have match_type set


def test_get_last_unreported_pairing_gets_most_recent(setup_databases):
    """Test that the most recent unreported pairing is returned."""
    guild_id = 123456789
    player_id = 111111

    # Save older pairing
    save_pairing(
        guild_id=guild_id,
        player1_id=player_id,
        player2_id=222222,
    )

    # Save newer pairing
    newer_pairing_id = save_pairing(
        guild_id=guild_id,
        player1_id=player_id,
        player2_id=333333,
    )

    # Should get the newer pairing
    result = get_last_unreported_pairing(player_id, guild_id)

    assert result is not None
    assert result['pairing_id'] == newer_pairing_id
    assert result['player2_id'] == 333333
