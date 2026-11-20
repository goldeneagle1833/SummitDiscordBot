"""Which table holds the current matches (the site's side).

Seasons 1-8 used ``match_records`` (archived to ``match_records_archive`` at
each season's end). The first Glicko-2 season creates ``season_match_records``
(see services/glicko2_season.py) and from then on every match is written to
and read from there, tagged with its event, and never archived.
``live_matches()`` names whichever applies, so queries read
``FROM {live_matches()}`` and work before and after the switch.

Kept free of services/ and repositories/ imports so any module can use it.
"""

import sqlite3

import webapp_config

LEGACY_MATCH_TABLE = "match_records"
SEASON_MATCH_TABLE = "season_match_records"


def live_matches(db_path=None) -> str:
    """The current match table's name (a cheap catalog lookup, never cached)."""
    conn = sqlite3.connect(str(db_path or webapp_config.MATCH_RECORDS_DB_PATH))
    try:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SEASON_MATCH_TABLE,)
        ).fetchone()
    finally:
        conn.close()
    return SEASON_MATCH_TABLE if found else LEGACY_MATCH_TABLE
