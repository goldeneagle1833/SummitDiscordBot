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

    cur.execute("""
        SELECT event_id, event_name, start_date
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
        }
    return None


def update_paper_elo(user_id, user_display_name: str, did_win: bool, opponent_id) -> tuple:
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
    cur.execute(
        "UPDATE paper_standings SET paper_elo = ?, paper_event_elo = ?, user_display_name = ? WHERE user_id = ?",
        (new_paper_elo, new_paper_event_elo, user_display_name, user_id_str),
    )

    conn.commit()
    conn.close()

    return (new_paper_elo, paper_change, new_paper_event_elo, paper_event_change, True)
