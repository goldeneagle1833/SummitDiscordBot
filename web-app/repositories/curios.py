"""Repository for curio tracking data access."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import COMMUNITY_DB_PATH


class CurioRepository:
    """Data access for curio_entries and curio_sets tables in community.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or COMMUNITY_DB_PATH)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_tables(self):
        """Create curio tables and seed default sets if they don't exist."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.executescript("""
            CREATE TABLE IF NOT EXISTS curio_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS curio_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                number_pulled INTEGER NOT NULL,
                description TEXT NOT NULL,
                set_id INTEGER NOT NULL,
                image_filename TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (set_id) REFERENCES curio_sets(id)
            );

            CREATE INDEX IF NOT EXISTS idx_curio_entries_set_id
                ON curio_entries(set_id);
            CREATE INDEX IF NOT EXISTS idx_curio_entries_updated_at
                ON curio_entries(updated_at DESC);
        """)

        # Seed default sets
        now = datetime.now(timezone.utc).isoformat()
        for set_name in ("Alpha", "Beta", "Arthurian Legends", "Gothic"):
            cur.execute(
                "INSERT OR IGNORE INTO curio_sets (name, is_default, created_at) VALUES (?, 1, ?)",
                (set_name, now),
            )

        conn.commit()
        conn.close()

    # --- Read operations ---

    def get_all_entries(self) -> list[dict]:
        """Get all curio entries with set names, ordered by updated_at DESC."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.name, e.number_pulled, e.description, e.set_id,
                   s.name AS set_name, e.image_filename, e.created_by,
                   e.created_at, e.updated_at
            FROM curio_entries e
            JOIN curio_sets s ON e.set_id = s.id
            ORDER BY e.updated_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "number_pulled": row[2],
                "description": row[3],
                "set_id": row[4],
                "set_name": row[5],
                "image_filename": row[6],
                "created_by": row[7],
                "created_at": row[8],
                "updated_at": row[9],
            }
            for row in rows
        ]

    def get_entry(self, entry_id: int) -> dict | None:
        """Get a single curio entry by ID."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.name, e.number_pulled, e.description, e.set_id,
                   s.name AS set_name, e.image_filename, e.created_by,
                   e.created_at, e.updated_at
            FROM curio_entries e
            JOIN curio_sets s ON e.set_id = s.id
            WHERE e.id = ?
        """, (entry_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "number_pulled": row[2],
            "description": row[3],
            "set_id": row[4],
            "set_name": row[5],
            "image_filename": row[6],
            "created_by": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    def get_all_sets(self) -> list[dict]:
        """Get all curio sets, defaults first then alphabetical."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, is_default, created_at
            FROM curio_sets
            ORDER BY is_default DESC, name ASC
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "is_default": bool(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]

    # --- Write operations ---

    def create_entry(
        self,
        name: str,
        number_pulled: int,
        description: str,
        set_id: int,
        image_filename: str,
        created_by: str,
    ) -> dict:
        """Create a new curio entry. Returns the created entry dict."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO curio_entries
               (name, number_pulled, description, set_id, image_filename, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, number_pulled, description, set_id, image_filename, created_by, now, now),
        )
        entry_id = cur.lastrowid
        conn.commit()
        conn.close()
        return self.get_entry(entry_id)

    def update_entry(self, entry_id: int, **fields) -> dict | None:
        """Update a curio entry. Only updates provided fields. Returns updated entry or None."""
        entry = self.get_entry(entry_id)
        if not entry:
            return None

        allowed = {"name", "number_pulled", "description", "set_id", "image_filename"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return entry

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entry_id]

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE curio_entries SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: int) -> str | None:
        """Delete a curio entry. Returns the old image_filename for cleanup, or None if not found."""
        entry = self.get_entry(entry_id)
        if not entry:
            return None

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM curio_entries WHERE id = ?", (entry_id,))
        conn.commit()
        conn.close()
        return entry["image_filename"]

    def create_set(self, name: str) -> dict:
        """Create a new custom set. Returns the created set dict. Raises on duplicate."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO curio_sets (name, is_default, created_at) VALUES (?, 0, ?)",
                (name, now),
            )
            set_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"Set '{name}' already exists")
        conn.close()
        return {"id": set_id, "name": name, "is_default": False, "created_at": now}
