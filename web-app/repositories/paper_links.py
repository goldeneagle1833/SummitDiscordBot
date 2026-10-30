"""Admin decisions that tie paper tournament results to Summit players.

Three small tables in match_records.db:

- paper_name_links: a paper name (normalised) linked to a Summit player, or
  marked "not this player" so it never auto-links to them again.
- paper_result_assignments: one Top 8 result given to a player by hand, or
  to nobody. Used when the deck was posted by someone other than the pilot
  (an organiser uploading every Top 8 deck under their own account).
- paper_badge_events: whether an event on the Top 8 page awards badges at
  all, when an admin has switched it from its default.
"""

import datetime
import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class PaperLinkRepository:
    """Data access for the paper result link tables in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_tables(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_name_links (
                name_key TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                paper_name TEXT,
                set_by TEXT,
                set_at TEXT NOT NULL,
                PRIMARY KEY (name_key, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_result_assignments (
                folder TEXT NOT NULL,
                deck_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                set_by TEXT,
                set_at TEXT NOT NULL,
                PRIMARY KEY (folder, deck_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_badge_events (
                folder TEXT PRIMARY KEY,
                awards_badges INTEGER NOT NULL,
                set_by TEXT,
                set_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    # -- name links -------------------------------------------------------

    def get_name_links(self) -> list[dict]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name_key, user_id, status, paper_name, set_by, set_at FROM paper_name_links"
        ).fetchall()
        conn.close()
        return [
            {"name_key": r[0], "user_id": r[1], "status": r[2], "paper_name": r[3],
             "set_by": r[4], "set_at": r[5]}
            for r in rows
        ]

    def link_name(self, name_key: str, paper_name: str, user_id: str, set_by: str | None = None):
        """Link a paper name to one player; any other link for that name is dropped."""
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM paper_name_links WHERE name_key = ? AND status = 'linked'", (name_key,)
        )
        conn.execute(
            """INSERT INTO paper_name_links (name_key, user_id, status, paper_name, set_by, set_at)
               VALUES (?, ?, 'linked', ?, ?, ?)
               ON CONFLICT(name_key, user_id) DO UPDATE SET status = 'linked',
                   paper_name = excluded.paper_name, set_by = excluded.set_by, set_at = excluded.set_at""",
            (name_key, str(user_id), paper_name, set_by, _now()),
        )
        conn.commit()
        conn.close()

    def reject_name(self, name_key: str, paper_name: str, user_id: str, set_by: str | None = None):
        """Mark a paper name as "not this player", so it never links to them."""
        conn = self._get_connection()
        conn.execute(
            """INSERT INTO paper_name_links (name_key, user_id, status, paper_name, set_by, set_at)
               VALUES (?, ?, 'rejected', ?, ?, ?)
               ON CONFLICT(name_key, user_id) DO UPDATE SET status = 'rejected',
                   paper_name = excluded.paper_name, set_by = excluded.set_by, set_at = excluded.set_at""",
            (name_key, str(user_id), paper_name, set_by, _now()),
        )
        conn.commit()
        conn.close()

    def clear_name(self, name_key: str, user_id: str):
        """Forget an admin decision, so the automatic rules apply again."""
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM paper_name_links WHERE name_key = ? AND user_id = ?", (name_key, str(user_id))
        )
        conn.commit()
        conn.close()

    # -- single results ---------------------------------------------------

    def get_assignments(self) -> dict:
        """{(folder, deck_id): user_id}; an empty user_id means nobody."""
        conn = self._get_connection()
        rows = conn.execute("SELECT folder, deck_id, user_id FROM paper_result_assignments").fetchall()
        conn.close()
        return {(r[0], r[1]): r[2] or "" for r in rows}

    def assign_result(self, folder: str, deck_id: str, user_id: str, set_by: str | None = None):
        conn = self._get_connection()
        conn.execute(
            """INSERT INTO paper_result_assignments (folder, deck_id, user_id, set_by, set_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(folder, deck_id) DO UPDATE SET user_id = excluded.user_id,
                   set_by = excluded.set_by, set_at = excluded.set_at""",
            (folder, deck_id, str(user_id or ""), set_by, _now()),
        )
        conn.commit()
        conn.close()

    def clear_assignment(self, folder: str, deck_id: str):
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM paper_result_assignments WHERE folder = ? AND deck_id = ?", (folder, deck_id)
        )
        conn.commit()
        conn.close()

    # -- events -----------------------------------------------------------

    def get_event_settings(self) -> dict:
        """{folder: bool} for events an admin has switched on or off."""
        conn = self._get_connection()
        rows = conn.execute("SELECT folder, awards_badges FROM paper_badge_events").fetchall()
        conn.close()
        return {r[0]: bool(r[1]) for r in rows}

    def set_event_awards(self, folder: str, awards: bool, set_by: str | None = None):
        conn = self._get_connection()
        conn.execute(
            """INSERT INTO paper_badge_events (folder, awards_badges, set_by, set_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(folder) DO UPDATE SET awards_badges = excluded.awards_badges,
                   set_by = excluded.set_by, set_at = excluded.set_at""",
            (folder, 1 if awards else 0, set_by, _now()),
        )
        conn.commit()
        conn.close()
