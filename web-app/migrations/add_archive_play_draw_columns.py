"""Migration: Add winner_went_first and loser_went_first columns to match_records_archive.

This migration adds columns to store play/draw data for future archived matches.
Old records will continue using first_player via COALESCE fallback in queries.

Date: 2026-03-17
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH


def migrate():
    """Add winner_went_first/loser_went_first columns to archive (no backfill)."""
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    print("Checking if match_records_archive exists...")
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records_archive'"
    )
    if not cur.fetchone():
        print("  Archive table does not exist - skipping migration")
        conn.close()
        return

    # Add winner_went_first column if not exists
    print("Adding winner_went_first column...")
    try:
        cur.execute("ALTER TABLE match_records_archive ADD COLUMN winner_went_first TEXT")
        print("  Column added")
    except sqlite3.OperationalError as e:
        print(f"  Note: {e} (likely already exists)")

    # Add loser_went_first column if not exists
    print("Adding loser_went_first column...")
    try:
        cur.execute("ALTER TABLE match_records_archive ADD COLUMN loser_went_first TEXT")
        print("  Column added")
    except sqlite3.OperationalError as e:
        print(f"  Note: {e} (likely already exists)")

    conn.commit()

    # Verify the migration
    print("\nVerifying migration...")
    cur.execute("PRAGMA table_info(match_records_archive)")
    columns = [col[1] for col in cur.fetchall()]
    print(f"  winner_went_first column exists: {'winner_went_first' in columns}")
    print(f"  loser_went_first column exists: {'loser_went_first' in columns}")

    conn.close()
    print("\nMigration complete!")
    print("Note: Existing records will remain NULL and use first_player fallback.")
    print("      New archived matches will populate these columns automatically.")


def rollback():
    """Remove winner_went_first and loser_went_first columns (not supported in SQLite)."""
    print("SQLite does not support DROP COLUMN.")
    print("To rollback, you would need to recreate the table without these columns.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        migrate()
