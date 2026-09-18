"""
Migration: Create tables for site-hosted single-elimination brackets.

Run with: python migrations/create_bracket_tables.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp_config

logger = logging.getLogger(__name__)


def create_bracket_tables(db_path=None):
    """Create all bracket tables if they don't exist."""
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH))
    cursor = conn.cursor()

    # One row per bracket. Drafts are admin-only until published.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brackets (
            bracket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            entrant_count INTEGER NOT NULL,
            bracket_size INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            seeded_from TEXT,
            elo_event_name TEXT,
            confirm_hours INTEGER NOT NULL DEFAULT 48,
            created_by TEXT,
            created_at TEXT NOT NULL,
            published_at TEXT,
            completed_at TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_brackets_status ON brackets(status)
    """)

    # The seeded field. Seed 1..entrant_count; seeds beyond that are byes.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bracket_entrants (
            bracket_id INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            user_id TEXT,
            display_name TEXT NOT NULL,
            elo INTEGER,
            games INTEGER,
            is_ticket_holder INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (bracket_id, seed)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bracket_entrants_user
        ON bracket_entrants(user_id)
    """)

    # Every slot in the tree, generated on publish. Winners feed next_match_id.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bracket_matches (
            bracket_id INTEGER NOT NULL,
            match_no INTEGER NOT NULL,
            round INTEGER NOT NULL,
            round_title TEXT,
            position INTEGER NOT NULL,
            next_match_no INTEGER,
            next_slot INTEGER,
            p1_seed INTEGER,
            p1_user_id TEXT,
            p1_name TEXT,
            p2_seed INTEGER,
            p2_user_id TEXT,
            p2_name TEXT,
            winner_user_id TEXT,
            winner_seed INTEGER,
            state TEXT NOT NULL DEFAULT 'pending',
            reported_by TEXT,
            reported_winner_id TEXT,
            reported_at TEXT,
            expires_at INTEGER,
            resolved_by TEXT,
            resolved_at TEXT,
            table_provisioned_at TEXT,
            table_p1_url TEXT,
            table_p2_url TEXT,
            replay_url TEXT,
            replay_added_by TEXT,
            replay_added_at TEXT,
            elo_applied_at TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            PRIMARY KEY (bracket_id, match_no)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bracket_matches_round
        ON bracket_matches(bracket_id, round, position)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bracket_matches_players
        ON bracket_matches(p1_user_id, p2_user_id)
    """)

    # Decklists submitted for a bracket. Hidden until the player is knocked
    # out (or the bracket finishes), so nobody can scout a live opponent.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bracket_decks (
            bracket_id INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            user_id TEXT,
            deck_url TEXT,
            deck_name TEXT,
            avatar_name TEXT,
            deck_json TEXT,
            submitted_by TEXT,
            submitted_at TEXT NOT NULL,
            PRIMARY KEY (bracket_id, seed)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bracket_decks_user
        ON bracket_decks(bracket_id, user_id)
    """)

    # Cached ticket-holder roster, synced from Discord so the seed pool can be
    # filtered the same way the bot's leaderboard message filters it.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ticket_holders (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            synced_at TEXT NOT NULL
        )
    """)

    # Brackets published before Sorcery Online tables and replays existed.
    cursor.execute("PRAGMA table_info(bracket_matches)")
    existing = {row[1] for row in cursor.fetchall()}
    for column in (
        "table_provisioned_at",
        "table_p1_url",
        "table_p2_url",
        "replay_url",
        "replay_added_by",
        "replay_added_at",
        "elo_applied_at",
    ):
        if column not in existing:
            cursor.execute(f"ALTER TABLE bracket_matches ADD COLUMN {column} TEXT")

    for column in ("winner_elo_change", "loser_elo_change"):
        if column not in existing:
            cursor.execute(f"ALTER TABLE bracket_matches ADD COLUMN {column} INTEGER")

    conn.commit()
    conn.close()
    logger.info("Bracket tables ensured")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_bracket_tables()
    print("Bracket tables created")
