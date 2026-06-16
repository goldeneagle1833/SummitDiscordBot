"""
Migration: Create deck_builder.db tables for user-saved decks.

Run with: python migrations/create_deck_builder_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import DECK_BUILDER_DB_PATH

logger = logging.getLogger(__name__)


def create_deck_builder_tables():
    """Create all deck builder tables if they don't exist."""
    conn = sqlite3.connect(str(DECK_BUILDER_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source_url TEXT,
            avatar_json TEXT,
            mainboard_json TEXT NOT NULL,
            sideboard_json TEXT NOT NULL DEFAULT '[]',
            card_tags_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_saved_decks_user
        ON saved_decks(user_id)
    """)

    conn.commit()
    conn.close()
    logger.info("deck_builder tables ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    create_deck_builder_tables()
    logger.info("Migration completed.")
