"""Repository for fart scores database access."""

import sqlite3
from pathlib import Path

from webapp_config import FART_SCORES_DB_PATH


class FartRepository:
    """Data access for fart_scores.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or FART_SCORES_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get_leaderboard(self) -> list[dict]:
        """Get fart leaderboard data ordered by score descending."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, user_display_name, score, date_last_updated
            FROM fart_scores
            ORDER BY score DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "rank": rank,
                "user_id": row[0],
                "username": row[1],
                "score": row[2],
                "last_updated": row[3],
            }
            for rank, row in enumerate(rows, start=1)
        ]
