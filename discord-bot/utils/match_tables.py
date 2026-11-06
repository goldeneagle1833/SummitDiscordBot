"""Which table holds the current matches.

Seasons 1-8 used ``match_records`` (archived to ``match_records_archive`` at
each season's end). The first Glicko-2 season creates ``season_match_records``
and from then on every match is written to and read from there, tagged with
its event, and never archived. ``live_matches()`` names whichever applies, so
queries read ``FROM {live_matches()}`` and work before and after the switch.
"""

import sqlite3

from services.glicko2_season import LEGACY_MATCH_TABLE, SEASON_MATCH_TABLE, live_match_table

MATCH_DB = "match_records.db"

__all__ = ["LEGACY_MATCH_TABLE", "SEASON_MATCH_TABLE", "live_matches"]


def live_matches() -> str:
    """The current match table's name (a cheap catalog lookup, never cached)."""
    conn = sqlite3.connect(MATCH_DB)
    try:
        return live_match_table(conn)
    finally:
        conn.close()
