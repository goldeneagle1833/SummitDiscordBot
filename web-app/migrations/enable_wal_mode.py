"""
Migration: Switch the shared bot/web databases to WAL journal mode.

In the default rollback-journal mode a writer waiting to commit locks out
every new reader, so one slow bot write behind a long web read turns into a
wave of "database is locked" errors on polled endpoints. In WAL mode readers
never block writers and writers never block readers.

journal_mode=WAL is stored in the database file, so once set it applies to
every connection from both the bot and the web app. Re-running is a no-op.

Run with: python migrations/enable_wal_mode.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import (
    ANALYTICS_DB_PATH,
    COMMUNITY_DB_PATH,
    ELO_DB_PATH,
    FART_SCORES_DB_PATH,
    MATCH_RECORDS_DB_PATH,
    MONITORING_DB_PATH,
)

logger = logging.getLogger(__name__)

# analytics.db is written on every page view by both gunicorn workers and the
# bot's content monitor; monitoring.db by the metrics flusher. Same contention
# story as the shared bot databases, so they get WAL too.
WAL_DB_PATHS = (
    MATCH_RECORDS_DB_PATH,
    ELO_DB_PATH,
    COMMUNITY_DB_PATH,
    FART_SCORES_DB_PATH,
    ANALYTICS_DB_PATH,
    MONITORING_DB_PATH,
)


def enable_wal_mode(db_paths=WAL_DB_PATHS):
    """Put each existing database into WAL mode. Returns {path: mode}."""
    modes = {}
    for db_path in db_paths:
        if not Path(db_path).exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=30)
            try:
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Could not enable WAL on {db_path}: {e}")
            continue
        modes[str(db_path)] = mode
        if mode.lower() != "wal":
            logger.warning(f"{db_path} journal_mode is {mode}, not wal")
    return modes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for path, mode in enable_wal_mode().items():
        print(f"{path}: {mode}")
