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
        """Get all ELO standings with both paper and online ELOs."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, user_display_name, online_elo, paper_elo
            FROM overall_standings
            ORDER BY online_elo DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "user_id": row[0],
                "display_name": row[1],
                "elo": row[2] if row[2] else 1500,
                "online_elo": row[2] if row[2] else 1500,
                "paper_elo": row[3] if row[3] else 1500,
                "primary_mode": "Paper" if (row[3] or 1500) > (row[2] or 1500) else "Online",
            }
            for row in rows
        ]

    def get_all_standings_with_event(self) -> list[dict]:
        """Get all ELO standings including event ELOs (both paper and online)."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, user_display_name,
                   online_elo, online_event_elo,
                   paper_elo, paper_event_elo
            FROM overall_standings
            ORDER BY online_elo DESC
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "user_id": row[0],
                "display_name": row[1],
                "elo": row[2] if row[2] else 1500,
                "event_elo": row[3] if row[3] else 1500,
                "online_elo": row[2] if row[2] else 1500,
                "online_event_elo": row[3] if row[3] else 1500,
                "paper_elo": row[4] if row[4] else 1500,
                "paper_event_elo": row[5] if row[5] else 1500,
                "primary_mode": "Paper" if (row[4] or 1500) > (row[2] or 1500) else "Online",
            }
            for row in rows
        ]

    def get_event_standings(self) -> list[dict]:
        """Get event ELO standings ordered by online_event_elo descending."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, user_display_name, online_event_elo
            FROM overall_standings
            ORDER BY online_event_elo DESC
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
        cur.execute("SELECT online_elo FROM overall_standings")
        elos = [row[0] for row in cur.fetchall()]
        conn.close()
        return elos

    def get_user_elo(self, user_id: int | str) -> int | None:
        """Get ELO for a specific user (handles both int and str to support large Google IDs)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT online_elo FROM overall_standings WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def upsert_user_elo(self, user_id: int, display_name: str, new_elo: int):
        """Insert or update a user's lifetime ELO in overall_standings."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO overall_standings (user_id, user_display_name, online_elo)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id)
               DO UPDATE SET online_elo = ?, user_display_name = ?""",
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

    def get_player_event_elo(self, user_id: int | str, event_id: int) -> dict | None:
        """Get a player's ELO and rank for a specific past event (handles both int and str)."""
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

    def get_archived_event_leaderboard(self, event_id: int) -> list[dict]:
        """Get full leaderboard for a specific archived event."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Check if event_standings_archive table exists
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='event_standings_archive'
        """)
        if not cur.fetchone():
            conn.close()
            return []

        cur.execute(
            """
            SELECT user_id, user_display_name, final_event_elo, final_rank
            FROM event_standings_archive
            WHERE event_id = ?
            ORDER BY final_rank ASC
        """,
            (event_id,),
        )
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "user_id": row[0],
                "display_name": row[1],
                "event_elo": row[2],
                "rank": row[3],
            }
            for row in rows
        ]

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
        """Reset a player's online ELO to default. Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE overall_standings SET online_elo = ?, online_event_elo = ? WHERE user_id = ?",
            (default_elo, default_elo, user_id),
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

    # --- Paper Standings (separate table for web-reported matches) ---

    def get_paper_standings(self) -> list[dict]:
        """Get all paper ELO standings from paper_standings table."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Check if table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return []

        cur.execute("""
            SELECT user_id, user_display_name, paper_elo, paper_event_elo
            FROM paper_standings
            ORDER BY paper_elo DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "user_id": str(row[0]),
                "display_name": row[1],
                "paper_elo": row[2] if row[2] else 1500,
                "paper_event_elo": row[3] if row[3] else 1500,
            }
            for row in rows
        ]

    def get_user_paper_elo(self, user_id: str) -> int | None:
        """Get paper ELO for a specific user from paper_standings."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return None

        cur.execute("SELECT paper_elo FROM paper_standings WHERE user_id = ?", (str(user_id),))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def reset_paper_elo(self, user_id: str, default_elo: int = 1500) -> bool:
        """Reset a player's paper ELO to default in paper_standings. Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return False

        cur.execute(
            "UPDATE paper_standings SET paper_elo = ?, paper_event_elo = ? WHERE user_id = ?",
            (default_elo, default_elo, str(user_id)),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated

    def upsert_paper_elo(self, user_id: str, display_name: str, new_elo: int):
        """Insert or update a user's paper ELO in paper_standings."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return

        cur.execute(
            """INSERT INTO paper_standings (user_id, user_display_name, paper_elo, paper_event_elo)
               VALUES (?, ?, ?, 1500)
               ON CONFLICT(user_id)
               DO UPDATE SET paper_elo = ?, user_display_name = ?""",
            (str(user_id), display_name, new_elo, new_elo, display_name),
        )
        conn.commit()
        conn.close()

    def delete_paper_player(self, user_id: str) -> bool:
        """Delete a player from paper_standings. Returns True if deleted."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return False

        cur.execute("DELETE FROM paper_standings WHERE user_id = ?", (str(user_id),))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def rename_paper_player(self, user_id: str, new_name: str) -> bool:
        """Update a player's display name in paper_standings. Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_standings'")
        if not cur.fetchone():
            conn.close()
            return False

        cur.execute(
            "UPDATE paper_standings SET user_display_name = ? WHERE user_id = ?",
            (new_name, str(user_id)),
        )
        updated = cur.rowcount > 0
        conn.commit()
        conn.close()
        return updated
