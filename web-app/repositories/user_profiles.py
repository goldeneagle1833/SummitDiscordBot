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
                email TEXT,
                email_verified INTEGER,
                first_login_at TEXT NOT NULL,
                last_login_at TEXT NOT NULL,
                -- Discord-specific fields
                discriminator TEXT,
                flags INTEGER,
                public_flags INTEGER,
                -- Google-specific fields
                given_name TEXT,
                family_name TEXT,
                locale TEXT,
                -- Store raw OAuth response for future reference
                raw_oauth_data TEXT,
                PRIMARY KEY (user_id, provider)
            )
        """)
        conn.commit()
        conn.close()

    def upsert_profile(
        self,
        user_id,
        display_name,
        avatar=None,
        provider="discord",
        email=None,
        email_verified=None,
        discriminator=None,
        flags=None,
        public_flags=None,
        given_name=None,
        family_name=None,
        locale=None,
        raw_oauth_data=None,
    ):
        """Create or update a user profile on login.

        On first login, creates a new record with both timestamps set to now.
        On subsequent logins, updates all provided fields and last_login_at
        while preserving first_login_at.

        Args:
            user_id: User's unique ID (Discord ID or google_<id>)
            display_name: User's display name
            avatar: URL to user's avatar
            provider: 'discord' or 'google'
            email: User's email address
            email_verified: Boolean (0/1) if email is verified
            discriminator: Discord discriminator (e.g., '1234')
            flags: Discord account flags
            public_flags: Discord public flags
            given_name: Google given/first name
            family_name: Google family/last name
            locale: User's locale (e.g., 'en-US')
            raw_oauth_data: JSON string of full OAuth response
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_profiles (
                user_id, provider, display_name, avatar, email, email_verified,
                discriminator, flags, public_flags, given_name, family_name,
                locale, raw_oauth_data, first_login_at, last_login_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                display_name = excluded.display_name,
                avatar = excluded.avatar,
                email = excluded.email,
                email_verified = excluded.email_verified,
                discriminator = excluded.discriminator,
                flags = excluded.flags,
                public_flags = excluded.public_flags,
                given_name = excluded.given_name,
                family_name = excluded.family_name,
                locale = excluded.locale,
                raw_oauth_data = excluded.raw_oauth_data,
                last_login_at = excluded.last_login_at
            """,
            (
                str(user_id),
                provider,
                display_name,
                avatar,
                email,
                1 if email_verified else 0 if email_verified is not None else None,
                discriminator,
                flags,
                public_flags,
                given_name,
                family_name,
                locale,
                raw_oauth_data,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

    def search_by_display_name(
        self, query: str, provider: str = "discord", limit: int = 10
    ) -> list[dict]:
        """
        Search user profiles by display name (case-insensitive prefix match).

        Args:
            query: Search string (min 2 characters recommended)
            provider: OAuth provider ('discord' or 'google'), default 'discord'
            limit: Maximum number of results to return

        Returns:
            list[dict]: List of user profile dicts with user_id, display_name, avatar
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Use LIKE for case-insensitive prefix match
        # The % wildcard matches any characters after the query
        search_pattern = f"{query}%"

        cur.execute(
            """
            SELECT user_id, display_name, avatar
            FROM user_profiles
            WHERE LOWER(display_name) LIKE LOWER(?)
              AND provider = ?
            ORDER BY display_name ASC
            LIMIT ?
            """,
            (search_pattern, provider, limit),
        )

        rows = cur.fetchall()
        profiles = [dict(row) for row in rows]

        conn.close()
        return profiles
