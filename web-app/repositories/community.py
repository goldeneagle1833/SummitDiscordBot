"""Repository for community database access."""

import sqlite3
import datetime
from pathlib import Path

from webapp_config import COMMUNITY_DB_PATH


class CommunityRepository:
    """Data access for community.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or COMMUNITY_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            exists = cur.fetchone() is not None
            conn.close()
            return exists
        except Exception:
            return False

    def get_discord_servers(self) -> list[dict]:
        """Get all Discord servers ordered by name."""
        if not self._table_exists("discord_servers"):
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, invite_url, state "
            "FROM discord_servers ORDER BY name"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "description": r[2], "invite_url": r[3], "state": r[4]}
            for r in rows
        ]

    def get_youtube_channels(self) -> list[dict]:
        """Get all YouTube channels."""
        if not self._table_exists("youtube_channels"):
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, channel_id, channel_url "
            "FROM youtube_channels ORDER BY name"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "channel_id": r[2], "channel_url": r[3]}
            for r in rows
        ]

    def get_websites(self) -> list[dict]:
        """Get all websites ordered by name."""
        if not self._table_exists("websites"):
            return []
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, url FROM websites ORDER BY name")
        rows = cur.fetchall()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "description": r[2], "url": r[3]}
            for r in rows
        ]

    def add_discord_server(self, name: str, invite_url: str, state: str, description: str = "", added_by: str | None = None) -> int:
        """Add a Discord server entry. Returns the new row ID."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO discord_servers (name, description, invite_url, state, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, invite_url, state, added_by, datetime.datetime.now().isoformat()),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def add_youtube_channel(self, name: str, channel_id: str, channel_url: str, added_by: str | None = None) -> int:
        """Add a YouTube channel entry. Returns the new row ID."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO youtube_channels (name, channel_id, channel_url, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, channel_id, channel_url, added_by, datetime.datetime.now().isoformat()),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def add_website(self, name: str, url: str, description: str = "", added_by: str | None = None) -> int:
        """Add a website entry. Returns the new row ID."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO websites (name, description, url, added_by, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description, url, added_by, datetime.datetime.now().isoformat()),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id
