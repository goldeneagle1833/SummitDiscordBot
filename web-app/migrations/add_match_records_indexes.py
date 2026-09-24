"""Index the bot's match tables on the columns the web app filters by.

match_records, match_records_archive and solo_match_reports were created
without any indexes, so every leaderboard, player page and archive lookup
scans the whole table (and the deck JSON stored on every row). These are
plain CREATE INDEX IF NOT EXISTS statements: safe to re-run, no table
rebuild, and the bot keeps writing while they build.
"""
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from webapp_config import MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

_INDEXES = {
    "match_records": {
        "idx_match_records_winner": "winner_id",
        "idx_match_records_loser": "losser_id",
        "idx_match_records_timestamp": "timestamp",
        "idx_match_records_pairing": "pairing_id",
    },
    "match_records_archive": {
        "idx_match_records_archive_event": "event_id",
        "idx_match_records_archive_winner": "winner_id",
        "idx_match_records_archive_loser": "losser_id",
        "idx_match_records_archive_timestamp": "timestamp",
    },
    "solo_match_reports": {
        "idx_solo_match_reports_reporter": "reporter_id",
    },
    "active_pairings": {
        "idx_active_pairings_status": "status",
        "idx_active_pairings_players": "player1_id, player2_id",
    },
}


def migrate(db_path=None):
    conn = sqlite3.connect(str(db_path or MATCH_RECORDS_DB_PATH), timeout=30)
    try:
        cur = conn.cursor()
        for table, indexes in _INDEXES.items():
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not cur.fetchone():
                continue
            existing = {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
            for name, cols in indexes.items():
                needed = {c.strip() for c in cols.split(",")}
                if not needed <= existing:
                    continue  # older schema without this column
                cur.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate()
    print("match_records indexes ensured")
