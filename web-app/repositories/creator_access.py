"""Repository for DB-backed creator access overrides in match_records.db."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class CreatorAccessRepository:
    """Manages creator_access table — users granted creator page access by admins."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS creator_access (
                user_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                granted_by TEXT
            )
        """)
        conn.commit()
        conn.close()

    def has_access(self, user_id: str) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM creator_access WHERE user_id = ?", (str(user_id),))
        result = cur.fetchone() is not None
        conn.close()
        return result

    def list_all(self) -> list[dict]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, display_name, granted_at, granted_by FROM creator_access ORDER BY display_name ASC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def add(self, user_id: str, display_name: str, granted_by: str | None = None):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO creator_access (user_id, display_name, granted_at, granted_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET display_name = excluded.display_name
            """,
            (str(user_id), display_name, now, granted_by),
        )
        conn.commit()
        conn.close()

    def remove(self, user_id: str) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM creator_access WHERE user_id = ?", (str(user_id),))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
