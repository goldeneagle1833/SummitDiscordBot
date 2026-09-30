"""Per-avatar event ELO: storage for Avatar-mode events.

Each event runs in one of two modes, chosen when it starts and locked from
then on (a trigger on ``events`` refuses any change):

- ``player``: one event ELO per player (``overall_standings.online_event_elo``).
- ``avatar``: one event ELO per (player, avatar), stored here. Every row
  carries its event, so an ended event's rows are its archive.
"""

import datetime
import sqlite3

PLAYER_MODE = "player"
AVATAR_MODE = "avatar"
ELO_MODES = (PLAYER_MODE, AVATAR_MODE)

START_ELO = 1500

_ELO_DB = "elo.db"


def ensure_avatar_elo_schema(conn: sqlite3.Connection) -> None:
    """Add the mode column, its lock and the per-avatar table to elo.db.

    Takes an open connection so create_events_table() can run it alongside
    the events table. The web app runs the same statements in its migration.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    if "elo_mode" not in columns:
        conn.execute(
            "ALTER TABLE events ADD COLUMN elo_mode TEXT NOT NULL DEFAULT 'player' "
            "CHECK (elo_mode IN ('player', 'avatar'))"
        )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS events_elo_mode_locked
           BEFORE UPDATE OF elo_mode ON events
           WHEN OLD.elo_mode IS NOT NEW.elo_mode
           BEGIN
               SELECT RAISE(ABORT, 'elo_mode cannot change after an event starts');
           END"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS event_avatar_standings (
               event_id          INTEGER NOT NULL,
               user_id           INTEGER NOT NULL,
               avatar            TEXT    NOT NULL,
               user_display_name TEXT,
               event_elo         INTEGER NOT NULL DEFAULT 1500,
               games_played      INTEGER NOT NULL DEFAULT 0,
               last_played_at    TEXT,
               PRIMARY KEY (event_id, user_id, avatar)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_avatar_standings_ladder "
        "ON event_avatar_standings (event_id, event_elo DESC)"
    )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_ELO_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_avatar_event_elo(event_id: int, user_id: int, avatar: str) -> int:
    """A player's event ELO on one avatar (1500 before their first game)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT event_elo FROM event_avatar_standings "
            "WHERE event_id = ? AND user_id = ? AND avatar = ?",
            (event_id, user_id, avatar),
        ).fetchone()
    finally:
        conn.close()
    return row["event_elo"] if row else START_ELO


def record_avatar_results(event_id: int, results) -> None:
    """Write both players' new avatar ELOs for one match in a single transaction.

    ``results`` is an iterable of (user_id, display_name, avatar, new_elo).
    Each row's games_played goes up by one.
    """
    now = datetime.datetime.now().isoformat()
    conn = _connect()
    try:
        for user_id, display_name, avatar, new_elo in results:
            conn.execute(
                """INSERT INTO event_avatar_standings
                       (event_id, user_id, avatar, user_display_name, event_elo,
                        games_played, last_played_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT (event_id, user_id, avatar) DO UPDATE SET
                       event_elo = excluded.event_elo,
                       user_display_name = COALESCE(excluded.user_display_name, user_display_name),
                       games_played = games_played + 1,
                       last_played_at = excluded.last_played_at""",
                (event_id, user_id, avatar, display_name, new_elo, now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def adjust_avatar_event_elo(
    event_id: int, user_id: int, avatar: str, elo_delta: int, games_delta: int = 0,
) -> None:
    """Shift an existing entry (used when a match is removed or corrected)."""
    conn = _connect()
    try:
        conn.execute(
            """UPDATE event_avatar_standings
               SET event_elo = event_elo + ?,
                   games_played = MAX(games_played + ?, 0)
               WHERE event_id = ? AND user_id = ? AND avatar = ?""",
            (elo_delta, games_delta, event_id, user_id, avatar),
        )
        conn.commit()
    finally:
        conn.close()


def set_avatar_event_elo(
    event_id: int, user_id: int, display_name: str, avatar: str, elo: int,
) -> int | None:
    """Set one entry's ELO (admin spot reset). Returns the previous value."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT event_elo FROM event_avatar_standings "
            "WHERE event_id = ? AND user_id = ? AND avatar = ?",
            (event_id, user_id, avatar),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE event_avatar_standings SET event_elo = ?, user_display_name = ? "
                "WHERE event_id = ? AND user_id = ? AND avatar = ?",
                (elo, display_name, event_id, user_id, avatar),
            )
        else:
            conn.execute(
                "INSERT INTO event_avatar_standings "
                "(event_id, user_id, avatar, user_display_name, event_elo) VALUES (?, ?, ?, ?, ?)",
                (event_id, user_id, avatar, display_name, elo),
            )
        conn.commit()
    finally:
        conn.close()
    return row["event_elo"] if row else None


def get_avatar_standings(event_id: int) -> list[dict]:
    """Every (player, avatar) entry of an event, best first."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT user_id, avatar, user_display_name, event_elo, games_played, last_played_at
               FROM event_avatar_standings
               WHERE event_id = ? AND games_played > 0
               ORDER BY event_elo DESC, games_played DESC, user_id ASC, avatar ASC""",
            (event_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_player_avatar_standings(event_id: int, user_id: int) -> list[dict]:
    """One player's avatar entries in an event, with each entry's ladder rank."""
    ladder = get_avatar_standings(event_id)
    return [
        {**entry, "rank": rank}
        for rank, entry in enumerate(ladder, start=1)
        if entry["user_id"] == user_id
    ]


def delete_player_avatar_standings(user_id: int, event_id: int | None = None) -> int:
    """Remove a player's avatar entries (one event, or all of them)."""
    conn = _connect()
    try:
        if event_id is None:
            cur = conn.execute("DELETE FROM event_avatar_standings WHERE user_id = ?", (user_id,))
        else:
            cur = conn.execute(
                "DELETE FROM event_avatar_standings WHERE user_id = ? AND event_id = ?",
                (user_id, event_id),
            )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
