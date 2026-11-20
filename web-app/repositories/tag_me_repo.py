"""The "Tag me" queue setting in match_records.db (web app side).

When a pairing is announced in the Discord LFG channel, players with "Tag me"
on (the default) are pinged; players who turned it off are named without a
ping. Only players who turned it OFF are stored, so everyone with no row
behaves as on. The bot writes the same table (discord-bot/repositories/tag_me_repo.py).
"""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class TagMeRepository:
    """Data access for the no_tag_players table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS no_tag_players (
                user_id TEXT PRIMARY KEY,
                set_at TEXT NOT NULL,
                source TEXT
            )
        """)
        conn.commit()
        conn.close()

    def wants_tag(self, user_id: str) -> bool:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM no_tag_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
        conn.close()
        return row is None

    def set_tag_me(self, user_id: str, tag_me: bool) -> bool:
        conn = self._get_connection()
        if tag_me:
            conn.execute("DELETE FROM no_tag_players WHERE user_id = ?", (str(user_id),))
        else:
            conn.execute(
                """
                INSERT INTO no_tag_players (user_id, set_at, source) VALUES (?, ?, 'website')
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat()),
            )
        conn.commit()
        conn.close()
        return tag_me
