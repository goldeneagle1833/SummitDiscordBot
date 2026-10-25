"""Voice-only players in match_records.db (Discord bot side).

A voice-only player only plays on voice, so the bot never DMs them the
"someone wants a no-voice game, want to play?" offer. It changes nothing
about pairing: voice and no-voice players never pair on their own anyway.
Players turn it on from the offer DM, with ``!voice_only`` / ``/voice-only``,
or on their website profile (the web app writes the same table).
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
            CREATE TABLE IF NOT EXISTS voice_only_players (
                user_id TEXT PRIMARY KEY,
                set_at TEXT NOT NULL,
                source TEXT
            )
        """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_voice_only_table():
    """Create the voice_only_players table if it doesn't exist."""
    with _get_connection():
        pass


def is_voice_only(user_id) -> bool:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM voice_only_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return row is not None


def voice_only_ids(user_ids) -> set[int]:
    """The given players who are voice only, as ints."""
    ids = [str(u) for u in user_ids]
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT user_id FROM voice_only_players WHERE user_id IN ({placeholders})", ids
        ).fetchall()
    return {int(row[0]) for row in rows if str(row[0]).isdigit()}


def set_voice_only(user_id, voice_only: bool, source: str = "discord") -> bool:
    """Turn voice only on or off. Returns the new setting."""
    with _get_connection() as conn:
        if voice_only:
            conn.execute(
                """
                INSERT INTO voice_only_players (user_id, set_at, source) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat(), source),
            )
        else:
            conn.execute("DELETE FROM voice_only_players WHERE user_id = ?", (str(user_id),))
    logger.info(f"Voice only {'on' if voice_only else 'off'} for {user_id} ({source})")
    return voice_only
