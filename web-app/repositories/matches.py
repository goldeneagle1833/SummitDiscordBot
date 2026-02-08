"""Repository for match records database access."""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class MatchRepository:
    """Data access for match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

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
