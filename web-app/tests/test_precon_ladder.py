"""Precon ladder (Lavamancer vs Frostmage) standings API."""

import datetime
import sqlite3
from pathlib import Path

import webapp_config
from services import precon_ladder

T0 = datetime.datetime.now().replace(microsecond=0) - datetime.timedelta(days=2)


def _seed(db_path):
    conn = sqlite3.connect(str(db_path))
    season = precon_ladder.start_season(conn, "LM vs FM 1", now=T0)
    for i in range(precon_ladder.MIN_RANKED_GAMES):
        precon_ladder.record_match(
            conn, winner_id=111, loser_id=222, winner_name="Alice", loser_name="Bob",
            winner_precon="LM", loser_precon="FM", now=T0 + datetime.timedelta(hours=i + 1),
        )
    precon_ladder.record_match(
        conn, winner_id=333, loser_id=111, winner_name="Cara", loser_name="Alice",
        winner_precon="FM", loser_precon="LM", now=T0 + datetime.timedelta(hours=20),
    )
    conn.close()
    return season


def test_standings_default_to_the_open_season(client):
    season = _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    resp = client.get("/api/precon/standings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["season"]["season_id"] == season["season_id"]
    assert data["season"]["is_open"] is True
    assert [p["key"] for p in data["precons"]] == ["lavamancer", "frostmage"]
    names = [row["name"] for row in data["standings"]]
    assert names[:2] == ["Alice", "Bob"]  # ranked first
    assert data["standings"][-1]["name"] == "Cara" and data["standings"][-1]["rank"] is None
    alice = data["standings"][0]
    assert alice["lm_wins"] == precon_ladder.MIN_RANKED_GAMES and alice["lm_losses"] == 1
    assert data["stats"]["lm_vs_fm"]["lm_wins"] == precon_ladder.MIN_RANKED_GAMES
    assert data["stats"]["lm_vs_fm"]["fm_wins"] == 1
    assert data["recent"][0]["winner_display_name"] == "Cara"


def test_no_season_yet_is_an_empty_ladder(client):
    resp = client.get("/api/precon/standings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["season"] is None and data["standings"] == [] and data["seasons"] == []


def test_unknown_season_is_404(client):
    _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    assert client.get("/api/precon/standings?season_id=999").status_code == 404


def test_bot_copy_is_identical():
    web_copy = Path(precon_ladder.__file__)
    bot_copy = web_copy.parents[2] / "discord-bot" / "services" / "precon_ladder.py"
    assert bot_copy.read_text(encoding="utf-8") == web_copy.read_text(encoding="utf-8")


def test_hub_summary_is_none_before_any_ladder(client):
    from services.precon_hub import hub_summary

    assert hub_summary() is None


def test_hub_summary_lists_the_open_ladder(client):
    from services.precon_hub import hub_summary

    _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    summary = hub_summary()
    assert summary["system"]["status"] == "live"
    assert summary["system"]["link"] == "/?ladder=precon#leaderboard"
    assert [p["display_name"] for p in summary["players"]] == ["Alice", "Bob", "Cara"]
    assert summary["players"][2]["provisional"] is True and summary["players"][0]["rank"] == 1


def test_player_endpoint_lists_their_ladder_and_games(client):
    _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    data = client.get("/api/precon/players/111").get_json()
    assert len(data["seasons"]) == 1
    entry = data["seasons"][0]
    assert entry["season"]["name"] == "LM vs FM 1"
    assert entry["standing"]["rank"] == 1 and entry["ranked_players"] == 2
    assert data["games"][0]["won"] is False and data["games"][0]["opponent_name"] == "Cara"
    assert data["games"][0]["precon"] == "lavamancer" and data["games"][0]["opponent_precon"] == "frostmage"


def test_player_with_no_precon_games_gets_empty_lists(client):
    data = client.get("/api/precon/players/999").get_json()
    assert data["seasons"] == [] and data["games"] == []
    assert client.get("/api/precon/players/google-abc").get_json()["seasons"] == []


def _seed_with_replay(db_path):
    conn = sqlite3.connect(str(db_path))
    precon_ladder.start_season(conn, "LM vs FM 1", now=T0)
    precon_ladder.record_match(
        conn, winner_id=111, loser_id=222, winner_name="Alice", loser_name="Bob",
        winner_precon="LM", loser_precon="FM", now=T0 + datetime.timedelta(hours=1),
        replay_url="https://playsorceryonline.com/replay/xyz",
    )
    conn.close()


def test_replay_link_shows_to_the_players_only(client):
    _seed_with_replay(webapp_config.MATCH_RECORDS_DB_PATH)
    assert client.get("/api/precon/players/111").get_json()["games"][0]["replay_url"] is None
    with client.session_transaction() as sess:
        sess["user_id"] = "111"
        sess["username"] = "Alice"
    game = client.get("/api/precon/players/111").get_json()["games"][0]
    assert game["replay_url"] == "https://playsorceryonline.com/replay/xyz"


# --- Admin page ---------------------------------------------------------------


def _no_bot(monkeypatch):
    import routes.api.matchmaking as mm

    calls = []

    def fake_relay(method, path, payload=None, unavailable_body=None, timeout=None):
        calls.append((method, path))
        return {"refreshed": True}, 200

    monkeypatch.setattr(mm, "relay_to_bot", fake_relay)
    return calls


def test_admin_endpoints_need_an_admin(client, user_session):
    assert client.get("/api/precon/admin").status_code == 403
    assert client.post("/api/precon/admin/seasons", json={"name": "x"}).status_code == 403
    assert client.put("/api/precon/admin/settings", json={"queue_enabled": True}).status_code == 403


def test_admin_starts_a_season_and_opens_the_queue(client, admin_session, monkeypatch):
    calls = _no_bot(monkeypatch)
    state = client.get("/api/precon/admin").get_json()
    assert state["settings"] == {
        "queue_enabled": False, "min_ranked_games": 5, "block_rematch": True, "season_days": 28,
        "pso_test_mode": False,
    }
    resp = client.post("/api/precon/admin/seasons", json={"name": "LM vs FM 1", "days": 14, "open_queue": True})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["settings"]["queue_enabled"] is True
    assert data["open_season_id"] == data["result"]["season_id"]
    season = data["seasons"][0]
    start = datetime.datetime.fromisoformat(season["starts_at"])
    assert datetime.datetime.fromisoformat(season["ends_at"]) - start == datetime.timedelta(days=14)
    assert data["bot_refreshed"] is True and ("POST", "/precon-refresh") in calls
    # A second one is refused while the first runs
    again = client.post("/api/precon/admin/seasons", json={"name": "Two"})
    assert again.status_code == 400 and "already running" in again.get_json()["error"]


def test_admin_rules_change_who_is_ranked(client, admin_session, monkeypatch):
    _no_bot(monkeypatch)
    _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    bad = client.put("/api/precon/admin/settings", json={"min_ranked_games": 0})
    assert bad.status_code == 400
    ok = client.put("/api/precon/admin/settings", json={"min_ranked_games": 1, "block_rematch": False})
    assert ok.status_code == 200
    assert ok.get_json()["settings"]["block_rematch"] is False
    standings = client.get("/api/precon/standings").get_json()
    assert standings["min_ranked_games"] == 1
    assert all(row["ranked"] for row in standings["standings"])  # Cara's one game now counts


def test_admin_edits_and_ends_a_season(client, admin_session, monkeypatch):
    _no_bot(monkeypatch)
    season = _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    # Moving the start past the first games takes them off the ladder
    new_start = (T0 + datetime.timedelta(hours=10)).isoformat()
    resp = client.put(
        f"/api/precon/admin/seasons/{season['season_id']}", json={"name": "Renamed", "starts_at": new_start},
    )
    assert resp.status_code == 200, resp.get_json()
    edited = resp.get_json()["seasons"][0]
    assert edited["name"] == "Renamed" and edited["games"] == 1
    # And moving it back brings them home again
    resp = client.put(f"/api/precon/admin/seasons/{season['season_id']}", json={"starts_at": T0.isoformat()})
    assert resp.get_json()["seasons"][0]["games"] == precon_ladder.MIN_RANKED_GAMES + 1
    bad = client.put(f"/api/precon/admin/seasons/{season['season_id']}", json={"ends_at": T0.isoformat()})
    assert bad.status_code == 400
    ended = client.post("/api/precon/admin/seasons/end")
    assert ended.status_code == 200 and ended.get_json()["open_season_id"] is None
    assert client.post("/api/precon/admin/seasons/end").status_code == 400


def test_admin_reports_and_removes_a_game(client, admin_session, monkeypatch):
    _no_bot(monkeypatch)
    _seed(webapp_config.MATCH_RECORDS_DB_PATH)
    body = {
        "winner_id": "444", "winner_name": "Dan", "winner_precon": "FM",
        "loser_id": "111", "loser_name": "Alice", "loser_precon": "lavamancer",
    }
    assert client.post("/api/precon/admin/matches", json={**body, "loser_id": "444"}).status_code == 400
    assert client.post("/api/precon/admin/matches", json={**body, "winner_precon": "x"}).status_code == 400
    resp = client.post("/api/precon/admin/matches", json=body)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    match_id = data["result"]["match_id"]
    assert data["result"]["rated"] is True and data["recent"][0]["match_id"] == match_id
    gone = client.delete(f"/api/precon/admin/matches/{match_id}")
    assert gone.status_code == 200
    assert all(g["match_id"] != match_id for g in gone.get_json()["recent"])
    assert client.delete(f"/api/precon/admin/matches/{match_id}").status_code == 400


def test_admin_still_saves_when_the_bot_is_down(client, admin_session, monkeypatch):
    import routes.api.matchmaking as mm

    monkeypatch.setattr(mm, "relay_to_bot", lambda *a, **k: ({}, 503))
    resp = client.put("/api/precon/admin/settings", json={"queue_enabled": True})
    assert resp.status_code == 200
    assert resp.get_json()["bot_refreshed"] is False
    assert resp.get_json()["settings"]["queue_enabled"] is True
