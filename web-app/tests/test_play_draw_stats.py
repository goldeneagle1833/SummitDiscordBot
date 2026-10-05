"""Tests for GET /api/avatars/play-draw-stats and its event filter."""

import sqlite3

import pytest


@pytest.fixture()
def patched(monkeypatch, elo_db, match_db, client):
    import routes.api.avatars as avatars
    monkeypatch.setattr(avatars, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)

    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE match_records_archive (
            event_id INTEGER,
            timestamp TEXT,
            first_player TEXT,
            winner_went_first TEXT,
            loser_went_first TEXT
        )
    """)
    # Current season: winner on the play twice
    for _ in range(2):
        conn.execute(
            "INSERT INTO match_records (timestamp, winner_went_first, loser_went_first) "
            "VALUES ('2026-09-01 12:00:00', 'y', 'n')"
        )
    # Past event 7: winner on the draw three times
    for _ in range(3):
        conn.execute(
            "INSERT INTO match_records_archive (event_id, timestamp, winner_went_first, loser_went_first) "
            "VALUES (7, '2026-05-01 12:00:00', 'n', 'y')"
        )
    # Before the tracking cutoff: never counted
    conn.execute(
        "INSERT INTO match_records_archive (event_id, timestamp, winner_went_first, loser_went_first) "
        "VALUES (7, '2026-01-01 12:00:00', 'y', 'n')"
    )
    conn.commit()
    conn.close()
    return client


def test_all_events_counts_both_tables(patched):
    data = patched.get("/api/avatars/play-draw-stats").get_json()
    assert data["play_stats"] == {"wins": 2, "losses": 3, "total": 5, "win_rate": 40.0}
    assert data["draw_stats"]["wins"] == 3


def test_past_event_only_counts_that_event(patched):
    data = patched.get("/api/avatars/play-draw-stats?event=7").get_json()
    assert data["event"] == "7"
    assert data["play_stats"] == {"wins": 0, "losses": 3, "total": 3, "win_rate": 0.0}
    assert data["draw_stats"] == {"wins": 3, "losses": 0, "total": 3, "win_rate": 100.0}


def test_current_event_for_admin_reads_live_table(patched, admin_session):
    data = patched.get("/api/avatars/play-draw-stats?event=current").get_json()
    assert data["play_stats"]["wins"] == 2
    assert data["play_stats"]["total"] == 2


def test_current_event_falls_back_to_all_for_non_admin(patched):
    data = patched.get("/api/avatars/play-draw-stats?event=current").get_json()
    assert data["event"] == "all"
    assert data["play_stats"]["total"] == 5


def test_invalid_event_is_rejected(patched):
    assert patched.get("/api/avatars/play-draw-stats?event=bogus").status_code == 400
