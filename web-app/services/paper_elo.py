"""Paper ELO service for web-reported match confirmations.

Uses a separate paper_standings table (TEXT PRIMARY KEY) to avoid conflicts
with the Discord bot's overall_standings table (INTEGER PRIMARY KEY).
This supports Google OAuth IDs (21+ digits) that overflow SQLite INTEGER.
"""

import logging
from datetime import datetime
from pathlib import Path

from webapp_config import ELO_DB_PATH
import sqlite3
from utils.avatar_elo import canonicalize_avatar_name

logger = logging.getLogger(__name__)


def calculate_elo(player_elo: int, opponent_elo: int, did_win: bool, k: int = 32) -> int:
    """
    Calculate new ELO rating using the standard Elo formula.

    Same formula as discord-bot/services/elo_service.py update_elo().

    Args:
        player_elo: Current player's Elo rating
        opponent_elo: Opponent's Elo rating
        did_win: True if player won, False if lost
        k: K-factor (default = 32)

    Returns:
        Updated Elo rating
    """
    expected_score = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    actual_score = 1 if did_win else 0
    new_elo = player_elo + k * (actual_score - expected_score)
    return round(new_elo)


def calculate_event_k_value(start_date: datetime) -> int:
    """
    Calculate K-value based on days since event started.

    Day 0: K=16, Day 1: K=18, ... Day 8+: K=32 (capped)

    Args:
        start_date: datetime when the event started

    Returns:
        int: K-value between 16 and 32
    """
    now = datetime.now()
    days_elapsed = (now - start_date).days
    k_value = 16 + (days_elapsed * 2)
    return min(k_value, 32)


def _ensure_paper_standings_table(cur):
    """Create paper_standings table if it doesn't exist."""
    cur.execute("""CREATE TABLE IF NOT EXISTS paper_standings
                   (user_id TEXT PRIMARY KEY,
                    user_display_name TEXT,
                    paper_elo INTEGER DEFAULT 1500,
                    paper_event_elo INTEGER DEFAULT 1500
                   )""")


def get_active_event():
    """
    Get the currently active event, if any.

    Returns:
        dict with event info or None if no active event
    """
    conn = sqlite3.connect(str(ELO_DB_PATH))
    cur = conn.cursor()

    # Check if events table exists
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='events'
    """)
    if not cur.fetchone():
        conn.close()
        return None

    columns = {row[1] for row in cur.execute("PRAGMA table_info(events)")}
    avatar_column = "avatar_specific" if "avatar_specific" in columns else "0"
    cur.execute(f"""
        SELECT event_id, event_name, start_date, {avatar_column}
        FROM events
        WHERE is_active = 1
        LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "event_id": row[0],
            "event_name": row[1],
            "start_date": datetime.fromisoformat(row[2]),
            "avatar_specific": bool(row[3]),
        }
    return None


def update_paper_elo(
    user_id,
    user_display_name: str,
    did_win: bool,
    opponent_id,
    avatar_name: str | None = None,
    opponent_avatar_name: str | None = None,
) -> tuple:
    """
    Update paper ELO ratings for web-confirmed matches.

    Uses paper_standings table (TEXT PRIMARY KEY) — separate from the Discord bot's
    overall_standings table. Supports Discord IDs and large Google OAuth IDs.

    Updates both paper lifetime ELO (K=32) and paper event ELO (dynamic K) if an event is active.
    If no event is active, ELO is not updated (returns 0 changes).

    Args:
        user_id: Discord/Google user ID (stored as TEXT string)
        user_display_name: Player's display name
        did_win: True if player won, False if lost
        opponent_id: Opponent's user ID (stored as TEXT string)

    Returns:
        Tuple of (new_paper_elo, paper_change, new_paper_event_elo, paper_event_change, event_active)
    """
    # All IDs stored as TEXT strings
    user_id_str = str(user_id)
    opponent_id_str = str(opponent_id)

    conn = sqlite3.connect(str(ELO_DB_PATH))
    cur = conn.cursor()

    _ensure_paper_standings_table(cur)

    # Get player's current paper ELOs (or insert if new)
    cur.execute(
        "SELECT paper_elo, paper_event_elo FROM paper_standings WHERE user_id=?", (user_id_str,)
    )
    player_row = cur.fetchone()

    if player_row:
        player_paper_elo = player_row[0] if player_row[0] else 1500
        player_paper_event_elo = player_row[1] if player_row[1] else 1500
        logger.debug(
            "Existing player %s: paper ELO=%d, paper event ELO=%d",
            user_id_str, player_paper_elo, player_paper_event_elo,
        )
    else:
        player_paper_elo = 1500
        player_paper_event_elo = 1500
        cur.execute(
            """INSERT OR IGNORE INTO paper_standings
               (user_id, user_display_name, paper_elo, paper_event_elo) VALUES (?, ?, ?, ?)""",
            (user_id_str, user_display_name, player_paper_elo, player_paper_event_elo),
        )
        logger.debug("New player %s inserted with default paper ELOs", user_id_str)

    # Get opponent's paper ELOs (or use default if not found)
    cur.execute(
        "SELECT paper_elo, paper_event_elo FROM paper_standings WHERE user_id=?", (opponent_id_str,)
    )
    opponent_row = cur.fetchone()

    if opponent_row:
        opponent_paper_elo = opponent_row[0] if opponent_row[0] else 1500
        opponent_paper_event_elo = opponent_row[1] if opponent_row[1] else 1500
    else:
        opponent_paper_elo = 1500
        opponent_paper_event_elo = 1500

    # Check for active event
    active_event = get_active_event()

    # If no active event, don't update ELO
    if not active_event:
        logger.debug("No active event - paper ELO not updated for %s", user_id_str)
        conn.close()
        return (player_paper_elo, 0, player_paper_event_elo, 0, False)

    if active_event.get("avatar_specific"):
        avatar_name = canonicalize_avatar_name(avatar_name)
        opponent_avatar_name = canonicalize_avatar_name(opponent_avatar_name)
        if not avatar_name or not opponent_avatar_name:
            conn.close()
            raise ValueError(
                "Avatar-specific event requires catalog-valid winner and loser avatars"
            )
        cur.execute(
            """SELECT event_elo FROM event_avatar_standings
               WHERE event_id = ? AND source = 'paper' AND user_id = ?
                 AND avatar_name = ? COLLATE NOCASE""",
            (active_event["event_id"], user_id_str, avatar_name),
        )
        row = cur.fetchone()
        player_paper_event_elo = row[0] if row else 1500
        cur.execute(
            """SELECT event_elo FROM event_avatar_standings
               WHERE event_id = ? AND source = 'paper' AND user_id = ?
                 AND avatar_name = ? COLLATE NOCASE""",
            (active_event["event_id"], opponent_id_str, opponent_avatar_name),
        )
        row = cur.fetchone()
        opponent_paper_event_elo = row[0] if row else 1500

    # Calculate new paper lifetime ELO (always K=32)
    new_paper_elo = calculate_elo(
        player_paper_elo, opponent_paper_elo, did_win, k=32
    )
    paper_change = new_paper_elo - player_paper_elo

    # Calculate new paper event ELO (dynamic K based on days elapsed)
    event_k = calculate_event_k_value(active_event["start_date"])
    new_paper_event_elo = calculate_elo(
        player_paper_event_elo, opponent_paper_event_elo, did_win, k=event_k
    )
    paper_event_change = new_paper_event_elo - player_paper_event_elo

    logger.info(
        "Player %s paper ELO updated - lifetime: %d -> %d (%+d), event (K=%d): %d -> %d (%+d)",
        user_id_str, player_paper_elo, new_paper_elo, paper_change,
        event_k, player_paper_event_elo, new_paper_event_elo, paper_event_change,
    )

    # Update paper ELO in paper_standings
    if active_event.get("avatar_specific"):
        cur.execute(
            "UPDATE paper_standings SET paper_elo = ?, user_display_name = ? WHERE user_id = ?",
            (new_paper_elo, user_display_name, user_id_str),
        )
        cur.execute(
            """INSERT INTO event_avatar_standings
               (event_id, source, user_id, user_display_name, avatar_name, event_elo)
               VALUES (?, 'paper', ?, ?, ?, ?)
               ON CONFLICT(event_id, source, user_id, avatar_name)
               DO UPDATE SET user_display_name = excluded.user_display_name,
                             event_elo = excluded.event_elo""",
            (active_event["event_id"], user_id_str, user_display_name, avatar_name, new_paper_event_elo),
        )
    else:
        cur.execute(
            "UPDATE paper_standings SET paper_elo = ?, paper_event_elo = ?, user_display_name = ? WHERE user_id = ?",
            (new_paper_elo, new_paper_event_elo, user_display_name, user_id_str),
        )

    conn.commit()
    conn.close()

    return (new_paper_elo, paper_change, new_paper_event_elo, paper_event_change, True)


def update_paper_match_elos(
    winner_id,
    winner_display_name: str,
    loser_id,
    loser_display_name: str,
    winner_avatar_name: str | None = None,
    loser_avatar_name: str | None = None,
    event_snapshot: dict | None = None,
) -> tuple[tuple, tuple]:
    """Atomically update both players for one confirmed paper match.

    Legacy events retain their established sequential calculation behavior.
    Avatar-specific events calculate both players from the same pre-match
    snapshot so live updates and full ladder replays are identical.
    """
    winner_id_str = str(winner_id)
    loser_id_str = str(loser_id)
    conn = sqlite3.connect(str(ELO_DB_PATH))
    cur = conn.cursor()
    _ensure_paper_standings_table(cur)

    def get_or_create(user_id: str, display_name: str) -> tuple[int, int]:
        row = cur.execute(
            "SELECT paper_elo, paper_event_elo FROM paper_standings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return (row[0] or 1500, row[1] or 1500)
        cur.execute(
            """INSERT INTO paper_standings
               (user_id, user_display_name, paper_elo, paper_event_elo)
               VALUES (?, ?, 1500, 1500)""",
            (user_id, display_name),
        )
        return (1500, 1500)

    try:
        winner_paper_elo, winner_event_elo = get_or_create(
            winner_id_str, winner_display_name
        )
        loser_paper_elo, loser_event_elo = get_or_create(
            loser_id_str, loser_display_name
        )
        current_event = get_active_event()
        if event_snapshot:
            if (
                not current_event
                or current_event.get("event_id") != event_snapshot.get("event_id")
            ):
                raise ValueError(
                    "This match belongs to an event that is no longer active. "
                    "Please ask an admin to review it."
                )
            active_event = dict(event_snapshot)
            if isinstance(active_event.get("start_date"), str):
                active_event["start_date"] = datetime.fromisoformat(
                    active_event["start_date"]
                )
        else:
            active_event = current_event
        if not active_event:
            conn.commit()
            return (
                (winner_paper_elo, 0, winner_event_elo, 0, False),
                (loser_paper_elo, 0, loser_event_elo, 0, False),
            )

        avatar_specific = bool(active_event.get("avatar_specific"))
        if avatar_specific:
            winner_avatar_name = canonicalize_avatar_name(winner_avatar_name)
            loser_avatar_name = canonicalize_avatar_name(loser_avatar_name)
            if not winner_avatar_name or not loser_avatar_name:
                raise ValueError(
                    "Avatar-specific event requires catalog-valid winner and loser avatars"
                )
            winner_row = cur.execute(
                """SELECT event_elo FROM event_avatar_standings
                   WHERE event_id = ? AND source = 'paper' AND user_id = ?
                     AND avatar_name = ? COLLATE NOCASE""",
                (active_event["event_id"], winner_id_str, winner_avatar_name),
            ).fetchone()
            loser_row = cur.execute(
                """SELECT event_elo FROM event_avatar_standings
                   WHERE event_id = ? AND source = 'paper' AND user_id = ?
                     AND avatar_name = ? COLLATE NOCASE""",
                (active_event["event_id"], loser_id_str, loser_avatar_name),
            ).fetchone()
            winner_event_elo = winner_row[0] if winner_row else 1500
            loser_event_elo = loser_row[0] if loser_row else 1500

        event_k = calculate_event_k_value(active_event["start_date"])
        winner_new_elo = calculate_elo(winner_paper_elo, loser_paper_elo, True, k=32)
        winner_new_event_elo = calculate_elo(
            winner_event_elo, loser_event_elo, True, k=event_k
        )

        # Lifetime Elo never changes behavior based on event format. Only the
        # per-avatar event ladder is calculated from a shared pre-match snapshot.
        loser_lifetime_opponent = winner_new_elo
        loser_event_opponent = (
            winner_event_elo if avatar_specific else winner_new_event_elo
        )
        loser_new_elo = calculate_elo(
            loser_paper_elo, loser_lifetime_opponent, False, k=32
        )
        loser_new_event_elo = calculate_elo(
            loser_event_elo, loser_event_opponent, False, k=event_k
        )

        winner_change = winner_new_elo - winner_paper_elo
        loser_change = loser_new_elo - loser_paper_elo
        winner_event_change = winner_new_event_elo - winner_event_elo
        loser_event_change = loser_new_event_elo - loser_event_elo

        for user_id, display_name, lifetime_elo in (
            (winner_id_str, winner_display_name, winner_new_elo),
            (loser_id_str, loser_display_name, loser_new_elo),
        ):
            cur.execute(
                """UPDATE paper_standings
                   SET paper_elo = ?, user_display_name = ? WHERE user_id = ?""",
                (lifetime_elo, display_name, user_id),
            )

        if avatar_specific:
            for user_id, display_name, avatar_name, event_elo in (
                (
                    winner_id_str,
                    winner_display_name,
                    winner_avatar_name,
                    winner_new_event_elo,
                ),
                (
                    loser_id_str,
                    loser_display_name,
                    loser_avatar_name,
                    loser_new_event_elo,
                ),
            ):
                cur.execute(
                    """INSERT INTO event_avatar_standings
                       (event_id, source, user_id, user_display_name, avatar_name, event_elo)
                       VALUES (?, 'paper', ?, ?, ?, ?)
                       ON CONFLICT(event_id, source, user_id, avatar_name)
                       DO UPDATE SET user_display_name = excluded.user_display_name,
                                     event_elo = excluded.event_elo""",
                    (
                        active_event["event_id"],
                        user_id,
                        display_name,
                        avatar_name,
                        event_elo,
                    ),
                )
        else:
            cur.execute(
                "UPDATE paper_standings SET paper_event_elo = ? WHERE user_id = ?",
                (winner_new_event_elo, winner_id_str),
            )
            cur.execute(
                "UPDATE paper_standings SET paper_event_elo = ? WHERE user_id = ?",
                (loser_new_event_elo, loser_id_str),
            )

        conn.commit()
        logger.info(
            "Paper match ELO updated atomically: winner=%s (%+d/%+d), loser=%s (%+d/%+d)",
            winner_id_str,
            winner_change,
            winner_event_change,
            loser_id_str,
            loser_change,
            loser_event_change,
        )
        return (
            (
                winner_new_elo,
                winner_change,
                winner_new_event_elo,
                winner_event_change,
                True,
            ),
            (
                loser_new_elo,
                loser_change,
                loser_new_event_elo,
                loser_event_change,
                True,
            ),
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
