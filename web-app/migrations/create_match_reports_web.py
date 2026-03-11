"""
Migration: Create match_reports_web table for web-based match reports.

This table is identical to match_records but uses TEXT for all ID fields
to support Google OAuth IDs (which exceed SQLite's 64-bit INTEGER limit).

Web-based match reports will be stored here with full "google_" prefixed IDs,
while Discord bot reports continue using match_records with numeric IDs.

Run with: python migrations/create_match_reports_web.py
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH


def create_match_reports_web_table():
    """Create match_reports_web table if it doesn't exist."""

    print(f"Connecting to: {MATCH_RECORDS_DB_PATH}")
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cursor = conn.cursor()

    # Check if table already exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='match_reports_web'"
    )

    if cursor.fetchone():
        print("✓ Table match_reports_web already exists, skipping creation")
        conn.close()
        return

    print("Creating match_reports_web table...")

    # Create table with TEXT columns for all IDs to support Google OAuth
    cursor.execute("""
        CREATE TABLE match_reports_web (
            -- Match identification
            match_id TEXT PRIMARY KEY,

            -- Player IDs (TEXT to support google_ prefixed IDs)
            reporter_id TEXT,
            winner_id TEXT NOT NULL,
            losser_id TEXT NOT NULL,

            -- Player display names
            winner_display_name TEXT NOT NULL,
            losser_display_name TEXT NOT NULL,

            -- Match outcome
            did_win INTEGER NOT NULL,
            timestamp TEXT NOT NULL,

            -- Match details
            first_player TEXT,
            match_time INTEGER,
            match_comment TEXT,

            -- Deck URLs
            curiosa_url TEXT,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,

            -- Deck data (JSON)
            json_deck_data TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,

            -- ELO changes
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,

            -- Turn order tracking
            winner_went_first TEXT,
            loser_went_first TEXT,

            -- Match categorization
            source TEXT DEFAULT 'Web',
            match_type TEXT DEFAULT 'ranked'
        )
    """)

    # Create indexes for common queries
    cursor.execute("""
        CREATE INDEX idx_match_reports_web_winner
        ON match_reports_web(winner_id)
    """)

    cursor.execute("""
        CREATE INDEX idx_match_reports_web_loser
        ON match_reports_web(losser_id)
    """)

    cursor.execute("""
        CREATE INDEX idx_match_reports_web_timestamp
        ON match_reports_web(timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX idx_match_reports_web_source
        ON match_reports_web(source)
    """)

    conn.commit()
    conn.close()

    print("✓ Successfully created match_reports_web table with indexes")
    print("✓ Web-based match reports will now use this table")


if __name__ == "__main__":
    try:
        create_match_reports_web_table()
        print("\n✅ Migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
