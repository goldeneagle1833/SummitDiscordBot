"""Repository for dust code storage and drop tracking."""

import datetime
import sqlite3
from contextlib import contextmanager


@contextmanager
def _get_connection():
    """Context manager for match_records.db connections."""
    conn = sqlite3.connect("match_records.db")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_dust_tables():
    """Create dust_codes and dust_drops tables if they don't exist."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS dust_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            donor_id INTEGER,
            donor_name TEXT,
            claimed_by_id INTEGER,
            claimed_by_name TEXT,
            donated_at TEXT NOT NULL,
            claimed_at TEXT,
            season_name TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS dust_drops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            games_since_reset INTEGER NOT NULL DEFAULT 0,
            last_reset_at TEXT NOT NULL,
            last_drop_game_number INTEGER,
            dropped_this_cycle INTEGER NOT NULL DEFAULT 0
        )""")
        # Migrate: add dropped_this_cycle column if missing
        cur.execute("PRAGMA table_info(dust_drops)")
        columns = [row[1] for row in cur.fetchall()]
        if "dropped_this_cycle" not in columns:
            cur.execute("ALTER TABLE dust_drops ADD COLUMN dropped_this_cycle INTEGER NOT NULL DEFAULT 0")
            # If a drop already happened this cycle, lock it
            cur.execute("UPDATE dust_drops SET dropped_this_cycle = 1 WHERE last_drop_game_number IS NOT NULL")
        # Ensure exactly one tracking row exists
        cur.execute("SELECT COUNT(*) FROM dust_drops")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO dust_drops (games_since_reset, last_reset_at) VALUES (0, ?)",
                (datetime.datetime.now().isoformat(),),
            )


def add_dust_code(code, donor_id, donor_name):
    """Store a new dust code as available."""
    with _get_connection() as conn:
        conn.cursor().execute(
            """INSERT INTO dust_codes (code, status, donor_id, donor_name, donated_at)
               VALUES (?, 'available', ?, ?, ?)""",
            (code, donor_id, donor_name, datetime.datetime.now().isoformat()),
        )


def get_available_code_count():
    """Return the number of unclaimed dust codes."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dust_codes WHERE status = 'available'")
        return cur.fetchone()[0]


def claim_next_code(player_id, player_name, season_name):
    """Claim the oldest available code for a player.

    Returns the code string, or None if no codes are available.
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, code FROM dust_codes WHERE status = 'available' ORDER BY id ASC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        code_id, code = row
        cur.execute(
            """UPDATE dust_codes
               SET status = 'claimed', claimed_by_id = ?, claimed_by_name = ?,
                   claimed_at = ?, season_name = ?
               WHERE id = ?""",
            (player_id, player_name, datetime.datetime.now().isoformat(), season_name, code_id),
        )
        return code


def has_player_claimed_this_season(player_id, season_name):
    """Check if a player already received a dust code this season."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dust_codes WHERE claimed_by_id = ? AND season_name = ?",
            (player_id, season_name),
        )
        return cur.fetchone()[0] > 0


def increment_game_counter():
    """Increment the global game counter and return (games_since_reset, drop_chance, locked).

    Resets the counter and lock back to 0 when it reaches 100.
    Drop chance starts at 0.1% and increases by 0.05% each game.
    Once a code drops in a 100-game cycle, locked=True for the rest.
    """
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT games_since_reset, dropped_this_cycle FROM dust_drops WHERE id = 1")
        current, dropped = cur.fetchone()
        new_count = current + 1

        if new_count >= 100:
            # Reset after 100 games
            cur.execute(
                "UPDATE dust_drops SET games_since_reset = 0, dropped_this_cycle = 0, last_reset_at = ? WHERE id = 1",
                (datetime.datetime.now().isoformat(),),
            )
        else:
            cur.execute(
                "UPDATE dust_drops SET games_since_reset = ? WHERE id = 1",
                (new_count,),
            )

        # Drop chance: 0.02% per game, capped at 2%
        drop_chance = min(new_count * 0.0002, 0.02)
        locked = bool(dropped)
        return new_count, drop_chance, locked


def record_drop(game_number):
    """Record that a drop happened at this game number and lock the cycle."""
    with _get_connection() as conn:
        conn.cursor().execute(
            "UPDATE dust_drops SET last_drop_game_number = ?, dropped_this_cycle = 1 WHERE id = 1",
            (game_number,),
        )


def get_drop_status():
    """Return current drop tracking info as a dict."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT games_since_reset, last_reset_at, last_drop_game_number, dropped_this_cycle FROM dust_drops WHERE id = 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        games = row[0]
        dropped = bool(row[3])
        # Next game would be games+1, chance = 0.02% per game, capped at 2%
        next_chance = min((games + 1) * 0.0002, 0.02)
        return {
            "games_since_reset": games,
            "current_chance": "LOCKED" if dropped else f"{next_chance:.2%}",
            "last_reset_at": row[1],
            "last_drop_game": row[2],
            "dropped_this_cycle": dropped,
        }


def code_exists(code):
    """Check if a code has already been loaded."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dust_codes WHERE code = ?", (code,))
        return cur.fetchone()[0] > 0
