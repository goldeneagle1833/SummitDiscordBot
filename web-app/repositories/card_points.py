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
        conn.execute(
            "INSERT INTO card_points (card_name, point_value) VALUES (?, ?) "
            "ON CONFLICT(card_name) DO UPDATE SET "
            "point_value = excluded.point_value, "
            "updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now')",
            (card_name, point_value),
        )
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
        cur = conn.execute(
            "DELETE FROM card_points WHERE card_name = ? COLLATE NOCASE",
            (card_name,),
        )
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
        self.set_config("max_budget", str(budget))
