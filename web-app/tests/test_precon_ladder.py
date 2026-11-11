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
