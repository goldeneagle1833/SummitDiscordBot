"""
Migration: Create external_matches table for 3rd-party match reports.

External matches are stored separately from bot-reported matches and have
no ELO impact.  They are included in the overall stats pool (win/loss
counts, match history) but do not touch overall_standings.

Run with: python migrations/create_external_matches_table.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)


def create_external_matches_table():
    """Create external_matches table if it doesn't exist."""
    logger.info("Ensuring external_matches table in: %s", MATCH_RECORDS_DB_PATH)
    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS external_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner_id TEXT NOT NULL,
            loser_id TEXT NOT NULL,
            winner_display_name TEXT,
            loser_display_name TEXT,
            winner_deck_url TEXT,
            loser_deck_url TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            winner_went_first TEXT,
            match_time INTEGER,
            match_comment TEXT,
            source TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    logger.info("external_matches table ready.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_external_matches_table()
