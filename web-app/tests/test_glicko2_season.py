"""Glicko-2 seasons (Season 9 on) on the site: schema, admin fixes, top cut minimum."""

import filecmp
import sqlite3
from pathlib import Path

from services import glicko2_season as g2
from tests.conftest import seed_elo_data

EVENT_ID = 9


def _start_glicko_event(elo_db, mode="player"):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active, elo_mode, rating_system) "
        "VALUES (?, 'Season 9', '2027-01-01T00:00:00', 1, ?, 'glicko2')",
        (EVENT_ID, mode),
    )
    conn.commit()
    conn.close()


def _seed_match(match_db, winner, loser, ts):
    conn = sqlite3.connect(str(match_db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(match_records)")}
    for col in ("winner_lifetime_elo_change", "loser_lifetime_elo_change"):
        if col not in cols:
            conn.execute(f"ALTER TABLE match_records ADD COLUMN {col} INTEGER")
    cur = conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change, losser_id, losser_display_name,
            loser_elo_change, timestamp, source, match_type,
            winner_lifetime_elo_change, loser_lifetime_elo_change, event_id, rating_system)
           VALUES (?, ?, 0, ?, ?, 0, ?, 'Discord', 'ranked', 16, -16, ?, 'glicko2')""",
        (winner, f"P{winner}", loser, f"P{loser}", ts, EVENT_ID),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


def _rebuild(elo_db, match_db):
    elo_conn, match_conn = sqlite3.connect(str(elo_db)), sqlite3.connect(str(match_db))
    try:
        g2.rebuild_season(elo_conn, match_conn, g2.get_event(elo_conn))
        elo_conn.commit()
        match_conn.commit()
    finally:
        elo_conn.close()
        match_conn.close()


def _event_elos(elo_db):
    conn = sqlite3.connect(str(elo_db))
    try:
        return dict(conn.execute("SELECT user_id, online_event_elo FROM overall_standings"))
    finally:
        conn.close()


def test_web_copy_matches_the_bot_module():
    web = Path(__file__).resolve().parents[1] / "services" / "glicko2_season.py"
    bot = Path(__file__).resolve().parents[2] / "discord-bot" / "services" / "glicko2_season.py"
    assert filecmp.cmp(bot, web, shallow=False), "keep both glicko2_season.py copies identical"


def test_startup_migration_adds_the_glicko2_schema(app, elo_db, match_db):
    conn = sqlite3.connect(str(elo_db))
    events = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    standings = {row[1] for row in conn.execute("PRAGMA table_info(overall_standings)")}
    conn.close()
    assert "rating_system" in events and "online_event_rating" in standings
    conn = sqlite3.connect(str(match_db))
    matches = {row[1] for row in conn.execute("PRAGMA table_info(match_records)")}
    conn.close()
    assert {"event_id", "rating_system"} <= matches


def test_remove_match_rebuilds_the_glicko2_season(admin_session, elo_db, match_db):
    _start_glicko_event(elo_db)
    seed_elo_data(elo_db, [{"user_id": u, "name": f"P{u}"} for u in ("1", "2", "3")])
    _seed_match(match_db, "1", "2", "2027-01-02T10:00:00")
    bad = _seed_match(match_db, "2", "3", "2027-01-02T11:00:00")
    _seed_match(match_db, "3", "1", "2027-01-02T12:00:00")
    _rebuild(elo_db, match_db)

    resp = admin_session.delete(f"/api/admin/remove-match/{bad}")
    assert resp.status_code == 200, resp.get_json()

    # Same as a season that only ever had the two remaining games
    p1, p2 = g2.play(g2.Rating(), g2.Rating(), "2027-01-02T10:00:00")
    p3, p1 = g2.play(g2.Rating(), p1, "2027-01-02T12:00:00")
    assert _event_elos(elo_db) == {"1": p1.display, "2": p2.display, "3": p3.display}


def test_leaderboard_marks_entries_short_of_the_top_cut_minimum(client, elo_db, match_db):
    _start_glicko_event(elo_db)
    seed_elo_data(elo_db, [{"user_id": u, "name": f"P{u}"} for u in ("1", "2", "3", "4")])
    for i in range(8):
        _seed_match(match_db, "1", "2", f"2027-01-02T10:{i:02d}:00")
    _seed_match(match_db, "3", "4", "2027-01-03T10:00:00")
    _rebuild(elo_db, match_db)

    data = client.get("/api/leaderboard/event").get_json()

    assert data["top_cut_min_games"] == g2.TOP_CUT_MIN_GAMES
    flags = {row["id"]: row["top_cut_eligible"] for row in data["leaderboard"]}
    assert flags == {"1": True, "2": True, "3": False, "4": False}


def test_elo_seasons_have_no_minimum(client, elo_db):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, is_active) VALUES (8, 'S8', '2026-10-01', 1)"
    )
    conn.commit()
    conn.close()
    assert client.get("/api/leaderboard/event").get_json()["top_cut_min_games"] == 0
