"""Migration: Add season_id column to match_reports_web table.

This allows filtering matches by season on the stats page.
Existing records will have NULL season_id (non-season matches).

Run with: python migrations/add_season_id_to_match_reports_web.py
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH


def migrate():
    """Add season_id column to match_reports_web."""
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    print(f"Connecting to: {MATCH_RECORDS_DB_PATH}")

    # Check if table exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='match_reports_web'"
    )
    if not cur.fetchone():
        print("  match_reports_web table does not exist - skipping migration")
        conn.close()
        return

    # Add season_id column if not exists
    print("Adding season_id column...")
    try:
        cur.execute("ALTER TABLE match_reports_web ADD COLUMN season_id INTEGER DEFAULT NULL")
        print("  Column added")
    except sqlite3.OperationalError as e:
        print(f"  Note: {e} (likely already exists)")

    # Add index for season filtering
    print("Adding index on season_id...")
    try:
        cur.execute(
            "CREATE INDEX idx_match_reports_web_season_id ON match_reports_web(season_id)"
        )
        print("  Index added")
    except sqlite3.OperationalError as e:
        print(f"  Note: {e} (likely already exists)")

    conn.commit()

    # Verify the migration
    print("\nVerifying migration...")
    cur.execute("PRAGMA table_info(match_reports_web)")
    columns = [col[1] for col in cur.fetchall()]
    print(f"  season_id column exists: {'season_id' in columns}")

    conn.close()
    print("\nMigration complete!")
    print("Note: Existing records will have NULL season_id (non-season matches).")


if __name__ == "__main__":
    try:
        migrate()
        print("\n✅ Migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
