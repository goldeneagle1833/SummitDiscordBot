"""The "Skill matching" queue setting in match_records.db (Discord bot side).

Opt-in test of skill-based matchmaking for the Ranked and Casual queues. A player who turns
it on is only paired with opponents whose rating is close to theirs; the
allowed gap starts small and widens the longer either player has waited (see
cogs/lfg/skill_match.py). Players who never turned it on pair as before.

Only players who turned it ON are stored, so everyone with no row (every
existing player) is unaffected. The web app writes the same table
(web-app/repositories/skill_match_repo.py).
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
            CREATE TABLE IF NOT EXISTS skill_match_players (
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


def create_skill_match_table():
    """Create the skill_match_players table if it doesn't exist."""
    with _get_connection():
        pass


def wants_skill_match(user_id) -> bool:
    """True if the player turned "Skill matching" on."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM skill_match_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return row is not None


def skill_match_ids(user_ids) -> set[int]:
    """The given players who turned "Skill matching" on, as ints."""
    ids = [str(u) for u in user_ids if u is not None]
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT user_id FROM skill_match_players WHERE user_id IN ({placeholders})", ids
        ).fetchall()
    return {int(row[0]) for row in rows if str(row[0]).isdigit()}


def set_skill_match(user_id, on: bool, source: str = "discord") -> bool:
    """Turn "Skill matching" on or off. Returns the new setting."""
    with _get_connection() as conn:
        if on:
            conn.execute(
                """
                INSERT INTO skill_match_players (user_id, set_at, source) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat(), source),
            )
        else:
            conn.execute("DELETE FROM skill_match_players WHERE user_id = ?", (str(user_id),))
    logger.info(f"Skill matching {'on' if on else 'off'} for {user_id} ({source})")
    return on
