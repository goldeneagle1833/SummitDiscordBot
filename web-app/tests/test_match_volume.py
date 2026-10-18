"""Games by type in the last 24h / 7 days vs the window before."""
import sqlite3
from datetime import datetime

from services.match_volume import match_volume

NOW = datetime(2026, 10, 18, 12, 0, 0)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE match_records (timestamp TEXT, match_type TEXT, source TEXT)")
    conn.execute("CREATE TABLE limited_match_records (timestamp TEXT)")
    conn.execute("CREATE TABLE rumble_match_records (timestamp TEXT)")
    conn.execute("CREATE TABLE match_reports_web (timestamp TEXT)")
    return conn


def _run(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return match_volume(conn.cursor(), tables, now=NOW)["windows"]


def test_types_and_windows():
    conn = _db()
    conn.executemany("INSERT INTO match_records VALUES (?, ?, ?)", [
        ("2026-10-18T11:00:00.123456", "ranked", "Discord"),   # last 24h, ISO format
        ("2026-10-18 01:00:00", None, None),                   # last 24h, ranked by default
        ("2026-10-17T06:00:00", "testing", "Discord"),         # previous 24h, casual
        ("2026-10-17 10:00:00", "points", "Discord"),          # previous 24h, omens
        ("2026-10-16 10:00:00", "ranked", "Bracket"),          # earlier this week, postseason
        ("2026-10-09 10:00:00", "ranked", "Discord"),          # previous 7 days
        ("2026-10-01 10:00:00", "ranked", "Discord"),          # too old
    ])
    conn.execute("INSERT INTO limited_match_records VALUES ('2026-10-18T09:00:00')")
    conn.execute("INSERT INTO rumble_match_records VALUES ('2026-10-10T09:00:00')")
    conn.execute("INSERT INTO match_reports_web VALUES ('2026-10-17 13:00:00')")

    w = _run(conn)
    assert w["day"]["current"] == {
        "ranked": 2, "casual": 0, "limited": 1, "rumble": 0, "omens": 0, "postseason": 0, "paper": 1,
    }
    assert w["day"]["previous"]["casual"] == 1
    assert w["day"]["previous"]["omens"] == 1
    assert sum(w["day"]["previous"].values()) == 2

    assert w["week"]["current"]["ranked"] == 2
    assert w["week"]["current"]["postseason"] == 1
    assert sum(w["week"]["current"].values()) == 7
    assert w["week"]["previous"]["ranked"] == 1
    assert w["week"]["previous"]["rumble"] == 1
    assert sum(w["week"]["previous"].values()) == 2


def test_missing_tables_give_zeros():
    conn = sqlite3.connect(":memory:")
    w = _run(conn)
    assert sum(w["day"]["current"].values()) == 0
    assert w["week"]["start"] == "2026-10-11 12:00:00"
