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


# Card played filter: the player's own cards from saved PSO callbacks
# (same layout as discord-bot/services/summit_result_reporting.py).
CALLBACK_SCHEMA = """
    CREATE TABLE IF NOT EXISTS sorcery_online_match_callbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        pairing_id INTEGER NOT NULL,
        queue_type TEXT NOT NULL,
        outcome TEXT NOT NULL,
        reporter_id INTEGER,
        winner_id INTEGER,
        loser_id INTEGER,
        match_id INTEGER,
        played_cards TEXT,
        raw_players TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Hicham"
        sess["auth_provider"] = "discord"


@pytest.fixture
def card_callbacks(filter_matches, match_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute(CALLBACK_SCHEMA)
    rows = [
        # match_id (rowid), queue, winner, loser, cards by player
        (1, "ranked", 100, 200, {"100": ["Desert", "Sling Pixies"], "200": ["Raise Dead"]}),
        (2, "ranked", 200, 100, {"200": ["Desert"], "100": ["Sling Pixies"]}),
        (4, "ranked", 100, 300, {"100": ["Desert", "Desert"], "300": ["Wildfire"]}),
        # Wrong players for match 3: must not attach to it
        (3, "ranked", 400, 500, {"400": ["Desert"], "500": ["Desert"]}),
        # Limited ids are their own sequence
        (5, "limited", 200, 100, {"100": ["Desert"]}),
    ]
    for mid, queue, w, lo, cards in rows:
        conn.execute(
            """INSERT INTO sorcery_online_match_callbacks
               (guild_id, pairing_id, queue_type, outcome, reporter_id, winner_id, loser_id,
                match_id, played_cards)
               VALUES (0, ?, ?, 'decided', ?, ?, ?, ?, ?)""",
            (mid, queue, w, w, lo, mid, json.dumps(cards)),
        )
    conn.commit()
    conn.close()


def test_card_filter_for_owner(client, card_callbacks):
    _login(client, "100")
    data = client.get("/api/player/100").get_json()
    opts = data["match_filters"]["options"]
    # Only Hicham's own cards, never the opponent's (Raise Dead, Wildfire)
    assert opts["cards"] == [{"name": "Desert", "games": 2}, {"name": "Sling Pixies", "games": 2}]
    assert opts["card_games"] == 3

    data = client.get("/api/player/100?card=desert").get_json()
    assert data["match_filters"]["active"] == {"card": "desert"}
    assert data["match_filters"]["ranked"] == {"wins": 2, "losses": 0}
    assert data["pagination"]["total_matches"] == 2

    data = client.get("/api/player/100?card=Sling Pixies&result=loss").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 0, "losses": 1}


def test_card_filter_hidden_when_card_stats_private(client, card_callbacks):
    data = client.get("/api/player/100").get_json()
    assert "cards" not in data["match_filters"]["options"]
    # The parameter is ignored, so nothing leaks through the record
    data = client.get("/api/player/100?card=Desert").get_json()
    assert data["match_filters"]["active"] == {}
    assert data["match_filters"]["ranked"] == {"wins": 2, "losses": 2}


def test_card_filter_when_card_stats_public(client, card_callbacks, monkeypatch):
    from repositories.user_profiles import UserProfileRepository
    monkeypatch.setattr(
        UserProfileRepository, "get_profile_visibility",
        lambda self, uid: {"card_stats": True},
    )
    data = client.get("/api/player/100?card=Desert").get_json()
    assert data["match_filters"]["ranked"] == {"wins": 2, "losses": 0}


def test_archive_original_ids(tmp_path):
    from services.player_card_stats import archive_original_ids, played_cards_by_match
    db = tmp_path / "m.db"
    conn = sqlite3.connect(str(db))
    # Columns as in discord-bot/repositories/elo_repo.create_match_records_archive
    conn.execute("""CREATE TABLE match_records_archive (
        archive_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL,
        original_match_id INTEGER, reporter_id INTEGER, winner_id INTEGER,
        winner_display_name TEXT, losser_id INTEGER, losser_display_name TEXT,
        did_win BOOLEAN, timestamp TEXT)""")
    conn.execute("INSERT INTO match_records_archive (event_id, original_match_id, winner_id, losser_id)"
                 " VALUES (8, 42, 100, 200)")
    conn.execute("INSERT INTO match_records_archive (event_id, original_match_id, winner_id, losser_id)"
                 " VALUES (8, 43, 300, 400)")
    conn.commit()
    conn.close()
    assert archive_original_ids(db, "google_100") == {1: 42}
    assert played_cards_by_match(db, "100") == {}  # no callback table yet
