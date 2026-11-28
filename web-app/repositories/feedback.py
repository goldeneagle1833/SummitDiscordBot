"""Repository for community feedback submissions."""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import FEEDBACK_DB_PATH


class FeedbackRepository:
    """Data access for the feedback table in feedback.db."""

    VALID_STATUSES = ("backlog", "next_up", "resolved", "not_planned")
    VALID_TYPES = ("feature_request", "bug_report", "general")
    VALID_SOURCES = ("site", "discord")

    # What the "Feedback auto PR" GitHub Action can say about an item.
    #   pending       waiting for the next Action run
    #   claimed       an Action run is working on it
    #   drafted       a draft PR was opened (auto_pr_url)
    #   duplicate     same ask as another item or an open PR
    #   needs_human   real, but too big or unclear to draft safely
    #   not_actionable spam, a question, or nothing to change
    #   failed        the run broke or the change failed the safety checks
    AUTO_STATUSES = (
        "pending", "claimed", "drafted", "duplicate", "needs_human",
        "not_actionable", "failed",
    )
    AUTO_RESULT_STATUSES = (
        "drafted", "duplicate", "needs_human", "not_actionable", "failed",
    )

    COLUMNS = (
        "id", "type", "title", "description", "status", "user_id",
        "username", "admin_notes", "created_at", "updated_at",
        "resolved_at", "notified", "source", "source_ref", "auto_status",
        "auto_pr_url", "auto_note", "auto_updated_at",
    )

    # Columns added after the table first shipped (added on startup).
    _ADDED_COLUMNS = (
        ("source", "TEXT NOT NULL DEFAULT 'site'"),
        ("source_ref", "TEXT"),
        ("auto_status", "TEXT"),
        ("auto_pr_url", "TEXT"),
        ("auto_note", "TEXT"),
        ("auto_updated_at", "TEXT"),
    )

    # A claim older than this is handed out again (the run probably died).
    CLAIM_TIMEOUT_HOURS = 6

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
        existing = {row[1] for row in conn.execute("PRAGMA table_info(feedback)")}
        for name, ddl in self._ADDED_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {name} {ddl}")
        conn.commit()
        conn.close()

    def _select(self, where: str = "", params: tuple = (), order: str = "id DESC",
                limit: int | None = None) -> list[dict]:
        sql = f"SELECT {', '.join(self.COLUMNS)} FROM feedback"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        conn = self._get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [dict(zip(self.COLUMNS, row)) for row in rows]

    def create(self, type: str, title: str, description: str,
               user_id: str | None = None, username: str | None = None,
               source: str = "site", source_ref: str | None = None) -> int:
        """Save a new item. New items wait for the auto PR run ('pending')."""
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO feedback (type, title, description, user_id, username,
                                     created_at, updated_at, source, source_ref,
                                     auto_status, auto_updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (type, title, description, user_id, username, now, now,
             source, source_ref, now),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def get_all(self) -> list[dict]:
        return self._select()

    def get_by_id(self, feedback_id: int) -> dict | None:
        rows = self._select("id = ?", (feedback_id,))
        return rows[0] if rows else None

    def get_by_source_ref(self, source: str, source_ref: str) -> dict | None:
        rows = self._select("source = ? AND source_ref = ?", (source, source_ref))
        return rows[0] if rows else None

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
        return self._select(
            "status = 'resolved' AND notified = 0 AND user_id IS NOT NULL",
            order="id ASC",
        )

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

    # ------------------------------------------------------------------
    # Auto PR automation
    # ------------------------------------------------------------------

    def claim_for_automation(self, limit: int) -> list[dict]:
        """Hand the oldest waiting items to an Action run and mark them claimed.

        Only open items (Backlog / Next up) are handed out. A claim that never
        reported back within CLAIM_TIMEOUT_HOURS is handed out again.
        """
        limit = max(0, min(int(limit), 10))
        if not limit:
            return []
        now = datetime.datetime.now()
        stale = (now - datetime.timedelta(hours=self.CLAIM_TIMEOUT_HOURS)).isoformat()
        conn = self._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            ids = [
                row[0] for row in conn.execute(
                    """SELECT id FROM feedback
                       WHERE status IN ('backlog', 'next_up')
                         AND (auto_status = 'pending'
                              OR (auto_status = 'claimed' AND auto_updated_at < ?))
                       ORDER BY id ASC LIMIT ?""",
                    (stale, limit),
                ).fetchall()
            ]
            if ids:
                marks = ",".join("?" * len(ids))
                conn.execute(
                    f"""UPDATE feedback SET auto_status = 'claimed', auto_updated_at = ?
                        WHERE id IN ({marks})""",
                    (now.isoformat(), *ids),
                )
            conn.commit()
        finally:
            conn.close()
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self._select(f"id IN ({marks})", tuple(ids), order="id ASC")

    def recent_for_dedupe(self, limit: int = 80) -> list[dict]:
        """Recent items (title + state only) so the Action can spot duplicates."""
        return [
            {
                "id": r["id"], "title": r["title"], "status": r["status"],
                "auto_status": r["auto_status"], "auto_pr_url": r["auto_pr_url"],
            }
            for r in self._select(limit=limit)
        ]

    def set_auto_result(self, feedback_id: int, auto_status: str,
                        pr_url: str | None = None, note: str | None = None) -> bool:
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """UPDATE feedback
               SET auto_status = ?, auto_pr_url = COALESCE(?, auto_pr_url),
                   auto_note = ?, auto_updated_at = ?
               WHERE id = ?""",
            (auto_status, pr_url, note, now, feedback_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def queue_for_automation(self, feedback_id: int) -> bool:
        """Put an item (old, failed, or skipped) back in line for the Action."""
        now = datetime.datetime.now().isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """UPDATE feedback
               SET auto_status = 'pending', auto_note = NULL, auto_updated_at = ?
               WHERE id = ?""",
            (now, feedback_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed
