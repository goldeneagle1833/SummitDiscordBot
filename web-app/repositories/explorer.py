"""Repository for Explorer Standings data (explorer.db)."""

import json
import logging
import sqlite3

from webapp_config import EXPLORER_DB_PATH

logger = logging.getLogger(__name__)


class ExplorerRepository:
    def _conn(self):
        conn = sqlite3.connect(str(EXPLORER_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    # ── Seasons ──────────────────────────────────────────────────────────────

    def create_season(self, name: str, description: str | None, points_config_json: str) -> dict:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO explorer_seasons (name, description, points_config)
                   VALUES (?, ?, ?)""",
                (name, description, points_config_json),
            )
            conn.commit()
            return self.get_season(cur.lastrowid)

    def get_all_seasons(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT s.id, s.name, s.description, s.points_config, s.created_at,
                          COUNT(e.id) AS event_count
                   FROM explorer_seasons s
                   LEFT JOIN explorer_events e ON e.season_id = s.id
                   GROUP BY s.id
                   ORDER BY s.id DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_season(self, season_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM explorer_seasons WHERE id = ?", (season_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_season(self, season_id: int) -> None:
        """Delete a season and all its events/results."""
        with self._conn() as conn:
            event_ids = conn.execute(
                "SELECT id FROM explorer_events WHERE season_id = ?", (season_id,)
            ).fetchall()
            for row in event_ids:
                conn.execute("DELETE FROM explorer_results WHERE event_id = ?", (row["id"],))
            conn.execute("DELETE FROM explorer_events WHERE season_id = ?", (season_id,))
            conn.execute("DELETE FROM explorer_seasons WHERE id = ?", (season_id,))
            conn.commit()

    # ── Events ────────────────────────────────────────────────────────────────

    def create_event(
        self,
        season_id: int,
        event_external_id: str,
        event_name: str,
        event_date: str | None,
        total_players: int | None,
        play_format: str | None,
        venue_name: str | None,
        source_url: str | None,
    ) -> dict:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO explorer_events
                   (season_id, cardeio_event_id, event_name, event_date,
                    total_players, play_format, venue_name, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    season_id, event_external_id, event_name, event_date,
                    total_players, play_format, venue_name, source_url,
                ),
            )
            conn.commit()
            return self.get_event(cur.lastrowid)

    def get_event(self, event_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM explorer_events WHERE id = ?", (event_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_event_by_cardeio_id(self, cardeio_event_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM explorer_events WHERE cardeio_event_id = ?",
                (cardeio_event_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_events_for_season(self, season_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM explorer_events
                   WHERE season_id = ?
                   ORDER BY event_date ASC, id ASC""",
                (season_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_event(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM explorer_results WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM explorer_events WHERE id = ?", (event_id,))
            conn.commit()

    # ── Results ───────────────────────────────────────────────────────────────

    def save_results(self, event_id: int, results: list[dict]) -> None:
        """Bulk-insert player results for an event."""
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO explorer_results
                   (event_id, cardeio_user_id, display_name, final_standing,
                    wins, total_players, image_url, team_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        event_id,
                        r["cardeio_user_id"],
                        r["display_name"],
                        r["final_standing"],
                        r.get("wins", 0),
                        r["total_players"],
                        r.get("image_url"),
                        r.get("team_name"),
                    )
                    for r in results
                ],
            )
            conn.commit()

    def get_results_for_season(self, season_id: int) -> list[dict]:
        """Return all results across all events in a season, joined with event info."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT r.*, e.id AS event_db_id, e.event_name, e.event_date,
                          e.total_players AS event_total_players
                   FROM explorer_results r
                   JOIN explorer_events e ON e.id = r.event_id
                   WHERE e.season_id = ?
                   ORDER BY e.event_date ASC, e.id ASC, r.final_standing ASC""",
                (season_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Admins ────────────────────────────────────────────────────────────────

    def add_explorer_admin(self, discord_user_id: str, display_name: str | None) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO explorer_admins (discord_user_id, display_name)
                   VALUES (?, ?)""",
                (discord_user_id, display_name),
            )
            conn.commit()

    def get_explorer_admins(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM explorer_admins ORDER BY added_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def remove_explorer_admin(self, discord_user_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM explorer_admins WHERE discord_user_id = ?",
                (discord_user_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def is_explorer_admin(self, discord_user_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM explorer_admins WHERE discord_user_id = ?",
                (discord_user_id,),
            ).fetchone()
        return row is not None

    # ── Player Aliases ─────────────────────────────────────────────────────

    def get_all_aliases(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM explorer_player_aliases ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_alias_map(self) -> dict[str, str]:
        """Return {alias_user_id: canonical_user_id} for all aliases."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT alias_user_id, canonical_user_id FROM explorer_player_aliases"
            ).fetchall()
        return {r["alias_user_id"]: r["canonical_user_id"] for r in rows}

    def create_alias(
        self,
        alias_user_id: str,
        canonical_user_id: str,
        alias_display_name: str | None,
        canonical_display_name: str | None,
    ) -> dict:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO explorer_player_aliases
                   (alias_user_id, canonical_user_id, alias_display_name, canonical_display_name)
                   VALUES (?, ?, ?, ?)""",
                (alias_user_id, canonical_user_id, alias_display_name, canonical_display_name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM explorer_player_aliases WHERE alias_user_id = ?",
                (alias_user_id,),
            ).fetchone()
        return dict(row)

    def delete_alias(self, alias_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM explorer_player_aliases WHERE id = ?", (alias_id,)
            )
            conn.commit()
        return cur.rowcount > 0

    def get_all_unique_players(self) -> list[dict]:
        """Return all unique players across all events with their cardeio_user_id and display_name."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT cardeio_user_id, display_name, COUNT(*) as event_count
                   FROM explorer_results
                   GROUP BY cardeio_user_id
                   ORDER BY display_name COLLATE NOCASE ASC"""
            ).fetchall()
        return [dict(r) for r in rows]
