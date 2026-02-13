"""Pure data access layer for community database (Discord servers, YouTube channels, websites)."""

import sqlite3
import datetime
import logging
from contextlib import contextmanager

logger = logging.getLogger("discord_bot")

DB_NAME = "community.db"


@contextmanager
def get_db_connection():
    """Context manager for community database connections with automatic commit/rollback."""
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_community_tables():
    """Create all community tables if they don't exist."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""CREATE TABLE IF NOT EXISTS discord_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            invite_url TEXT NOT NULL,
            state TEXT NOT NULL,
            added_by INTEGER,
            added_at TEXT
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS youtube_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_url TEXT NOT NULL,
            added_by INTEGER,
            added_at TEXT
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS websites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            url TEXT NOT NULL,
            added_by INTEGER,
            added_at TEXT
        )""")


# --- Discord Servers ---


def add_discord_server(name, invite_url, state, description="", added_by=None):
    """Add a Discord server entry. Returns the new row ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO discord_servers (name, description, invite_url, state, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, invite_url, state, added_by, datetime.datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_all_discord_servers():
    """Get all Discord servers ordered by name."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, invite_url, state FROM discord_servers ORDER BY name"
        )
        return [
            {"id": r[0], "name": r[1], "description": r[2], "invite_url": r[3], "state": r[4]}
            for r in cur.fetchall()
        ]


# --- YouTube Channels ---


def add_youtube_channel(name, channel_id, channel_url, added_by=None):
    """Add a YouTube channel entry. Returns the new row ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO youtube_channels (name, channel_id, channel_url, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, channel_id, channel_url, added_by, datetime.datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_all_youtube_channels():
    """Get all YouTube channels."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, channel_id, channel_url FROM youtube_channels ORDER BY name"
        )
        return [
            {"id": r[0], "name": r[1], "channel_id": r[2], "channel_url": r[3]}
            for r in cur.fetchall()
        ]


# --- Websites ---


def add_website(name, url, description="", added_by=None):
    """Add a website entry. Returns the new row ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO websites (name, description, url, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description, url, added_by, datetime.datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_all_websites():
    """Get all websites ordered by name."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, url FROM websites ORDER BY name")
        return [
            {"id": r[0], "name": r[1], "description": r[2], "url": r[3]}
            for r in cur.fetchall()
        ]


# --- Generic removal ---


VALID_TABLES = {"discord_servers", "youtube_channels", "websites"}


def remove_entry(table, entry_id):
    """Remove an entry by table name and ID. Returns True if a row was deleted."""
    if table not in VALID_TABLES:
        raise ValueError(f"Invalid table: {table}. Must be one of {VALID_TABLES}")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
        return cur.rowcount > 0
