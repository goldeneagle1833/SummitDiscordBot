"""Migration: Add season_id column to match_reports_web table.

This allows filtering matches by season on the stats page.
Existing records will have NULL season_id (non-season matches).

Run with: python migrations/add_season_id_to_match_reports_web.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)


def migrate():
    """Add season_id column to match_reports_web."""
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    logger.info("Connecting to: %s", MATCH_RECORDS_DB_PATH)

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='match_reports_web'"
    )
    if not cur.fetchone():
        logger.info("match_reports_web table does not exist - skipping migration")
        conn.close()
        return

    logger.info("Adding season_id column...")
    try:
        cur.execute("ALTER TABLE match_reports_web ADD COLUMN season_id INTEGER DEFAULT NULL")
        logger.info("Column added")
    except sqlite3.OperationalError as e:
        logger.info("Skipped season_id column: %s (likely already exists)", e)

    logger.info("Adding index on season_id...")
    try:
        cur.execute(
            "CREATE INDEX idx_match_reports_web_season_id ON match_reports_web(season_id)"
        )
        logger.info("Index added")
    except sqlite3.OperationalError as e:
        logger.info("Skipped season_id index: %s (likely already exists)", e)

    conn.commit()

    cur.execute("PRAGMA table_info(match_reports_web)")
    columns = [col[1] for col in cur.fetchall()]
    logger.info("season_id column exists: %s", "season_id" in columns)

    conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        migrate()
        logger.info("Migration completed successfully")
    except Exception:
        logger.exception("Migration failed")
        sys.exit(1)
