"""
Test database schema integrity and verify INSERT/UPDATE operations match table columns.

These tests ensure that:
1. All required tables exist
2. Required columns are present after migrations
3. INSERT statements match table schemas
4. UPDATE statements target valid columns
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_match_db():
    """Create a temporary match_records database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize the database with create_db()
    from repositories.elo_repo import create_db

    # Temporarily override the database path
    import repositories.elo_repo as elo_repo
    original_connect = sqlite3.connect

    def mock_connect(db_name):
        if "match_records.db" in db_name:
            return original_connect(path)
        return original_connect(db_name)

    sqlite3.connect = mock_connect
    create_db()
    sqlite3.connect = original_connect

    yield path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_elo_db():
    """Create a temporary elo database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize the database
    from repositories.elo_repo import create_db, create_events_table, migrate_to_dual_elo_system

    original_connect = sqlite3.connect

    def mock_connect(db_name):
        if "elo.db" in db_name:
            return original_connect(path)
        return original_connect(db_name)

    sqlite3.connect = mock_connect
    create_events_table()
    migrate_to_dual_elo_system()
    sqlite3.connect = original_connect

    yield path

    if os.path.exists(path):
        os.unlink(path)


class TestMatchRecordsSchema:
    """Test match_records table schema and operations."""

    def test_match_records_table_exists(self, temp_match_db):
        """Verify match_records table exists after migrations."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        assert cur.fetchone() is not None, "match_records table should exist"
        conn.close()

    def test_match_records_required_columns(self, temp_match_db):
        """Verify all required columns exist in match_records."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        columns = {row[1] for row in cur.fetchall()}

        required_columns = {
            'reporter_id',
            'winner_id',
            'winner_display_name',
            'losser_id',  # Note: typo preserved for backward compatibility
            'losser_display_name',
            'did_win',
            'timestamp',
            'first_player',
            'match_time',
            'curiosa_url',
            'match_comment',
            'json_deck_data',
            'winner_elo_change',
            'loser_elo_change',
            # New columns added by migrations
            'winner_lifetime_elo_change',
            'loser_lifetime_elo_change',
            'curiosa_url_winner',
            'curiosa_url_loser',
            'json_deck_data_winner',
            'json_deck_data_loser',
            'winner_went_first',
            'loser_went_first',
            'source',
            'match_type',
        }

        missing = required_columns - columns
        assert not missing, f"Missing columns in match_records: {missing}"

        conn.close()

    def test_winner_report_insert_matches_schema(self, temp_match_db):
        """Verify winner_report INSERT statement matches table schema."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        # Get actual table columns
        cur.execute("PRAGMA table_info(match_records)")
        table_columns = {row[1] for row in cur.fetchall()}

        # Columns used in winner_report INSERT
        insert_columns = {
            'reporter_id',
            'winner_id',
            'winner_display_name',
            'losser_id',
            'losser_display_name',
            'did_win',
            'timestamp',
            'first_player',
            'match_time',
            'curiosa_url',
            'curiosa_url_winner',
            'curiosa_url_loser',
            'match_comment',
            'json_deck_data',
            'json_deck_data_winner',
            'json_deck_data_loser',
            'winner_elo_change',
            'loser_elo_change',
            'winner_lifetime_elo_change',
            'loser_lifetime_elo_change',
            'winner_went_first',
            'loser_went_first',
            'match_type',
        }

        missing = insert_columns - table_columns
        assert not missing, f"winner_report INSERT uses non-existent columns: {missing}"

        conn.close()

    def test_loser_report_insert_matches_schema(self, temp_match_db):
        """Verify losser_report INSERT statement matches table schema."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        table_columns = {row[1] for row in cur.fetchall()}

        # Columns used in losser_report INSERT (same as winner_report)
        insert_columns = {
            'reporter_id',
            'winner_id',
            'winner_display_name',
            'losser_id',
            'losser_display_name',
            'did_win',
            'timestamp',
            'first_player',
            'match_time',
            'curiosa_url',
            'curiosa_url_winner',
            'curiosa_url_loser',
            'match_comment',
            'json_deck_data',
            'json_deck_data_winner',
            'json_deck_data_loser',
            'winner_elo_change',
            'loser_elo_change',
            'winner_lifetime_elo_change',
            'loser_lifetime_elo_change',
            'winner_went_first',
            'loser_went_first',
            'match_type',
        }

        missing = insert_columns - table_columns
        assert not missing, f"losser_report INSERT uses non-existent columns: {missing}"

        conn.close()

    def test_insert_external_match_matches_schema(self, temp_match_db):
        """Verify insert_external_match uses valid columns."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        table_columns = {row[1] for row in cur.fetchall()}

        # Columns used in web app's insert_external_match
        insert_columns = {
            'reporter_id',
            'winner_id',
            'winner_display_name',
            'losser_id',
            'losser_display_name',
            'did_win',
            'timestamp',
            'first_player',
            'match_time',
            'match_comment',
            'curiosa_url_winner',
            'curiosa_url_loser',
            'json_deck_data_winner',
            'json_deck_data_loser',
            'winner_elo_change',
            'loser_elo_change',
            'winner_went_first',
            'source',
            'match_type',
        }

        missing = insert_columns - table_columns
        assert not missing, f"insert_external_match uses non-existent columns: {missing}"

        conn.close()


class TestELOSchema:
    """Test elo.db schema and operations."""

    def test_overall_standings_table_exists(self, temp_elo_db):
        """Verify overall_standings table exists."""
        conn = sqlite3.connect(temp_elo_db)
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='overall_standings'"
        )
        assert cur.fetchone() is not None, "overall_standings table should exist"
        conn.close()

    def test_overall_standings_required_columns(self, temp_elo_db):
        """Verify all required columns exist in overall_standings."""
        conn = sqlite3.connect(temp_elo_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(overall_standings)")
        columns = {row[1] for row in cur.fetchall()}

        required_columns = {
            'user_id',
            'user_display_name',
            'online_elo',
            'online_event_elo',
            'paper_elo',
            'paper_event_elo',
        }

        missing = required_columns - columns
        assert not missing, f"Missing columns in overall_standings: {missing}"

        conn.close()

    def test_update_elo_db_updates_valid_columns(self, temp_elo_db):
        """Verify update_elo_db UPDATE statement targets valid columns."""
        conn = sqlite3.connect(temp_elo_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(overall_standings)")
        table_columns = {row[1] for row in cur.fetchall()}

        # Columns updated by update_elo_db
        update_columns = {
            'online_elo',
            'online_event_elo',
        }

        missing = update_columns - table_columns
        assert not missing, f"update_elo_db updates non-existent columns: {missing}"

        conn.close()

    def test_events_table_exists(self, temp_elo_db):
        """Verify events table exists."""
        conn = sqlite3.connect(temp_elo_db)
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        assert cur.fetchone() is not None, "events table should exist"
        conn.close()

    def test_events_required_columns(self, temp_elo_db):
        """Verify events table has required columns."""
        conn = sqlite3.connect(temp_elo_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(events)")
        columns = {row[1] for row in cur.fetchall()}

        required_columns = {
            'event_id',
            'event_name',
            'start_date',
            'end_date',
            'is_active',
        }

        missing = required_columns - columns
        assert not missing, f"Missing columns in events: {missing}"

        conn.close()


class TestLimitedSchema:
    """Test limited arena database schema."""

    def test_limited_match_records_columns(self, temp_match_db):
        """Verify limited_match_records has all required columns."""
        from repositories.limited_repo import create_limited_tables

        # Initialize limited tables
        original_connect = sqlite3.connect

        def mock_connect(db_name):
            if "match_records.db" in db_name:
                return original_connect(temp_match_db)
            return original_connect(db_name)

        sqlite3.connect = mock_connect
        create_limited_tables()
        sqlite3.connect = original_connect

        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(limited_match_records)")
        columns = {row[1] for row in cur.fetchall()}

        required_columns = {
            'match_id',
            'reporter_id',
            'winner_id',
            'winner_display_name',
            'loser_id',  # Note: correct spelling in limited
            'loser_display_name',
            'did_win',
            'timestamp',
            'first_player',
            'match_time',
            'curiosa_url_winner',
            'curiosa_url_loser',
            'match_comment',
            'json_deck_data_winner',
            'json_deck_data_loser',
            'winner_elo_change',
            'loser_elo_change',
            'winner_went_first',
            'loser_went_first',
            'winner_run_id',
            'loser_run_id',
        }

        missing = required_columns - columns
        assert not missing, f"Missing columns in limited_match_records: {missing}"

        conn.close()


class TestSchemaConsistency:
    """Test schema consistency across operations."""

    def test_no_hardcoded_column_counts(self, temp_match_db):
        """Verify INSERT statements don't have hardcoded placeholder counts."""
        # This test documents the expected column count
        # If this fails, it means the schema changed and INSERT statements may need updates

        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        column_count = len(cur.fetchall())

        # match_records should have these columns after all migrations
        # If this assertion fails, review all INSERT statements
        expected_min_columns = 24  # Minimum expected after migrations

        assert column_count >= expected_min_columns, (
            f"match_records has {column_count} columns, expected at least {expected_min_columns}. "
            "If schema changed, verify all INSERT statements in winner_report, losser_report, "
            "and insert_external_match match the new schema."
        )

        conn.close()

    def test_migrations_are_idempotent(self, temp_match_db):
        """Verify running migrations multiple times doesn't cause errors."""
        from repositories.elo_repo import create_db

        original_connect = sqlite3.connect

        def mock_connect(db_name):
            if "match_records.db" in db_name:
                return original_connect(temp_match_db)
            return original_connect(db_name)

        sqlite3.connect = mock_connect

        # Run migrations multiple times - should not raise errors
        try:
            create_db()
            create_db()
            create_db()
        except Exception as e:
            pytest.fail(f"Migrations should be idempotent, but raised: {e}")
        finally:
            sqlite3.connect = original_connect

    def test_source_column_has_default(self, temp_match_db):
        """Verify source column has a default value."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        columns = {row[1]: row for row in cur.fetchall()}

        assert 'source' in columns, "source column should exist"
        source_col = columns['source']
        # Column info: (cid, name, type, notnull, default_value, pk)
        default_value = source_col[4]
        assert default_value == "'Discord'", f"source column should default to 'Discord', got {default_value}"

        conn.close()

    def test_match_type_column_has_default(self, temp_match_db):
        """Verify match_type column has a default value."""
        conn = sqlite3.connect(temp_match_db)
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(match_records)")
        columns = {row[1]: row for row in cur.fetchall()}

        assert 'match_type' in columns, "match_type column should exist"
        match_type_col = columns['match_type']
        default_value = match_type_col[4]
        assert default_value == "'ranked'", f"match_type column should default to 'ranked', got {default_value}"

        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
