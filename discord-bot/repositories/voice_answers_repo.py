"""Each player's last voice answers in match_records.db (Discord bot side).

The join modal asks "Are you willing to play this match with voice on Discord?"
and "...without voice?". The answers from the player's last join (from Discord
or Play Sorcery Online) are ticked the next time the modal opens.
"""

import datetime
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS last_voice_answers (
                user_id TEXT PRIMARY KEY,
                voice INTEGER NOT NULL,
                no_voice INTEGER NOT NULL,
                set_at TEXT NOT NULL
            )
        """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_voice_answers(user_id):
    """(willing with voice, willing without voice) from the last join, or None."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT voice, no_voice FROM last_voice_answers WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return (bool(row[0]), bool(row[1])) if row else None


def save_voice_answers(user_id, voice, no_voice):
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO last_voice_answers (user_id, voice, no_voice, set_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET voice = excluded.voice, no_voice = excluded.no_voice,
                set_at = excluded.set_at
            """,
            (str(user_id), int(bool(voice)), int(bool(no_voice)), datetime.datetime.now().isoformat()),
        )
