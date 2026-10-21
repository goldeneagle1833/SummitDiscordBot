"""Season ticket roles in elo.db (Discord bot side).

Each season can have its own ticket role. ``!ticket_role`` creates (or picks)
next season's role and puts it on sale: Summit Store listings set to
"current season ticket" give that role. ``!start_event`` then makes the
on-sale role the season's active ticket role, so the leaderboard, top cut and
the website count only that season's ticket holders.

A season started without one keeps using TICKET_HOLDER_ROLE_IDS from config.

The web app reads the same table (web-app/services/ticket_roles.py).

status: on_sale (next season, not counted yet) | active (this season) | past
"""

import datetime
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "elo.db"


@contextmanager
def _get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_ticket_roles_table():
    with _get_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS season_ticket_roles (
                   role_id TEXT PRIMARY KEY,
                   name TEXT NOT NULL,
                   status TEXT NOT NULL,
                   event_id INTEGER,
                   created_by TEXT,
                   created_at TEXT NOT NULL,
                   activated_at TEXT
               )"""
        )


def put_role_on_sale(role_id, name: str, created_by=None) -> None:
    """Make this next season's ticket role. Replaces any other on-sale role."""
    create_ticket_roles_table()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute(
            "UPDATE season_ticket_roles SET status = 'past' "
            "WHERE status = 'on_sale' AND role_id != ?",
            (str(role_id),),
        )
        conn.execute(
            """INSERT INTO season_ticket_roles (role_id, name, status, created_by, created_at)
               VALUES (?, ?, 'on_sale', ?, ?)
               ON CONFLICT(role_id) DO UPDATE SET
                   name = excluded.name, status = 'on_sale', event_id = NULL""",
            (str(role_id), name, str(created_by) if created_by else None, now),
        )


def activate_on_sale_role(event_id: int) -> dict | None:
    """At season start: the on-sale role becomes this season's ticket role.

    The previous season's role stops counting. Returns the activated role,
    or None when nothing was on sale (the season falls back to config).
    """
    create_ticket_roles_table()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute("UPDATE season_ticket_roles SET status = 'past' WHERE status = 'active'")
        row = conn.execute(
            "SELECT * FROM season_ticket_roles WHERE status = 'on_sale' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE season_ticket_roles SET status = 'active', event_id = ?, activated_at = ? "
            "WHERE role_id = ?",
            (event_id, now, row["role_id"]),
        )
        return {**dict(row), "status": "active", "event_id": event_id}


def get_role(status: str) -> dict | None:
    """The newest on_sale or active role, or None."""
    create_ticket_roles_table()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM season_ticket_roles WHERE status = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (status,),
        ).fetchone()
    return dict(row) if row else None


def ticket_holder_role_ids(fallback) -> set[int]:
    """Roles that make someone a ticket holder this season."""
    try:
        active = get_role("active")
    except sqlite3.Error as e:
        logger.warning(f"Could not read season ticket roles: {e}")
        active = None
    if active:
        return {int(active["role_id"])}
    return {int(r) for r in fallback or ()}
