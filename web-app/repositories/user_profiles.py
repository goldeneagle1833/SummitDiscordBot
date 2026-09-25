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
            'nav_preferences': 'TEXT',
            'profile_reset_at': 'TEXT',
            'manually_added_by': 'TEXT',
            'manually_added_at': 'TEXT',
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

    @staticmethod
    def _escape_like(query: str) -> str:
        """Escape LIKE wildcards so user input matches literally."""
        return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search_users(self, query: str, limit: int = 10) -> list[dict]:
        """
        Search players across all providers and name fields.

        Searches user_profiles (display_name, given_name, family_name) and,
        for players who have never logged into the website, falls back to
        display names recorded in match_records and match_records_archive.

        Args:
            query: Search string (min 2 characters recommended)
            limit: Maximum number of results to return

        Returns:
            list[dict]: List of dicts with user_id, display_name, avatar, provider
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        escaped = self._escape_like(query)
        search_pattern = f"%{escaped}%"
        prefix_pattern = f"{escaped}%"

        cur.execute(
            """
            SELECT user_id,
                   -- A player who has chosen a display name is known by it
                   -- everywhere else on the site, so return that, not the
                   -- handle they signed up with.
                   COALESCE(NULLIF(custom_display_name, ''), display_name) AS display_name,
                   avatar, provider
            FROM user_profiles
            WHERE LOWER(display_name) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(custom_display_name) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(given_name) LIKE LOWER(?) ESCAPE '\\'
               OR LOWER(family_name) LIKE LOWER(?) ESCAPE '\\'
            ORDER BY
                -- Prioritize exact name matches
                CASE WHEN LOWER(COALESCE(NULLIF(custom_display_name, ''), display_name))
                          = LOWER(?) THEN 0 ELSE 1 END,
                -- Then prefix matches
                CASE WHEN LOWER(COALESCE(NULLIF(custom_display_name, ''), display_name))
                          LIKE LOWER(?) ESCAPE '\\' THEN 0 ELSE 1 END,
                -- Then alphabetically
                COALESCE(NULLIF(custom_display_name, ''), display_name) ASC
            LIMIT ?
            """,
            (
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                query,
                prefix_pattern,
                limit,
            ),
        )

        profiles = [dict(row) for row in cur.fetchall()]

        def _stripped(uid: str) -> str:
            # Google users' match/elo data is keyed on the bare ID
            return uid[7:] if uid.startswith("google_") else uid

        seen_ids = {_stripped(str(p["user_id"])) for p in profiles}

        # Fall back to match history for players who never logged into the
        # website. These tables are created by the bot, so tolerate absence.
        remaining = limit - len(profiles)
        if remaining > 0:
            existing_tables = {
                row[0]
                for row in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                    " AND name IN ('match_records', 'match_records_archive')"
                ).fetchall()
            }
            union_parts = []
            for table in ("match_records", "match_records_archive"):
                if table in existing_tables:
                    union_parts.append(
                        f"SELECT winner_id AS user_id, winner_display_name AS display_name,"
                        f" timestamp FROM {table}"
                    )
                    union_parts.append(
                        f"SELECT losser_id AS user_id, losser_display_name AS display_name,"
                        f" timestamp FROM {table}"
                    )

            if union_parts:
                union_sql = " UNION ALL ".join(union_parts)
                cur.execute(
                    f"""
                    SELECT CAST(user_id AS TEXT) AS user_id,
                           display_name,
                           MAX(timestamp) AS last_seen
                    FROM ({union_sql})
                    WHERE user_id IS NOT NULL
                      AND display_name IS NOT NULL
                      AND LOWER(display_name) LIKE LOWER(?) ESCAPE '\\'
                    GROUP BY CAST(user_id AS TEXT)
                    ORDER BY
                        CASE WHEN LOWER(display_name) = LOWER(?) THEN 0 ELSE 1 END,
                        CASE WHEN LOWER(display_name) LIKE LOWER(?) ESCAPE '\\' THEN 0 ELSE 1 END,
                        display_name ASC
                    """,
                    (search_pattern, query, prefix_pattern),
                )
                for row in cur.fetchall():
                    uid = str(row["user_id"])
                    if _stripped(uid) in seen_ids:
                        continue
                    seen_ids.add(_stripped(uid))
                    profiles.append({
                        "user_id": uid,
                        "display_name": row["display_name"],
                        "avatar": None,
                        "provider": "discord",
                    })
                    if len(profiles) >= limit:
                        break

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
                SELECT user_id, display_name, custom_display_name, avatar, provider, profile_reset_at
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
                SELECT user_id, display_name, custom_display_name, avatar, provider, profile_reset_at
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

    def get_all_custom_display_names(self) -> dict:
        """Every chosen display name, keyed by id.

        Google accounts are stored with a `google_` prefix that the bot's
        tables do not use, so each name is also filed under the bare id.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT user_id, custom_display_name FROM user_profiles"
                " WHERE custom_display_name IS NOT NULL AND custom_display_name != ''"
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []
        conn.close()

        names = {}
        for user_id, name in rows:
            user_id = str(user_id)
            names[user_id] = name
            if user_id.startswith("google_"):
                names.setdefault(user_id[7:], name)
        return names

    def get_custom_display_names(self, user_ids) -> dict:
        """The chosen names for a set of players, keyed by the id asked for.

        Google accounts are keyed with a `google_` prefix here but appear
        without it in the bot's tables, so a caller holding a bare id still
        gets an answer.
        """
        wanted = {}
        for user_id in user_ids or []:
            if not user_id:
                continue
            asked = str(user_id)
            wanted.setdefault(asked, asked)
            wanted.setdefault(f"google_{asked}", asked)

        if not wanted:
            return {}

        conn = self._get_connection()
        cur = conn.cursor()
        keys = list(wanted)
        names = {}
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            try:
                cur.execute(
                    "SELECT user_id, custom_display_name FROM user_profiles"
                    f" WHERE user_id IN ({placeholders})",
                    chunk,
                )
            except sqlite3.OperationalError:
                break
            for user_id, name in cur.fetchall():
                if name:
                    names[wanted[str(user_id)]] = name

        conn.close()
        return names

    # --- Profile visibility settings ---

    VISIBILITY_SECTIONS = [
        "elo_history",
        "elo_brackets",
        "avatar_performance",
        "avatar_matchups",
        "recent_decks",
        "recorded_games",
        "deck_urls",
        "deck_snapshots",
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
        """Set or change the user's chosen display name.

        A player can rename themselves as often as they like: the bot keeps
        rewriting the standings name from Discord, so the site's chosen name
        is the only one they control. Returns False only if the profile does
        not exist.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_profiles SET custom_display_name = ? WHERE user_id = ? AND provider = ?",
            (custom_name, str(user_id), provider),
        )
        conn.commit()
        rows_updated = cur.rowcount
        conn.close()
        return rows_updated > 0

    # --- Nav bar preferences ---

    def get_nav_preferences(self, user_id: str) -> list[str] | None:
        """Get saved nav bar link labels for a user. Returns None if not set."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT nav_preferences FROM user_profiles WHERE user_id = ?",
            (str(user_id),),
        )
        row = cur.fetchone()
        conn.close()

        if row and row[0]:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def set_nav_preferences(self, user_id: str, labels: list[str]) -> bool:
        """Save nav bar link labels for a user."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_profiles SET nav_preferences = ? WHERE user_id = ?",
            (json.dumps(labels), str(user_id)),
        )
        conn.commit()
        updated = cur.rowcount > 0
        conn.close()
        return updated

    def get_profile_reset_at(self, user_id: str) -> str | None:
        """Get the profile reset timestamp for a user, or None if never reset."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT profile_reset_at FROM user_profiles WHERE user_id = ?",
            (str(user_id),),
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None

    def set_profile_reset_at(self, user_id: str) -> bool:
        """Set the profile reset timestamp to now. Returns True if updated."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_profiles SET profile_reset_at = ? WHERE user_id = ?",
            (now, str(user_id)),
        )
        conn.commit()
        updated = cur.rowcount > 0
        conn.close()
        return updated

    def clear_profile_reset(self, user_id: str) -> bool:
        """Clear the profile reset timestamp (undo a reset). Returns True if updated."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_profiles SET profile_reset_at = NULL WHERE user_id = ?",
            (str(user_id),),
        )
        conn.commit()
        updated = cur.rowcount > 0
        conn.close()
        return updated

    # ------------------------------------------------------------------
    # Manually added profiles (admin "add user by Discord name")
    # ------------------------------------------------------------------

    def create_manual_profile(
        self,
        user_id: str,
        display_name: str,
        provider: str = "discord",
        avatar: str | None = None,
        added_by: str | None = None,
    ) -> bool:
        """Create a profile for someone who has never logged in.

        Used by the admin "add user" page so a known Discord player is
        searchable and linkable before their first login. Never overwrites an
        existing profile: returns False if one already exists for this
        (user_id, provider) pair.

        Args:
            user_id: Discord snowflake (or 'google_<id>') for the new profile
            display_name: Name to show for the user
            provider: 'discord' or 'google'
            avatar: Optional avatar hash/URL
            added_by: Name of the admin creating the profile

        Returns:
            bool: True if a row was created, False if one already existed.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_profiles (
                user_id, provider, display_name, avatar,
                first_login_at, last_login_at,
                manually_added_by, manually_added_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, provider) DO NOTHING
            """,
            (str(user_id), provider, display_name, avatar, now, now, added_by, now),
        )
        conn.commit()
        created = cur.rowcount > 0
        conn.close()
        return created

    def delete_manual_profile(self, user_id: str, provider: str = "discord") -> bool:
        """Delete a manually added profile that has never been logged into.

        Profiles belonging to real logins are left untouched — account
        deletion goes through AdminService.delete_account instead.

        Returns:
            bool: True if a row was deleted.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM user_profiles
            WHERE user_id = ?
              AND provider = ?
              AND manually_added_at IS NOT NULL
              AND last_login_at <= manually_added_at
            """,
            (str(user_id), provider),
        )
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted

    def list_profiles(
        self, query: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """List user profiles, newest first, optionally filtered by name or ID.

        Returns:
            tuple: (profiles, total_matching_count). Each profile carries
            ``manually_added`` and ``has_logged_in`` flags so the admin UI can
            tell placeholder profiles apart from real accounts.
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        where = ""
        params: list = []
        if query:
            pattern = f"%{self._escape_like(query)}%"
            where = (
                " WHERE LOWER(display_name) LIKE LOWER(?) ESCAPE '\\'"
                " OR LOWER(custom_display_name) LIKE LOWER(?) ESCAPE '\\'"
                " OR user_id LIKE ? ESCAPE '\\'"
            )
            params = [pattern, pattern, pattern]

        total = cur.execute(
            f"SELECT COUNT(*) FROM user_profiles{where}", params
        ).fetchone()[0]

        cur.execute(
            f"""
            SELECT user_id, provider, display_name, custom_display_name, avatar,
                   first_login_at, last_login_at, manually_added_by, manually_added_at
            FROM user_profiles{where}
            ORDER BY COALESCE(manually_added_at, first_login_at) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )

        profiles = []
        for row in cur.fetchall():
            profile = dict(row)
            manually_added = profile.get("manually_added_at") is not None
            profile["manually_added"] = manually_added
            profile["has_logged_in"] = (
                not manually_added
                or (profile.get("last_login_at") or "") > profile["manually_added_at"]
            )
            profiles.append(profile)

        conn.close()
        return profiles, total

    def find_unprofiled_players(self, query: str, limit: int = 10) -> list[dict]:
        """Find players seen in match history who have no user_profiles row.

        These are the people an admin can usefully add a profile for: the bot
        already knows their Discord ID and name, but they have never logged
        into the website.

        Returns:
            list[dict]: [{"user_id": str, "display_name": str, "last_seen": str}]
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        existing_tables = {
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name IN ('match_records', 'match_records_archive')"
            ).fetchall()
        }

        union_parts = []
        for table in ("match_records", "match_records_archive"):
            if table in existing_tables:
                union_parts.append(
                    f"SELECT winner_id AS user_id, winner_display_name AS display_name,"
                    f" timestamp FROM {table}"
                )
                union_parts.append(
                    f"SELECT losser_id AS user_id, losser_display_name AS display_name,"
                    f" timestamp FROM {table}"
                )

        if not union_parts:
            conn.close()
            return []

        escaped = self._escape_like(query)
        union_sql = " UNION ALL ".join(union_parts)
        cur.execute(
            f"""
            SELECT CAST(user_id AS TEXT) AS user_id,
                   display_name,
                   MAX(timestamp) AS last_seen
            FROM ({union_sql})
            WHERE user_id IS NOT NULL
              AND display_name IS NOT NULL
              AND LOWER(display_name) LIKE LOWER(?) ESCAPE '\\'
              AND CAST(user_id AS TEXT) NOT IN (SELECT user_id FROM user_profiles)
            GROUP BY CAST(user_id AS TEXT)
            ORDER BY
                CASE WHEN LOWER(display_name) = LOWER(?) THEN 0 ELSE 1 END,
                CASE WHEN LOWER(display_name) LIKE LOWER(?) ESCAPE '\\' THEN 0 ELSE 1 END,
                display_name ASC
            LIMIT ?
            """,
            (f"%{escaped}%", query, f"{escaped}%", limit),
        )
        results = [dict(row) for row in cur.fetchall()]
        conn.close()
        return results

    def filter_existing_user_ids(self, user_ids: list[str]) -> set[str]:
        """Return the subset of user_ids that already have a profile row."""
        if not user_ids:
            return set()
        conn = self._get_connection()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in user_ids)
        rows = cur.execute(
            f"SELECT user_id FROM user_profiles WHERE user_id IN ({placeholders})",
            [str(uid) for uid in user_ids],
        ).fetchall()
        conn.close()
        return {str(row[0]) for row in rows}
