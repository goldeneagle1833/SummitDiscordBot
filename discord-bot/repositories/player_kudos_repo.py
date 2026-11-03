"""Repository for player kudos in match_records.db (Discord bot side).

A kudos is the friendly opposite of a Report Player report: from the
**Give Kudos** button on a match message a player thanks their opponent and
says why. Each kudos is tied to one recorded match between the two players
(``match_records.match_id``), one per giver per match.

Same table as web-app/repositories/player_kudos_repo.py, which also serves
the partner API, the admin list and the homepage Player of the Day.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("discord_bot")

DB_NAME = "match_records.db"

# A match older than this can no longer get kudos (same as the web app).
KUDOS_WINDOW_DAYS = 14


class KudosError(Exception):
    """``code`` is "no_match" or "already_given"."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_exists() -> bool:
    """Read-only check, so it never waits on another writer's lock."""
    conn = sqlite3.connect(DB_NAME)
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'player_kudos'"
        ).fetchone() is not None
    finally:
        conn.close()


def create_player_kudos_table():
    """Create the player_kudos table if it doesn't exist.

    Called on every kudos lookup, so it checks first with a plain read:
    CREATE ... IF NOT EXISTS opens a write transaction and could wait up to
    5 s for the bot's or website's write lock.
    """
    if _table_exists():
        return
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_kudos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                giver_id TEXT NOT NULL,
                giver_name TEXT,
                receiver_id TEXT NOT NULL,
                receiver_name TEXT,
                match_id INTEGER NOT NULL,
                pairing_id INTEGER,
                match_type TEXT,
                reasons TEXT NOT NULL DEFAULT '[]',
                message TEXT,
                anonymous INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                hidden INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_player_kudos_giver_match "
            "ON player_kudos (giver_id, match_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_kudos_receiver "
            "ON player_kudos (receiver_id, created_at)"
        )


def _matches_sql(conn, pairing_id):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    if not cols:
        return None, None
    since = (datetime.now(timezone.utc) - timedelta(days=KUDOS_WINDOW_DAYS)).strftime("%Y-%m-%d")
    pairing_col = "m.pairing_id" if "pairing_id" in cols else "NULL"
    where = """
        ((CAST(m.winner_id AS TEXT) = :giver AND CAST(m.losser_id AS TEXT) = :receiver)
          OR (CAST(m.winner_id AS TEXT) = :receiver AND CAST(m.losser_id AS TEXT) = :giver))
        AND m.timestamp >= :since AND m.match_id IS NOT NULL
    """
    if pairing_id:
        if "pairing_id" not in cols:
            return None, None
        where += " AND m.pairing_id = :pairing"
    return pairing_col, (where, since)


def find_kudos_match(giver_id, receiver_id, pairing_id=None):
    """Return {"match_id", "pairing_id", "match_type"} or None.

    Prefers the match recorded for ``pairing_id``; if that pairing has no
    recorded match (some result paths don't store the pairing), any match
    between the two in the last KUDOS_WINDOW_DAYS days counts. Raises
    KudosError("already_given") when they played but the giver already
    thanked the opponent for it.
    """
    if pairing_id:
        match = _find_kudos_match(giver_id, receiver_id, pairing_id)
        if match:
            return match
    return _find_kudos_match(giver_id, receiver_id, None)


def _find_kudos_match(giver_id, receiver_id, pairing_id=None):
    create_player_kudos_table()
    with _get_connection() as conn:
        conn.row_factory = sqlite3.Row
        pairing_col, parts = _matches_sql(conn, pairing_id)
        if not parts:
            return None
        where, since = parts
        params = {
            "giver": str(giver_id), "receiver": str(receiver_id),
            "since": since, "pairing": int(pairing_id or 0),
        }
        row = conn.execute(
            f"""
            SELECT m.match_id, {pairing_col} AS pairing_id, m.match_type
            FROM match_records m
            WHERE {where}
              AND NOT EXISTS (SELECT 1 FROM player_kudos k
                              WHERE k.giver_id = :giver AND k.match_id = m.match_id)
            ORDER BY m.timestamp DESC LIMIT 1
            """,
            params,
        ).fetchone()
        if row:
            return dict(row)
        played = conn.execute(
            f"SELECT 1 FROM match_records m WHERE {where} LIMIT 1", params
        ).fetchone()
        if played:
            raise KudosError("already_given", "Kudos were already given for this match")
        return None


def save_player_kudos(
    *,
    giver_id,
    receiver_id,
    reasons,
    message=None,
    anonymous=False,
    giver_name=None,
    receiver_name=None,
    pairing_id=None,
    source=None,
) -> int:
    """Store a kudos for the players' latest unthanked match; returns its id.

    Raises KudosError when there's no recorded match to tie it to or the
    giver already thanked this opponent for it.
    """
    match = find_kudos_match(giver_id, receiver_id, pairing_id)
    if not match:
        raise KudosError("no_match", "No recorded match between these players yet")
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO player_kudos (
                    giver_id, giver_name, receiver_id, receiver_name, match_id,
                    pairing_id, match_type, reasons, message, anonymous, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(giver_id),
                    giver_name,
                    str(receiver_id),
                    receiver_name,
                    int(match["match_id"]),
                    match.get("pairing_id") or pairing_id or None,
                    match.get("match_type"),
                    json.dumps(list(reasons or [])),
                    (message or "").strip() or None,
                    1 if anonymous else 0,
                    source,
                ),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise KudosError("already_given", "Kudos were already given for this match")
