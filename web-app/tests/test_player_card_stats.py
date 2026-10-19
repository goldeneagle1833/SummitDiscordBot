"""A player's Card Stats tab: their own PSO played cards, private unless they opt in."""

import json
import sqlite3

from repositories.user_profiles import UserProfileRepository
from services.player_card_stats import summarize


def _seed_callbacks(match_db, games):
    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sorcery_online_match_callbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL DEFAULT 0, pairing_id INTEGER NOT NULL DEFAULT 0,
            queue_type TEXT NOT NULL DEFAULT 'ranked', outcome TEXT NOT NULL,
            reporter_id INTEGER, winner_id INTEGER, loser_id INTEGER, match_id TEXT,
            played_cards TEXT, raw_players TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    """)
    for winner, loser, played in games:
        conn.execute(
            "INSERT INTO sorcery_online_match_callbacks (outcome, winner_id, loser_id, match_id, played_cards)"
            " VALUES ('decided', ?, ?, 'm', ?)",
            (winner, loser, json.dumps(played)),
        )
    conn.commit()
    conn.close()


def _as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


GAMES = [
    (1, 2, {"1": ["Bolt", "Wolves"], "2": ["Other"]}),
    (2, 1, {"1": ["Wolves"], "2": ["Other"]}),
    (1, 3, {"1": ["Bolt", "Bolt"], "3": ["Other"]}),
]


def test_summary_counts_only_this_player_and_effect():
    result = summarize([(True, ["Bolt", "Wolves"]), (False, ["Wolves"]), (True, ["Bolt"])])
    cards = {c["name"]: c for c in result["cards"]}
    assert result["games"] == 3 and result["wins"] == 2
    assert cards["Bolt"]["games"] == 2 and cards["Bolt"]["win_rate"] == 100.0
    assert cards["Bolt"]["win_rate_not_played"] == 0.0 and cards["Bolt"]["effect"] == 100.0
    assert cards["Wolves"]["games"] == 2 and cards["Wolves"]["win_rate"] == 50.0


def test_card_stats_private_by_default(client, match_db):
    _seed_callbacks(match_db, GAMES)
    assert client.get("/api/player/1/card-stats").status_code == 403  # logged out
    _as(client, "2")
    assert client.get("/api/player/1/card-stats").status_code == 403  # another player


def test_owner_sees_own_cards_only(client, match_db):
    _seed_callbacks(match_db, GAMES)
    _as(client, "1")
    resp = client.get("/api/player/1/card-stats")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {c["name"] for c in data["cards"]}
    assert names == {"Bolt", "Wolves"}
    assert data["games"] == 3 and data["wins"] == 2
    bolt = next(c for c in data["cards"] if c["name"] == "Bolt")
    assert bolt["games"] == 2  # a card listed twice in one game counts once


def test_public_when_player_opts_in(client, match_db):
    _seed_callbacks(match_db, GAMES)
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('1', 'discord', 'P', 'now', 'now')"
    )
    conn.commit()
    conn.close()
    UserProfileRepository(match_db).set_profile_visibility("1", {"card_stats": True})
    _as(client, "2")
    assert client.get("/api/player/1/card-stats").status_code == 200


def test_queue_filter_splits_ranked_and_casual(client, match_db):
    _seed_callbacks(match_db, GAMES)
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO sorcery_online_match_callbacks (queue_type, outcome, winner_id, loser_id, match_id, played_cards)"
        " VALUES ('testing', 'decided', 1, 4, 'c', ?)",
        (json.dumps({"1": ["Casual Card"], "4": ["Other"]}),),
    )
    conn.commit()
    conn.close()
    _as(client, "1")

    def stats(queue):
        return client.get(f"/api/player/1/card-stats?queue={queue}").get_json()

    assert stats("all")["games"] == 4
    ranked = stats("ranked")
    assert ranked["games"] == 3 and ranked["queue"] == "ranked"
    assert "Casual Card" not in {c["name"] for c in ranked["cards"]}
    casual = stats("casual")
    assert casual["games"] == 1 and {c["name"] for c in casual["cards"]} == {"Casual Card"}
    assert stats("bogus")["queue"] == "all"
