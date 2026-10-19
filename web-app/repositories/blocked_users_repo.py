"""Repository for blocked users in match_records.db (web app side)."""

import sqlite3
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

    def get_all_blocks(self, limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
        """Get every block record (admin view). Returns (rows, total_count)."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM blocked_users")
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT user_id, blocked_user_id, reason, created_at
            FROM blocked_users
            ORDER BY created_at DESC, user_id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = [
            {
                "user_id": row["user_id"],
                "blocked_user_id": row["blocked_user_id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in cur.fetchall()
        ]
        conn.close()
        return rows, total

    @staticmethod
    def _id_forms(user_id: str) -> tuple[str, str]:
        """Both ways a player's ID can be stored ('123' and 'google_123')."""
        bare = BlockedUsersRepository._stripped(user_id)
        return bare, f"google_{bare}"

    def get_blocks_involving(self, user_id: str) -> dict:
        """Every block a player made and every block made against them.

        Matches the bare and google_-prefixed forms of the ID, since a
        Google login stores its list under 'google_<id>'.
        Returns {"blocked": [...], "blocked_by": [...]}, each entry
        {"user_id", "created_at"}, newest first. Reasons are left out.
        """
        forms = self._id_forms(user_id)
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT blocked_user_id, created_at FROM blocked_users"
            " WHERE user_id IN (?, ?) ORDER BY created_at DESC",
            forms,
        )
        blocked = [
            {"user_id": row["blocked_user_id"], "created_at": row["created_at"]}
            for row in cur.fetchall()
        ]
        cur.execute(
            "SELECT user_id, created_at FROM blocked_users"
            " WHERE blocked_user_id IN (?, ?) ORDER BY created_at DESC",
            forms,
        )
        blocked_by = [
            {"user_id": row["user_id"], "created_at": row["created_at"]}
            for row in cur.fetchall()
        ]
        conn.close()
        return {"blocked": blocked, "blocked_by": blocked_by}

    def get_block_between(self, user_id_a: str, user_id_b: str) -> dict:
        """Which direction(s) a pair is blocked in.

        Returns {"a_blocked_b": bool, "b_blocked_a": bool}.
        """
        a_forms = self._id_forms(user_id_a)
        b_forms = self._id_forms(user_id_b)
        conn = self._get_connection()
        cur = conn.cursor()

        def has_block(blocker_forms, blocked_forms) -> bool:
            cur.execute(
                "SELECT 1 FROM blocked_users WHERE user_id IN (?, ?)"
                " AND blocked_user_id IN (?, ?) LIMIT 1",
                (*blocker_forms, *blocked_forms),
            )
            return cur.fetchone() is not None

        result = {
            "a_blocked_b": has_block(a_forms, b_forms),
            "b_blocked_a": has_block(b_forms, a_forms),
        }
        conn.close()
        return result

    @staticmethod
    def _stripped(pid: str) -> str:
        s = str(pid)
        return s[7:] if s.startswith("google_") else s

    def block_user(self, user_id: str, blocked_user_id: str, reason: str | None = None) -> bool:
        """Block a user. Returns True if newly blocked, False if already blocked."""
        if self._stripped(user_id) == self._stripped(blocked_user_id):
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
