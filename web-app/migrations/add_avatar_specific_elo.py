"""Idempotent schema migration for opt-in avatar-specific event ELO."""

import sqlite3

from webapp_config import ELO_DB_PATH, MATCH_RECORDS_DB_PATH


def _add_column(conn, table, definition):
    column = definition.split()[0]
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def migrate():
    elo_conn = sqlite3.connect(str(ELO_DB_PATH))
    elo_conn.execute("""CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        is_active BOOLEAN DEFAULT 1,
        avatar_specific BOOLEAN NOT NULL DEFAULT 0
    )""")
    _add_column(elo_conn, "events", "avatar_specific BOOLEAN NOT NULL DEFAULT 0")
    elo_conn.execute("""CREATE TABLE IF NOT EXISTS event_avatar_standings (
        event_id INTEGER NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('online', 'paper')),
        user_id TEXT NOT NULL,
        user_display_name TEXT NOT NULL,
        avatar_name TEXT NOT NULL COLLATE NOCASE,
        event_elo INTEGER NOT NULL DEFAULT 1500,
        PRIMARY KEY (event_id, source, user_id, avatar_name)
    )""")
    elo_conn.execute("""CREATE INDEX IF NOT EXISTS idx_event_avatar_standings_rank
        ON event_avatar_standings(event_id, source, event_elo DESC)""")
    elo_conn.commit()
    elo_conn.close()

    match_conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    for table in ("match_records", "match_records_archive", "match_reports_web"):
        exists = match_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        if exists:
            _add_column(match_conn, table, "winner_avatar TEXT")
            _add_column(match_conn, table, "loser_avatar TEXT")
    exists = match_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = 'match_confirmations'"
    ).fetchone()
    if exists:
        _add_column(match_conn, "match_confirmations", "winner_avatar TEXT")
        _add_column(match_conn, "match_confirmations", "loser_avatar TEXT")
    match_conn.commit()
    match_conn.close()
