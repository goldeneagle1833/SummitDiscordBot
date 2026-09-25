"""Tests for GET /api/avatars/season-top-players (home-page avatar badges)."""

import json
import sqlite3

import pytest


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}]})


def _add_match(db, winner, loser, w_avatar, l_avatar, source="Discord"):
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, losser_id, losser_display_name,
            json_deck_data_winner, json_deck_data_loser, timestamp, source)
           VALUES (?, ?, ?, ?, ?, ?, '2026-09-01 12:00:00', ?)""",
        (winner[0], winner[1], loser[0], loser[1], _deck(w_avatar), _deck(l_avatar), source),
    )
    conn.commit()
    conn.close()


def _set_active_event(elo_db, active=True):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_name, start_date, is_active) VALUES ('Season X', '2026-08-01', ?)",
        (1 if active else 0,),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def patched(monkeypatch, elo_db, match_db, client):
    import routes.api.avatars as avatars
    monkeypatch.setattr(avatars, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)
    return client


ALICE = ("111", "Alice")
BOB = ("222", "Bob")
CARL = ("333", "Carl")


def test_no_active_season_returns_empty(patched, elo_db, match_db):
    _set_active_event(elo_db, active=False)
    _add_match(match_db, ALICE, BOB, "Avatar of Earth", "Avatar of Air")
    resp = patched.get("/api/avatars/season-top-players")
    assert resp.status_code == 200
    assert resp.get_json() == {"badges": []}


def test_picks_top_player_per_avatar(patched, elo_db, match_db):
    _set_active_event(elo_db)
    # Alice: 12-0 on Earth (qualifies). Carl: 3-0 on Earth (under 10 games).
    for _ in range(12):
        _add_match(match_db, ALICE, BOB, "Avatar of Earth", "Avatar of Air")
    for _ in range(3):
        _add_match(match_db, CARL, BOB, "Avatar of Earth", "Dragonlord")

    resp = patched.get("/api/avatars/season-top-players")
    badges = {b["avatar"]: b for b in resp.get_json()["badges"]}

    assert badges["Avatar of Earth"]["player_id"] == "111"
    assert badges["Avatar of Earth"]["player_name"] == "Alice"
    assert badges["Avatar of Earth"]["wins"] == 12
    # Bob has 12 Air games (qualifies) but only 3 Dragonlord games (no badge).
    assert badges["Avatar of Air"]["player_id"] == "222"
    assert "Dragonlord" not in badges
    # Carl's 3-0 Earth run doesn't beat or replace Alice.
    assert all(b["player_id"] != "333" for b in badges.values())


def test_is_public_and_ignores_external_sources(patched, elo_db, match_db):
    _set_active_event(elo_db)
    _add_match(match_db, ALICE, BOB, "Avatar of Earth", "Avatar of Air", source="SomeOtherSite")
    resp = patched.get("/api/avatars/season-top-players")
    assert resp.status_code == 200
    assert resp.get_json()["badges"] == []
