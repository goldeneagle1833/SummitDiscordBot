"""Repository for match records database access."""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class MatchRepository:
    """Data access for match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_columns()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_columns(self):
        """Add source and match_type columns if they don't exist yet."""
        conn = self._get_connection()
        cur = conn.cursor()
        # Check if match_records table exists at all
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        if not cur.fetchone():
            conn.close()
            return
        for col, default in [("source", "Discord"), ("match_type", "ranked")]:
            try:
                cur.execute(
                    f"ALTER TABLE match_records ADD COLUMN {col} TEXT DEFAULT '{default}'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            cur.execute(
                f"UPDATE match_records SET {col} = '{default}' WHERE {col} IS NULL"
            )
        conn.commit()
        conn.close()

    def get_available_dates(self) -> list[str]:
        """Get all unique dates that have match data."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT date(timestamp) as match_date
            FROM match_records
            WHERE timestamp IS NOT NULL
            ORDER BY match_date DESC
        """)
        dates = [row[0] for row in cur.fetchall()]
        conn.close()
        return dates

    def get_matches_by_date(self, date: str) -> list[dict]:
        """Get matches for a specific date."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                rowid as match_id,
                winner_display_name,
                winner_elo_change,
                losser_display_name,
                loser_elo_change,
                match_time,
                timestamp,
                winner_id,
                losser_id
            FROM match_records
            WHERE date(timestamp) = ?
            ORDER BY rowid DESC
        """,
            (date,),
        )
        rows = cur.fetchall()
        conn.close()
        return self._rows_to_match_dicts(rows)

    def get_recent_matches(self, hours: int = 24) -> list[dict]:
        """Get matches from the last N hours."""
        # Validate hours is a positive integer to prevent injection
        if not isinstance(hours, int) or hours < 1:
            hours = 24
        if hours > 8760:  # Cap at 1 year
            hours = 8760

        conn = self._get_connection()
        cur = conn.cursor()
        # Use parameterized query - SQLite datetime modifier needs string concatenation
        # but we've validated hours is a safe integer above
        hours_modifier = f"-{hours} hours"
        cur.execute(
            """
            SELECT
                rowid as match_id,
                winner_display_name,
                winner_elo_change,
                losser_display_name,
                loser_elo_change,
                match_time,
                timestamp,
                winner_id,
                losser_id
            FROM match_records
            WHERE timestamp >= datetime('now', ?)
            ORDER BY rowid DESC
        """,
            (hours_modifier,),
        )
        rows = cur.fetchall()
        conn.close()
        return self._rows_to_match_dicts(rows)

    def _rows_to_match_dicts(self, rows) -> list[dict]:
        """Convert database rows to match dictionaries."""
        return [
            {
                "match_id": row[0],
                "winner": row[1] or "Unknown",
                "winner_elo_change": row[2] or 0,
                "loser": row[3] or "Unknown",
                "loser_elo_change": row[4] or 0,
                "match_time": row[5] or 0,
                "timestamp": row[6],
                "winner_id": str(row[7]),
                "loser_id": str(row[8]),
            }
            for row in rows
        ]

    def get_wins_count(self, user_id: int) -> int:
        """Get number of wins for a user (includes archived matches for lifetime stats)."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Count from current match_records
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE winner_id = ?", (user_id,)
        )
        current_count = cur.fetchone()[0]

        # Also count from archive if it exists (for lifetime stats)
        archive_count = 0
        try:
            cur.execute(
                "SELECT COUNT(*) FROM match_records_archive WHERE winner_id = ?",
                (user_id,),
            )
            archive_count = cur.fetchone()[0]
        except Exception:
            pass  # Archive table may not exist

        conn.close()
        return current_count + archive_count

    def get_losses_count(self, user_id: int) -> int:
        """Get number of losses for a user (includes archived matches for lifetime stats)."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Count from current match_records
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE losser_id = ?", (user_id,)
        )
        current_count = cur.fetchone()[0]

        # Also count from archive if it exists (for lifetime stats)
        archive_count = 0
        try:
            cur.execute(
                "SELECT COUNT(*) FROM match_records_archive WHERE losser_id = ?",
                (user_id,),
            )
            archive_count = cur.fetchone()[0]
        except Exception:
            pass  # Archive table may not exist

        conn.close()
        return current_count + archive_count

    def get_season_wins_count(self, user_id: int, event_start: str) -> int:
        """Get number of wins for a user since the event started."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE winner_id = ? AND timestamp >= ?",
            (user_id, event_start),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count

    def get_season_losses_count(self, user_id: int, event_start: str) -> int:
        """Get number of losses for a user since the event started."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE losser_id = ? AND timestamp >= ?",
            (user_id, event_start),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count

    def get_season_players(self, event_start: str) -> list[int]:
        """Get all player IDs who have played since the event started."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT user_id FROM (
                SELECT winner_id as user_id FROM match_records WHERE timestamp >= ?
                UNION
                SELECT losser_id as user_id FROM match_records WHERE timestamp >= ?
            )
        """,
            (event_start, event_start),
        )
        players = [row[0] for row in cur.fetchall()]
        conn.close()
        return players

    def get_match_by_id(self, match_id: int) -> dict | None:
        """Get a single match by its ID."""
        conn = self._get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT
                    winner_id,
                    losser_id,
                    winner_display_name,
                    losser_display_name,
                    timestamp,
                    json_deck_data,
                    json_deck_data_winner,
                    json_deck_data_loser
                FROM match_records
                WHERE rowid = ?
            """,
                (match_id,),
            )
            row = cur.fetchone()
            has_new_columns = True
        except sqlite3.OperationalError:
            cur.execute(
                """
                SELECT
                    winner_id,
                    losser_id,
                    winner_display_name,
                    losser_display_name,
                    timestamp,
                    json_deck_data
                FROM match_records
                WHERE rowid = ?
            """,
                (match_id,),
            )
            row = cur.fetchone()
            has_new_columns = False

        conn.close()

        if not row:
            return None

        result = {
            "winner_id": str(row[0]),
            "loser_id": str(row[1]),
            "winner_name": row[2],
            "loser_name": row[3],
            "timestamp": row[4],
            "old_json_deck": row[5] if len(row) > 5 else None,
        }

        if has_new_columns and len(row) > 6:
            result["winner_json"] = row[6]
            result["loser_json"] = row[7]

        return result

    def get_match_elo_changes(self, match_id: str) -> tuple[int, int]:
        """Get ELO changes for a match."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT winner_elo_change, loser_elo_change FROM match_records WHERE match_id = ?",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()
        return (row[0] if row else 0, row[1] if row else 0)

    def get_matches_with_deck_data(self) -> list[dict]:
        """Get all matches that have deck data for avatar/card analysis.

        Includes both current event matches and archived matches for lifetime stats.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        all_results = []

        # Query current match_records
        try:
            cur.execute("""
                SELECT
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                ORDER BY timestamp DESC
            """)
            rows = cur.fetchall()
            for row in rows:
                all_results.append({"row": row, "use_new_columns": True})
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data,
                    curiosa_url,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data IS NOT NULL
                ORDER BY timestamp DESC
            """)
            rows = cur.fetchall()
            for row in rows:
                all_results.append({"row": row, "use_new_columns": False})

        # Also query match_records_archive for lifetime stats
        try:
            cur.execute("""
                SELECT
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    rowid as match_id
                FROM match_records_archive
                WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                ORDER BY timestamp DESC
            """)
            archive_rows = cur.fetchall()
            for row in archive_rows:
                all_results.append({"row": row, "use_new_columns": True})
        except sqlite3.OperationalError:
            # Archive table may not exist or have old schema
            try:
                cur.execute("""
                    SELECT
                        winner_id,
                        winner_display_name,
                        losser_id,
                        losser_display_name,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        first_player,
                        match_time,
                        json_deck_data,
                        curiosa_url,
                        rowid as match_id
                    FROM match_records_archive
                    WHERE json_deck_data IS NOT NULL
                    ORDER BY timestamp DESC
                """)
                archive_rows = cur.fetchall()
                for row in archive_rows:
                    all_results.append({"row": row, "use_new_columns": False})
            except sqlite3.OperationalError:
                pass  # Archive table doesn't exist yet

        conn.close()
        return all_results

    def get_player_matches(self, player_id: str, limit: int = 100) -> list[dict]:
        """Get matches for a specific player."""
        conn = self._get_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT
                    rowid as match_id,
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser
                FROM match_records
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (player_id, player_id, limit),
            )
        except sqlite3.OperationalError:
            cur.execute(
                """
                SELECT
                    rowid as match_id,
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data,
                    curiosa_url
                FROM match_records
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (player_id, player_id, limit),
            )

        rows = cur.fetchall()
        conn.close()
        return rows

    def insert_external_match(
        self,
        winner_id: str,
        loser_id: str,
        winner_name: str | None,
        loser_name: str | None,
        winner_deck_url: str | None,
        loser_deck_url: str | None,
        json_deck_data_winner: str | None,
        json_deck_data_loser: str | None,
        winner_went_first: str | None,
        match_time: int | None,
        match_comment: str | None,
        source: str,
        timestamp: str,
        winner_elo_change: int,
        loser_elo_change: int,
    ) -> int:
        """Insert an external match into match_records. Returns the rowid."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO match_records
               (reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, did_win,
                timestamp, first_player, match_time, match_comment,
                curiosa_url_winner, curiosa_url_loser,
                json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change,
                winner_went_first, source, match_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                None,  # reporter_id
                winner_id,
                winner_name,
                loser_id,  # maps to losser_id column
                loser_name,  # maps to losser_display_name column
                1,  # did_win (winner perspective)
                timestamp,
                winner_went_first,
                match_time,
                match_comment,
                winner_deck_url,
                loser_deck_url,
                json_deck_data_winner,
                json_deck_data_loser,
                winner_elo_change,
                loser_elo_change,
                winner_went_first,
                source,
                "ranked",
            ),
        )
        rowid = cur.lastrowid
        conn.commit()
        conn.close()
        return rowid

    def get_match_full_details(self, match_id: int) -> dict | None:
        """Get full match details including ELO changes for admin operations."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT rowid, winner_id, losser_id, winner_display_name,
                      losser_display_name, winner_elo_change, loser_elo_change, timestamp
               FROM match_records WHERE rowid = ?""",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "match_id": row[0],
            "winner_id": row[1],
            "loser_id": row[2],
            "winner_name": row[3],
            "loser_name": row[4],
            "winner_elo_change": row[5] or 0,
            "loser_elo_change": row[6] or 0,
            "timestamp": row[7],
        }

    def delete_match(self, match_id: int) -> bool:
        """Delete a match record by rowid. Returns True if deleted."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM match_records WHERE rowid = ?", (match_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_distinct_sources(self) -> list[str]:
        """Get all distinct source names from match_records."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT source FROM match_records WHERE source IS NOT NULL ORDER BY source"
        )
        sources = [row[0] for row in cur.fetchall()]
        conn.close()
        return sources

    def get_source_win_loss(self, user_id: str, source: str) -> dict:
        """Get win/loss counts for a user from a specific source."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE winner_id = ? AND source = ?",
            (user_id, source),
        )
        wins = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE losser_id = ? AND source = ?",
            (user_id, source),
        )
        losses = cur.fetchone()[0]
        conn.close()
        return {"wins": wins, "losses": losses}

    def get_player_source_breakdown(self, player_id: str) -> list[dict]:
        """Get win/loss breakdown by source for a player."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT source,
                      SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN losser_id = ? THEN 1 ELSE 0 END) as losses
               FROM match_records
               WHERE (winner_id = ? OR losser_id = ?) AND source IS NOT NULL
               GROUP BY source""",
            (player_id, player_id, player_id, player_id),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"source": row[0], "wins": row[1], "losses": row[2]}
            for row in rows
        ]

    def get_source_player_stats(self, source: str) -> list[dict]:
        """Get all players and their win/loss for a given source."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT player_id, display_name,
                      SUM(wins) as wins, SUM(losses) as losses
               FROM (
                   SELECT winner_id as player_id,
                          winner_display_name as display_name,
                          1 as wins, 0 as losses
                   FROM match_records WHERE source = ?
                   UNION ALL
                   SELECT losser_id as player_id,
                          losser_display_name as display_name,
                          0 as wins, 1 as losses
                   FROM match_records WHERE source = ?
               )
               GROUP BY player_id
               ORDER BY wins DESC""",
            (source, source),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"user_id": str(row[0]), "display_name": row[1], "wins": row[2], "losses": row[3]}
            for row in rows
        ]
