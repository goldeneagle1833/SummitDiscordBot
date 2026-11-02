"""Matches tab filters on the player profile (opponent, result, avatars, play/draw)."""

import json
import sqlite3

import pytest

import routes.api.players as players_routes


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar, "type": "Avatar"}]})


@pytest.fixture
def filter_matches(match_db, elo_db, monkeypatch):
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    conn = sqlite3.connect(str(match_db))
    games = [
        # winner, winner name, loser, loser name, winner avatar, loser avatar, type
        ("100", "Hicham", "200", "Geoffrey", "Pathfinder", "Seer", "ranked"),
        ("200", "Geoffrey", "100", "Hicham", "Seer", "Pathfinder", "ranked"),
        ("200", "Geoffrey", "100", "Hicham", "Witch", "Pathfinder", "ranked"),
        ("100", "Hicham", "300", "Bob", "Druid", "Witch", "ranked"),
        ("200", "Geoffrey", "100", "Hicham", "Seer", "Druid", "casual"),
    ]
    for i, (w, wn, l, ln, wa, la, mtype) in enumerate(games):
        conn.execute(
            """INSERT INTO match_records
               (winner_id, winner_display_name, winner_elo_change,
                losser_id, losser_display_name, loser_elo_change,
                timestamp, match_type, json_deck_data_winner, json_deck_data_loser)
               VALUES (?, ?, 10, ?, ?, -10, ?, ?, ?, ?)""",
            (w, wn, l, ln, f"2026-10-0{i + 1} 12:00:00", mtype, _deck(wa), _deck(la)),
        )
    conn.commit()
    conn.close()


def test_options_and_no_filter(client, filter_matches):
    data = client.get("/api/player/100").get_json()
    mf = data["match_filters"]
    assert mf["options"]["opponents"] == [
        {"id": "200", "name": "Geoffrey", "games": 4},
        {"id": "300", "name": "Bob", "games": 1},
    ]
    assert mf["options"]["avatars"] == ["Druid", "Pathfinder"]
    assert mf["options"]["opponent_avatars"] == ["Seer", "Witch"]
    assert mf["active"] == {}
    assert mf["ranked"] == {"wins": 2, "losses": 2}
    assert len(data["matches"]) == 4


def test_record_against_one_opponent(client, filter_matches):
    data = client.get("/api/player/100?opponent=200").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 1, "losses": 2}
    assert data["match_filters"]["casual"] == {"wins": 0, "losses": 1}
    assert {m["opponent"] for m in data["matches"]} == {"Geoffrey"}
    assert data["pagination"]["total_matches"] == 3
    # Choices stay the full list
    assert len(data["match_filters"]["options"]["opponents"]) == 2


def test_filters_combine(client, filter_matches):
    data = client.get("/api/player/100?opponent=200&result=loss&opponent_avatar=seer").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 0, "losses": 1}
    assert [m["opponent_avatar"] for m in data["matches"]] == ["Seer"]

    data = client.get("/api/player/100?avatar=Druid").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 1, "losses": 0}
    assert data["match_filters"]["casual"] == {"wins": 0, "losses": 1}


def test_play_draw(client, filter_matches, match_db):
    conn = sqlite3.connect(str(match_db))
    # Hicham went first in his first win and second loss; his first loss uses
    # the old first_player column (winner went first, so Hicham was on the draw)
    conn.execute("UPDATE match_records SET winner_went_first = 'y', loser_went_first = 'n' WHERE timestamp LIKE '2026-10-01%'")
    conn.execute("UPDATE match_records SET first_player = 'y' WHERE timestamp LIKE '2026-10-02%'")
    conn.execute("UPDATE match_records SET winner_went_first = 'n', loser_went_first = 'y' WHERE timestamp LIKE '2026-10-03%'")
    conn.commit()
    conn.close()

    data = client.get("/api/player/100?play_draw=play").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 1, "losses": 1}
    assert {m["first_player"] for m in data["matches"]} == {"Play"}

    data = client.get("/api/player/100?play_draw=draw").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 0, "losses": 1}
    assert [m["first_player"] for m in data["matches"]] == ["Draw"]

    # Games with nothing recorded only show with no play/draw filter
    data = client.get("/api/player/100").get_json()
    assert sum(m["first_player"] is None for m in data["matches"]) == 1
