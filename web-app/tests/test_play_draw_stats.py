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


# --- ELO bracket matrix: event filter + on the play / on the draw ---

def _deck(avatar):
    import json
    return json.dumps({"avatar": [{"name": avatar}]})


@pytest.fixture()
def matrix(monkeypatch, elo_db, match_db, client):
    import routes.api.avatars as avatars
    monkeypatch.setattr(avatars, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)

    conn = sqlite3.connect(str(elo_db))
    conn.execute("ALTER TABLE overall_standings ADD COLUMN elo INTEGER")
    conn.execute("INSERT INTO overall_standings (user_id, elo) VALUES ('hi', 1650), ('lo', 1450)")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE match_records_archive (
            event_id INTEGER, timestamp TEXT, first_player TEXT,
            winner_went_first TEXT, loser_went_first TEXT,
            winner_id TEXT, winner_display_name TEXT, losser_id TEXT, losser_display_name TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT
        )
    """)
    # Current season: 'hi' beats 'lo' 6 times on the play
    for _ in range(6):
        conn.execute(
            "INSERT INTO match_records (winner_id, losser_id, json_deck_data_winner, json_deck_data_loser,"
            " timestamp, winner_went_first) VALUES ('hi', 'lo', ?, ?, '2026-09-01', 'y')",
            (_deck("Sparkmage"), _deck("Geomancer")),
        )
    # Past event 7: 'lo' beats 'hi' 5 times on the draw
    for _ in range(5):
        conn.execute(
            "INSERT INTO match_records_archive (event_id, winner_id, losser_id, json_deck_data_winner,"
            " json_deck_data_loser, timestamp, winner_went_first) VALUES (7, 'lo', 'hi', ?, ?, '2026-05-01', 'n')",
            (_deck("Geomancer"), _deck("Sparkmage")),
        )
    conn.commit()
    conn.close()
    return client


def _row(data, bracket):
    return next(r for r in data["rows"] if r["bracket"] == bracket)


def test_matrix_all_events_has_play_draw(matrix):
    data = matrix.get("/api/avatars/elo-bracket-matrix?source=discord").get_json()
    hi = _row(data, 1600)
    assert hi["overall"]["total"] == 11
    # 'hi' was on the play in all 11: won 6 live, lost 5 archived to 'lo' on the draw
    assert hi["on_play"] == {"wins": 6, "losses": 5, "total": 11, "win_rate": 54.5}
    assert hi["on_draw"] == {"wins": 0, "losses": 0, "total": 0, "win_rate": None}
    lo = _row(data, 1400)
    assert lo["on_draw"] == {"wins": 5, "losses": 6, "total": 11, "win_rate": 45.5}


def test_matrix_past_event_only_counts_that_event(matrix):
    # Too few games for the row threshold, so no rows - but nothing from the live table leaks in
    data = matrix.get("/api/avatars/elo-bracket-matrix?source=discord&event=7").get_json()
    assert data["event"] == "7"
    assert all(r["overall"]["total"] <= 5 for r in data["rows"])


def test_matrix_current_event_for_admin(matrix, admin_session):
    data = matrix.get("/api/avatars/elo-bracket-matrix?source=discord&event=current").get_json()
    assert data["event"] == "current"
    assert data["rows"] == []  # 6 games is under the 10-game row threshold


def test_matrix_current_event_falls_back_for_non_admin(matrix):
    data = matrix.get("/api/avatars/elo-bracket-matrix?source=discord&event=current").get_json()
    assert data["event"] == "all"
    assert _row(data, 1600)["overall"]["total"] == 11
