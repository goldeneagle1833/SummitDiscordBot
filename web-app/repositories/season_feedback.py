"""Repository for post-season feedback survey responses (feedback.db)."""

import datetime
import json
import sqlite3
from pathlib import Path

import webapp_config

COLUMNS = ["id", "season", "user_id", "username", "answers", "created_at"]


class SeasonFeedbackRepository:
    """Data access for the season_feedback table.

    Answers are stored as one JSON document per response so the question
    list can change between seasons without a migration.
    """

    def __init__(self, db_path: Path | str | None = None):
        # Resolved at call time so tests can point webapp_config at a temp DB.
        self._db_path = str(db_path or webapp_config.FEEDBACK_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""CREATE TABLE IF NOT EXISTS season_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT NOT NULL,
            user_id TEXT,
            username TEXT,
            answers TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_season_feedback_season "
            "ON season_feedback (season)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _row_to_dict(row) -> dict:
        record = dict(zip(COLUMNS, row))
        record["answers"] = json.loads(record["answers"] or "{}")
        return record

    def create(self, season: str, answers: dict,
               user_id: str | None = None, username: str | None = None) -> int:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO season_feedback (season, user_id, username, answers, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (season, user_id, username, json.dumps(answers), now),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def list_seasons(self) -> list[str]:
        """Distinct season labels, most recently submitted first."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT season FROM season_feedback GROUP BY season ORDER BY MAX(id) DESC"
        )
        seasons = [row[0] for row in cur.fetchall()]
        conn.close()
        return seasons

    def list_responses(self, season: str | None = None) -> list[dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        if season:
            cur.execute(
                f"SELECT {', '.join(COLUMNS)} FROM season_feedback "
                "WHERE season = ? ORDER BY id DESC",
                (season,),
            )
        else:
            cur.execute(
                f"SELECT {', '.join(COLUMNS)} FROM season_feedback ORDER BY id DESC"
            )
        rows = [self._row_to_dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_by_id(self, response_id: int) -> dict | None:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT {', '.join(COLUMNS)} FROM season_feedback WHERE id = ?",
            (response_id,),
        )
        row = cur.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def delete(self, response_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM season_feedback WHERE id = ?", (response_id,))
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed
