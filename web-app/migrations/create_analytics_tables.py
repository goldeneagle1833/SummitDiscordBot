"""
Migration: Create analytics tables for page views and banner clicks.

Run with: python migrations/create_analytics_tables.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import ANALYTICS_DB_PATH


def create_analytics_tables():
    """Create page_views and banner_clicks tables if they don't exist."""
    conn = sqlite3.connect(str(ANALYTICS_DB_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            path TEXT NOT NULL,
            user_agent TEXT,
            referrer TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_views_timestamp
        ON page_views(timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_views_path
        ON page_views(path)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banner_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            banner_type TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_banner_clicks_timestamp
        ON banner_clicks(timestamp DESC)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subtitle TEXT,
            link TEXT NOT NULL,
            badge_text TEXT NOT NULL DEFAULT 'NEW',
            color TEXT NOT NULL DEFAULT 'blue',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("analytics tables ready")


if __name__ == "__main__":
    create_analytics_tables()
    print("Migration completed.")
