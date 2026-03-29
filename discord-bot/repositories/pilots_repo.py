"""Data access layer for the pilots (feature flags) table in elo.db."""

import sqlite3
import logging

logger = logging.getLogger("discord_bot")


def create_pilots_table():
    """Create the pilots table if it doesn't exist. Idempotent."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS pilots (
        name TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 0
    )""")
    conn.commit()
    conn.close()


def get_pilot(name: str) -> dict | None:
    """Get a single pilot by name. Returns dict or None."""
    create_pilots_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT name, enabled FROM pilots WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"name": row[0], "enabled": bool(row[1])}
    return None


def get_all_pilots() -> list[dict]:
    """Get all pilots."""
    create_pilots_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute("SELECT name, enabled FROM pilots ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [{"name": row[0], "enabled": bool(row[1])} for row in rows]


def set_pilot(name: str, enabled: bool):
    """Insert or update a pilot flag."""
    create_pilots_table()
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO pilots (name, enabled) VALUES (?, ?)
           ON CONFLICT(name) DO UPDATE SET enabled = ?""",
        (name, int(enabled), int(enabled)),
    )
    conn.commit()
    conn.close()
    logger.info("Pilot '%s' set to %s", name, enabled)
