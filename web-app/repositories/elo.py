"""Repository for ELO database access."""

import sqlite3
from pathlib import Path

from webapp_config import ELO_DB_PATH


class EloRepository:
    """Data access for elo.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or ELO_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def get_all_standings(self) -> list[dict]:
        """Get all ELO standings (lifetime) ordered by ELO descending."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, user_display_name, elo
            FROM overall_standings
            ORDER BY elo DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {"user_id": row[0], "display_name": row[1], "elo": row[2]} for row in rows
        ]

    def get_all_standings_with_event(self) -> list[dict]:
        """Get all ELO standings including event ELO."""
        conn = self._get_connection()
        cur = conn.cursor()
        # Check if event_elo column exists
        cur.execute("PRAGMA table_info(overall_standings)")
        columns = [col[1] for col in cur.fetchall()]

        if "event_elo" in columns:
            cur.execute("""
                SELECT user_id, user_display_name, elo, event_elo
                FROM overall_standings
                ORDER BY elo DESC
            """)
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "user_id": row[0],
                    "display_name": row[1],
                    "elo": row[2],
                    "event_elo": row[3] if row[3] else 1500,
                }
                for row in rows
            ]
        else:
            # Fallback if event_elo doesn't exist yet
            cur.execute("""
                SELECT user_id, user_display_name, elo
                FROM overall_standings
                ORDER BY elo DESC
            """)
            rows = cur.fetchall()
            conn.close()
            return [
                {
                    "user_id": row[0],
                    "display_name": row[1],
                    "elo": row[2],
                    "event_elo": 1500,
                }
                for row in rows
            ]

    def get_event_standings(self) -> list[dict]:
        """Get event ELO standings ordered by event_elo descending."""
        conn = self._get_connection()
        cur = conn.cursor()
        # Check if event_elo column exists
        cur.execute("PRAGMA table_info(overall_standings)")
        columns = [col[1] for col in cur.fetchall()]

        if "event_elo" not in columns:
            conn.close()
            return []

        cur.execute("""
            SELECT user_id, user_display_name, event_elo
            FROM overall_standings
            WHERE event_elo != 1500
            ORDER BY event_elo DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {"user_id": row[0], "display_name": row[1], "event_elo": row[2]}
            for row in rows
        ]

    def get_active_event(self) -> dict | None:
        """Get the currently active event, if any."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Check if events table exists
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
        if not cur.fetchone():
            conn.close()
            return None

        cur.execute("""
            SELECT event_id, event_name, start_date
            FROM events
            WHERE is_active = 1
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()

        if row:
            return {"event_id": row[0], "event_name": row[1], "start_date": row[2]}
        return None

    def get_all_elos(self) -> list[int]:
        """Get all lifetime ELO values for distribution calculation."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT elo FROM overall_standings")
        elos = [row[0] for row in cur.fetchall()]
        conn.close()
        return elos

    def get_user_elo(self, user_id: int) -> int | None:
        """Get ELO for a specific user."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT elo FROM overall_standings WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def upsert_user_elo(self, user_id: int, display_name: str, new_elo: int):
        """Insert or update a user's lifetime ELO in overall_standings."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO overall_standings (user_id, user_display_name, elo)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id)
               DO UPDATE SET elo = ?, user_display_name = ?""",
            (user_id, display_name, new_elo, new_elo, display_name),
        )
        conn.commit()
        conn.close()

    def get_all_events(self) -> list[dict]:
        """Get all events (past and active) for filtering."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Check if events table exists
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='events'
        """)
        if not cur.fetchone():
            conn.close()
            return []

        cur.execute("""
            SELECT event_id, event_name, start_date, end_date, is_active
            FROM events
            ORDER BY start_date DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "event_id": row[0],
                "event_name": row[1],
                "start_date": row[2],
                "end_date": row[3],
                "is_active": bool(row[4]),
            }
            for row in rows
        ]

    def get_player_event_elo(self, user_id: int, event_id: int) -> dict | None:
        """Get a player's ELO and rank for a specific past event."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Check if event_standings_archive table exists
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='event_standings_archive'
        """)
        if not cur.fetchone():
            conn.close()
            return None

        cur.execute(
            """
            SELECT final_event_elo, final_rank, user_display_name
            FROM event_standings_archive
            WHERE event_id = ? AND user_id = ?
        """,
            (event_id, user_id),
        )
        row = cur.fetchone()
        conn.close()

        if row:
            return {
                "elo": row[0],
                "rank": row[1],
                "display_name": row[2],
            }
        return None

    def delete_player(self, user_id: int) -> bool:
        """Delete a player from overall_standings. Returns True if deleted."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM overall_standings WHERE user_id = ?", (user_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def reset_player_elo(self, user_id: int, default_elo: int = 1500) -> bool:
        """Reset a player's ELO to default. Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()
        # Check if event_elo column exists
        cur.execute("PRAGMA table_info(overall_standings)")
        columns = [col[1] for col in cur.fetchall()]
        if "event_elo" in columns:
            cur.execute(
                "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
                (default_elo, default_elo, user_id),
            )
        else:
            cur.execute(
                "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
                (default_elo, user_id),
            )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def rename_player(self, user_id: int, new_name: str) -> bool:
        """Update a player's display name. Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE overall_standings SET user_display_name = ? WHERE user_id = ?",
            (new_name, user_id),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated
