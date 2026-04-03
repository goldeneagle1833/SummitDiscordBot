"""Data access layer for Limited queue (arena draft mode) tables.

Manages tables in match_records.db and elo.db:
- limited_arena_runs: Arena run lifecycle tracking
- limited_match_records: Match results for limited games
- limited_active_pairings: Active pairings for limited matches
- limited_elo (in elo.db): Separate ELO tracking for limited mode
"""

import sqlite3
import datetime
import logging

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH

logger = logging.getLogger(__name__)


def _match_conn():
    return sqlite3.connect(str(MATCH_RECORDS_DB_PATH))


def _elo_conn():
    return sqlite3.connect(str(ELO_DB_PATH))


def create_limited_tables():
    """Create all limited-mode tables if they don't exist. Idempotent."""
    conn = _match_conn()
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

    conn = _elo_conn()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS limited_elo (
        user_id INTEGER PRIMARY KEY,
        user_display_name TEXT,
        elo INTEGER NOT NULL DEFAULT 1500
    )""")

    conn.commit()
    conn.close()


def _run_from_row(row):
    """Convert a run row tuple to a dict."""
    if not row:
        return None
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


_RUN_SELECT = """SELECT run_id, user_id, user_display_name, deck_url, json_deck_data,
                        wins, losses, starting_elo, status, created_at, completed_at
                 FROM limited_arena_runs"""


def create_arena_run(user_id, display_name, deck_url, json_deck_data=None, starting_elo=1500):
    """Create a new arena run. Returns run_id."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO limited_arena_runs
           (user_id, user_display_name, deck_url, json_deck_data, starting_elo, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, display_name, deck_url, json_deck_data, starting_elo,
         datetime.datetime.now().isoformat()),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def get_active_arena_run(user_id):
    """Get the user's active arena run, or None."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        _RUN_SELECT + " WHERE user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return _run_from_row(row)


def get_arena_run(run_id):
    """Get an arena run by ID."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(_RUN_SELECT + " WHERE run_id = ?", (run_id,))
    row = cur.fetchone()
    conn.close()
    return _run_from_row(row)


def get_latest_arena_run(user_id):
    """Get the user's most recent arena run regardless of status."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        _RUN_SELECT + " WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return _run_from_row(row)


def update_arena_run_record(run_id, wins, losses):
    """Update wins/losses for an arena run."""
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE limited_arena_runs SET wins = ?, losses = ? WHERE run_id = ?",
        (wins, losses, run_id),
    )
    conn.commit()
    conn.close()


def complete_arena_run(run_id, status="completed"):
    """Mark an arena run as completed or forfeited."""
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE limited_arena_runs SET status = ?, completed_at = ? WHERE run_id = ?",
        (status, datetime.datetime.now().isoformat(), run_id),
    )
    conn.commit()
    conn.close()


def get_limited_elo(user_id):
    """Get a user's current Limited ELO rating. Returns 1500 if no record."""
    create_limited_tables()
    conn = _elo_conn()
    cur = conn.cursor()
    cur.execute("SELECT elo FROM limited_elo WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else 1500


def upsert_limited_elo(user_id, display_name, new_elo):
    """Insert or update a user's Limited ELO rating."""
    create_limited_tables()
    conn = _elo_conn()
    cur = conn.cursor()
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


def insert_limited_match_record(
    reporter_id, winner_id, winner_display_name, loser_id, loser_display_name,
    did_win, first_player, match_time, curiosa_url_winner, curiosa_url_loser,
    match_comment, json_deck_data_winner, json_deck_data_loser,
    winner_elo_change, loser_elo_change, winner_went_first, loser_went_first,
    winner_run_id, loser_run_id,
):
    """Insert a limited match record. Returns match_id."""
    create_limited_tables()
    conn = _match_conn()
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
            reporter_id, winner_id, winner_display_name, loser_id, loser_display_name,
            did_win, datetime.datetime.now().isoformat(), first_player, match_time,
            curiosa_url_winner, curiosa_url_loser, match_comment,
            json_deck_data_winner, json_deck_data_loser,
            winner_elo_change, loser_elo_change,
            winner_went_first, loser_went_first,
            winner_run_id, loser_run_id,
        ),
    )
    match_id = cur.lastrowid
    conn.commit()
    conn.close()
    return match_id


def get_matches_for_run(run_id, user_id):
    """Get all match records for a specific arena run, ordered chronologically."""
    create_limited_tables()
    conn = _match_conn()
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
