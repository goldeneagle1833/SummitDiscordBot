"""Add winner_lifetime_elo_after / loser_lifetime_elo_after columns.

These columns store the absolute lifetime ELO after each match, making it
possible to render an accurate ELO history graph without reconstruction.
Runs on both match_reports_web and the bot's match_records / archive tables
(which the web app reads for the player profile graph).
"""
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

_TABLES = ["match_reports_web", "match_records", "match_records_archive"]
_COLUMNS = ["winner_lifetime_elo_after", "loser_lifetime_elo_after"]


def migrate():
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    for table in _TABLES:
        # Check if table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            continue

        for col in _COLUMNS:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER")
                logger.info("Added %s to %s", col, table)
            except sqlite3.OperationalError:
                pass  # Column already exists

    conn.commit()
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
