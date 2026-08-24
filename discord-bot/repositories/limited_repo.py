"""Data access layer for Limited queue (arena draft mode) tables.

Manages four separate tables in match_records.db and elo.db:
- limited_arena_runs: Arena run lifecycle tracking
- limited_match_records: Match results for limited games
- limited_active_pairings: Active pairings for limited matches
- limited_elo (in elo.db): Separate ELO tracking for limited mode
"""

import sqlite3
import datetime
import logging

logger = logging.getLogger("discord_bot")


# --- Table Creation ---


def create_limited_tables():
    """Create all limited-mode tables if they don't exist. Idempotent."""
    # Tables in match_records.db
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS limited_arena_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        user_display_name TEXT NOT NULL,
        deck_url TEXT NOT NULL,
        json_deck_data TEXT,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        starting_elo INTEGER NOT NULL DEFAULT 1500,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )""")

    cur.execute("""CREATE INDEX IF NOT EXISTS idx_limited_runs_user_status
                   ON limited_arena_runs(user_id, status)""")

    cur.execute("""CREATE TABLE IF NOT EXISTS limited_match_records (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER,
        winner_id INTEGER,
        winner_display_name TEXT,
        loser_id INTEGER,
        loser_display_name TEXT,
        did_win BOOLEAN,
        timestamp TEXT,
        first_player TEXT,
        match_time INTEGER,
        curiosa_url_winner TEXT,
        curiosa_url_loser TEXT,
        match_comment TEXT,
        json_deck_data_winner TEXT,
        json_deck_data_loser TEXT,
        winner_elo_change INTEGER,
        loser_elo_change INTEGER,
        winner_went_first TEXT,
        loser_went_first TEXT,
        winner_run_id INTEGER,
        loser_run_id INTEGER
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS limited_active_pairings (
        pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        player1_id INTEGER NOT NULL,
        player2_id INTEGER NOT NULL,
        player1_deck_url TEXT,
        player2_deck_url TEXT,
        player1_run_id INTEGER,
        player2_run_id INTEGER,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active'
    )""")

    conn.commit()
    conn.close()

    # Table in elo.db
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS limited_elo (
        user_id INTEGER PRIMARY KEY,
        user_display_name TEXT,
        elo INTEGER NOT NULL DEFAULT 1500,
        lifetime_elo INTEGER NOT NULL DEFAULT 1500
    )""")

    # Migration: add lifetime_elo column if it doesn't exist yet
    cur.execute("PRAGMA table_info(limited_elo)")
    columns = [col[1] for col in cur.fetchall()]
    if "lifetime_elo" not in columns:
        cur.execute("ALTER TABLE limited_elo ADD COLUMN lifetime_elo INTEGER NOT NULL DEFAULT 1500")
        # Initialize lifetime_elo to current elo for existing players
        cur.execute("UPDATE limited_elo SET lifetime_elo = elo WHERE lifetime_elo = 1500 AND elo != 1500")

    conn.commit()
    conn.close()

    logger.info("Limited tables created/verified successfully")


# --- Arena Run Operations ---


def create_arena_run(
    user_id: int,
    display_name: str,
    deck_url: str,
    json_deck_data: str = None,
    starting_elo: int = 1500,
) -> int:
    """Create a new arena run. Returns run_id."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO limited_arena_runs
           (user_id, user_display_name, deck_url, json_deck_data, starting_elo, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            display_name,
            deck_url,
            json_deck_data,
            starting_elo,
            datetime.datetime.now().isoformat(),
        ),
    )

    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created arena run %d for user %s (starting ELO: %d)", run_id, user_id, starting_elo)
    return run_id


def get_active_arena_run(user_id: int) -> dict | None:
    """Get the user's active arena run, or None if no active run."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT run_id, user_id, user_display_name, deck_url, json_deck_data,
                  wins, losses, starting_elo, status, created_at, completed_at
           FROM limited_arena_runs
           WHERE user_id = ? AND status = 'active'
           ORDER BY created_at DESC
           LIMIT 1""",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "run_id": row[0],
            "user_id": row[1],
            "user_display_name": row[2],
            "deck_url": row[3],
            "json_deck_data": row[4],
            "wins": row[5],
            "losses": row[6],
            "starting_elo": row[7],
            "status": row[8],
            "created_at": row[9],
            "completed_at": row[10],
        }
    return None


def get_arena_run(run_id: int) -> dict | None:
    """Get an arena run by ID."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT run_id, user_id, user_display_name, deck_url, json_deck_data,
                  wins, losses, starting_elo, status, created_at, completed_at
           FROM limited_arena_runs
           WHERE run_id = ?""",
        (run_id,),
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "run_id": row[0],
            "user_id": row[1],
            "user_display_name": row[2],
            "deck_url": row[3],
            "json_deck_data": row[4],
            "wins": row[5],
            "losses": row[6],
            "starting_elo": row[7],
            "status": row[8],
            "created_at": row[9],
            "completed_at": row[10],
        }
    return None


def get_latest_arena_run(user_id: int) -> dict | None:
    """Get the user's most recent arena run regardless of status."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT run_id, user_id, user_display_name, deck_url, json_deck_data,
                  wins, losses, starting_elo, status, created_at, completed_at
           FROM limited_arena_runs
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT 1""",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if row:
        return {
            "run_id": row[0],
            "user_id": row[1],
            "user_display_name": row[2],
            "deck_url": row[3],
            "json_deck_data": row[4],
            "wins": row[5],
            "losses": row[6],
            "starting_elo": row[7],
            "status": row[8],
            "created_at": row[9],
            "completed_at": row[10],
        }
    return None


def update_arena_run_record(run_id: int, wins: int, losses: int):
    """Update wins/losses for an arena run."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE limited_arena_runs SET wins = ?, losses = ? WHERE run_id = ?",
        (wins, losses, run_id),
    )
    conn.commit()
    conn.close()


def complete_arena_run(run_id: int, status: str = "completed"):
    """Mark an arena run as completed or forfeited."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE limited_arena_runs SET status = ?, completed_at = ? WHERE run_id = ?",
        (status, datetime.datetime.now().isoformat(), run_id),
    )
    conn.commit()
    conn.close()
    logger.info("Arena run %d marked as %s", run_id, status)


def close_all_active_runs() -> int:
    """Close all active arena runs (mark as 'closed'). No ELO penalties applied.

    Returns:
        Number of runs closed.
    """
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cur.execute(
        "UPDATE limited_arena_runs SET status = 'closed', completed_at = ? WHERE status = 'active'",
        (now,),
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    if count:
        logger.info("Closed %d active arena runs", count)
    return count


# --- Limited Match Record Operations ---


def insert_limited_match_record(
    reporter_id,
    winner_id,
    winner_display_name,
    loser_id,
    loser_display_name,
    did_win,
    first_player,
    match_time,
    curiosa_url_winner,
    curiosa_url_loser,
    match_comment,
    json_deck_data_winner,
    json_deck_data_loser,
    winner_elo_change,
    loser_elo_change,
    winner_went_first,
    loser_went_first,
    winner_run_id,
    loser_run_id,
) -> int:
    """Insert a limited match record. Returns match_id."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO limited_match_records
           (reporter_id, winner_id, winner_display_name, loser_id, loser_display_name,
            did_win, timestamp, first_player, match_time,
            curiosa_url_winner, curiosa_url_loser, match_comment,
            json_deck_data_winner, json_deck_data_loser,
            winner_elo_change, loser_elo_change,
            winner_went_first, loser_went_first,
            winner_run_id, loser_run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            reporter_id,
            winner_id,
            winner_display_name,
            loser_id,
            loser_display_name,
            did_win,
            datetime.datetime.now().isoformat(),
            first_player,
            match_time,
            curiosa_url_winner,
            curiosa_url_loser,
            match_comment,
            json_deck_data_winner,
            json_deck_data_loser,
            winner_elo_change,
            loser_elo_change,
            winner_went_first,
            loser_went_first,
            winner_run_id,
            loser_run_id,
        ),
    )

    match_id = cur.lastrowid
    conn.commit()
    conn.close()
    return match_id


# --- Limited ELO Operations ---


def get_limited_elo(user_id: int) -> int:
    """Get a user's current Limited ELO rating.

    Returns 1500 if the user has no limited ELO record.
    """
    create_limited_tables()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT elo FROM limited_elo WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 1500


def get_limited_lifetime_elo(user_id: int) -> int:
    """Get a user's lifetime Limited ELO rating.

    Returns 1500 if the user has no limited ELO record.
    """
    create_limited_tables()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT lifetime_elo FROM limited_elo WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 1500


def upsert_limited_elo(user_id: int, display_name: str, new_elo: int, elo_change: int = None):
    """Insert or update a user's Limited ELO rating.

    If elo_change is provided, lifetime_elo is also adjusted by that amount.
    If elo_change is None (e.g. admin spot fix), only season elo is set.
    """
    create_limited_tables()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    if elo_change is not None:
        cur.execute(
            """INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   user_display_name = excluded.user_display_name,
                   elo = excluded.elo,
                   lifetime_elo = lifetime_elo + ?""",
            (user_id, display_name, new_elo, 1500 + elo_change, elo_change),
        )
    else:
        cur.execute(
            """INSERT INTO limited_elo (user_id, user_display_name, elo)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   user_display_name = excluded.user_display_name,
                   elo = excluded.elo""",
            (user_id, display_name, new_elo),
        )
    conn.commit()
    conn.close()


def get_all_limited_standings() -> list[dict]:
    """Get all limited ELO standings sorted by ELO descending."""
    create_limited_tables()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, user_display_name, elo, lifetime_elo FROM limited_elo ORDER BY elo DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"user_id": row[0], "display_name": row[1], "elo": row[2], "lifetime_elo": row[3]}
        for row in rows
    ]


def get_limited_wins_count(user_id: int) -> int:
    """Get total limited match wins for a user."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM limited_match_records WHERE winner_id = ?",
        (user_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_limited_losses_count(user_id: int) -> int:
    """Get total limited match losses for a user."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM limited_match_records WHERE loser_id = ?",
        (user_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


# --- Limited Pairings Operations ---


def save_limited_pairing(
    guild_id: int,
    player1_id: int,
    player2_id: int,
    player1_deck_url: str = None,
    player2_deck_url: str = None,
    player1_run_id: int = None,
    player2_run_id: int = None,
) -> int:
    """Save a new active limited pairing. Returns pairing_id."""
    if guild_id is None:
        raise ValueError("guild_id cannot be None")

    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO limited_active_pairings
           (guild_id, player1_id, player2_id, player1_deck_url, player2_deck_url,
            player1_run_id, player2_run_id, created_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
        (
            guild_id,
            player1_id,
            player2_id,
            player1_deck_url,
            player2_deck_url,
            player1_run_id,
            player2_run_id,
            datetime.datetime.now().isoformat(),
        ),
    )

    pairing_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(
        "Saved limited pairing %d: guild=%d, p1=%d, p2=%d",
        pairing_id, guild_id, player1_id, player2_id,
    )
    return pairing_id


def get_limited_pairing_between_players(
    guild_id: int, user_id: int, opponent_id: int
) -> dict | None:
    """Get the most recent active limited pairing between two players."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT pairing_id, guild_id, player1_id, player2_id,
                  player1_deck_url, player2_deck_url,
                  player1_run_id, player2_run_id, created_at
           FROM limited_active_pairings
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
            "player1_run_id": row[6],
            "player2_run_id": row[7],
            "created_at": row[8],
        }
    return None


def get_limited_pairing_by_id(guild_id: int, pairing_id: int) -> dict | None:
    """Get a Limited pairing by its stable ID, including reported pairings."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT pairing_id, guild_id, player1_id, player2_id,
                  player1_deck_url, player2_deck_url,
                  player1_run_id, player2_run_id, created_at, status
           FROM limited_active_pairings
           WHERE guild_id = ? AND pairing_id = ?""",
        (guild_id, pairing_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_limited_pairing_reported(
    guild_id: int, user_id: int, opponent_id: int, pairing_id: int = None
) -> bool:
    """Mark a limited pairing as reported. Returns True if updated."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    if pairing_id:
        cur.execute(
            """UPDATE limited_active_pairings
               SET status = 'reported'
               WHERE pairing_id = ? AND guild_id = ? AND status = 'active'""",
            (pairing_id, guild_id),
        )
    else:
        cur.execute(
            """UPDATE limited_active_pairings
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


def get_matches_for_run(run_id: int, user_id: int) -> list[dict]:
    """Get all match records for a specific arena run, ordered chronologically."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute(
        """SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                  timestamp, winner_elo_change, loser_elo_change
           FROM limited_match_records
           WHERE winner_run_id = ? OR loser_run_id = ?
           ORDER BY timestamp ASC""",
        (run_id, run_id),
    )
    rows = cur.fetchall()
    conn.close()

    matches = []
    for row in rows:
        won = row[1] == user_id
        matches.append({
            "match_id": row[0],
            "won": won,
            "opponent_name": row[4] if won else row[2],
            "opponent_id": row[3] if won else row[1],
            "elo_change": row[6] if won else row[7],
            "timestamp": row[5],
        })
    return matches


def cleanup_old_limited_pairings(hours: int = 24):
    """Mark limited pairings older than specified hours as expired."""
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
    cur.execute(
        """UPDATE limited_active_pairings
           SET status = 'expired'
           WHERE status = 'active' AND created_at < ?""",
        (cutoff,),
    )

    conn.commit()
    conn.close()


# --- Limited Archive Tables ---


def create_limited_archive_tables():
    """Create archive tables for limited event data. Idempotent."""
    # limited_event_standings_archive in elo.db
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS limited_event_standings_archive (
        archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        event_name TEXT,
        user_id INTEGER NOT NULL,
        user_display_name TEXT,
        final_elo INTEGER,
        final_rank INTEGER,
        archived_at TEXT
    )""")
    conn.commit()
    conn.close()

    # limited_match_records_archive and limited_arena_runs_archive in match_records.db
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS limited_match_records_archive (
        archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        original_match_id INTEGER,
        reporter_id INTEGER,
        winner_id INTEGER,
        winner_display_name TEXT,
        loser_id INTEGER,
        loser_display_name TEXT,
        did_win BOOLEAN,
        timestamp TEXT,
        first_player TEXT,
        match_time INTEGER,
        curiosa_url_winner TEXT,
        curiosa_url_loser TEXT,
        match_comment TEXT,
        json_deck_data_winner TEXT,
        json_deck_data_loser TEXT,
        winner_elo_change INTEGER,
        loser_elo_change INTEGER,
        winner_went_first TEXT,
        loser_went_first TEXT,
        winner_run_id INTEGER,
        loser_run_id INTEGER,
        archived_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS limited_arena_runs_archive (
        archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        original_run_id INTEGER,
        user_id INTEGER,
        user_display_name TEXT,
        deck_url TEXT,
        wins INTEGER,
        losses INTEGER,
        starting_elo INTEGER,
        status TEXT,
        created_at TEXT,
        completed_at TEXT,
        archived_at TEXT
    )""")
    conn.commit()
    conn.close()
    logger.info("Limited archive tables created/verified successfully")


# --- Limited Archive Operations ---


def archive_limited_standings(event_id: int, event_name: str, archived_at: str) -> list:
    """Copy current limited_elo standings into the archive. Returns list of (user_id, name, elo)."""
    create_limited_archive_tables()

    conn_elo = sqlite3.connect("elo.db")
    cur = conn_elo.cursor()
    cur.execute("SELECT user_id, user_display_name, elo FROM limited_elo ORDER BY elo DESC")
    rows = cur.fetchall()

    for rank, (user_id, display_name, elo) in enumerate(rows, start=1):
        cur.execute(
            """INSERT INTO limited_event_standings_archive
               (event_id, event_name, user_id, user_display_name, final_elo, final_rank, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, event_name, user_id, display_name, elo, rank, archived_at),
        )

    conn_elo.commit()
    conn_elo.close()
    logger.info("Archived %d limited standings for event %d", len(rows), event_id)
    return [(uid, name, elo) for uid, name, elo in rows]


def archive_limited_matches(event_id: int, archived_at: str) -> int:
    """Copy limited_match_records into the archive and clear the live table. Returns count."""
    create_limited_archive_tables()

    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM limited_match_records")
    matches = cur.fetchall()
    cur.execute("PRAGMA table_info(limited_match_records)")
    columns = [col[1] for col in cur.fetchall()]

    for match in matches:
        d = dict(zip(columns, match))
        cur.execute(
            """INSERT INTO limited_match_records_archive
               (event_id, original_match_id, reporter_id, winner_id, winner_display_name,
                loser_id, loser_display_name, did_win, timestamp, first_player, match_time,
                curiosa_url_winner, curiosa_url_loser, match_comment,
                json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change,
                winner_went_first, loser_went_first,
                winner_run_id, loser_run_id, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                d.get("match_id"),
                d.get("reporter_id"),
                d.get("winner_id"),
                d.get("winner_display_name"),
                d.get("loser_id"),
                d.get("loser_display_name"),
                d.get("did_win"),
                d.get("timestamp"),
                d.get("first_player"),
                d.get("match_time"),
                d.get("curiosa_url_winner"),
                d.get("curiosa_url_loser"),
                d.get("match_comment"),
                d.get("json_deck_data_winner"),
                d.get("json_deck_data_loser"),
                d.get("winner_elo_change"),
                d.get("loser_elo_change"),
                d.get("winner_went_first"),
                d.get("loser_went_first"),
                d.get("winner_run_id"),
                d.get("loser_run_id"),
                archived_at,
            ),
        )

    cur.execute("DELETE FROM limited_match_records")
    conn.commit()
    conn.close()
    logger.info("Archived %d limited match records for event %d", len(matches), event_id)
    return len(matches)


def archive_limited_arena_runs(event_id: int, archived_at: str) -> int:
    """Copy limited_arena_runs into the archive and clear the live table. Returns count."""
    create_limited_archive_tables()

    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM limited_arena_runs")
    runs = cur.fetchall()
    cur.execute("PRAGMA table_info(limited_arena_runs)")
    columns = [col[1] for col in cur.fetchall()]

    for run in runs:
        d = dict(zip(columns, run))
        cur.execute(
            """INSERT INTO limited_arena_runs_archive
               (event_id, original_run_id, user_id, user_display_name, deck_url,
                wins, losses, starting_elo, status, created_at, completed_at, archived_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                d.get("run_id"),
                d.get("user_id"),
                d.get("user_display_name"),
                d.get("deck_url"),
                d.get("wins"),
                d.get("losses"),
                d.get("starting_elo"),
                d.get("status"),
                d.get("created_at"),
                d.get("completed_at"),
                archived_at,
            ),
        )

    cur.execute("DELETE FROM limited_arena_runs")
    cur.execute("DELETE FROM limited_active_pairings")
    conn.commit()
    conn.close()
    logger.info("Archived %d limited arena runs for event %d", len(runs), event_id)
    return len(runs)


def reset_limited_elo_to_default():
    """Reset season limited_elo entries to 1500. Lifetime ELO is preserved."""
    conn = sqlite3.connect("elo.db")
    conn.execute("UPDATE limited_elo SET elo = 1500")
    conn.commit()
    conn.close()
    logger.info("Reset all limited season ELO ratings to 1500 (lifetime preserved)")
