"""GET /api/player/<id>/avatar/<name> follows the profile's period picker."""

import json
import sqlite3

import pytest

import routes.api.players as players_routes

PLAYER = "111"


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar, "type": "Avatar"}]})


@pytest.fixture()
def avatar_matches(match_db, elo_db, monkeypatch, client):
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(
        players_routes.ExternalMatchRepository, "get_player_matches",
        lambda self, pid: [
            {"winner_id": PLAYER, "loser_name": "Ext", "timestamp": "2026-10-05 10:00:00",
             "json_deck_data_winner": _deck("Pathfinder"), "json_deck_data_loser": _deck("Witch")},
        ],
    )

    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (7, 'Season 7', '2026-05-01', '2026-06-30', 0)")
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (8, 'Season 8', '2026-09-01', NULL, 1)")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(match_db))
    conn.execute("CREATE TABLE match_records_archive AS SELECT * FROM match_records WHERE 0")
    conn.execute("ALTER TABLE match_records_archive ADD COLUMN event_id INTEGER")
    cols = ("winner_id, winner_display_name, losser_id, losser_display_name, timestamp, "
            "json_deck_data_winner, json_deck_data_loser")
    # Current event: two Pathfinder wins
    for _ in range(2):
        conn.execute(
            f"INSERT INTO match_records ({cols}) VALUES (?, 'Hicham', '222', 'Bob', '2026-10-01 12:00:00', ?, ?)",
            (PLAYER, _deck("Pathfinder"), _deck("Druid")),
        )
    # Past event 7: one Pathfinder loss, one game on another avatar
    conn.execute(
        f"INSERT INTO match_records_archive ({cols}, event_id) VALUES ('222', 'Bob', ?, 'Hicham', '2026-05-10 12:00:00', ?, ?, 7)",
        (PLAYER, _deck("Druid"), _deck("Pathfinder")),
    )
    conn.execute(
        f"INSERT INTO match_records_archive ({cols}, event_id) VALUES (?, 'Hicham', '222', 'Bob', '2026-05-11 12:00:00', ?, ?, 7)",
        (PLAYER, _deck("Witch"), _deck("Druid")),
    )
    conn.commit()
    conn.close()
    return client


def _get(client, qs=""):
    return client.get(f"/api/player/{PLAYER}/avatar/Pathfinder{qs}")


def test_lifetime_counts_everything(avatar_matches):
    data = _get(avatar_matches).get_json()
    assert (data["wins"], data["losses"]) == (3, 1)  # 2 live + 1 external, 1 archived


def test_current_event_only_live_games(avatar_matches):
    data = _get(avatar_matches, "?event=current").get_json()
    assert (data["wins"], data["losses"]) == (3, 0)  # external game is dated in the event
    assert data["event_filter"] == "current"


def test_past_event_only_that_event(avatar_matches):
    data = _get(avatar_matches, "?event=7").get_json()
    assert (data["wins"], data["losses"]) == (0, 1)
    assert data["matchups"][0]["opponent_avatar"] == "Druid"


def test_empty_period_keeps_player_name(avatar_matches):
    conn = sqlite3.connect(str(players_routes.ELO_DB_PATH))
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (6, 'Season 6', '2026-03-01', '2026-04-30', 0)")
    conn.commit()
    conn.close()
    data = _get(avatar_matches, "?event=6").get_json()
    assert data["total"] == 0
    assert data["player_name"] == "Hicham"


def test_unknown_period_is_rejected(avatar_matches):
    assert _get(avatar_matches, "?event=bogus").status_code == 400
    assert _get(avatar_matches, "?event=season_nope").status_code == 400
