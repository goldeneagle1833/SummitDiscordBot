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
        elo INTEGER NOT NULL DEFAULT 1500,
        lifetime_elo INTEGER NOT NULL DEFAULT 1500
    )""")

    # Migration: add lifetime_elo column if it doesn't exist yet
    cur.execute("PRAGMA table_info(limited_elo)")
    columns = [col[1] for col in cur.fetchall()]
    if "lifetime_elo" not in columns:
        cur.execute("ALTER TABLE limited_elo ADD COLUMN lifetime_elo INTEGER NOT NULL DEFAULT 1500")
        cur.execute("UPDATE limited_elo SET lifetime_elo = elo WHERE lifetime_elo = 1500 AND elo != 1500")

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


def upsert_limited_elo(user_id, display_name, new_elo, elo_change=None):
    """Insert or update a user's Limited ELO rating.

    If elo_change is provided, lifetime_elo is also adjusted by that amount.
    If elo_change is None (e.g. admin spot fix), only season elo is set.
    """
    create_limited_tables()
    conn = _elo_conn()
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


def get_all_limited_standings():
    """Get all limited ELO standings sorted by ELO descending."""
    create_limited_tables()
    conn = _elo_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, user_display_name, elo FROM limited_elo ORDER BY elo DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"user_id": row[0], "display_name": row[1], "elo": row[2]}
        for row in rows
    ]


def get_limited_wins_count(user_id):
    """Get total limited match wins for a user."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM limited_match_records WHERE winner_id = ?",
        (user_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_limited_losses_count(user_id):
    """Get total limited match losses for a user."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM limited_match_records WHERE loser_id = ?",
        (user_id,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


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


# --- Archive fallback queries ---


def get_latest_arena_run_from_archive(user_id):
    """Get the user's most recent archived arena run, or None.

    Falls back to the archive table when the live table has no runs
    (e.g. between events after data has been archived).
    """
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_run_id, user_id, user_display_name, deck_url, NULL,
                      wins, losses, starting_elo, status, created_at, completed_at
               FROM limited_arena_runs_archive
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    return _run_from_row(row)


def get_matches_for_archived_run(original_run_id, user_id):
    """Get match records for an archived arena run, ordered chronologically."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                      timestamp, winner_elo_change, loser_elo_change
               FROM limited_match_records_archive
               WHERE winner_run_id = ? OR loser_run_id = ?
               ORDER BY timestamp ASC""",
            (original_run_id, original_run_id),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
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


def get_all_archived_matches_for_user(user_id):
    """Get all archived match records for a user across all runs, ordered chronologically."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                      timestamp, winner_elo_change, loser_elo_change
               FROM limited_match_records_archive
               WHERE winner_id = ? OR loser_id = ?
               ORDER BY timestamp ASC""",
            (user_id, user_id),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
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


def get_trophy_runs(limit=20):
    """Get completed 4-0 arena runs, newest first."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT run_id, user_id, user_display_name, deck_url, wins, losses,
                  starting_elo, created_at, completed_at
           FROM limited_arena_runs
           WHERE status = 'completed' AND wins = 4 AND losses <= 2
           ORDER BY completed_at DESC
           LIMIT ?""",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "run_id": r[0],
            "user_id": r[1],
            "user_display_name": r[2],
            "deck_url": r[3],
            "wins": r[4],
            "losses": r[5],
            "starting_elo": r[6],
            "created_at": r[7],
            "completed_at": r[8],
        }
        for r in rows
    ]


def get_run_matchups(run_id):
    """Get detailed matchup info for a run, including opponent deck URLs when their run is done."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT m.match_id, m.winner_id, m.winner_display_name,
                  m.loser_id, m.loser_display_name,
                  m.timestamp, m.winner_elo_change, m.loser_elo_change,
                  m.match_time, m.curiosa_url_winner, m.curiosa_url_loser,
                  m.winner_run_id, m.loser_run_id
           FROM limited_match_records m
           WHERE m.winner_run_id = ? OR m.loser_run_id = ?
           ORDER BY m.timestamp ASC""",
        (run_id, run_id),
    )
    rows = cur.fetchall()

    # Look up opponent run statuses to decide deck visibility
    run_ids = set()
    for r in rows:
        if r[11]:
            run_ids.add(r[11])
        if r[12]:
            run_ids.add(r[12])
    run_ids.discard(run_id)

    opponent_run_status = {}
    for rid in run_ids:
        cur.execute("SELECT status FROM limited_arena_runs WHERE run_id = ?", (rid,))
        row = cur.fetchone()
        if row:
            opponent_run_status[rid] = row[0]

    conn.close()

    matches = []
    for r in rows:
        is_viewer_winner = r[11] == run_id
        opp_run_id = r[12] if is_viewer_winner else r[11]
        opp_status = opponent_run_status.get(opp_run_id)
        opp_run_done = opp_status in ("completed", "forfeited") if opp_status else True

        match = {
            "match_id": r[0],
            "winner_id": r[1],
            "winner_name": r[2],
            "loser_id": r[3],
            "loser_name": r[4],
            "timestamp": r[5],
            "winner_elo_change": r[6],
            "loser_elo_change": r[7],
            "match_time": r[8],
            "viewer_deck_url": r[9] if is_viewer_winner else r[10],
            "opponent_deck_url": (r[10] if is_viewer_winner else r[9]) if opp_run_done else None,
        }
        matches.append(match)

    return matches


def get_all_limited_match_history():
    """Get all limited match records with deck links, ordered by newest first."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                  timestamp, curiosa_url_winner, curiosa_url_loser,
                  winner_elo_change, loser_elo_change,
                  winner_run_id, loser_run_id
           FROM limited_match_records
           ORDER BY timestamp DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    return [_match_row_to_dict(r) for r in rows]


def get_all_runs_for_user(user_id):
    """Get all arena runs for a user with win/loss records, ordered by newest first."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        _RUN_SELECT + " WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [_run_from_row(r) for r in rows]


def get_matches_for_run_with_decks(run_id):
    """Get all match records for a run including deck links."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                  timestamp, curiosa_url_winner, curiosa_url_loser,
                  winner_elo_change, loser_elo_change,
                  winner_run_id, loser_run_id
           FROM limited_match_records
           WHERE winner_run_id = ? OR loser_run_id = ?
           ORDER BY timestamp ASC""",
        (run_id, run_id),
    )
    rows = cur.fetchall()
    conn.close()
    return [_match_row_to_dict(r) for r in rows]


def _match_row_to_dict(row):
    """Convert a match record row to a dict with deck links."""
    return {
        "match_id": row[0],
        "winner_id": row[1],
        "winner_display_name": row[2],
        "loser_id": row[3],
        "loser_display_name": row[4],
        "timestamp": row[5],
        "winner_deck_url": row[6],
        "loser_deck_url": row[7],
        "winner_elo_change": row[8],
        "loser_elo_change": row[9],
        "winner_run_id": row[10],
        "loser_run_id": row[11],
    }


def get_all_archived_match_history():
    """Get all archived limited match records with deck links, ordered by newest first."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                      timestamp, curiosa_url_winner, curiosa_url_loser,
                      winner_elo_change, loser_elo_change,
                      winner_run_id, loser_run_id
               FROM limited_match_records_archive
               ORDER BY timestamp DESC"""
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [_match_row_to_dict(r) for r in rows]


def get_all_archived_runs_for_user(user_id):
    """Get all archived arena runs for a user, ordered by newest first."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_run_id, user_id, user_display_name, deck_url, NULL,
                      wins, losses, starting_elo, status, created_at, completed_at
               FROM limited_arena_runs_archive
               WHERE user_id = ?
               ORDER BY created_at DESC""",
            (user_id,),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [_run_from_row(r) for r in rows]


def get_archived_arena_run(run_id):
    """Get an archived arena run by its original run_id."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_run_id, user_id, user_display_name, deck_url, NULL,
                      wins, losses, starting_elo, status, created_at, completed_at
               FROM limited_arena_runs_archive
               WHERE original_run_id = ?""",
            (run_id,),
        )
        row = cur.fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    return _run_from_row(row)


def get_matches_for_archived_run_with_decks(run_id):
    """Get all archived match records for a run including deck links."""
    conn = _match_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT original_match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                      timestamp, curiosa_url_winner, curiosa_url_loser,
                      winner_elo_change, loser_elo_change,
                      winner_run_id, loser_run_id
               FROM limited_match_records_archive
               WHERE winner_run_id = ? OR loser_run_id = ?
               ORDER BY timestamp ASC""",
            (run_id, run_id),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [_match_row_to_dict(r) for r in rows]


def get_limited_leaderboard_stats():
    """Get aggregate limited stats: total runs, total matches, trophy count."""
    create_limited_tables()
    conn = _match_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM limited_arena_runs WHERE status IN ('completed', 'forfeited')")
    total_runs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM limited_match_records")
    total_matches = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM limited_arena_runs WHERE status = 'completed' AND wins = 4")
    trophy_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT user_id) FROM limited_arena_runs")
    unique_players = cur.fetchone()[0]

    conn.close()
    return {
        "total_runs": total_runs,
        "total_matches": total_matches,
        "trophy_runs": trophy_count,
        "unique_players": unique_players,
    }
