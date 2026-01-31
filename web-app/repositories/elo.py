"""Repository for ELO database access."""

import sqlite3
from pathlib import Path

from webapp_config import ELO_DB_PATH


class EloRepository:
    """Data access for elo.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or ELO_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get_all_standings(self) -> list[dict]:
        """Get all ELO standings ordered by ELO descending."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, user_display_name, elo
            FROM overall_standings
            ORDER BY elo DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {"user_id": row[0], "display_name": row[1], "elo": row[2]}
            for row in rows
        ]

    def get_all_elos(self) -> list[int]:
        """Get all ELO values for distribution calculation."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT elo FROM overall_standings")
        elos = [row[0] for row in cur.fetchall()]
        conn.close()
        return elos

    def get_user_elo(self, user_id: int) -> int | None:
        """Get ELO for a specific user."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT elo FROM overall_standings WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
