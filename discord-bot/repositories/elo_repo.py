"""Pure data access layer for ELO, match records, and event databases."""

import sqlite3
import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")


@contextmanager
def get_db_connection(db_name):
    """Context manager for database connections with automatic commit/rollback."""
    conn = sqlite3.connect(db_name)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Table Creation / Migration ---


def create_db():
    """Create all required database tables if they don't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Create match_records table with auto-increment match_id
    cur.execute("""CREATE TABLE IF NOT EXISTS match_records
                   (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER,
                    winner_id INTEGER,
                    winner_display_name TEXT,
                    losser_id INTEGER,
                    losser_display_name TEXT,
                    did_win BOOLEAN,
                    timestamp TEXT,
                    first_player TEXT,
                    match_time INTEGER,
                    curiosa_url TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT,
                    winner_elo_change INTEGER,
                    loser_elo_change INTEGER
                   )""")

    # Add match_id column if it doesn't exist (migration for existing databases)
    try:
        cur.execute(
            "ALTER TABLE match_records ADD COLUMN match_id INTEGER PRIMARY KEY AUTOINCREMENT"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists or table was created with it

    # Add elo_change columns if they don't exist (migration for existing databases)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN winner_elo_change INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN loser_elo_change INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add new deck columns for winner and loser (Phase 1 migration)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN curiosa_url_winner TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN curiosa_url_loser TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN json_deck_data_winner TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN json_deck_data_loser TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add winner/loser went first columns (replaces ambiguous first_player)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN winner_went_first TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN loser_went_first TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add source column (Discord vs external sources)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN source TEXT DEFAULT 'Discord'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    cur.execute("UPDATE match_records SET source = 'Discord' WHERE source IS NULL")

    # Add match_type column (ranked vs testing/casual)
    try:
        cur.execute("ALTER TABLE match_records ADD COLUMN match_type TEXT DEFAULT 'ranked'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    cur.execute("UPDATE match_records SET match_type = 'ranked' WHERE match_type IS NULL")

    # Create solo_match_reports table with auto-increment report_id
    cur.execute("""CREATE TABLE IF NOT EXISTS solo_match_reports
                   (report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER,
                    reporter_name TEXT,
                    opponent_name TEXT,
                    is_winner BOOLEAN,
                    first_player TEXT,
                    match_time INTEGER,
                    curiosa_link TEXT,
                    match_comment TEXT,
                    report_date DATETIME,
                    json_deck_data TEXT
                   )""")

    conn.commit()
    conn.close()

    # Create admin audit log table
    from repositories.audit_repo import create_audit_table
    create_audit_table()

    # Create user_links table
    create_user_links_table()


def create_challenge_db():
    """Create the challenge_matches table if it doesn't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS challenge_matches
                   (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenger_id INTEGER NOT NULL,
                    challenged_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    match_time DATETIME NOT NULL,
                    winner_id INTEGER,
                    curiosa_url TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT
                   )""")

    conn.commit()
    conn.close()


def create_events_table():
    """Create the events table for tracking event-based ELO seasons."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    is_active BOOLEAN DEFAULT 1
                   )""")

    # Create event standings archive table
    cur.execute("""CREATE TABLE IF NOT EXISTS event_standings_archive (
                    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_display_name TEXT,
                    final_event_elo INTEGER,
                    final_rank INTEGER,
                    archived_at TEXT
                   )""")

    conn.commit()
    conn.close()


def create_match_records_archive():
    """Create the match_records_archive table for archived event matches."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS match_records_archive (
                    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    original_match_id INTEGER,
                    reporter_id INTEGER,
                    winner_id INTEGER,
                    winner_display_name TEXT,
                    losser_id INTEGER,
                    losser_display_name TEXT,
                    did_win BOOLEAN,
                    timestamp TEXT,
                    first_player TEXT,
                    match_time INTEGER,
                    curiosa_url TEXT,
                    curiosa_url_winner TEXT,
                    curiosa_url_loser TEXT,
                    match_comment TEXT,
                    json_deck_data TEXT,
                    json_deck_data_winner TEXT,
                    json_deck_data_loser TEXT,
                    winner_elo_change INTEGER,
                    loser_elo_change INTEGER,
                    winner_lifetime_elo_change INTEGER,
                    loser_lifetime_elo_change INTEGER,
                    archived_at TEXT
                   )""")

    conn.commit()
    conn.close()


def create_ladder_challenge_table():
    """Create the ladder_challenges table if it doesn't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS ladder_challenges
                   (challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    challenger_id INTEGER NOT NULL,
                    selected_opponent_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    winner_id INTEGER,
                    match_id INTEGER
                   )""")

    conn.commit()
    conn.close()


def create_active_pairings_table():
    """Create the active_pairings table if it doesn't exist."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS active_pairings
                   (pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    player1_id INTEGER NOT NULL,
                    player2_id INTEGER NOT NULL,
                    player1_deck_url TEXT,
                    player2_deck_url TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                   )""")

    # Migration: add guild_id column if it doesn't exist (for existing tables)
    try:
        cur.execute("ALTER TABLE active_pairings ADD COLUMN guild_id INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()


def ensure_event_elo_column():
    """Add event_elo column to overall_standings if it doesn't exist."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    try:
        cur.execute(
            "ALTER TABLE overall_standings ADD COLUMN event_elo INTEGER DEFAULT 1500"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()



def create_user_links_table():
    """Create the user_links table for cross-source account linking."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS user_links
                   (discord_user_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    source_user_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY (source, source_user_id)
                   )""")

    conn.commit()
    conn.close()


# --- Read Operations ---


def get_active_event():
    """
    Get the currently active event, if any.

    Returns:
        dict with event info or None if no active event
    """
    create_events_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""SELECT event_id, event_name, start_date
                   FROM events
                   WHERE is_active = 1
                   LIMIT 1""")
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "event_id": row[0],
            "event_name": row[1],
            "start_date": datetime.datetime.fromisoformat(row[2]),
        }
    return None


def get_user_elo(user_id: int) -> int:
    """
    Get a user's current ELO from the database.

    Args:
        user_id: The Discord user ID

    Returns:
        The user's current ELO, or 1500 if not found
    """
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT elo FROM overall_standings WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 1500


def get_user_event_elo(user_id: int) -> int:
    """
    Get a user's current event ELO from the database.

    Args:
        user_id: The Discord user ID

    Returns:
        The user's current event ELO, or 1500 if not found
    """
    ensure_event_elo_column()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT event_elo FROM overall_standings WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 1500


def get_past_events():
    """
    Get a list of all past (ended) events.

    Returns:
        List of dicts with event info
    """
    create_events_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""SELECT event_id, event_name, start_date, end_date
                   FROM events
                   WHERE is_active = 0
                   ORDER BY end_date DESC""")
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "event_id": row[0],
            "event_name": row[1],
            "start_date": row[2],
            "end_date": row[3],
        }
        for row in rows
    ]


def get_event_archive_standings(event_id: int):
    """
    Get archived standings for a specific event.

    Args:
        event_id: The event ID to get standings for

    Returns:
        List of tuples (rank, display_name, final_elo)
    """
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT final_rank, user_display_name, final_event_elo
                   FROM event_standings_archive
                   WHERE event_id = ?
                   ORDER BY final_rank ASC
                   LIMIT 16""",
        (event_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return rows


def get_top_16_user_ids():
    """
    Get the user IDs of the top 16 players by current event ELO.

    Only counts players who have played at least one event match (event_elo != 1500).
    Falls back to lifetime ELO if no active event.

    Returns:
        List of user_id integers for the top 16 players
    """
    ensure_event_elo_column()
    active_event = get_active_event()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    if active_event:
        cur.execute(
            "SELECT user_id FROM overall_standings WHERE event_elo != 1500 ORDER BY event_elo DESC LIMIT 16"
        )
    else:
        cur.execute("SELECT user_id FROM overall_standings ORDER BY elo DESC LIMIT 16")

    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_total_match_count():
    """Get the total number of matches recorded in the database."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM match_records")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_ladder_challenge_today(user_id: int) -> bool:
    """
    Check if a user has already issued a ladder challenge today.

    Args:
        user_id: The Discord user ID

    Returns:
        True if they already used their challenge today, False otherwise
    """
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "SELECT COUNT(*) FROM ladder_challenges WHERE challenger_id = ? AND created_at LIKE ?",
        (user_id, f"{today}%"),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


# --- Write Operations ---


def save_ladder_challenge(challenger_id: int, selected_opponent_id: int = None) -> int:
    """
    Save a ladder challenge to the database.

    Args:
        challenger_id: ID of the Top 16 player who issued the challenge
        selected_opponent_id: ID of the randomly selected opponent (if any)

    Returns:
        The challenge_id
    """
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO ladder_challenges (challenger_id, selected_opponent_id, status, created_at)
           VALUES (?, ?, 'open', ?)""",
        (challenger_id, selected_opponent_id, datetime.datetime.now().isoformat()),
    )

    challenge_id = cur.lastrowid
    conn.commit()
    conn.close()
    return challenge_id


def delete_ladder_challenge(challenge_id: int):
    """Delete a ladder challenge record (used when no one joins so it doesn't count as daily use)."""
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM ladder_challenges WHERE challenge_id = ?", (challenge_id,))
    conn.commit()
    conn.close()


def complete_ladder_challenge(challenge_id: int, winner_id: int, match_id: int = None):
    """Mark a ladder challenge as completed."""
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """UPDATE ladder_challenges SET status = 'completed', completed_at = ?, winner_id = ?, match_id = ?
           WHERE challenge_id = ?""",
        (datetime.datetime.now().isoformat(), winner_id, match_id, challenge_id),
    )

    conn.commit()
    conn.close()


async def save_challenge_match(
    challenger_id: int, challenged_id: int, status: str, winner_id: int = None
):
    """
    Save a challenge match to the database.

    Args:
        challenger_id: ID of the player who initiated the challenge
        challenged_id: ID of the player who was challenged
        status: Match status ('pending', 'completed', 'declined', 'cancelled')
        winner_id: ID of the winning player (if match is completed)
    """
    create_challenge_db()
    conn = sqlite3.connect("match_records.db")
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO challenge_matches
            (challenger_id, challenged_id, status, match_time, winner_id)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
        """,
            (challenger_id, challenged_id, status, winner_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving challenge match: {e}")
    finally:
        conn.close()


# --- Active Pairings Operations ---


def save_pairing(
    guild_id: int,
    player1_id: int,
    player2_id: int,
    player1_deck_url: str = None,
    player2_deck_url: str = None,
) -> int:
    """
    Save a new active pairing to the database.

    Args:
        guild_id: Discord guild/server ID
        player1_id: Discord ID of first player
        player2_id: Discord ID of second player
        player1_deck_url: Optional deck URL for player 1
        player2_deck_url: Optional deck URL for player 2

    Returns:
        The pairing_id of the created record
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO active_pairings
           (guild_id, player1_id, player2_id, player1_deck_url, player2_deck_url, created_at, status)
           VALUES (?, ?, ?, ?, ?, ?, 'active')""",
        (
            guild_id,
            player1_id,
            player2_id,
            player1_deck_url,
            player2_deck_url,
            datetime.datetime.now().isoformat(),
        ),
    )

    pairing_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pairing_id


def get_active_pairing_for_user(guild_id: int, user_id: int) -> dict | None:
    """
    Get the active pairing for a user in a specific guild.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of the user

    Returns:
        Dict with pairing info or None if no active pairing
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT pairing_id, guild_id, player1_id, player2_id, player1_deck_url, player2_deck_url, created_at
           FROM active_pairings
           WHERE guild_id = ? AND (player1_id = ? OR player2_id = ?) AND status = 'active'
           ORDER BY created_at DESC
           LIMIT 1""",
        (guild_id, user_id, user_id),
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "pairing_id": row[0],
            "guild_id": row[1],
            "player1_id": row[2],
            "player2_id": row[3],
            "player1_deck_url": row[4],
            "player2_deck_url": row[5],
            "created_at": row[6],
        }
    return None


def get_opponent_from_pairing(guild_id: int, user_id: int) -> int | None:
    """
    Get the opponent ID from an active pairing in a specific guild.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of the user

    Returns:
        The opponent's Discord ID or None if no active pairing
    """
    pairing = get_active_pairing_for_user(guild_id, user_id)
    if pairing:
        if pairing["player1_id"] == user_id:
            return pairing["player2_id"]
        return pairing["player1_id"]
    return None


def get_pairing_between_players(guild_id: int, user_id: int, opponent_id: int) -> dict | None:
    """
    Get the most recent active pairing between two specific players.

    Searches by both player IDs to find the exact pairing, ordered by
    most recent first. This handles cases where old pairings were never reported.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of one player
        opponent_id: Discord ID of the other player

    Returns:
        Dict with pairing info or None if no active pairing between these players
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT pairing_id, guild_id, player1_id, player2_id, player1_deck_url, player2_deck_url, created_at
           FROM active_pairings
           WHERE guild_id = ? AND status = 'active'
           AND ((player1_id = ? AND player2_id = ?) OR (player1_id = ? AND player2_id = ?))
           ORDER BY created_at DESC
           LIMIT 1""",
        (guild_id, user_id, opponent_id, opponent_id, user_id),
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "pairing_id": row[0],
            "guild_id": row[1],
            "player1_id": row[2],
            "player2_id": row[3],
            "player1_deck_url": row[4],
            "player2_deck_url": row[5],
            "created_at": row[6],
        }
    return None


def validate_pairing(guild_id: int, user_id: int, opponent_id: int) -> bool:
    """
    Validate that a user has an active pairing with a specific opponent in a guild.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of the user
        opponent_id: Discord ID of the claimed opponent

    Returns:
        True if there's an active pairing between these users, False otherwise
    """
    pairing = get_active_pairing_for_user(guild_id, user_id)
    if not pairing:
        return False

    # Check if the opponent matches either player in the pairing
    players = {pairing["player1_id"], pairing["player2_id"]}
    return user_id in players and opponent_id in players


def mark_pairing_reported(guild_id: int, user_id: int, opponent_id: int) -> bool:
    """
    Mark a pairing as reported (match result submitted).

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of one player
        opponent_id: Discord ID of the other player

    Returns:
        True if a pairing was updated, False otherwise
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """UPDATE active_pairings
           SET status = 'reported'
           WHERE status = 'active'
           AND guild_id = ?
           AND ((player1_id = ? AND player2_id = ?) OR (player1_id = ? AND player2_id = ?))""",
        (guild_id, user_id, opponent_id, opponent_id, user_id),
    )

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def cancel_pairing(guild_id: int, user_id: int) -> bool:
    """
    Cancel an active pairing for a user in a specific guild.

    Args:
        guild_id: Discord guild/server ID
        user_id: Discord ID of the user

    Returns:
        True if a pairing was cancelled, False otherwise
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """UPDATE active_pairings
           SET status = 'cancelled'
           WHERE status = 'active'
           AND guild_id = ?
           AND (player1_id = ? OR player2_id = ?)""",
        (guild_id, user_id, user_id),
    )

    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def cleanup_old_pairings(hours: int = 24):
    """
    Clean up pairings older than the specified hours.
    Marks them as 'expired' if still active.

    Args:
        hours: Number of hours after which to expire pairings
    """
    create_active_pairings_table()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()

    cur.execute(
        """UPDATE active_pairings
           SET status = 'expired'
           WHERE status = 'active' AND created_at < ?""",
        (cutoff,),
    )

    conn.commit()
    conn.close()
