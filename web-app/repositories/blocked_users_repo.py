"""Repository for blocked users in match_records.db (web app side)."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class BlockedUsersRepository:
    """Data access for blocked_users table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id TEXT NOT NULL,
                blocked_user_id TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, blocked_user_id)
            )
        """)
        # Migration: add reason column to existing tables
        try:
            conn.execute("ALTER TABLE blocked_users ADD COLUMN reason TEXT")
        except Exception:
            pass
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blocked_users_user_id
            ON blocked_users (user_id)
        """)
        conn.commit()
        conn.close()

    def get_blocked_users(self, user_id: str) -> list[dict]:
        """Get list of blocked user entries for a player."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT blocked_user_id, reason FROM blocked_users WHERE user_id = ? ORDER BY created_at DESC",
            (str(user_id),),
        )
        result = [{"blocked_user_id": row["blocked_user_id"], "reason": row["reason"]} for row in cur.fetchall()]
        conn.close()
        return result

    def block_user(self, user_id: str, blocked_user_id: str, reason: str | None = None) -> bool:
        """Block a user. Returns True if newly blocked, False if already blocked."""
        if str(user_id) == str(blocked_user_id):
            return False
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO blocked_users (user_id, blocked_user_id, reason) VALUES (?, ?, ?)",
                (str(user_id), str(blocked_user_id), reason),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def unblock_user(self, user_id: str, blocked_user_id: str) -> bool:
        """Unblock a user. Returns True if was blocked and now removed."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM blocked_users WHERE user_id = ? AND blocked_user_id = ?",
            (str(user_id), str(blocked_user_id)),
        )
        conn.commit()
        removed = cur.rowcount > 0
        conn.close()
        return removed
