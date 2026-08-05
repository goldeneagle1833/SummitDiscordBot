"""Repository for reaction role mappings."""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class ReactionRolesRepository:
    """Data access for reaction_role_messages and reaction_role_mappings tables."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reaction_role_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            );
            CREATE TABLE IF NOT EXISTS reaction_role_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                emoji TEXT NOT NULL,
                emoji_id TEXT,
                role_id TEXT NOT NULL,
                role_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                UNIQUE(message_id, emoji)
            );
        """)
        conn.commit()
        conn.close()

    # --- Messages ---

    def get_all_messages(self) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, channel_id, message_id, label, created_at "
            "FROM reaction_role_messages ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_message(self, channel_id: str, message_id: str, label: str = "") -> dict:
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO reaction_role_messages (channel_id, message_id, label) "
            "VALUES (?, ?, ?)",
            (channel_id, message_id, label),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reaction_role_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        conn.close()
        return dict(row)

    def delete_message(self, message_id: str) -> bool:
        conn = self._get_connection()
        # Delete mappings first
        conn.execute(
            "DELETE FROM reaction_role_mappings WHERE message_id = ?",
            (message_id,),
        )
        cur = conn.execute(
            "DELETE FROM reaction_role_messages WHERE message_id = ?",
            (message_id,),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    # --- Mappings ---

    def get_mappings_for_message(self, message_id: str) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, message_id, emoji, emoji_id, role_id, role_name, created_at "
            "FROM reaction_role_mappings WHERE message_id = ? ORDER BY id",
            (message_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_mappings(self) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, message_id, emoji, emoji_id, role_id, role_name, created_at "
            "FROM reaction_role_mappings ORDER BY message_id, id"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_mapping(
        self, message_id: str, emoji: str, role_id: str, role_name: str = "",
        emoji_id: str | None = None,
    ) -> dict:
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO reaction_role_mappings "
            "(message_id, emoji, emoji_id, role_id, role_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (message_id, emoji, emoji_id, role_id, role_name),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reaction_role_mappings "
            "WHERE message_id = ? AND emoji = ?",
            (message_id, emoji),
        ).fetchone()
        conn.close()
        return dict(row)

    def delete_mapping(self, mapping_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.execute(
            "DELETE FROM reaction_role_mappings WHERE id = ?",
            (mapping_id,),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def get_all_message_ids(self) -> set[str]:
        """Return all tracked message IDs (for fast lookup by the bot)."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT message_id FROM reaction_role_messages"
        ).fetchall()
        conn.close()
        return {r["message_id"] for r in rows}

    def get_role_map(self) -> dict[str, dict]:
        """Return {message_id: {emoji_key: role_id}} for bot consumption.

        For custom emojis (emoji_id is set), the key is the int emoji_id.
        For unicode emojis, the key is the emoji string.
        """
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT message_id, emoji, emoji_id, role_id FROM reaction_role_mappings"
        ).fetchall()
        conn.close()

        role_map: dict[str, dict] = {}
        for r in rows:
            mid = r["message_id"]
            if mid not in role_map:
                role_map[mid] = {}
            # For custom emojis, use the int ID as key
            if r["emoji_id"]:
                key = int(r["emoji_id"])
            else:
                key = r["emoji"]
            role_map[mid][key] = int(r["role_id"])
        return role_map

    def get_channel_for_message(self, message_id: str) -> str | None:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT channel_id FROM reaction_role_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        conn.close()
        return row["channel_id"] if row else None
