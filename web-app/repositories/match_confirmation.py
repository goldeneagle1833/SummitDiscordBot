"""Repository for match confirmation database access."""

import sqlite3
from pathlib import Path
from typing import Optional

from webapp_config import MATCH_RECORDS_DB_PATH


class MatchConfirmationRepository:
    """Data access for match_confirmations table."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table_exists()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self._db_path)

    def _ensure_table_exists(self) -> None:
        """
        Ensure match_confirmations table exists, create if missing.

        This method is called during __init__ to guarantee the table exists
        before any operations are performed. Safe to call multiple times.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_confirmations'"
        )

        if not cursor.fetchone():
            # Table doesn't exist, create it
            cursor.executescript("""
                BEGIN TRANSACTION;

                CREATE TABLE IF NOT EXISTS match_confirmations (
                    -- Primary Key
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- Players involved
                    submitter_discord_id TEXT NOT NULL,
                    opponent_discord_id TEXT NOT NULL,
                    winner_discord_id TEXT NOT NULL,
                    loser_discord_id TEXT NOT NULL,

                    -- Match details
                    winner_deck_url TEXT,
                    loser_deck_url TEXT,
                    went_first TEXT CHECK(went_first IN ('submitter', 'opponent')),
                    final_life_winner INTEGER NOT NULL,
                    final_life_loser INTEGER NOT NULL,

                    -- Status tracking
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'disputed', 'expired', 'auto_confirmed')),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    reminder_sent_at INTEGER,
                    confirmed_at INTEGER,
                    dispute_reason TEXT,

                    -- Constraints
                    CHECK(submitter_discord_id != opponent_discord_id),
                    CHECK(winner_discord_id IN (submitter_discord_id, opponent_discord_id)),
                    CHECK(loser_discord_id IN (submitter_discord_id, opponent_discord_id)),
                    CHECK(winner_discord_id != loser_discord_id)
                );

                -- Indexes for query performance
                CREATE INDEX IF NOT EXISTS idx_opponent_pending
                    ON match_confirmations(opponent_discord_id, status, expires_at)
                    WHERE status = 'pending';

                CREATE INDEX IF NOT EXISTS idx_status_created
                    ON match_confirmations(status, created_at);

                CREATE INDEX IF NOT EXISTS idx_expires_reminder
                    ON match_confirmations(expires_at, reminder_sent_at)
                    WHERE status = 'pending' AND reminder_sent_at IS NULL;

                CREATE INDEX IF NOT EXISTS idx_submitter_recent
                    ON match_confirmations(submitter_discord_id, created_at DESC);

                COMMIT;
            """)

            import logging
            logger = logging.getLogger(__name__)
            logger.info("Created match_confirmations table with indexes")

        # Migration: Add match_type column if it doesn't exist
        cursor.execute("PRAGMA table_info(match_confirmations)")
        columns = [row[1] for row in cursor.fetchall()]

        if "match_type" not in columns:
            cursor.execute("""
                ALTER TABLE match_confirmations
                ADD COLUMN match_type TEXT DEFAULT 'ranked' CHECK(match_type IN ('ranked', 'casual'))
            """)
            conn.commit()

            import logging
            logger = logging.getLogger(__name__)
            logger.info("Added match_type column to match_confirmations table")

        # Re-fetch columns after potential match_type migration
        cursor.execute("PRAGMA table_info(match_confirmations)")
        columns = [row[1] for row in cursor.fetchall()]

        if "season_id" not in columns:
            cursor.execute("""
                ALTER TABLE match_confirmations
                ADD COLUMN season_id INTEGER DEFAULT NULL
            """)
            conn.commit()

            import logging
            logger = logging.getLogger(__name__)
            logger.info("Added season_id column to match_confirmations table")

        conn.close()

    def create_confirmation(
        self,
        submitter_id: int | str,
        opponent_id: int | str,
        winner_id: int | str,
        loser_id: int | str,
        final_life_winner: int,
        final_life_loser: int,
        went_first: str,
        winner_deck_url: Optional[str] = None,
        loser_deck_url: Optional[str] = None,
        match_type: str = "ranked",
        season_id: Optional[int] = None,
    ) -> int:
        """
        Create a new match confirmation request.

        Args:
            submitter_id: Discord user ID of player submitting report (int or str to handle large Google IDs)
            opponent_id: Discord user ID of player who must confirm (int or str to handle large Google IDs)
            winner_id: Discord user ID of winner (int or str to handle large Google IDs)
            loser_id: Discord user ID of loser (int or str to handle large Google IDs)
            final_life_winner: Winner's final life total
            final_life_loser: Loser's final life total
            went_first: Turn order relative to submitter ('submitter'|'opponent')
            winner_deck_url: Optional Curiosa.io deck URL for winner
            loser_deck_url: Optional Curiosa.io deck URL for loser
            match_type: Match type ('ranked' or 'casual'), defaults to 'ranked'
            season_id: Optional season ID to attribute this match to

        Returns:
            int: The confirmation_id of created record
        """
        import time

        conn = self._get_connection()
        cursor = conn.cursor()

        created_at = int(time.time())
        expires_at = created_at + (48 * 60 * 60)  # 48 hours from now (updated from 24hr)

        cursor.execute(
            """
            INSERT INTO match_confirmations (
                submitter_discord_id, opponent_discord_id,
                winner_discord_id, loser_discord_id,
                winner_deck_url, loser_deck_url,
                final_life_winner, final_life_loser,
                went_first, match_type, season_id, status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                str(submitter_id),
                str(opponent_id),
                str(winner_id),
                str(loser_id),
                winner_deck_url,
                loser_deck_url,
                final_life_winner,
                final_life_loser,
                went_first,
                match_type,
                season_id,
                created_at,
                expires_at,
            ),
        )

        confirmation_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return confirmation_id

    def get_pending_confirmations(self, user_id: int | str) -> list[dict]:
        """
        Get all pending confirmations for a user (where they are the opponent).

        Args:
            user_id: Discord user ID (int or str to handle large Google IDs)

        Returns:
            list[dict]: List of pending confirmation records
        """
        import time

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute(
            """
            SELECT * FROM match_confirmations
            WHERE opponent_discord_id = ?
              AND status = 'pending'
              AND expires_at > ?
            ORDER BY created_at DESC
            """,
            (str(user_id), current_time),
        )

        rows = cursor.fetchall()
        confirmations = [dict(row) for row in rows]

        conn.close()
        return confirmations

    def update_confirmation_status(
        self,
        confirmation_id: int,
        status: str,
        confirmed_at: Optional[int] = None,
        dispute_reason: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a match confirmation.

        Args:
            confirmation_id: ID of confirmation to update
            status: New status ('confirmed', 'disputed', 'auto_confirmed')
            confirmed_at: Unix timestamp when confirmed
            dispute_reason: Optional reason for dispute

        Returns:
            bool: True if update succeeded, False if not found
        """
        import time

        if confirmed_at is None:
            confirmed_at = int(time.time())

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE match_confirmations
            SET status = ?, confirmed_at = ?, dispute_reason = ?
            WHERE id = ?
            """,
            (status, confirmed_at, dispute_reason, confirmation_id),
        )

        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        return rows_affected > 0

    def get_expired_confirmations(self) -> list[dict]:
        """
        Get all confirmations that have expired and are still pending.

        Returns:
            list[dict]: List of expired confirmation records
        """
        import time

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_time = int(time.time())

        cursor.execute(
            """
            SELECT * FROM match_confirmations
            WHERE status = 'pending'
              AND expires_at <= ?
            ORDER BY expires_at ASC
            """,
            (current_time,),
        )

        rows = cursor.fetchall()
        confirmations = [dict(row) for row in rows]

        conn.close()
        return confirmations

    def check_duplicate_pending(self, submitter_id: int, opponent_id: int) -> bool:
        """
        Check if a pending confirmation already exists for these players within 1 hour.

        Args:
            submitter_id: Discord user ID of submitter
            opponent_id: Discord user ID of opponent

        Returns:
            bool: True if duplicate exists, False otherwise
        """
        import time

        conn = self._get_connection()
        cursor = conn.cursor()

        one_hour_ago = int(time.time()) - (60 * 60)

        cursor.execute(
            """
            SELECT COUNT(*) FROM match_confirmations
            WHERE submitter_discord_id = ?
              AND opponent_discord_id = ?
              AND status = 'pending'
              AND created_at > ?
            """,
            (str(submitter_id), str(opponent_id), one_hour_ago),
        )

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    def get_confirmation_by_id(self, confirmation_id: int) -> Optional[dict]:
        """
        Get a specific confirmation by ID.

        Args:
            confirmation_id: ID of confirmation

        Returns:
            dict or None: Confirmation record if found
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM match_confirmations WHERE id = ?", (confirmation_id,)
        )

        row = cursor.fetchone()
        confirmation = dict(row) if row else None

        conn.close()
        return confirmation

    def get_recent_lfg_opponents(self, user_id: int | str, limit: int = 5) -> list[dict]:
        """
        Get recent opponents from match history for LFG auto-fill.

        Note: This requires match_records table to exist, which may not be present yet.
        Returns empty list if table doesn't exist.

        Args:
            user_id: Discord user ID (int or str to handle large Google IDs)
            limit: Maximum number of opponents to return

        Returns:
            list[dict]: List of recent opponent info (discord_id, last_matched_at, match_count)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check if match_records table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='match_records'"
        )
        if not cursor.fetchone():
            conn.close()
            return []

        conn.row_factory = sqlite3.Row

        # Query for recent opponents
        cursor.execute(
            """
            SELECT
                CASE
                    WHEN winner_id = ? THEN losser_id
                    ELSE winner_id
                END as opponent_id,
                MAX(timestamp) as last_matched_at,
                COUNT(*) as match_count
            FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            GROUP BY opponent_id
            ORDER BY last_matched_at DESC
            LIMIT ?
            """,
            (str(user_id), str(user_id), str(user_id), limit),
        )

        rows = cursor.fetchall()
        opponents = [dict(row) for row in rows]

        conn.close()
        return opponents

    def get_confirmations_needing_reminder(self) -> list[dict]:
        """
        Get all pending confirmations that need a 24-hour reminder.

        Finds confirmations where:
        - status is 'pending'
        - reminder_sent_at is NULL (reminder not yet sent)
        - created_at is more than 24 hours ago
        - expires_at is still in the future (not expired yet)

        Returns:
            list[dict]: List of confirmation records needing reminders
        """
        import time

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        current_time = int(time.time())
        twenty_four_hours_ago = current_time - (24 * 60 * 60)

        cursor.execute(
            """
            SELECT * FROM match_confirmations
            WHERE status = 'pending'
              AND reminder_sent_at IS NULL
              AND created_at <= ?
              AND expires_at > ?
            ORDER BY created_at ASC
            """,
            (twenty_four_hours_ago, current_time),
        )

        rows = cursor.fetchall()
        confirmations = [dict(row) for row in rows]

        conn.close()
        return confirmations

    def update_reminder_sent(self, confirmation_id: int) -> bool:
        """
        Mark that a reminder has been sent for a confirmation.

        Sets reminder_sent_at to current timestamp.

        Args:
            confirmation_id: ID of confirmation

        Returns:
            bool: True if update succeeded, False if not found
        """
        import time

        conn = self._get_connection()
        cursor = conn.cursor()

        reminder_sent_at = int(time.time())

        cursor.execute(
            """
            UPDATE match_confirmations
            SET reminder_sent_at = ?
            WHERE id = ?
            """,
            (reminder_sent_at, confirmation_id),
        )

        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()

        return rows_affected > 0
