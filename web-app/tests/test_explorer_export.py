"""Admin CSV export of a Community Series leaderboard."""

import csv
import io
import json

import pytest

from repositories.explorer import ExplorerRepository

CONFIG = {
    "participation": 10,
    "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
    "persecutor": {"1": 10, "2": 5},
    "trials_threshold": 10,
}


@pytest.fixture()
def series(app):
    repo = ExplorerRepository()
    season = repo.create_season("Season 3: Ohio", None, json.dumps(CONFIG))
    first = repo.create_event(
        season_id=season["id"], event_external_id="evt-1", event_name="Cornerstone",
        event_date="2026-05-01", total_players=8, play_format="Constructed",
        venue_name="Waterloo Games", source_url="https://sorcerytcg.com/events/1",
    )
    second = repo.create_event(
        season_id=season["id"], event_external_id="evt-2", event_name="Summit Clash",
        event_date="2026-06-01", total_players=8, play_format="Constructed",
        venue_name="Sorcerers Summit", source_url="https://sorcerytcg.com/events/2",
    )
    repo.save_results(first["id"], [
        {"cardeio_user_id": "u1", "display_name": "Alice", "final_standing": 1, "wins": 3,
         "total_players": 8, "image_url": None, "team_name": "Frogs"},
        {"cardeio_user_id": "u2", "display_name": "=HYPERLINK(\"x\")", "final_standing": 2, "wins": 2,
         "total_players": 8, "image_url": None, "team_name": ""},
    ])
    repo.save_results(second["id"], [
        {"cardeio_user_id": "u1", "display_name": "Alice", "final_standing": 2, "wins": 2,
         "total_players": 8, "image_url": None, "team_name": "Frogs"},
    ])
    return season


def _rows(response):
    text = response.get_data(as_text=True).lstrip("﻿")
    return list(csv.DictReader(io.StringIO(text)))


def test_standings_export_matches_the_leaderboard(admin_session, series):
    resp = admin_session.get(f"/api/explorer/leaderboard/{series['id']}/export.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "season-3-ohio-standings.csv" in resp.headers["Content-Disposition"]

    rows = _rows(resp)
    assert [r["Player"] for r in rows] == ["Alice", "'=HYPERLINK(\"x\")"]
    alice = rows[0]
    # 10+3 (bonus wins 3 -> 0) +10 first, then 10+0+5 second.
    assert alice["Rank"] == "1"
    assert alice["Events"] == "2"
    assert alice["Persecutor"] == "15"
    assert alice["Qualified"] == "Yes"
    assert alice["Team"] == "Frogs"


def test_results_export_has_one_row_per_player_per_event(explorer_admin_session, series):
    resp = explorer_admin_session.get(
        f"/api/explorer/leaderboard/{series['id']}/export.csv?view=results"
    )
    assert resp.status_code == 200
    rows = _rows(resp)
    assert [(r["Event"], r["Place"]) for r in rows] == [
        ("Cornerstone", "1"), ("Cornerstone", "2"), ("Summit Clash", "2"),
    ]
    assert rows[0]["Venue"] == "Waterloo Games"
    assert rows[0]["Event Link"] == "https://sorcerytcg.com/events/1"
    assert rows[0]["Persecutor"] == "10"
    assert rows[2]["Series Rank"] == "1"


def test_players_cannot_export(user_session, series):
    resp = user_session.get(f"/api/explorer/leaderboard/{series['id']}/export.csv")
    assert resp.status_code in (401, 403)


def test_signed_out_visitors_cannot_export(client, series):
    resp = client.get(f"/api/explorer/leaderboard/{series['id']}/export.csv")
    assert resp.status_code in (401, 403)


def test_unknown_series_and_view(admin_session, series):
    assert admin_session.get("/api/explorer/leaderboard/9999/export.csv").status_code == 404
    bad = admin_session.get(f"/api/explorer/leaderboard/{series['id']}/export.csv?view=nope")
    assert bad.status_code == 400
