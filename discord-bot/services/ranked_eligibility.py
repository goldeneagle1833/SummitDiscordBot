"""Who may play ranked: anyone who isn't brand new.

A player needs at least two recorded games of any kind before joining ranked.
Casual, ranked, rumble, limited, website-reported and past-season games all
count, so the check only ever stops someone on their first or second game.
"""

import logging
import sqlite3

logger = logging.getLogger("discord_bot")

MIN_GAMES_FOR_RANKED = 2

# (table, winner column, loser column) for every place a played game is recorded
_GAME_TABLES = (
    ("match_records", "winner_id", "losser_id"),
    ("match_records_archive", "winner_id", "losser_id"),
    ("rumble_match_records", "winner_id", "losser_id"),
    ("limited_match_records", "winner_id", "loser_id"),
    ("limited_match_records_archive", "winner_id", "loser_id"),
    ("match_reports_web", "winner_id", "losser_id"),
)


def count_recorded_games(user_id: int, stop_at: int = MIN_GAMES_FOR_RANKED,
                         db_path: str = "match_records.db") -> int:
    """How many games a player has on record, counting no further than ``stop_at``."""
    total = 0
    conn = sqlite3.connect(db_path)
    try:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, winner_col, loser_col in _GAME_TABLES:
            if table not in existing:
                continue
            # Website tables store ids as text, so match either form
            total += conn.execute(
                f"""SELECT COUNT(*) FROM (
                        SELECT 1 FROM {table}
                        WHERE {winner_col} IN (?, ?) OR {loser_col} IN (?, ?)
                        LIMIT ?
                    )""",
                (user_id, str(user_id), user_id, str(user_id), stop_at),
            ).fetchone()[0]
            if total >= stop_at:
                break
    finally:
        conn.close()
    return min(total, stop_at)


def ranked_block_message(user_id: int) -> str | None:
    """Why this player can't join ranked yet, or None when they can.

    If the history can't be read the player is let through: a database
    hiccup should never lock established players out of ranked.
    """
    try:
        played = count_recorded_games(user_id)
    except sqlite3.Error as e:
        logger.warning("Could not check ranked eligibility for %s: %s", user_id, e)
        return None
    if played >= MIN_GAMES_FOR_RANKED:
        return None
    remaining = MIN_GAMES_FOR_RANKED - played
    return (
        f"Ranked opens after your first {MIN_GAMES_FOR_RANKED} games. "
        f"You've played {played} so far, so play {remaining} more "
        f"game{'s' if remaining != 1 else ''} in the **Casual** queue (or any other queue) "
        "and then join Ranked."
    )
