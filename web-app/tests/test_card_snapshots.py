"""Saved PSO card tables (services/card_snapshots): fetched once per release.

Seasons come from the real elo.db ``events`` table the conftest builds; the
PSO body is the real /cards shape.
"""

import sqlite3
from datetime import datetime, timezone

import pytest

import webapp_config
from services import card_snapshots as snaps
from services import ranked_analytics

NOV_3 = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def body(released="2026-10-31"):
    return {"generatedAt": 1, "releasedThrough": released, "dataAvailable": True,
            "totalGames": 10, "totalPlayerGames": 20, "cards": []}


@pytest.fixture()
def pso(app, monkeypatch):
    state = {"calls": [], "answer": body()}

    def fake_forward(method, route, params=None, body=None):
        state["calls"].append(params)
        answer = state["answer"]
        if isinstance(answer, Exception):
            raise answer
        return ranked_analytics.ProxyResult(200, answer)

    monkeypatch.setattr(ranked_analytics, "forward", fake_forward)
    conn = sqlite3.connect(str(webapp_config.ELO_DB_PATH))
    conn.execute("DELETE FROM events")
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES "
                 "(8, 'Gothic Season 8', '2026-09-01 00:00:00', '2026-10-31 23:59:59', 0)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(webapp_config, "SEASON_FILTERS", [])
    return state


def at(moment, monkeypatch):
    monkeypatch.setattr(snaps, "_now", lambda: moment)


def test_selections_cover_all_time_recent_and_each_season(pso):
    keys = {s["key"]: s for s in snaps.selections(NOV_3)}
    assert set(keys) == {"all", "recent", "season:8"}
    assert keys["season:8"]["from"] == "2026-09-01"
    assert keys["recent"]["through"] == "2026-10-31"


def test_first_refresh_saves_everything_then_nothing_until_next_release(pso, monkeypatch):
    at(NOV_3, monkeypatch)
    assert snaps.refresh_due(NOV_3) == 3
    assert {"format": "constructed"} in pso["calls"]
    assert {"format": "constructed", "from": "2026-09-01", "through": "2026-10-31"} in pso["calls"]
    assert snaps.refresh_due(NOV_3) == 0

    later = datetime(2026, 11, 14, 23, 0, tzinfo=timezone.utc)
    at(later, monkeypatch)
    assert snaps.refresh_due(later) == 0

    nov_15 = datetime(2026, 11, 15, 0, 5, tzinfo=timezone.utc)
    at(nov_15, monkeypatch)
    pso["answer"] = body("2026-11-14")
    assert snaps.refresh_due(nov_15) == 3


def test_pso_behind_is_retried_hourly_not_every_tick(pso, monkeypatch):
    nov_15 = datetime(2026, 11, 15, 0, 5, tzinfo=timezone.utc)
    at(nov_15, monkeypatch)
    pso["answer"] = body("2026-10-31")  # PSO hasn't released Nov 1-14 yet
    snaps.refresh_due(nov_15)
    calls = len(pso["calls"])
    soon = datetime(2026, 11, 15, 0, 20, tzinfo=timezone.utc)
    at(soon, monkeypatch)
    snaps.refresh_due(soon)
    # Only Season 8 (ended Oct 31) is fully up to date; nothing re-asked within the hour.
    assert len(pso["calls"]) == calls
    hour = datetime(2026, 11, 15, 1, 10, tzinfo=timezone.utc)
    at(hour, monkeypatch)
    pso["answer"] = body("2026-11-14")
    assert snaps.refresh_due(hour) == 2  # all + recent; Season 8 was already complete


def test_saved_copy_survives_pso_going_down(pso, monkeypatch):
    at(NOV_3, monkeypatch)
    snaps.refresh_due(NOV_3)
    pso["answer"] = ranked_analytics.AnalyticsUnavailable("down")
    snaps.fetch_and_save(snaps.find(None, None))  # a failed refresh keeps the old copy
    assert snaps.saved("all")["releasedThrough"] == "2026-10-31"


def test_never_saved_and_pso_down_asks_at_most_hourly(pso, monkeypatch):
    at(NOV_3, monkeypatch)
    pso["answer"] = ranked_analytics.AnalyticsUnavailable("down")
    selection = snaps.find(None, None)
    assert snaps.get(selection) is None
    assert snaps.get(selection) is None
    assert len(pso["calls"]) == 1


def test_custom_range_is_not_a_named_selection(pso):
    assert snaps.find("2026-10-03", None) is None
    assert snaps.find(None, None)["key"] == "all"


def test_card_win_rates_page_reads_the_saved_copy(client, pso, monkeypatch):
    monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "k")
    snaps.refresh_due()
    calls = len(pso["calls"])
    pso["answer"] = ranked_analytics.AnalyticsUnavailable("down")
    for _ in range(3):
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 200
        assert resp.get_json()["releasedThrough"] == "2026-10-31"
        resp = client.get("/api/ranked-analytics/cards?format=constructed&from=2026-09-01&through=2026-10-31")
        assert resp.status_code == 200
    assert len(pso["calls"]) == calls
