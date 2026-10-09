"""Repository for player reports in match_records.db (Discord bot side).

A player report is filed from the **Report Player** button on a match
message: the reporter ticks what went wrong and can add free-text feedback.
Admins read them on the web app's admin log page, next to blocked users.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_player_reports_table():
    """Create player_reports table if it doesn't exist."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id TEXT NOT NULL,
                reporter_name TEXT,
                reported_id TEXT NOT NULL,
                reported_name TEXT,
                pairing_id INTEGER,
                match_type TEXT,
                reasons TEXT NOT NULL DEFAULT '[]',
                details TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_player_reports_reported_id
            ON player_reports (reported_id)
        """)


def save_player_report(
    *,
    reporter_id,
    reported_id,
    reasons,
    details=None,
    reporter_name=None,
    reported_name=None,
    pairing_id=None,
    match_type=None,
) -> int:
    """Store a player report and return its id."""
    create_player_reports_table()
    with _get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO player_reports (
                reporter_id, reporter_name, reported_id, reported_name,
                pairing_id, match_type, reasons, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(reporter_id),
                reporter_name,
                str(reported_id),
                reported_name,
                pairing_id or None,
                match_type,
                json.dumps(list(reasons or [])),
                (details or "").strip() or None,
            ),
        )
        return cur.lastrowid
