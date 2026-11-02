"""Voice-only players in match_records.db (web app side).

The Discord bot never DMs a voice-only player the "want to play a no-voice
game?" offer. The bot writes the same table (discord-bot/repositories/voice_only_repo.py).
"""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class VoiceOnlyRepository:
    """Data access for the voice_only_players table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_only_players (
                user_id TEXT PRIMARY KEY,
                set_at TEXT NOT NULL,
                source TEXT
            )
        """)
        conn.commit()
        conn.close()

    def is_voice_only(self, user_id: str) -> bool:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM voice_only_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
        conn.close()
        return row is not None

    def set_voice_only(self, user_id: str, voice_only: bool) -> bool:
        conn = self._get_connection()
        if voice_only:
            conn.execute(
                """
                INSERT INTO voice_only_players (user_id, set_at, source) VALUES (?, ?, 'website')
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat()),
            )
        else:
            conn.execute("DELETE FROM voice_only_players WHERE user_id = ?", (str(user_id),))
        conn.commit()
        conn.close()
        return voice_only
