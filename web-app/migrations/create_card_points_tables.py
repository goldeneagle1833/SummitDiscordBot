"""
Migration: Create card_points and points_config tables in elo.db.

These tables support the points-based deck restriction system where admins
assign point values to cards and set a maximum budget for decks.

Run with: python migrations/create_card_points_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import ELO_DB_PATH

logger = logging.getLogger(__name__)


def create_card_points_tables():
    """Create card_points and points_config tables if they don't exist."""
    conn = sqlite3.connect(str(ELO_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            point_value INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS points_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_points_admins (
            discord_user_id TEXT PRIMARY KEY,
            display_name TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_points_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            card_name TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        )
    """)

    # Set default max budget if not exists
    cursor.execute("""
        INSERT OR IGNORE INTO points_config (key, value) VALUES ('max_budget', '50')
    """)

    conn.commit()
    conn.close()
    logger.info("card_points and points_config tables ensured.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_card_points_tables()
    print("Done.")
