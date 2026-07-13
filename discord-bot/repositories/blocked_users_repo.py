"""Repository for blocked users in match_records.db (Discord bot side)."""

import sqlite3
import logging
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


def create_blocked_users_table():
    """Create blocked_users table if it doesn't exist."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id TEXT NOT NULL,
                blocked_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, blocked_user_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blocked_users_user_id
            ON blocked_users (user_id)
        """)


def get_blocked_user_ids(user_id: int | str) -> set[str]:
    """Get the set of user IDs that a player has blocked."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT blocked_user_id FROM blocked_users WHERE user_id = ?",
            (str(user_id),),
        )
        return {row[0] for row in cur.fetchall()}


def is_blocked_pair(user_id_a: int | str, user_id_b: int | str) -> bool:
    """Check if either player has blocked the other (mutual check for matchmaking)."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 FROM blocked_users
            WHERE (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?)
            LIMIT 1
            """,
            (str(user_id_a), str(user_id_b), str(user_id_b), str(user_id_a)),
        )
        return cur.fetchone() is not None
