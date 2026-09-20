"""
Migration: Create explorer.db tables for Explorer Series host applications.

Covers the public "apply to host an Explorer event" form, the per-admin
scoring used to review applicants, and reviewer comments.

Run with: python migrations/create_explorer_application_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp_config

logger = logging.getLogger(__name__)


def create_explorer_application_tables(db_path=None):
    """Create the Explorer application tables if they don't exist."""
    # Resolved at call time so tests can point webapp_config at a temp DB.
    path = db_path or webapp_config.EXPLORER_DB_PATH
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Applicant identity. discord_user_id is the verified session user
            -- for real applications, and NULL for candidates an admin added by
            -- hand before the person has applied.
            discord_user_id TEXT,
            discord_handle TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,

            -- Location, geocoded once on submission for the review map.
            city TEXT,
            state TEXT,
            country TEXT,
            latitude REAL,
            longitude REAL,
            geocoded_at TEXT,

            -- Venue
            lgs_name TEXT,
            lgs_url TEXT,
            lgs_confirmed TEXT,

            -- Application answers
            expected_attendance TEXT,
            proposed_dates TEXT,
            events_run TEXT,
            events_run_count INTEGER,
            avg_headcount TEXT,
            motivation TEXT,
            read_navigator_role INTEGER DEFAULT 0,
            reference_contact TEXT,
            anything_else TEXT,
            referral TEXT,

            -- Review workflow
            status TEXT NOT NULL DEFAULT 'pending',
            source TEXT NOT NULL DEFAULT 'application',
            created_by TEXT,
            submitted_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_explorer_applications_status
        ON explorer_applications (status)
    """)

    # One application per Discord account; admin-added candidates have a NULL
    # discord_user_id and SQLite treats NULLs as distinct, so they don't collide.
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_explorer_applications_user
        ON explorer_applications (discord_user_id)
        WHERE discord_user_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_application_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL
                REFERENCES explorer_applications(id) ON DELETE CASCADE,
            voter_user_id TEXT NOT NULL,
            voter_name TEXT,
            enthusiasm INTEGER,
            track_record INTEGER,
            local_activity INTEGER,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE (application_id, voter_user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS explorer_application_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL
                REFERENCES explorer_applications(id) ON DELETE CASCADE,
            author_user_id TEXT NOT NULL,
            author_name TEXT,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_explorer_application_comments_app
        ON explorer_application_comments (application_id)
    """)

    # Local game store attendance, looked up from the applicant's sorcerytcg.com
    # store link. Added after the table shipped, so ensure them here.
    lgs_columns = {
        "lgs_store_name": "TEXT",
        "lgs_median_players": "INTEGER",
        "lgs_event_count": "INTEGER",
        "lgs_history": "TEXT",
        "lgs_checked_at": "TEXT",
        "lgs_lookup_error": "TEXT",
    }
    cursor.execute("PRAGMA table_info(explorer_applications)")
    existing = {row[1] for row in cursor.fetchall()}
    for column, column_type in lgs_columns.items():
        if column not in existing:
            cursor.execute(
                f"ALTER TABLE explorer_applications ADD COLUMN {column} {column_type}"
            )
            logger.info("Added %s to explorer_applications", column)

    conn.commit()
    conn.close()
    logger.info("Explorer application tables ensured at %s", path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_explorer_application_tables()
    print("Explorer application tables created.")
