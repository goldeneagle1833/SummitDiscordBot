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

        cur.execute("PRAGMA table_info(events)")
        columns = {r[1] for r in cur.fetchall()}
        mode_column = "elo_mode" if "elo_mode" in columns else "'player'"
        end_column = "scheduled_end_at" if "scheduled_end_at" in columns else "NULL"
        cur.execute(f"""
            SELECT event_id, event_name, start_date, {mode_column}, {end_column}
            FROM events
            WHERE is_active = 1
            LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()

        if row:
            return {
                "event_id": row[0],
                "event_name": row[1],
                "start_date": row[2],
                # "player": one event ELO per player; "avatar": one per player and avatar
                "elo_mode": row[3] or "player",
                # Unix seconds the bot will end the event at, or None when unscheduled
                "scheduled_end_at": row[4],
            }
        return None

    def get_event_elo_mode(self, event_id: int) -> str:
        """An event's ELO mode ("player" for events from before modes existed)."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(events)")
            if "elo_mode" not in {r[1] for r in cur.fetchall()}:
                return "player"
            cur.execute("SELECT elo_mode FROM events WHERE event_id = ?", (event_id,))
            row = cur.fetchone()
        finally:
            conn.close()
        return (row[0] if row else None) or "player"

    def get_avatar_standings(self, event_id: int) -> list[dict]:
        """Every (player, avatar) entry of an Avatar-mode event, best first."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_avatar_standings'"
            )
            if not cur.fetchone():
                return []
            cur.execute(
                """SELECT user_id, avatar, user_display_name, event_elo, games_played
                   FROM event_avatar_standings
                   WHERE event_id = ? AND games_played > 0
                   ORDER BY event_elo DESC, games_played DESC, user_id ASC, avatar ASC""",
                (event_id,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        return [
            {
                "user_id": row[0],
                "avatar": row[1],
                "display_name": row[2],
                "event_elo": row[3],
                "games_played": row[4],
            }
            for row in rows
        ]

    def get_player_avatar_standings(self, event_id: int, user_id) -> list[dict]:
        """One player's avatar entries in an event, each with its ladder rank."""
        return [
            {**entry, "rank": rank}
            for rank, entry in enumerate(self.get_avatar_standings(event_id), start=1)
            if str(entry["user_id"]) == str(user_id)
        ]

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

    def get_display_names(self, user_ids) -> dict:
        """Current display names for a set of players, keyed by id.

        Callers that already hold a name (a bracket seeding, an old match row)
        use this to show what the rest of the site shows, since a player can
        rename themselves after the fact.
        """
        ids = [str(u) for u in user_ids if u]
        if not ids:
            return {}

        conn = self._get_connection()
        cur = conn.cursor()
        names = {}
        # Overall last: where a player is in both, the online ladder's name is
        # the one the leaderboard shows.
        for table in ("paper_standings", "overall_standings"):
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                placeholders = ",".join("?" * len(chunk))
                try:
                    cur.execute(
                        f"SELECT user_id, user_display_name FROM {table}"
                        f" WHERE CAST(user_id AS TEXT) IN ({placeholders})",
                        chunk,
                    )
                except sqlite3.OperationalError:
                    break
                for user_id, name in cur.fetchall():
                    if name:
                        names[str(user_id)] = name

        conn.close()
        return names

    def set_user_elo(self, user_id: int | str, new_elo: int) -> bool:
        """Move an existing player's lifetime ELO, leaving their name alone.

        `upsert_user_elo` rewrites the display name too, which is right when
        the caller is the bot reporting a game under the player's current
        name, and wrong when it is working from a name recorded earlier.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE overall_standings SET online_elo = ? WHERE user_id = ?",
            (new_elo, user_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def reverse_match_elo(self, player_changes, avatar_event_id=None) -> None:
        """Undo one match on every ladder it moved, in one transaction.

        ``player_changes`` is a list of dicts with user_id, lifetime, event and
        (Avatar-mode events) avatar / avatar_change. Each ladder is reverted by
        its own recorded change.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            for change in player_changes:
                cur.execute(
                    "UPDATE overall_standings SET online_elo = online_elo - ?, "
                    "online_event_elo = online_event_elo - ? WHERE user_id = ?",
                    (change["lifetime"], change["event"], change["user_id"]),
                )
                if avatar_event_id and change.get("avatar") and change.get("avatar_change") is not None:
                    cur.execute(
                        "UPDATE event_avatar_standings SET event_elo = event_elo - ?, "
                        "games_played = MAX(games_played - 1, 0) "
                        "WHERE event_id = ? AND user_id = ? AND avatar = ?",
                        (change["avatar_change"], avatar_event_id, change["user_id"], change["avatar"]),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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

    # The archive keeps the legacy final_event_elo/final_rank pair and, since
    # dual ELO, the online pair. Events are rated on the online ladder, and the
    # legacy columns were once filled with max(paper, online), which archived
    # every sub-1500 player as a 1500, so readers prefer the online columns.
    _ARCHIVE_ELO = "COALESCE(final_online_event_elo, final_event_elo)"
    _ARCHIVE_RANK = "COALESCE(final_online_rank, final_rank)"

    def _archive_exprs(self, cur: sqlite3.Cursor) -> tuple[str, str] | None:
        """SQL for a row's (elo, rank) in event_standings_archive; None without the table."""
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='event_standings_archive'
        """)
        if not cur.fetchone():
            return None
        cur.execute("PRAGMA table_info(event_standings_archive)")
        columns = {row[1] for row in cur.fetchall()}
        if {"final_online_event_elo", "final_online_rank"} <= columns:
            return self._ARCHIVE_ELO, self._ARCHIVE_RANK
        return "final_event_elo", "final_rank"

    def get_player_event_elo(self, user_id: int | str, event_id: int) -> dict | None:
        """Get a player's final ELO and rank for a past event (handles both int and str).

        The rank is the player's place in get_archived_event_leaderboard(),
        not the stored final_rank.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            exprs = self._archive_exprs(cur)
            if not exprs:
                return None
            elo_expr, rank_expr = exprs

            cur.execute(
                f"""
                SELECT {elo_expr}, {rank_expr}, user_display_name
                FROM event_standings_archive
                WHERE event_id = ? AND user_id = ?
                """,
                (event_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            elo, stored_rank, display_name = row

            # Players ahead on the leaderboard: higher ELO, or the same ELO and
            # an earlier stored rank (the leaderboard's tie-break)
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM event_standings_archive
                WHERE event_id = ?
                  AND ({elo_expr} > ? OR ({elo_expr} = ? AND {rank_expr} < ?))
                """,
                (event_id, elo, elo, stored_rank),
            )
            ahead = cur.fetchone()[0]
            return {
                "elo": elo,
                "rank": ahead + 1,
                "display_name": display_name,
            }
        finally:
            conn.close()

    def get_archive_summaries(self) -> dict[int, dict]:
        """Per archived event: how many players finished and who won.

        {event_id: {"players", "champion", "champion_id"}}, the champion
        being the first row of get_archived_event_leaderboard() for that event.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            exprs = self._archive_exprs(cur)
            if not exprs:
                return {}
            elo_expr, rank_expr = exprs
            cur.execute(
                f"""
                SELECT event_id, user_id, user_display_name
                FROM event_standings_archive
                ORDER BY event_id, {elo_expr} DESC, {rank_expr} ASC, user_display_name COLLATE NOCASE ASC
                """
            )
            summaries: dict[int, dict] = {}
            for event_id, user_id, display_name in cur.fetchall():
                summary = summaries.get(event_id)
                if summary is None:
                    summaries[event_id] = {"players": 1, "champion": display_name, "champion_id": user_id}
                else:
                    summary["players"] += 1
            return summaries
        finally:
            conn.close()

    def get_archived_event_leaderboard(self, event_id: int) -> list[dict]:
        """Get full leaderboard for a specific archived event, best first."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            exprs = self._archive_exprs(cur)
            if not exprs:
                return []
            elo_expr, rank_expr = exprs

            cur.execute(
                f"""
                SELECT user_id, user_display_name, {elo_expr}
                FROM event_standings_archive
                WHERE event_id = ?
                ORDER BY {elo_expr} DESC, {rank_expr} ASC, user_display_name COLLATE NOCASE ASC
                """,
                (event_id,),
            )
            return [
                {
                    "user_id": row[0],
                    "display_name": row[1],
                    "event_elo": row[2],
                    "rank": rank,
                }
                for rank, row in enumerate(cur.fetchall(), start=1)
            ]
        finally:
            conn.close()

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

    def search_players_by_name(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search bot players by display name across overall_standings and
        paper_standings (case-insensitive substring match).

        Used as a fallback for player search so bot-only players (those who
        have never logged into the web app and therefore have no row in
        user_profiles) still appear in autocomplete.

        Returns:
            list[dict]: [{"user_id": str, "display_name": str}, ...]
        """
        conn = self._get_connection()
        cur = conn.cursor()

        pattern = f"%{query}%"
        prefix_pattern = f"{query}%"
        results: dict[str, str] = {}

        for table in ("overall_standings", "paper_standings"):
            try:
                cur.execute(
                    f"""
                    SELECT user_id, user_display_name
                    FROM {table}
                    WHERE LOWER(user_display_name) LIKE LOWER(?)
                    ORDER BY
                        CASE WHEN LOWER(user_display_name) = LOWER(?) THEN 0 ELSE 1 END,
                        CASE WHEN LOWER(user_display_name) LIKE LOWER(?) THEN 0 ELSE 1 END,
                        user_display_name ASC
                    LIMIT ?
                    """,
                    (pattern, query, prefix_pattern, limit),
                )
                for uid, name in cur.fetchall():
                    if uid is not None and name:
                        results.setdefault(str(uid), name)
            except sqlite3.OperationalError:
                # Table may not exist yet
                pass

        conn.close()
        return [
            {"user_id": uid, "display_name": name} for uid, name in results.items()
        ][:limit]

    def get_display_name(self, user_id: str) -> str | None:
        """Look up a player's display name from standings tables (fallback
        for users with no user_profiles row)."""
        conn = self._get_connection()
        cur = conn.cursor()

        name = None
        for table in ("overall_standings", "paper_standings"):
            try:
                cur.execute(
                    f"SELECT user_display_name FROM {table} WHERE user_id = ?",
                    (str(user_id),),
                )
                row = cur.fetchone()
                if row and row[0]:
                    name = row[0]
                    break
            except sqlite3.OperationalError:
                pass

        conn.close()
        return name
