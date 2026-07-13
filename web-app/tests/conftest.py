"""Shared fixtures for web-app tests."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Override database paths BEFORE any app code runs
_tmp_dir = tempfile.mkdtemp(prefix="summit_test_")

os.environ["ELO_DB_PATH"] = str(Path(_tmp_dir) / "elo.db")
os.environ["MATCH_RECORDS_DB_PATH"] = str(Path(_tmp_dir) / "match_records.db")
os.environ["FART_SCORES_DB_PATH"] = str(Path(_tmp_dir) / "fart_scores.db")
os.environ["COMMUNITY_DB_PATH"] = str(Path(_tmp_dir) / "community.db")
os.environ["ANALYTICS_DB_PATH"] = str(Path(_tmp_dir) / "analytics.db")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["API_KEYS"] = "test-api-key-123"
os.environ["ADMIN_IDS"] = "admin_user_1"

# Force reload webapp_config to pick up env overrides
import importlib
import webapp_config
importlib.reload(webapp_config)

from repositories.matches import MatchRepository
# Reset the class-level flag so columns get ensured with fresh DBs
MatchRepository._columns_ensured = False


def _patch_db_paths(elo_db, match_db, tmp_path):
    """Patch database paths in webapp_config AND all repository modules
    that import the paths at module level."""
    import repositories.elo
    import repositories.matches
    import repositories.user_profiles
    import repositories.match_confirmation
    import repositories.audit
    import repositories.blocked_users_repo

    webapp_config.ELO_DB_PATH = elo_db
    webapp_config.MATCH_RECORDS_DB_PATH = match_db
    webapp_config.FART_SCORES_DB_PATH = tmp_path / "fart_scores.db"
    webapp_config.COMMUNITY_DB_PATH = tmp_path / "community.db"
    webapp_config.ANALYTICS_DB_PATH = tmp_path / "analytics.db"

    # Patch the module-level bindings that repos captured via `from webapp_config import ...`
    repositories.elo.ELO_DB_PATH = elo_db
    repositories.matches.MATCH_RECORDS_DB_PATH = match_db
    repositories.matches.ELO_DB_PATH = elo_db
    repositories.user_profiles.MATCH_RECORDS_DB_PATH = match_db
    repositories.match_confirmation.MATCH_RECORDS_DB_PATH = match_db
    repositories.audit.MATCH_RECORDS_DB_PATH = match_db
    repositories.blocked_users_repo.MATCH_RECORDS_DB_PATH = match_db

    # Patch auth module-level bindings
    import utils.auth
    utils.auth.ADMINS = webapp_config.ADMINS
    utils.auth.VALID_API_KEYS = webapp_config.VALID_API_KEYS
    utils.auth.CURIO_EDITORS = webapp_config.CURIO_EDITORS


@pytest.fixture()
def elo_db(tmp_path):
    """Create a temporary ELO database with test schema."""
    db_path = tmp_path / "elo.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE overall_standings (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT,
            online_elo INTEGER DEFAULT 1500,
            online_event_elo INTEGER DEFAULT 1500,
            paper_elo INTEGER DEFAULT 1500,
            paper_event_elo INTEGER DEFAULT 1500
        )
    """)
    cur.execute("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT,
            start_date TEXT,
            end_date TEXT,
            is_active INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE paper_standings (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT,
            paper_elo INTEGER DEFAULT 1500,
            paper_event_elo INTEGER DEFAULT 1500
        )
    """)
    cur.execute("""
        CREATE TABLE event_standings_archive (
            user_id TEXT,
            event_id INTEGER,
            final_event_elo INTEGER DEFAULT 1500,
            final_rank INTEGER,
            user_display_name TEXT,
            PRIMARY KEY (user_id, event_id)
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def match_db(tmp_path):
    """Create a temporary match records database with test schema."""
    db_path = tmp_path / "match_records.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE match_records (
            winner_id TEXT,
            winner_display_name TEXT,
            winner_elo_change REAL,
            losser_id TEXT,
            losser_display_name TEXT,
            loser_elo_change REAL,
            match_time INTEGER,
            timestamp TEXT,
            old_json_deck TEXT,
            winner_json TEXT,
            loser_json TEXT,
            source TEXT DEFAULT 'Discord',
            match_type TEXT DEFAULT 'ranked'
        )
    """)
    cur.execute("""
        CREATE TABLE user_profiles (
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'discord',
            display_name TEXT NOT NULL,
            custom_display_name TEXT,
            avatar TEXT,
            email TEXT,
            email_verified INTEGER,
            first_login_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL,
            discriminator TEXT,
            flags INTEGER,
            public_flags INTEGER,
            given_name TEXT,
            family_name TEXT,
            locale TEXT,
            raw_oauth_data TEXT,
            PRIMARY KEY (user_id, provider)
        )
    """)
    cur.execute("""
        CREATE TABLE match_reports_web (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submitter_user_id TEXT,
            submitter_display_name TEXT,
            opponent_user_id TEXT,
            opponent_display_name TEXT,
            winner_user_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            confirmed_at TEXT,
            deck_url TEXT,
            opponent_deck_url TEXT,
            season_id TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE solo_match_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            opponent_name TEXT,
            result TEXT,
            deck_url TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT,
            admin_name TEXT,
            action TEXT,
            target_id TEXT,
            details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def app(elo_db, match_db, tmp_path):
    """Create a test Flask app with temporary databases."""
    _patch_db_paths(elo_db, match_db, tmp_path)
    webapp_config.ADMINS = ["admin_user_1"]
    webapp_config.VALID_API_KEYS = ["test-api-key-123"]
    webapp_config.CURIO_EDITORS = ["editor_1"]

    # Reset class-level flags
    MatchRepository._columns_ensured = False

    from app import create_app
    test_app = create_app()
    test_app.config["TESTING"] = True
    yield test_app


@pytest.fixture()
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture()
def admin_session(client):
    """Return a client with an active admin session."""
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
        sess["username"] = "AdminUser"
    return client


@pytest.fixture()
def user_session(client):
    """Return a client with an active non-admin session."""
    with client.session_transaction() as sess:
        sess["user_id"] = "regular_user_1"
        sess["username"] = "RegularUser"
    return client


def seed_elo_data(db_path, players):
    """Helper to insert player standings into the ELO database."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    for p in players:
        cur.execute("""
            INSERT OR REPLACE INTO overall_standings
            (user_id, user_display_name, online_elo, online_event_elo, paper_elo, paper_event_elo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            p["user_id"], p["name"],
            p.get("online_elo", 1500), p.get("online_event_elo", 1500),
            p.get("paper_elo", 1500), p.get("paper_event_elo", 1500),
        ))
    conn.commit()
    conn.close()


def seed_matches(db_path, matches):
    """Helper to insert match records."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    for m in matches:
        cur.execute("""
            INSERT INTO match_records
            (winner_id, winner_display_name, winner_elo_change,
             losser_id, losser_display_name, loser_elo_change,
             match_time, timestamp, source, match_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["winner_id"], m.get("winner_name", "Winner"),
            m.get("winner_elo_change", 16),
            m["loser_id"], m.get("loser_name", "Loser"),
            m.get("loser_elo_change", -16),
            m.get("match_time"), m.get("timestamp", "2025-01-15 12:00:00"),
            m.get("source", "Discord"), m.get("match_type", "ranked"),
        ))
    conn.commit()
    conn.close()
