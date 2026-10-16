"""Avatars and Matchups tabs: form, last played and matchups per avatar played."""

import json
import sqlite3

import pytest

import routes.api.players as players_routes


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar, "type": "Avatar"}]})


@pytest.fixture
def avatar_games(match_db, elo_db, monkeypatch):
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    games = [
        # (winner, loser, winner avatar, loser avatar, timestamp, winner elo change, loser elo change)
        ("100", "200", "Witch", "Geomancer", "2026-10-01 12:00:00", 12, -12),
        ("200", "100", "Geomancer", "Witch", "2026-10-02 12:00:00", 10, -10),
        ("100", "200", "Druid", "Sparkmage", "2026-10-03 12:00:00", 8, -8),
    ]
    conn = sqlite3.connect(str(match_db))
    for w, l, wa, la, ts, wc, lc in games:
        conn.execute(
            """INSERT INTO match_records
               (winner_id, winner_display_name, winner_elo_change,
                losser_id, losser_display_name, loser_elo_change,
                timestamp, match_type, reporter_id,
                json_deck_data_winner, json_deck_data_loser)
               VALUES (?, 'A', ?, ?, 'B', ?, ?, 'ranked', ?, ?, ?)""",
            (w, wc, l, lc, ts, w, _deck(wa), _deck(la)),
        )
    conn.commit()
    conn.close()


def test_owner_gets_form_last_played_and_matchups_per_avatar(client, avatar_games):
    with client.session_transaction() as sess:
        sess["user_id"] = "100"
    data = client.get("/api/player/100").get_json()

    perf = {a["name"]: a for a in data["avatar_performance"]}
    assert perf["Witch"]["wins"] == 1 and perf["Witch"]["losses"] == 1
    assert perf["Witch"]["form"] == ["L", "W"]  # newest first
    assert perf["Witch"]["last_played"].startswith("2026-10-02")
    assert perf["Witch"]["elo_change"] == 2
    assert perf["Druid"]["form"] == ["W"]

    by_avatar = data["avatar_matchups_by_avatar"]
    assert [m["opponent_avatar"] for m in by_avatar["Witch"]] == ["Geomancer"]
    assert by_avatar["Witch"][0]["total_games"] == 2
    assert [m["opponent_avatar"] for m in by_avatar["Druid"]] == ["Sparkmage"]
    overall = {m["opponent_avatar"]: m for m in data["avatar_matchups"]}
    assert overall["Geomancer"]["wins"] == 1 and overall["Sparkmage"]["wins"] == 1


def test_matchups_per_avatar_stay_private(client, avatar_games):
    data = client.get("/api/player/100").get_json()
    assert data["avatar_matchups_by_avatar"] == {}
    assert data["avatar_matchups"] == []
