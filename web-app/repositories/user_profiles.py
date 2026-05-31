"""Repository for user profile storage in match_records.db."""

import json
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
        """Create user_profiles table if it doesn't exist and ensure schema is up-to-date."""
        conn = self._get_connection()
        cur = conn.cursor()

        # Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'discord',
                display_name TEXT NOT NULL,
                custom_display_name TEXT,
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

        # Check if table has all required columns (for existing tables)
        cur.execute("PRAGMA table_info(user_profiles)")
        existing_columns = {row[1] for row in cur.fetchall()}

        required_columns = {
            'email': 'TEXT',
            'email_verified': 'INTEGER',
            'discriminator': 'TEXT',
            'flags': 'INTEGER',
            'public_flags': 'INTEGER',
            'given_name': 'TEXT',
            'family_name': 'TEXT',
            'locale': 'TEXT',
            'raw_oauth_data': 'TEXT',
            'custom_display_name': 'TEXT',
            'profile_public_sections': 'TEXT',
        }

        # Add missing columns
        columns_added = []
        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                cur.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}")
                columns_added.append(col_name)

        if columns_added:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Added missing columns to user_profiles: {', '.join(columns_added)}")

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

    def search_users(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search user profiles across all providers and name fields.

        Searches display_name, given_name, and family_name fields for matches.
        Works for both Discord and Google users.

        Args:
            query: Search string (min 2 characters recommended)
            limit: Maximum number of results to return

        Returns:
            list[dict]: List of user profile dicts with user_id, display_name, avatar, provider
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Use LIKE for case-insensitive prefix match
        search_pattern = f"%{query}%"

        cur.execute(
            """
            SELECT user_id, display_name, avatar, provider
            FROM user_profiles
            WHERE LOWER(display_name) LIKE LOWER(?)
               OR LOWER(given_name) LIKE LOWER(?)
               OR LOWER(family_name) LIKE LOWER(?)
            ORDER BY
                -- Prioritize exact display_name matches
                CASE WHEN LOWER(display_name) = LOWER(?) THEN 0 ELSE 1 END,
                -- Then prefix matches
                CASE WHEN LOWER(display_name) LIKE LOWER(?) THEN 0 ELSE 1 END,
                -- Then alphabetically
                display_name ASC
            LIMIT ?
            """,
            (search_pattern, search_pattern, search_pattern, query, f"{query}%", limit),
        )

        rows = cur.fetchall()
        profiles = [dict(row) for row in rows]

        conn.close()
        return profiles

    def get_by_user_id(self, user_id: str, provider: str = None) -> dict | None:
        """
        Get a user profile by user_id.

        Args:
            user_id: User's unique ID (Discord numeric ID or 'google_<id>')
            provider: Optional provider filter ('discord' or 'google')

        Returns:
            dict: User profile with user_id, display_name, custom_display_name, avatar, provider
                  None if not found
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if provider:
            cur.execute(
                """
                SELECT user_id, display_name, custom_display_name, avatar, provider
                FROM user_profiles
                WHERE user_id = ? AND provider = ?
                LIMIT 1
                """,
                (str(user_id), provider),
            )
        else:
            # Search across all providers
            cur.execute(
                """
                SELECT user_id, display_name, custom_display_name, avatar, provider
                FROM user_profiles
                WHERE user_id = ?
                LIMIT 1
                """,
                (str(user_id),),
            )

        row = cur.fetchone()
        profile = dict(row) if row else None

        conn.close()
        return profile

    def get_custom_display_name(self, user_id: str, provider: str = None) -> str | None:
        """Get the user's custom display name, or None if not set."""
        conn = self._get_connection()
        cur = conn.cursor()

        if provider:
            cur.execute(
                "SELECT custom_display_name FROM user_profiles WHERE user_id = ? AND provider = ?",
                (str(user_id), provider),
            )
        else:
            cur.execute(
                "SELECT custom_display_name FROM user_profiles WHERE user_id = ?",
                (str(user_id),),
            )

        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    # --- Profile visibility settings ---

    VISIBILITY_SECTIONS = [
        "elo_history",
        "elo_brackets",
        "avatar_performance",
        "avatar_matchups",
        "recent_decks",
        "match_history",
        "recorded_games",
    ]

    def get_profile_visibility(self, user_id: str) -> dict:
        """Get profile visibility settings. All sections default to False (private)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT profile_public_sections FROM user_profiles WHERE user_id = ?",
            (str(user_id),),
        )
        row = cur.fetchone()
        conn.close()

        defaults = {s: False for s in self.VISIBILITY_SECTIONS}
        if row and row[0]:
            try:
                saved = json.loads(row[0])
                for key in self.VISIBILITY_SECTIONS:
                    if key in saved:
                        defaults[key] = bool(saved[key])
            except (json.JSONDecodeError, TypeError):
                pass
        return defaults

    def set_profile_visibility(self, user_id: str, sections: dict) -> bool:
        """Update profile visibility settings. Only valid section keys are stored."""
        filtered = {
            k: bool(v) for k, v in sections.items() if k in self.VISIBILITY_SECTIONS
        }
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_profiles SET profile_public_sections = ? WHERE user_id = ?",
            (json.dumps(filtered), str(user_id)),
        )
        conn.commit()
        updated = cur.rowcount > 0
        conn.close()
        return updated

    def set_custom_display_name(self, user_id: str, provider: str, custom_name: str) -> bool:
        """Set the user's custom display name (one-time only).

        Returns True if set successfully, False if already set or user not found.
        """
        import logging
        logger = logging.getLogger(__name__)

        conn = self._get_connection()
        cur = conn.cursor()

        # Check if already set
        cur.execute(
            "SELECT custom_display_name FROM user_profiles WHERE user_id = ? AND provider = ?",
            (str(user_id), provider),
        )
        row = cur.fetchone()

        if not row:
            logger.warning(f"set_custom_display_name: User not found - user_id={user_id}, provider={provider}")
            conn.close()
            return False

        current_custom_name = row[0]
        logger.info(f"set_custom_display_name: user_id={user_id}, provider={provider}, current_custom_name={current_custom_name!r}, new_name={custom_name!r}")

        if current_custom_name:
            # Already has a custom display name
            logger.warning(f"set_custom_display_name: Already set - user_id={user_id}, existing_name={current_custom_name!r}")
            conn.close()
            return False

        cur.execute(
            "UPDATE user_profiles SET custom_display_name = ? WHERE user_id = ? AND provider = ?",
            (custom_name, str(user_id), provider),
        )
        conn.commit()
        rows_updated = cur.rowcount
        conn.close()

        logger.info(f"set_custom_display_name: SUCCESS - user_id={user_id}, rows_updated={rows_updated}")
        return True
