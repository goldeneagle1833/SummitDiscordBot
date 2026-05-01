"""Repository for per-avatar image display settings (brightness, position)."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import ANALYTICS_DB_PATH


class AvatarImageSettingsRepository:
    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or ANALYTICS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        conn = self._get_connection()
        conn.execute("""CREATE TABLE IF NOT EXISTS avatar_image_settings (
            avatar_name TEXT PRIMARY KEY,
            brightness REAL NOT NULL DEFAULT 1.0,
            position_x INTEGER NOT NULL DEFAULT 50,
            position_y INTEGER NOT NULL DEFAULT 25,
            opacity REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL
        )""")
        # Migration: add opacity column if it doesn't exist yet
        try:
            conn.execute("ALTER TABLE avatar_image_settings ADD COLUMN opacity REAL NOT NULL DEFAULT 0.5")
        except Exception:
            pass
        conn.commit()
        conn.close()

    def get_all(self) -> dict:
        """Return all avatar image settings as {avatar_name: {brightness, position_x, position_y}}."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM avatar_image_settings").fetchall()
        conn.close()
        return {
            row["avatar_name"]: {
                "brightness": row["brightness"],
                "position_x": row["position_x"],
                "position_y": row["position_y"],
                "opacity": row["opacity"],
            }
            for row in rows
        }

    def get(self, avatar_name: str) -> dict | None:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM avatar_image_settings WHERE avatar_name = ?",
            (avatar_name,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "brightness": row["brightness"],
            "position_x": row["position_x"],
            "position_y": row["position_y"],
            "opacity": row["opacity"],
        }

    def upsert(self, avatar_name: str, brightness: float, position_x: int, position_y: int, opacity: float = 0.5):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            """INSERT INTO avatar_image_settings (avatar_name, brightness, position_x, position_y, opacity, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(avatar_name) DO UPDATE SET
                   brightness = excluded.brightness,
                   position_x = excluded.position_x,
                   position_y = excluded.position_y,
                   opacity = excluded.opacity,
                   updated_at = excluded.updated_at""",
            (avatar_name, brightness, position_x, position_y, opacity, now),
        )
        conn.commit()
        conn.close()

    def delete(self, avatar_name: str):
        conn = self._get_connection()
        conn.execute("DELETE FROM avatar_image_settings WHERE avatar_name = ?", (avatar_name,))
        conn.commit()
        conn.close()
