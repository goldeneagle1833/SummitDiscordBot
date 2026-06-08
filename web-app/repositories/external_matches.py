"""Repository for external match records (3rd-party reported, no ELO)."""

import sqlite3

from webapp_config import MATCH_RECORDS_DB_PATH


class ExternalMatchRepository:
    """Data access for the external_matches table in match_records.db."""

    def __init__(self, db_path=None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def insert(
        self,
        winner_id: str,
        loser_id: str,
        winner_deck_url: str | None,
        loser_deck_url: str | None,
        json_deck_data_winner: str | None,
        json_deck_data_loser: str | None,
        source: str,
        timestamp: str,
        winner_name: str | None = None,
        loser_name: str | None = None,
        winner_went_first: str | None = None,
        match_time: int | None = None,
        match_comment: str | None = None,
    ) -> int:
        """Insert an external match. Returns the new row id."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO external_matches
               (winner_id, loser_id, winner_display_name, loser_display_name,
                winner_deck_url, loser_deck_url,
                json_deck_data_winner, json_deck_data_loser,
                winner_went_first, match_time, match_comment,
                source, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                winner_id,
                loser_id,
                winner_name,
                loser_name,
                winner_deck_url,
                loser_deck_url,
                json_deck_data_winner,
                json_deck_data_loser,
                winner_went_first,
                match_time,
                match_comment,
                source,
                timestamp,
            ),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
        return row_id

    def get_wins_count(self, user_id: str) -> int:
        """Count wins for a user in external matches."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM external_matches WHERE winner_id = ?",
                (user_id,),
            )
            count = cur.fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        conn.close()
        return count

    def get_losses_count(self, user_id: str) -> int:
        """Count losses for a user in external matches."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COUNT(*) FROM external_matches WHERE loser_id = ?",
                (user_id,),
            )
            count = cur.fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        conn.close()
        return count

    def get_player_matches(self, player_id: str, limit: int = 100) -> list[dict]:
        """Get external match history for a player."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT id, winner_id, loser_id,
                          winner_display_name, loser_display_name,
                          winner_deck_url, loser_deck_url,
                          json_deck_data_winner, json_deck_data_loser,
                          winner_went_first, match_time, match_comment,
                          source, timestamp
                   FROM external_matches
                   WHERE winner_id = ? OR loser_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (player_id, player_id, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            rows = []
        conn.close()
        return rows
