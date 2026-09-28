"""
Regression tests for ending an event (!end_event) on databases whose archive
tables predate newer columns.

end_current_event() used to rely on start_new_event() having run the archive
table migrations. Calling !end_event directly on a long-lived database then
failed with "table match_records_archive has no column named voice".
"""

import datetime
import sqlite3

import pytest

from services.elo_service import end_current_event, start_new_event
from repositories.elo_repo import get_active_event


LEGACY_ARCHIVE_SCHEMA = """CREATE TABLE match_records_archive (
    archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    original_match_id INTEGER,
    reporter_id INTEGER,
    winner_id INTEGER,
    winner_display_name TEXT,
    losser_id INTEGER,
    losser_display_name TEXT,
    did_win BOOLEAN,
    timestamp TEXT,
    first_player TEXT,
    match_time INTEGER,
    curiosa_url TEXT,
    curiosa_url_winner TEXT,
    curiosa_url_loser TEXT,
    match_comment TEXT,
    json_deck_data TEXT,
    json_deck_data_winner TEXT,
    json_deck_data_loser TEXT,
    winner_elo_change INTEGER,
    loser_elo_change INTEGER,
    winner_lifetime_elo_change INTEGER,
    loser_lifetime_elo_change INTEGER,
    archived_at TEXT
)"""


def _insert_match(timestamp: str, voice: int = 0):
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO match_records
           (reporter_id, winner_id, winner_display_name, losser_id, losser_display_name,
            did_win, timestamp, first_player, match_time, curiosa_url, match_comment,
            json_deck_data, winner_elo_change, loser_elo_change, match_type, voice)
           VALUES (101, 101, 'Winner', 202, 'Loser', 1, ?, 'n', 0, NULL, '', '{}',
                   16, -16, 'ranked', ?)""",
        (timestamp, voice),
    )
    conn.commit()
    conn.close()


def _archive_rows():
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM match_records_archive").fetchall()
    conn.close()
    return rows


def test_end_event_migrates_legacy_archive_table():
    """!end_event must work when match_records_archive lacks newer columns."""
    start_new_event("Season 1")

    # Downgrade the archive table to the shape it had before match_type/voice
    conn = sqlite3.connect("match_records.db")
    conn.execute("DROP TABLE match_records_archive")
    conn.execute(LEGACY_ARCHIVE_SCHEMA)
    conn.commit()
    conn.close()

    played_at = (datetime.datetime.now() + datetime.timedelta(minutes=1)).isoformat()
    _insert_match(played_at, voice=1)

    summary = end_current_event()

    assert summary is not None
    assert summary["event_name"] == "Season 1"
    assert summary["total_matches"] == 1
    assert get_active_event() is None

    rows = _archive_rows()
    assert len(rows) == 1
    assert rows[0]["voice"] == 1
    assert rows[0]["match_type"] == "ranked"


def test_end_event_creates_missing_archive_table():
    """!end_event must work even if the archive table was never created."""
    conn = sqlite3.connect("elo.db")
    conn.execute(
        "INSERT INTO events (event_name, start_date, is_active) VALUES (?, ?, 1)",
        ("Season 2", datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect("match_records.db")
    conn.execute("DROP TABLE IF EXISTS match_records_archive")
    conn.commit()
    conn.close()

    played_at = (datetime.datetime.now() + datetime.timedelta(minutes=1)).isoformat()
    _insert_match(played_at)

    summary = end_current_event()

    assert summary is not None
    assert summary["total_matches"] == 1
    assert len(_archive_rows()) == 1
    assert get_active_event() is None
