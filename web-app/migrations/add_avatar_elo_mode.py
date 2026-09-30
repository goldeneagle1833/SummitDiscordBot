"""Player/Avatar event ELO mode.

Each event runs in Player mode (one event ELO per player) or Avatar mode (one
event ELO per player and avatar). The bot owns these tables and creates the
same schema in discord-bot/repositories/avatar_elo_repo.py and elo_repo.py;
this makes sure the site can read them even before the bot has restarted.

- elo.db: events.elo_mode (locked by a trigger once set) and
  event_avatar_standings, one row per (event, player, avatar).
- match_records.db: each side's avatar and per-avatar ELO change/after on
  match_records and its archive, and the avatars locked to a pairing.
"""
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp_config

logger = logging.getLogger(__name__)

AVATAR_MATCH_COLUMNS = (
    "winner_avatar TEXT",
    "loser_avatar TEXT",
    "winner_avatar_elo_change INTEGER",
    "loser_avatar_elo_change INTEGER",
    "winner_avatar_elo_after INTEGER",
    "loser_avatar_elo_after INTEGER",
)


def _table_exists(cur, table):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def _add_columns(cur, table, columns):
    if not _table_exists(cur, table):
        return
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    for column in columns:
        if column.split()[0] not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
            logger.info("Added %s to %s", column.split()[0], table)


def migrate(elo_db_path=None, match_db_path=None):
    # Paths are read at call time so tests (and scripts) can point elsewhere
    conn = sqlite3.connect(str(elo_db_path or webapp_config.ELO_DB_PATH))
    try:
        cur = conn.cursor()
        if _table_exists(cur, "events"):
            _add_columns(
                cur, "events",
                ["elo_mode TEXT NOT NULL DEFAULT 'player' CHECK (elo_mode IN ('player', 'avatar'))"],
            )
            cur.execute(
                """CREATE TRIGGER IF NOT EXISTS events_elo_mode_locked
                   BEFORE UPDATE OF elo_mode ON events
                   WHEN OLD.elo_mode IS NOT NEW.elo_mode
                   BEGIN
                       SELECT RAISE(ABORT, 'elo_mode cannot change after an event starts');
                   END"""
            )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS event_avatar_standings (
                   event_id          INTEGER NOT NULL,
                   user_id           INTEGER NOT NULL,
                   avatar            TEXT    NOT NULL,
                   user_display_name TEXT,
                   event_elo         INTEGER NOT NULL DEFAULT 1500,
                   games_played      INTEGER NOT NULL DEFAULT 0,
                   last_played_at    TEXT,
                   PRIMARY KEY (event_id, user_id, avatar)
               )"""
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_avatar_standings_ladder "
            "ON event_avatar_standings (event_id, event_elo DESC)"
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(str(match_db_path or webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        cur = conn.cursor()
        for table in ("match_records", "match_records_archive"):
            _add_columns(cur, table, AVATAR_MATCH_COLUMNS)
        _add_columns(cur, "active_pairings", ["player1_avatar TEXT", "player2_avatar TEXT"])
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
