"""Repository for community feedback submissions."""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import FEEDBACK_DB_PATH


class FeedbackRepository:
    """Data access for the feedback table in feedback.db."""

    VALID_STATUSES = ("backlog", "next_up", "resolved", "not_planned")
    VALID_TYPES = ("feature_request", "bug_report", "general")

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or FEEDBACK_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'backlog',
            user_id TEXT,
            username TEXT,
            admin_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            notified INTEGER NOT NULL DEFAULT 0
        )""")
        conn.commit()
        conn.close()

    def create(self, type: str, title: str, description: str,
               user_id: str | None = None, username: str | None = None) -> int:
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO feedback (type, title, description, user_id, username,
                                     created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (type, title, description, user_id, username, now, now),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def get_all(self) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, type, title, description, status, user_id, username,
                      admin_notes, created_at, updated_at, resolved_at, notified
               FROM feedback ORDER BY id DESC"""
        )
        columns = [
            "id", "type", "title", "description", "status", "user_id",
            "username", "admin_notes", "created_at", "updated_at",
            "resolved_at", "notified",
        ]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_by_id(self, feedback_id: int) -> dict | None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, type, title, description, status, user_id, username,
                      admin_notes, created_at, updated_at, resolved_at, notified
               FROM feedback WHERE id = ?""",
            (feedback_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        columns = [
            "id", "type", "title", "description", "status", "user_id",
            "username", "admin_notes", "created_at", "updated_at",
            "resolved_at", "notified",
        ]
        return dict(zip(columns, row))

    def update_status(self, feedback_id: int, status: str,
                      admin_notes: str | None = None) -> bool:
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        resolved_at = now if status == "resolved" else None
        # Reset notified flag when moving to resolved so bot can DM the user
        notified = 0 if status == "resolved" else None
        if admin_notes is not None:
            if notified is not None:
                cur.execute(
                    """UPDATE feedback
                       SET status = ?, admin_notes = ?, updated_at = ?,
                           resolved_at = COALESCE(?, resolved_at),
                           notified = ?
                       WHERE id = ?""",
                    (status, admin_notes, now, resolved_at, notified, feedback_id),
                )
            else:
                cur.execute(
                    """UPDATE feedback
                       SET status = ?, admin_notes = ?, updated_at = ?,
                           resolved_at = COALESCE(?, resolved_at)
                       WHERE id = ?""",
                    (status, admin_notes, now, resolved_at, feedback_id),
                )
        else:
            if notified is not None:
                cur.execute(
                    """UPDATE feedback
                       SET status = ?, updated_at = ?,
                           resolved_at = COALESCE(?, resolved_at),
                           notified = ?
                       WHERE id = ?""",
                    (status, now, resolved_at, notified, feedback_id),
                )
            else:
                cur.execute(
                    """UPDATE feedback
                       SET status = ?, updated_at = ?,
                           resolved_at = COALESCE(?, resolved_at)
                       WHERE id = ?""",
                    (status, now, resolved_at, feedback_id),
                )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def delete(self, feedback_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def get_pending_notifications(self) -> list[dict]:
        """Get resolved feedback items that haven't been notified yet
        and have a user_id (logged-in submitter)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT id, type, title, description, status, user_id, username,
                      admin_notes, created_at, updated_at, resolved_at, notified
               FROM feedback
               WHERE status = 'resolved' AND notified = 0 AND user_id IS NOT NULL"""
        )
        columns = [
            "id", "type", "title", "description", "status", "user_id",
            "username", "admin_notes", "created_at", "updated_at",
            "resolved_at", "notified",
        ]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        conn.close()
        return rows

    def mark_notified(self, feedback_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE feedback SET notified = 1 WHERE id = ?",
            (feedback_id,),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed
