"""
Migration: Create explorer.db tables for the Explorer Standings feature.

Run with: python migrations/create_explorer_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import EXPLORER_DB_PATH

logger = logging.getLogger(__name__)


def create_explorer_tables():
    """Create all Explorer Standings tables if they don't exist."""
    conn = sqlite3.connect(str(EXPLORER_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            points_config TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL REFERENCES explorer_seasons(id),
            cardeio_event_id TEXT NOT NULL UNIQUE,
            cardeio_final_tournament_id TEXT,
            cardeio_swiss_phase_id TEXT NOT NULL,
            event_name TEXT NOT NULL,
            event_date TEXT,
            total_players INTEGER,
            play_format TEXT,
            venue_name TEXT,
            source_url TEXT,
            fetched_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES explorer_events(id),
            cardeio_user_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            final_standing INTEGER NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0,
            total_players INTEGER NOT NULL,
            image_url TEXT,
            team_name TEXT,
            UNIQUE(event_id, cardeio_user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_admins (
            discord_user_id TEXT PRIMARY KEY,
            display_name TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    logger.info("explorer tables ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    create_explorer_tables()
    logger.info("Migration completed.")
