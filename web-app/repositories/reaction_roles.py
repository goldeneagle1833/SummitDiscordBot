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
            CREATE TABLE IF NOT EXISTS reaction_role_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                message_id TEXT,
                channel_id TEXT,
                post_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            );
            CREATE TABLE IF NOT EXISTS reaction_role_guild_roles (
                role_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                color INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0,
                assignable INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            );
            CREATE TABLE IF NOT EXISTS reaction_role_guild_emojis (
                emoji_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                animated INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            );
            CREATE TABLE IF NOT EXISTS reaction_role_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                message_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            );
        """)
        # Columns for messages the bot posted itself (title/body it keeps updated).
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(reaction_role_messages)")}
        for name, ddl in (
            ("title", "TEXT NOT NULL DEFAULT ''"),
            ("body", "TEXT NOT NULL DEFAULT ''"),
            ("managed", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE reaction_role_messages ADD COLUMN {name} {ddl}")
        conn.commit()
        conn.close()

    # --- Messages ---

    def get_all_messages(self) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, channel_id, message_id, label, title, body, managed, created_at "
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

    def get_message(self, message_id: str) -> dict | None:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM reaction_role_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_message_text(self, message_id: str, title: str, body: str) -> bool:
        """Update the title/body of a bot-posted message (label follows the title)."""
        conn = self._get_connection()
        cur = conn.execute(
            "UPDATE reaction_role_messages SET title = ?, body = ?, label = ? "
            "WHERE message_id = ? AND managed = 1",
            (title, body, title, message_id),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

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

    def get_mapping(self, mapping_id: int) -> dict | None:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM reaction_role_mappings WHERE id = ?", (mapping_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def count_mappings(self, message_id: str) -> int:
        conn = self._get_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM reaction_role_mappings WHERE message_id = ?",
            (message_id,),
        ).fetchone()[0]
        conn.close()
        return count

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

    # --- Bot job queue (the bot polls this every few seconds) ---

    def enqueue(
        self, action: str, message_id: str | None = None,
        channel_id: str | None = None, post_id: int | None = None,
    ) -> None:
        """Ask the bot to act: 'sync', 'clear', 'delete_post' or 'post'."""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO reaction_role_queue (action, message_id, channel_id, post_id) "
            "VALUES (?, ?, ?, ?)",
            (action, message_id, channel_id, post_id),
        )
        conn.commit()
        conn.close()

    # --- Posts the bot should publish ---

    def create_post(self, channel_id: str, title: str, body: str) -> dict:
        conn = self._get_connection()
        cur = conn.execute(
            "INSERT INTO reaction_role_posts (channel_id, title, body) VALUES (?, ?, ?)",
            (channel_id, title, body),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM reaction_role_posts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_open_posts(self) -> list[dict]:
        """Posts the bot has not published yet, or that failed."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM reaction_role_posts WHERE status IN ('pending', 'failed') "
            "ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_post(self, post_id: int) -> bool:
        conn = self._get_connection()
        cur = conn.execute(
            "DELETE FROM reaction_role_posts WHERE id = ? AND status IN ('pending', 'failed')",
            (post_id,),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    # --- Server roles / custom emojis (snapshot the bot keeps current) ---

    def get_discord_options(self) -> dict:
        """Roles (highest first) and custom emojis, plus when the bot last saved them."""
        conn = self._get_connection()
        roles = conn.execute(
            "SELECT role_id, name, color, position, assignable "
            "FROM reaction_role_guild_roles ORDER BY position DESC"
        ).fetchall()
        emojis = conn.execute(
            "SELECT emoji_id, name, animated FROM reaction_role_guild_emojis ORDER BY name COLLATE NOCASE"
        ).fetchall()
        updated = conn.execute(
            "SELECT MAX(updated_at) FROM reaction_role_guild_roles"
        ).fetchone()[0]
        conn.close()
        return {
            "roles": [dict(r) for r in roles],
            "emojis": [dict(e) for e in emojis],
            "updated_at": updated,
        }
