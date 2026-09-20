"""
Migration: map support for the Explorer Series.

Adds coordinates to explorer_events so the Community Series page can plot an
events map, and a small key/value settings table so admins can turn that map
on and off.

Run with: python migrations/create_explorer_map_support.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp_config

logger = logging.getLogger(__name__)

EVENT_COLUMNS = {
    "latitude": "REAL",
    "longitude": "REAL",
    "geocoded_at": "TEXT",
}


def create_explorer_map_support(db_path=None):
    """Add event coordinates and the explorer_settings table."""
    # Resolved at call time so tests can point webapp_config at a temp DB.
    path = db_path or webapp_config.EXPLORER_DB_PATH
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # explorer_events predates this, so add the columns if they're missing.
    cursor.execute("PRAGMA table_info(explorer_events)")
    existing = {row[1] for row in cursor.fetchall()}
    if existing:  # table exists at all
        for column, column_type in EVENT_COLUMNS.items():
            if column not in existing:
                cursor.execute(
                    f"ALTER TABLE explorer_events ADD COLUMN {column} {column_type}"
                )
                logger.info("Added %s to explorer_events", column)

    conn.commit()
    conn.close()
    logger.info("Explorer map support ensured at %s", path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_explorer_map_support()
    print("Explorer map support created.")
