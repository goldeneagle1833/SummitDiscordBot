"""Average ELO gap reads each side's pre-match rating from the stored after/change."""
import sqlite3

from services.elo_gap import elo_gap_by_day

_COLS = (
    "timestamp TEXT, winner_avatar_elo_after INTEGER, winner_avatar_elo_change INTEGER,"
    " loser_avatar_elo_after INTEGER, loser_avatar_elo_change INTEGER,"
    " winner_lifetime_elo_after INTEGER, winner_lifetime_elo_change INTEGER,"
    " loser_lifetime_elo_after INTEGER, loser_lifetime_elo_change INTEGER"
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE match_records ({_COLS})")
    return conn


def test_avatar_ratings_win_over_lifetime():
    conn = _db()
    # Avatar: winner 1600 before, loser 1500 before -> gap 100
    conn.execute(
        "INSERT INTO match_records VALUES ('2026-10-12 20:00:00', 1616, 16, 1484, -16, 1716, 16, 1584, -16)"
    )
    assert elo_gap_by_day(conn.cursor(), ["match_records"]) == [["2026-10-12", 1, 100]]


def test_lifetime_fallback_and_skips_missing():
    conn = _db()
    # Lifetime only: 1450 vs 1530 -> gap 80 (underdog won)
    conn.execute(
        "INSERT INTO match_records VALUES ('2026-10-12 20:00:00', NULL, NULL, NULL, NULL, 1470, 20, 1510, -20)"
    )
    conn.execute(
        "INSERT INTO match_records VALUES ('2026-10-12 21:00:00', NULL, NULL, NULL, NULL, NULL, NULL, 1500, 0)"
    )
    conn.execute(
        "INSERT INTO match_records VALUES ('2026-10-13 09:00:00', NULL, NULL, NULL, NULL, 1500, 0, 1500, 0)"
    )
    assert elo_gap_by_day(conn.cursor(), ["match_records"]) == [
        ["2026-10-12", 1, 80],
        ["2026-10-13", 1, 0],
    ]


def test_table_without_rating_columns_is_ignored():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE match_records_archive (timestamp TEXT)")
    assert elo_gap_by_day(conn.cursor(), ["match_records_archive"]) == []
