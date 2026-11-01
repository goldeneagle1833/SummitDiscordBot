"""Avatars and Popular Cards follow the Meta Report's batch release."""

import sqlite3
from datetime import date, datetime, timezone

from services import data_release as dr


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_release_follows_meta_report_clock():
    # Before 00:00 UTC on Nov 1 the October batch isn't out yet
    assert dr.released_through(_utc(2026, 10, 31, 23, 30)) == date(2026, 9, 30)
    assert dr.next_release(_utc(2026, 10, 31, 23, 30)) == date(2026, 11, 1)
    # From 00:00 UTC all of October is released
    assert dr.released_through(_utc(2026, 11, 1, 0, 0)) == date(2026, 10, 31)
    assert dr.next_release(_utc(2026, 11, 1, 0, 0)) == date(2026, 11, 15)
    # Nov 1-14 comes out on the 15th, Nov 15-30 on Dec 1
    assert dr.released_through(_utc(2026, 11, 15, 2, 0)) == date(2026, 11, 14)
    assert dr.next_release(_utc(2026, 11, 15, 2, 0)) == date(2026, 12, 1)
    assert dr.released_through(_utc(2026, 12, 20)) == date(2026, 12, 14)
    assert dr.next_release(_utc(2026, 12, 20)) == date(2027, 1, 1)


def test_release_info_shape():
    info = dr.release_info(_utc(2026, 11, 3))
    assert info == {"through": "2026-10-31", "period": "2026-10-b", "next_release": "2026-11-15"}


def test_released_connection_hides_unreleased_games(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "cutoff_timestamp", lambda now=None: "2026-11-01T00:00:00")
    path = tmp_path / "m.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE match_records (id INTEGER PRIMARY KEY, timestamp TEXT, source TEXT)")
    conn.execute("CREATE TABLE solo_match_reports (report_date TEXT)")
    conn.executemany("INSERT INTO match_records (timestamp, source) VALUES (?, 'Discord')",
                     [("2026-10-31T23:59:59.5",), ("2026-11-01T00:00:00.1",), ("2026-11-03T10:00:00",)])
    conn.executemany("INSERT INTO solo_match_reports VALUES (?)", [("2026-10-30",), ("2026-11-02",)])
    conn.commit()
    conn.close()

    rc = dr.released_connection(path)
    assert rc.release_cutoff == "2026-11-01T00:00:00"
    assert rc.execute("SELECT rowid, timestamp FROM match_records").fetchall() == [(1, "2026-10-31T23:59:59.5")]
    assert rc.execute("SELECT COUNT(*) FROM solo_match_reports").fetchone()[0] == 1
    # Missing tables (archive, external_matches) are simply skipped
    rc.close()
    # The database itself is untouched
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM match_records").fetchone()[0] == 3
