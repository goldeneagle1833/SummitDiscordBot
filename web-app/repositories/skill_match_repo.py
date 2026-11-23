"""The "Skill matching" queue setting in match_records.db (web app side).

Opt-in test of skill-based matchmaking in the Discord Ranked queue: players
who turn it on are only paired with opponents near their rating (the gap
widens the longer they wait). Only players who turned it ON are stored, so
everyone with no row is unaffected. The bot reads and writes the same table
(discord-bot/repositories/skill_match_repo.py).
"""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class SkillMatchRepository:
    """Data access for the skill_match_players table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_match_players (
                user_id TEXT PRIMARY KEY,
                set_at TEXT NOT NULL,
                source TEXT
            )
        """)
        conn.commit()
        conn.close()

    def wants_skill_match(self, user_id: str) -> bool:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM skill_match_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
        conn.close()
        return row is not None

    def set_skill_match(self, user_id: str, on: bool) -> bool:
        conn = self._get_connection()
        if on:
            conn.execute(
                """
                INSERT INTO skill_match_players (user_id, set_at, source) VALUES (?, ?, 'website')
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat()),
            )
        else:
            conn.execute("DELETE FROM skill_match_players WHERE user_id = ?", (str(user_id),))
        conn.commit()
        conn.close()
        return on
