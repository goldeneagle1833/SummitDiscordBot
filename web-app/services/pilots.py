"""Read-only pilot (feature flag) checks for the web app.

Reads from the shared pilots table in elo.db (managed by the Discord bot
via !pilot_on / !pilot_off commands).
"""

import sqlite3
import logging

from webapp_config import ELO_DB_PATH

logger = logging.getLogger(__name__)


def is_pilot_active(name: str) -> bool:
    """Check if a pilot is active. Returns False if pilot doesn't exist."""
    try:
        conn = sqlite3.connect(str(ELO_DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT enabled FROM pilots WHERE name = ?", (name,))
        row = cur.fetchone()
        conn.close()
        return bool(row and row[0])
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return False
