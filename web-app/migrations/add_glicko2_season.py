"""Glicko-2 seasons (Season 9 on).

The bot owns these columns and creates the same schema through
discord-bot/services/glicko2_season.py; this makes sure the site can read
them even before the bot has restarted. See services/glicko2_season.py
(an identical copy) for how a Glicko-2 season is stored.

- elo.db: events.rating_system (locked once set), Glicko-2 columns on
  overall_standings and event_avatar_standings, event_rating_adjustments.
- match_records.db: match_records.event_id and rating_system.
"""
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import webapp_config
from services.glicko2_season import ensure_elo_schema, ensure_match_schema

logger = logging.getLogger(__name__)


def migrate(elo_db_path=None, match_db_path=None):
    # Paths are read at call time so tests (and scripts) can point elsewhere
    conn = sqlite3.connect(str(elo_db_path or webapp_config.ELO_DB_PATH))
    try:
        ensure_elo_schema(conn)
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(str(match_db_path or webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        ensure_match_schema(conn)
        conn.commit()
    finally:
        conn.close()
