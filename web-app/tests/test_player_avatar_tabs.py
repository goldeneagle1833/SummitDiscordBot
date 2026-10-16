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


def _profile(match_db, user_id="100"):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES (?, 'discord', 'A', 'now', 'now')",
        (user_id,),
    )
    conn.commit()
    conn.close()


def _open_avatar_sections(match_db):
    from repositories.user_profiles import UserProfileRepository
    UserProfileRepository(match_db).set_profile_visibility(
        "100", {"avatar_performance": True, "avatar_matchups": True}
    )


def test_owner_hides_an_avatar_without_deleting_it(client, avatar_games, match_db):
    _profile(match_db)
    _open_avatar_sections(match_db)
    with client.session_transaction() as sess:
        sess["user_id"] = "100"
    resp = client.put("/api/player/100/hidden-avatars", json={"avatars": ["Druid"]})
    assert resp.status_code == 200 and resp.get_json()["avatars"] == ["Druid"]

    # The owner still gets it, flagged, so they can show it again
    owner = client.get("/api/player/100").get_json()
    perf = {a["name"]: a for a in owner["avatar_performance"]}
    assert perf["Druid"]["hidden"] is True and perf["Witch"]["hidden"] is False

    # Visitors don't see it at all, and the games still count
    with client.session_transaction() as sess:
        sess["user_id"] = "200"
    visitor = client.get("/api/player/100").get_json()
    assert [a["name"] for a in visitor["avatar_performance"]] == ["Witch"]
    assert "Druid" not in visitor["avatar_matchups_by_avatar"]
    assert visitor["wins"] + visitor["losses"] == 3


def test_only_the_owner_can_hide_avatars(client, avatar_games, match_db):
    _profile(match_db)
    assert client.put("/api/player/100/hidden-avatars", json={"avatars": ["Druid"]}).status_code == 401
    with client.session_transaction() as sess:
        sess["user_id"] = "200"
    assert client.put("/api/player/100/hidden-avatars", json={"avatars": ["Druid"]}).status_code == 403
    with client.session_transaction() as sess:
        sess["user_id"] = "100"
    assert client.put("/api/player/100/hidden-avatars", json={"avatars": "Druid"}).status_code == 400


def test_avatars_tab_counts_only_ranked_games_in_the_period(client, avatar_games, match_db, elo_db, monkeypatch):
    """A casual game, or an external game from an earlier season, must not add avatars."""
    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO events (event_name, start_date, is_active) VALUES ('Now', '2026-10-01 00:00:00', 1)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change, losser_id, losser_display_name,
            loser_elo_change, timestamp, match_type, reporter_id, json_deck_data_winner, json_deck_data_loser)
           VALUES ('100', 'A', 0, '200', 'B', 0, '2026-10-04 12:00:00', 'casual', '100', ?, ?)""",
        (_deck("Necromancer"), _deck("Seer")),
    )
    conn.commit()
    conn.close()
    old_external = {
        "id": 1, "winner_id": "100", "loser_id": "300", "timestamp": "2026-03-25 12:00:00",
        "winner_display_name": "A", "loser_display_name": "C", "match_time": 0, "source": "Paper",
        "winner_deck_url": None, "loser_deck_url": None, "winner_went_first": None, "match_comment": None,
        "json_deck_data_winner": _deck("Savior"), "json_deck_data_loser": _deck("Seer"),
    }
    new_external = {**old_external, "id": 2, "timestamp": "2026-10-05 12:00:00", "json_deck_data_winner": _deck("Witch")}
    monkeypatch.setattr(
        players_routes.ExternalMatchRepository, "get_player_matches",
        lambda self, pid, limit=100: [new_external, old_external],
    )
    with client.session_transaction() as sess:
        sess["user_id"] = "100"

    current = client.get("/api/player/100?event=current").get_json()
    perf = {a["name"]: a for a in current["avatar_performance"]}
    assert "Necromancer" not in perf and "Savior" not in perf
    assert perf["Witch"]["wins"] == 2  # the ranked win plus the external one this season

    lifetime = client.get("/api/player/100").get_json()
    names = {a["name"] for a in lifetime["avatar_performance"]}
    assert "Savior" in names and "Necromancer" not in names
