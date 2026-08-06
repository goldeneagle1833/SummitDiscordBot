"""
Test suite for match reporting functions.

These tests validate the core report features:
- record_match
- solo_match_report

Run with: pytest tests/test_match_reports.py -v
"""

import pytest
import sqlite3
import os
import sys
import asyncio
import datetime
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import (
    record_match,
    solo_match_report,
    create_db,
    get_event_match_count,
    get_event_participant_ids,
    get_player_event_match_count,
    get_current_event_match_elo_snapshot,
)
from repositories.audit_repo import log_admin_action
import repositories.elo_repo as elo_repo


# Test database path
TEST_DB_PATH = "test_match_records.db"
TEST_ELO_DB_PATH = "test_elo.db"


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Setup test database before each test and cleanup after."""
    elo_repo._dual_elo_migrated = False
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
                     online_elo INTEGER DEFAULT 1500,
                     online_event_elo INTEGER DEFAULT 1500,
                     paper_elo INTEGER DEFAULT 1500,
                     paper_event_elo INTEGER DEFAULT 1500)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS events (
                   event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   event_name TEXT NOT NULL,
                   start_date TEXT NOT NULL,
                   end_date TEXT,
                   is_active BOOLEAN DEFAULT 1)""")
    conn.commit()
    conn.close()

    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ladder_challenges (
                   challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   challenger_id INTEGER NOT NULL,
                   challenged_id INTEGER NOT NULL,
                   challenger_rank INTEGER,
                   challenged_rank INTEGER,
                   stakes_multiplier TEXT DEFAULT 'Normal',
                   status TEXT DEFAULT 'pending',
                   created_at TEXT NOT NULL,
                   expires_at TEXT NOT NULL,
                   responded_at TEXT,
                   accepted_at TEXT,
                   completed_at TEXT,
                   winner_id INTEGER,
                   match_id INTEGER,
                   guild_id INTEGER)""")
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


class TestRecordMatch:
    """Tests for record_match function."""

    @pytest.mark.asyncio
    async def test_record_match_creates_record(self):
        """Test that record_match creates a match record in the database."""
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=None):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="y",
                match_time=30,
                match_comment="Test match",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="y",
                loser_went_first="n",
            )

        # Verify return value: (match_id, winner_elo_change, loser_elo_change,
        #                        winner_lifetime_change, loser_lifetime_change, event_active)
        match_id, winner_elo_change, loser_elo_change, winner_lt, loser_lt, event_active = result
        assert isinstance(match_id, int)
        assert winner_elo_change == 0  # no active event
        assert loser_elo_change == 0

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT winner_id, losser_id FROM match_records WHERE match_id = ?", (match_id,))
        row = cur.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 111111111
        assert row[1] == 222222222

    @pytest.mark.asyncio
    async def test_record_match_updates_both_player_elos(self):
        """Test that record_match updates both players' ELO atomically when an event is active."""
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )

        match_id, winner_elo_change, loser_elo_change, winner_lt, loser_lt, event_active = result
        assert event_active is True
        assert winner_elo_change > 0
        assert loser_elo_change < 0

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT online_elo FROM overall_standings WHERE user_id = ?", (111111111,))
        winner_row = cur.fetchone()
        cur.execute("SELECT online_elo FROM overall_standings WHERE user_id = ?", (222222222,))
        loser_row = cur.fetchone()
        conn.close()

        assert winner_row is not None and winner_row[0] > 1500
        assert loser_row is not None and loser_row[0] < 1500

    @pytest.mark.asyncio
    async def test_record_match_testing_type_skips_elo(self):
        """Test that match_type='testing' inserts a record but skips ELO updates."""
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=20,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
                match_type="testing",
            )

        match_id, winner_elo_change, loser_elo_change, winner_lt, loser_lt, event_active = result
        assert event_active is False
        assert winner_elo_change == 0
        assert loser_elo_change == 0

        # No ELO row should exist since nothing was written
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM overall_standings WHERE user_id = ?", (111111111,))
        assert cur.fetchone() is None
        conn.close()

    @pytest.mark.asyncio
    async def test_record_match_points_type_skips_elo(self):
        """Test that match_type='points' (Omens) inserts a record but skips ELO updates."""
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=20,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
                match_type="points",
            )

        match_id, winner_elo_change, loser_elo_change, winner_lt, loser_lt, event_active = result
        assert match_id is not None
        assert event_active is False
        assert winner_elo_change == 0
        assert loser_elo_change == 0
        assert winner_lt == 0
        assert loser_lt == 0

        # No ELO row should exist since nothing was written
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM overall_standings WHERE user_id = ?", (111111111,))
        assert cur.fetchone() is None
        conn.close()

        # Match record should still be inserted
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT match_type, winner_elo_change, loser_elo_change, "
            "winner_lifetime_elo_change, loser_lifetime_elo_change "
            "FROM match_records WHERE rowid = ?",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "points"
        assert row[1] == 0
        assert row[2] == 0
        assert row[3] == 0
        assert row[4] == 0

    @pytest.mark.asyncio
    async def test_record_match_stored_elo_changes_are_accurate(self):
        """Test that stored winner/loser ELO changes match what record_match returns.

        Uses unequal starting ELOs so the sequential calculation produces asymmetric
        changes (loser_change != -winner_change), proving values aren't approximated.
        """
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }

        # Pre-seed the winner at a higher ELO so changes are asymmetric
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO overall_standings "
            "(user_id, user_display_name, online_elo, online_event_elo) "
            "VALUES (?, ?, ?, ?)",
            (111111111, "Winner", 1600, 1600),
        )
        cur.execute(
            "INSERT OR IGNORE INTO overall_standings "
            "(user_id, user_display_name, online_elo, online_event_elo) "
            "VALUES (?, ?, ?, ?)",
            (222222222, "Loser", 1400, 1400),
        )
        conn.commit()
        conn.close()

        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )

        match_id, winner_elo_change, loser_elo_change, winner_lt, loser_lt, event_active = result

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT winner_elo_change, loser_elo_change FROM match_records WHERE match_id = ?",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()

        assert row is not None
        # Stored values must exactly match what record_match returned
        assert row[0] == winner_elo_change
        assert row[1] == loser_elo_change

        # Verify the loser's actual ELO in the DB reflects the correct change
        # (previously the loser ELO was updated by a separate call; now it's atomic)
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute("SELECT online_event_elo FROM overall_standings WHERE user_id = ?", (222222222,))
        loser_db_row = cur.fetchone()
        conn.close()

        assert loser_db_row is not None
        assert loser_db_row[0] == 1400 + loser_elo_change

    def test_event_match_counts_include_only_elo_counting_matches(self):
        """Season leaderboard counts should match games that affected event ELO."""
        event_start = datetime.datetime.now()
        before_event = (event_start - datetime.timedelta(days=1)).isoformat()
        after_event = (event_start + datetime.timedelta(minutes=1)).isoformat()
        event_start_str = event_start.isoformat()

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        rows = [
            (1, 101, 201, before_event, 16, -16, "ranked"),
            (2, 101, 202, after_event, 16, -16, "ranked"),
            (3, 101, 203, after_event, 0, 0, "testing"),
            (4, 101, 204, after_event, 0, 0, "ranked"),
            (5, 105, 101, after_event, None, None, "ranked"),
        ]
        cur.executemany(
            """
            INSERT INTO match_records
            (reporter_id, winner_id, winner_display_name, losser_id, losser_display_name,
             did_win, timestamp, first_player, match_time, curiosa_url, match_comment,
             json_deck_data, winner_elo_change, loser_elo_change, match_type)
            VALUES (?, ?, 'Winner', ?, 'Loser', 1, ?, 'n', 0, NULL, '', '{}', ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()

        assert get_event_match_count(event_start_str) == 2
        assert get_player_event_match_count(101, event_start_str) == 2
        assert get_player_event_match_count(202, event_start_str) == 1
        assert get_player_event_match_count(203, event_start_str) == 0
        assert get_player_event_match_count(204, event_start_str) == 0
        assert get_event_participant_ids(event_start_str) == {101, 105, 202}


class TestMatchEloSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_returns_before_after_for_ranked_match(self):
        elo_repo._dual_elo_migrated = False
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }

        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )
            match_id = result[0]
            assert match_id is not None

            snapshot = get_current_event_match_elo_snapshot(match_id)

        assert snapshot["winner"]["lifetime_before"] == 1500
        assert snapshot["winner"]["lifetime_after"] > 1500
        assert snapshot["loser"]["lifetime_before"] == 1500
        assert snapshot["loser"]["lifetime_after"] < 1500
        assert snapshot["winner"]["event_before"] == 1500
        assert snapshot["winner"]["event_after"] > 1500
        assert snapshot["loser"]["event_before"] == 1500
        assert snapshot["loser"]["event_after"] < 1500

    @pytest.mark.asyncio
    async def test_snapshot_works_without_ladder_table(self):
        elo_repo._dual_elo_migrated = False
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS ladder_challenges")
        conn.commit()
        conn.close()

        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )
            match_id = result[0]
            assert match_id is not None

            snapshot = get_current_event_match_elo_snapshot(match_id)

        assert snapshot["winner"]["event_before"] == 1500
        assert snapshot["winner"]["lifetime_before"] == 1500

    @pytest.mark.asyncio
    async def test_snapshot_accounts_for_spot_reset_before_match(self):
        elo_repo._dual_elo_migrated = False
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }

        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )

            log_admin_action(
                999,
                "Admin",
                "spot_elo_reset",
                target_id=111111111,
                target_name="Winner",
                previous_state={"event_elo": 1508},
                new_state={"event_elo": 1600},
            )

            conn = sqlite3.connect("elo.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE overall_standings SET online_event_elo = 1600 WHERE user_id = ?",
                (111111111,),
            )
            conn.commit()
            conn.close()

            second_result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
            )
            second_match_id = second_result[0]
            assert second_match_id is not None

            snapshot = get_current_event_match_elo_snapshot(second_match_id)

        assert snapshot["winner"]["event_before"] == 1600
        assert snapshot["winner"]["event_after"] > 1600
        assert any("manual event Elo reset" in note for note in snapshot["notes"])

    @pytest.mark.asyncio
    async def test_snapshot_marks_top_cut_lifetime_unavailable(self):
        elo_repo._dual_elo_migrated = False
        fake_event = {
            "event_name": "Test Event",
            "start_date": datetime.datetime.now() - datetime.timedelta(days=1),
        }

        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=fake_event):
            result = await record_match(
                reporter_id=123456789,
                winner_id=111111111,
                winner_global="Winner",
                loser_id=222222222,
                loser_global="Loser",
                first_player="n",
                match_time=25,
                match_comment="",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first="n",
                loser_went_first="y",
                match_type="testing",
            )
            match_id = result[0]
            assert match_id is not None
            conn = sqlite3.connect("elo.db")
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO overall_standings "
                "(user_id, user_display_name, online_elo, online_event_elo) "
                "VALUES (?, ?, ?, ?)",
                (111111111, "Winner", 1516, 1500),
            )
            cur.execute(
                "INSERT OR IGNORE INTO overall_standings "
                "(user_id, user_display_name, online_elo, online_event_elo) "
                "VALUES (?, ?, ?, ?)",
                (222222222, "Loser", 1485, 1500),
            )
            conn.commit()
            conn.close()
            log_admin_action(
                999,
                "Admin",
                "top_cut_report",
                target_id=111111111,
                target_name="Winner",
                previous_state={"winner_id": 111111111, "loser_id": 222222222},
                new_state={"match_id": match_id, "lifetime_only": True},
            )

            snapshot = get_current_event_match_elo_snapshot(match_id)

        assert snapshot["winner"]["lifetime_before"] is None
        assert snapshot["loser"]["lifetime_before"] is None
        assert any("Lifetime Elo unavailable" in note for note in snapshot["notes"])




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

    def test_record_match_signature(self):
        """Verify record_match has correct signature."""
        import inspect

        sig = inspect.signature(record_match)
        params = list(sig.parameters.keys())

        expected_params = [
            "reporter_id",
            "winner_id",
            "winner_global",
            "loser_id",
            "loser_global",
            "first_player",
            "match_time",
            "match_comment",
            "winner_deck_url",
            "loser_deck_url",
            "winner_went_first",
            "loser_went_first",
            "match_type",
            "elo_multiplier_winner",
            "elo_multiplier_loser",
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
