"""The "Tag me" queue setting in match_records.db (Discord bot side).

When a pairing is announced in the LFG channel the bot names both players.
Players with "Tag me" on (the default) get a real @-mention that pings them;
players who turned it off are still named, but the mention doesn't ping.

Only players who turned it OFF are stored, so everyone with no row (every
existing player) behaves as on. The web app writes the same table
(web-app/repositories/tag_me_repo.py).
"""

import datetime
import logging
import re
import sqlite3
from contextlib import contextmanager

import discord

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS no_tag_players (
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


def create_tag_me_table():
    """Create the no_tag_players table if it doesn't exist."""
    with _get_connection():
        pass


def wants_tag(user_id) -> bool:
    """True unless the player turned "Tag me" off."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM no_tag_players WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return row is None


def untagged_ids(user_ids) -> set[int]:
    """The given players who turned "Tag me" off, as ints."""
    ids = [str(u) for u in user_ids if u is not None]
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    with _get_connection() as conn:
        rows = conn.execute(
            f"SELECT user_id FROM no_tag_players WHERE user_id IN ({placeholders})", ids
        ).fetchall()
    return {int(row[0]) for row in rows if str(row[0]).isdigit()}


def set_tag_me(user_id, tag_me: bool, source: str = "discord") -> bool:
    """Turn "Tag me" on or off. Returns the new setting."""
    with _get_connection() as conn:
        if tag_me:
            conn.execute("DELETE FROM no_tag_players WHERE user_id = ?", (str(user_id),))
        else:
            conn.execute(
                """
                INSERT INTO no_tag_players (user_id, set_at, source) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET set_at = excluded.set_at, source = excluded.source
                """,
                (str(user_id), datetime.datetime.now(datetime.timezone.utc).isoformat(), source),
            )
    logger.info(f"Tag me {'on' if tag_me else 'off'} for {user_id} ({source})")
    return tag_me


def pairing_mentions(*user_ids) -> discord.AllowedMentions:
    """Allowed mentions for a pairing message: ping only players with "Tag me" on.

    If the setting can't be read, everyone is pinged, as before the setting existed.
    """
    ids = [int(u) for u in user_ids if u is not None]
    try:
        off = untagged_ids(ids)
    except Exception as e:
        logger.warning("Could not read Tag me settings, pinging everyone: %s", e)
        off = set()
    return discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=[discord.Object(id=u) for u in ids if u not in off],
    )


_USER_MENTION = re.compile(r"<@!?(\d+)>")


def mentioned_ids(text) -> list[int]:
    """Discord user ids @-mentioned in a message's text, in order, without repeats."""
    seen = []
    for match in _USER_MENTION.finditer(text or ""):
        user_id = int(match.group(1))
        if user_id not in seen:
            seen.append(user_id)
    return seen


def tag_me_mentions_for(text) -> discord.AllowedMentions:
    """Allowed mentions for a message: ping only the mentioned players with "Tag me" on."""
    return pairing_mentions(*mentioned_ids(text))


async def send_with_tag_me(channel, content=None, **kwargs):
    """``channel.send`` that names everyone it mentions but pings only players with "Tag me" on.

    Used for every post in the backup (DM-disabled) channel and the LFG channel.
    """
    kwargs.setdefault("allowed_mentions", tag_me_mentions_for(content))
    return await channel.send(content, **kwargs)
