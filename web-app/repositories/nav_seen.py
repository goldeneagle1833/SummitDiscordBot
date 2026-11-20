"""When each logged-in person last opened each menu page (for new-content dots)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import webapp_config


class NavSeenRepository:
    def __init__(self, db_path=None):
        self._explicit_path = db_path

    @property
    def _db_path(self) -> str:
        return str(self._explicit_path or webapp_config.MATCH_RECORDS_DB_PATH)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS nav_seen (
                   user_id TEXT NOT NULL,
                   page TEXT NOT NULL,
                   seen_at TEXT NOT NULL,
                   PRIMARY KEY (user_id, page)
               )"""
        )
        return conn

    def get_seen(self, user_id: str) -> dict[str, str]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT page, seen_at FROM nav_seen WHERE user_id = ?", (str(user_id),)
            ).fetchall()
            return {page: seen_at for page, seen_at in rows}
        finally:
            conn.close()

    def mark_seen(self, user_id: str, pages: list[str]) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = self._conn()
        try:
            conn.executemany(
                """INSERT INTO nav_seen (user_id, page, seen_at) VALUES (?, ?, ?)
                   ON CONFLICT(user_id, page) DO UPDATE SET seen_at = excluded.seen_at""",
                [(str(user_id), page, now) for page in pages],
            )
            conn.commit()
            return now
        finally:
            conn.close()
