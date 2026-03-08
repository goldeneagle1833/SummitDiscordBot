"""Repository for user profile storage in match_records.db."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from webapp_config import MATCH_RECORDS_DB_PATH


class UserProfileRepository:
    """Data access for user_profiles table in match_records.db."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or MATCH_RECORDS_DB_PATH)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_table(self):
        """Create user_profiles table if it doesn't exist."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'discord',
                display_name TEXT NOT NULL,
                avatar TEXT,
                first_login_at TEXT NOT NULL,
                last_login_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider)
            )
        """)
        conn.commit()
        conn.close()

    def upsert_profile(self, user_id, display_name, avatar, provider="discord"):
        """Create or update a user profile on login.

        On first login, creates a new record with both timestamps set to now.
        On subsequent logins, updates display_name, avatar, and last_login_at
        while preserving first_login_at.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_profiles (user_id, provider, display_name, avatar, first_login_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                display_name = excluded.display_name,
                avatar = excluded.avatar,
                last_login_at = excluded.last_login_at
            """,
            (str(user_id), provider, display_name, avatar, now, now),
        )
        conn.commit()
        conn.close()
