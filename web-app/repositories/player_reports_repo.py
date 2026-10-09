"""Repository for player reports in match_records.db (web app side).

Players file these from the Discord bot's **Report Player** button on a match
message. The admin log page lists them under Blocked Users.
"""

import json
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class PlayerReportsRepository:
    """Data access for the player_reports table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        # Same shape as discord-bot/repositories/player_reports_repo.py
        conn = self._get_connection()
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
        conn.commit()
        conn.close()

    @staticmethod
    def _reasons(raw) -> list[str]:
        try:
            value = json.loads(raw or "[]")
        except (TypeError, ValueError):
            return []
        return [str(v) for v in value] if isinstance(value, list) else []

    def get_all_reports(self, limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
        """Get every player report, newest first. Returns (rows, total_count)."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM player_reports")
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT id, reporter_id, reporter_name, reported_id, reported_name,
                   pairing_id, match_type, reasons, details, created_at
            FROM player_reports
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = []
        for row in cur.fetchall():
            entry = dict(row)
            entry["reasons"] = self._reasons(row["reasons"])
            rows.append(entry)
        conn.close()
        return rows, total
