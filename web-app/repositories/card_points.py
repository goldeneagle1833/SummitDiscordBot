"""Repository for card points database access."""

import sqlite3
from pathlib import Path

from webapp_config import ELO_DB_PATH


class CardPointsRepository:
    """Data access for card_points and points_config tables in elo.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or ELO_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Card points CRUD ---

    def get_all_card_points(self) -> list[dict]:
        """Get all cards with assigned point values."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, card_name, point_value, created_at, updated_at "
            "FROM card_points ORDER BY card_name"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_card_points(self, card_name: str) -> dict | None:
        """Get point value for a specific card."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT id, card_name, point_value, created_at, updated_at "
            "FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def set_card_points(self, card_name: str, point_value: int) -> dict:
        """Set or update point value for a card. Returns the upserted row."""
        conn = self._get_connection()
        # Check existing value for history logging
        existing = conn.execute(
            "SELECT point_value FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        ).fetchone()

        conn.execute(
            "INSERT INTO card_points (card_name, point_value) VALUES (?, ?) "
            "ON CONFLICT(card_name) DO UPDATE SET "
            "point_value = excluded.point_value, "
            "updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')",
            (card_name, point_value),
        )

        if existing is None:
            self._log_history(conn, "added", card_name, None, str(point_value))
        elif existing["point_value"] != point_value:
            self._log_history(conn, "changed", card_name, str(existing["point_value"]), str(point_value))

        conn.commit()
        row = conn.execute(
            "SELECT id, card_name, point_value, created_at, updated_at "
            "FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        ).fetchone()
        conn.close()
        return dict(row)

    def delete_card_points(self, card_name: str) -> bool:
        """Remove a card's point assignment. Returns True if a row was deleted."""
        conn = self._get_connection()
        existing = conn.execute(
            "SELECT point_value FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        ).fetchone()
        cur = conn.execute(
            "DELETE FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        )
        if cur.rowcount > 0 and existing:
            self._log_history(conn, "removed", card_name, str(existing["point_value"]), None)
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def bulk_set_card_points(self, entries: list[dict]) -> int:
        """Bulk upsert card points. Each entry: {card_name, point_value}. Returns count."""
        conn = self._get_connection()
        count = 0
        for entry in entries:
            conn.execute(
                "INSERT INTO card_points (card_name, point_value) VALUES (?, ?) "
                "ON CONFLICT(card_name) DO UPDATE SET "
                "point_value = excluded.point_value, "
                "updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')",
                (entry["card_name"], entry["point_value"]),
            )
            count += 1
        conn.commit()
        conn.close()
        return count

    # --- Config ---

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Get a config value."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT value FROM points_config WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row["value"] if row else default

    def set_config(self, key: str, value: str) -> None:
        """Set a config value."""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO points_config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_max_budget(self) -> int:
        """Get the max point budget for decks."""
        val = self.get_config("max_budget", "50")
        return int(val)

    def set_max_budget(self, budget: int) -> None:
        """Set the max point budget for decks."""
        old_budget = self.get_config("max_budget", "50")
        self.set_config("max_budget", str(budget))
        if str(budget) != old_budget:
            conn = self._get_connection()
            self._log_history(conn, "budget_changed", None, old_budget, str(budget))
            conn.commit()
            conn.close()

    # --- History ---

    def _log_history(self, conn, action: str, card_name: str | None,
                     old_value: str | None, new_value: str | None) -> None:
        """Log a change to card_points_history (uses existing connection)."""
        conn.execute(
            "INSERT INTO card_points_history (action, card_name, old_value, new_value) "
            "VALUES (?, ?, ?, ?)",
            (action, card_name, old_value, new_value),
        )

    def get_history(self, limit: int = 100) -> list[dict]:
        """Get recent card points history entries."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT id, action, card_name, old_value, new_value, changed_at "
            "FROM card_points_history ORDER BY changed_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Card points admins ---

    def get_card_points_admins(self) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM card_points_admins ORDER BY added_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_card_points_admin(self, discord_user_id: str, display_name: str | None) -> None:
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO card_points_admins (discord_user_id, display_name) VALUES (?, ?)",
            (discord_user_id, display_name),
        )
        conn.commit()
        conn.close()

    def remove_card_points_admin(self, discord_user_id: str) -> bool:
        conn = self._get_connection()
        cur = conn.execute(
            "DELETE FROM card_points_admins WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def is_card_points_admin(self, discord_user_id: str) -> bool:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT 1 FROM card_points_admins WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        conn.close()
        return row is not None
