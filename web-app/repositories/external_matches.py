"""Repository for external match reports and source ELO database access."""

import sqlite3
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH


class ExternalMatchRepository:
    """Data access for external_match_reports and source_elo tables."""

    def __init__(
        self,
        match_db_path: Path | str | None = None,
        elo_db_path: Path | str | None = None,
    ):
        self._match_db_path = str(match_db_path or MATCH_RECORDS_DB_PATH)
        self._elo_db_path = str(elo_db_path or ELO_DB_PATH)

    def _get_match_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._match_db_path)

    def _get_elo_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._elo_db_path)

    def ensure_tables(self):
        """Create external_match_reports, source_elo, and user_links tables if needed."""
        # external_match_reports in match_records.db
        conn = self._get_match_connection()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS external_match_reports
                       (report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        winner_id TEXT NOT NULL,
                        loser_id TEXT NOT NULL,
                        winner_display_name TEXT,
                        loser_display_name TEXT,
                        winner_deck_url TEXT,
                        loser_deck_url TEXT,
                        json_deck_data_winner TEXT,
                        json_deck_data_loser TEXT,
                        winner_went_first TEXT,
                        match_time INTEGER,
                        match_comment TEXT,
                        source TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        winner_elo_change INTEGER,
                        loser_elo_change INTEGER
                       )""")
        conn.commit()
        conn.close()

        # source_elo and user_links in elo.db
        conn = self._get_elo_connection()
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS source_elo
                       (user_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        user_display_name TEXT,
                        elo INTEGER DEFAULT 1500,
                        PRIMARY KEY (user_id, source)
                       )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_links
                       (discord_user_id INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        source_user_id TEXT NOT NULL,
                        linked_at TEXT NOT NULL,
                        PRIMARY KEY (source, source_user_id)
                       )""")
        conn.commit()
        conn.close()

    def insert_report(
        self,
        winner_id: str,
        loser_id: str,
        winner_name: str | None,
        loser_name: str | None,
        winner_deck_url: str,
        loser_deck_url: str,
        json_deck_data_winner: str,
        json_deck_data_loser: str,
        winner_went_first: str | None,
        match_time: int | None,
        match_comment: str | None,
        source: str,
        timestamp: str,
        winner_elo_change: int,
        loser_elo_change: int,
    ) -> int:
        """Insert an external match report. Returns the report_id."""
        self.ensure_tables()
        conn = self._get_match_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO external_match_reports
               (winner_id, loser_id, winner_display_name, loser_display_name,
                winner_deck_url, loser_deck_url, json_deck_data_winner,
                json_deck_data_loser, winner_went_first, match_time,
                match_comment, source, timestamp,
                winner_elo_change, loser_elo_change)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                winner_elo_change,
                loser_elo_change,
            ),
        )
        report_id = cur.lastrowid
        conn.commit()
        conn.close()
        return report_id

    def get_source_elo(self, user_id: str, source: str) -> int:
        """Get a user's ELO for a specific source. Returns 1500 if not found."""
        self.ensure_tables()
        conn = self._get_elo_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT elo FROM source_elo WHERE user_id = ? AND source = ?",
            (user_id, source),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 1500

    def update_source_elo(
        self, user_id: str, source: str, display_name: str, new_elo: int
    ):
        """Upsert a user's ELO for a specific source."""
        self.ensure_tables()
        conn = self._get_elo_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO source_elo (user_id, source, user_display_name, elo)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, source)
               DO UPDATE SET elo = ?, user_display_name = ?""",
            (user_id, source, display_name, new_elo, new_elo, display_name),
        )
        conn.commit()
        conn.close()

    def get_source_elo_standings(self, source: str) -> list[dict]:
        """Get ELO standings for a specific source, ordered by ELO descending."""
        self.ensure_tables()
        conn = self._get_elo_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT user_id, user_display_name, elo
               FROM source_elo
               WHERE source = ?
               ORDER BY elo DESC""",
            (source,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {"user_id": row[0], "display_name": row[1], "elo": row[2]}
            for row in rows
        ]

    def get_all_sources(self) -> list[str]:
        """Get all distinct source names from external match reports."""
        self.ensure_tables()
        conn = self._get_match_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT source FROM external_match_reports ORDER BY source"
        )
        sources = [row[0] for row in cur.fetchall()]
        conn.close()
        return sources

    def get_match_count_by_source(self, user_id: str, source: str) -> dict:
        """Get win/loss counts for a user from a specific source."""
        self.ensure_tables()
        conn = self._get_match_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM external_match_reports WHERE winner_id = ? AND source = ?",
            (user_id, source),
        )
        wins = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM external_match_reports WHERE loser_id = ? AND source = ?",
            (user_id, source),
        )
        losses = cur.fetchone()[0]
        conn.close()
        return {"wins": wins, "losses": losses}
