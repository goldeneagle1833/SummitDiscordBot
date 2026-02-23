"""
Test suite for match reporting functions.

These tests validate the core report features:
- winner_report
- losser_report
- solo_match_report

Run with: pytest tests/test_match_reports.py -v
"""

import pytest
import sqlite3
import os
import sys
import asyncio
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import (
    winner_report,
    losser_report,
    solo_match_report,
    create_db,
    update_elo_db,
)


# Test database path
TEST_DB_PATH = "test_match_records.db"
TEST_ELO_DB_PATH = "test_elo.db"


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Setup test database before each test and cleanup after."""
    # Setup: Remove any existing test databases
    for db_path in [TEST_DB_PATH, TEST_ELO_DB_PATH, "match_records.db", "elo.db"]:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass  # File may be locked from previous test

    # Create fresh test database
    create_db()

    # Create ELO database
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS overall_standings
                   (user_id INTEGER PRIMARY KEY, 
                    user_display_name TEXT,
                    elo INTEGER DEFAULT 1500)""")
    conn.commit()
    conn.close()

    yield  # Run the test

    # Teardown: Clean up test databases
    for db_path in [TEST_DB_PATH, TEST_ELO_DB_PATH, "match_records.db", "elo.db"]:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass  # File may be locked, ignore


class TestWinnerReport:
    """Tests for winner_report function."""

    @pytest.mark.asyncio
    async def test_winner_report_creates_record(self):
        """Test that winner_report creates a match record in the database."""
        # Mock scrape_Curosa to avoid network calls
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            result = await winner_report(
                reporter_id=123456789,
                user_id=111111111,
                user_display_name="Winner",
                did_win=True,
                opponent_id=222222222,
                opponent_display_name="Loser",
                first_player="y",
                match_time=30,
                curiosa_link="https://curiosa.io/test",
                match_comment="Test match",
                interaction_user_id=111111111,
                interaction_global="Winner",
            )

        # Verify return value: (match_id, winner_id, loser_id, event_active)
        match_id, winner_id, loser_id, event_active = result
        assert winner_id == 111111111
        assert loser_id == 222222222
        assert isinstance(match_id, int)

        # Verify database record
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM match_records WHERE winner_id = ?", (111111111,))
        row = cur.fetchone()
        conn.close()

        assert row is not None

    @pytest.mark.asyncio
    async def test_winner_report_updates_elo(self):
        """Test that winner_report updates ELO ratings when an event is active."""
        import datetime
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            await winner_report(
                reporter_id=123456789,
                user_id=111111111,
                user_display_name="Winner",
                did_win=True,
                opponent_id=222222222,
                opponent_display_name="Loser",
                first_player="n",
                match_time=25,
                curiosa_link="",
                match_comment="",
                interaction_user_id=111111111,
                interaction_global="Winner",
            )

        # Check ELO was updated
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT elo FROM overall_standings WHERE user_id = ?", (111111111,))
        row = cur.fetchone()
        conn.close()

        assert row is not None
        # Winner should have ELO > 1500 (default)
        assert row[0] > 1500

    @pytest.mark.asyncio
    async def test_winner_report_correct_parameter_count(self):
        """Test that winner_report accepts exactly 12 parameters."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            # This should NOT raise TypeError about argument count
            try:
                await winner_report(
                    123456789,  # reporter_id
                    111111111,  # user_id
                    "Winner",  # user_display_name
                    True,  # did_win
                    222222222,  # opponent_id
                    "Loser",  # opponent_display_name
                    "y",  # first_player
                    30,  # match_time
                    "",  # curiosa_link
                    "",  # match_comment
                    111111111,  # interaction_user_id
                    "Winner",  # interaction_global
                )
            except TypeError as e:
                if "positional arguments" in str(e):
                    pytest.fail(f"winner_report has wrong number of parameters: {e}")
                raise


class TestLosserReport:
    """Tests for losser_report function."""

    @pytest.mark.asyncio
    async def test_losser_report_creates_record(self):
        """Test that losser_report creates a match record in the database."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            result = await losser_report(
                reporter_id=123456789,
                user_id=111111111,
                user_display_name="Winner",
                did_win=False,
                opponent_id=222222222,
                opponent_display_name="Loser",
                first_player="n",
                match_time=45,
                curiosa_link="https://curiosa.io/test",
                match_comment="Test loss report",
                interaction_user_id=222222222,
                interaction_global="Loser",
            )

        # Verify return value: (match_id, winner_id, loser_id, event_active)
        match_id, winner_id, loser_id, event_active = result
        assert winner_id == 111111111
        assert loser_id == 222222222
        assert isinstance(match_id, int)

        # Verify database record
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT * FROM match_records WHERE winner_id = ?", (111111111,))
        row = cur.fetchone()
        conn.close()

        assert row is not None

    @pytest.mark.asyncio
    async def test_losser_report_correct_parameter_count(self):
        """Test that losser_report accepts exactly 12 parameters."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            try:
                await losser_report(
                    123456789,  # reporter_id
                    111111111,  # user_id
                    "Winner",  # user_display_name
                    False,  # did_win
                    222222222,  # opponent_id
                    "Loser",  # opponent_display_name
                    "n",  # first_player
                    30,  # match_time
                    "",  # curiosa_link
                    "",  # match_comment
                    222222222,  # interaction_user_id
                    "Loser",  # interaction_global
                )
            except TypeError as e:
                if "positional arguments" in str(e):
                    pytest.fail(f"losser_report has wrong number of parameters: {e}")
                raise


class TestSoloMatchReport:
    """Tests for solo_match_report function."""

    @pytest.mark.asyncio
    async def test_solo_match_report_creates_record(self):
        """Test that solo_match_report creates a record in the database."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            await solo_match_report(
                reporter_id=123456789,
                reporter_global="TestPlayer",
                opponent_name="OpponentName",
                is_winner=True,
                first_player="y",
                match_time=20,
                curiosa_link="https://curiosa.io/test",
                match_comment="Solo test match",
            )

        # Verify database record
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM solo_match_reports WHERE reporter_id = ?", (123456789,)
        )
        row = cur.fetchone()
        conn.close()

        assert row is not None
        # row[0] is the auto-increment ID, reporter_id starts at row[1]
        assert row[1] == 123456789  # reporter_id
        assert row[2] == "TestPlayer"  # reporter_name
        assert row[3] == "OpponentName"  # opponent_name
        assert row[4] == 1  # is_winner (True)

    @pytest.mark.asyncio
    async def test_solo_match_report_loss(self):
        """Test solo_match_report with a loss."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            await solo_match_report(
                reporter_id=987654321,
                reporter_global="LosingPlayer",
                opponent_name="WinningOpponent",
                is_winner=False,
                first_player="n",
                match_time=35,
                curiosa_link="",
                match_comment="I lost this one",
            )

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT is_winner FROM solo_match_reports WHERE reporter_id = ?",
            (987654321,),
        )
        row = cur.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 0  # is_winner (False)

    @pytest.mark.asyncio
    async def test_solo_match_report_correct_parameter_count(self):
        """Test that solo_match_report accepts exactly 8 parameters."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"):
            try:
                await solo_match_report(
                    reporter_id=123456789,
                    reporter_global="TestPlayer",
                    opponent_name="Opponent",
                    is_winner=True,
                    first_player="y",
                    match_time=30,
                    curiosa_link="",
                    match_comment="",
                )
            except TypeError as e:
                if "positional arguments" in str(e):
                    pytest.fail(
                        f"solo_match_report has wrong number of parameters: {e}"
                    )
                raise


class TestDatabaseIntegrity:
    """Tests for database integrity and schema."""

    def test_create_db_creates_tables(self):
        """Test that create_db creates required tables."""
        create_db()

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()

        # Check match_records table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        assert cur.fetchone() is not None

        # Check solo_match_reports table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='solo_match_reports'"
        )
        assert cur.fetchone() is not None

        conn.close()

    def test_match_records_schema(self):
        """Test that match_records table has correct columns."""
        create_db()

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(match_records)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()

        expected_columns = {
            "reporter_id",
            "winner_id",
            "winner_display_name",
            "losser_id",
            "losser_display_name",
            "did_win",
            "timestamp",
            "first_player",
            "match_time",
            "curiosa_url",
            "match_comment",
            "json_deck_data",
        }

        assert expected_columns.issubset(columns), (
            f"Missing columns: {expected_columns - columns}"
        )

    def test_solo_match_reports_schema(self):
        """Test that solo_match_reports table has correct columns."""
        create_db()

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(solo_match_reports)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()

        expected_columns = {
            "reporter_id",
            "reporter_name",
            "opponent_name",
            "is_winner",
            "first_player",
            "match_time",
            "curiosa_link",
            "match_comment",
            "report_date",
            "json_deck_data",
        }

        assert expected_columns.issubset(columns), (
            f"Missing columns: {expected_columns - columns}"
        )


class TestFunctionSignatures:
    """Tests to verify function signatures match expected parameters."""

    def test_winner_report_signature(self):
        """Verify winner_report has correct signature."""
        import inspect

        sig = inspect.signature(winner_report)
        params = list(sig.parameters.keys())

        expected_params = [
            "reporter_id",
            "user_id",
            "user_display_name",
            "did_win",
            "opponent_id",
            "opponent_display_name",
            "first_player",
            "match_time",
            "curiosa_link",
            "match_comment",
            "interaction_user_id",
            "interaction_global",
            "winner_deck_url",
            "loser_deck_url",
            "winner_went_first",
            "loser_went_first",
            "match_type",
        ]

        assert params == expected_params, f"Expected {expected_params}, got {params}"

    def test_losser_report_signature(self):
        """Verify losser_report has correct signature."""
        import inspect

        sig = inspect.signature(losser_report)
        params = list(sig.parameters.keys())

        expected_params = [
            "reporter_id",
            "user_id",
            "user_display_name",
            "did_win",
            "opponent_id",
            "opponent_display_name",
            "first_player",
            "match_time",
            "curiosa_link",
            "match_comment",
            "interaction_user_id",
            "interaction_global",
            "winner_deck_url",
            "loser_deck_url",
            "winner_went_first",
            "loser_went_first",
        ]

        assert params == expected_params, f"Expected {expected_params}, got {params}"

    def test_solo_match_report_signature(self):
        """Verify solo_match_report has correct signature."""
        import inspect

        sig = inspect.signature(solo_match_report)
        params = list(sig.parameters.keys())

        expected_params = [
            "reporter_id",
            "reporter_global",
            "opponent_name",
            "is_winner",
            "first_player",
            "match_time",
            "curiosa_link",
            "match_comment",
        ]

        assert params == expected_params, f"Expected {expected_params}, got {params}"
        assert len(params) == 8, (
            f"solo_match_report should have 8 params, has {len(params)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
