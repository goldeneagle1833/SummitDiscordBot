"""Tests for the open Staples API (GET /api/staples).

PSO's card rows use the exact shape its /cards route returns (see
tests/test_ranked_analytics.py and the vendored cardTable.ts). Seasons come
from the real elo.db ``events`` table the conftest builds.
"""

import sqlite3
from datetime import date

import pytest

import webapp_config
from services import ranked_analytics
from services import staples as svc

def rate(games, win_rate):
    wins = round(games * win_rate)
    return {"playerGames": games, "matches": games, "wins": wins, "winRate": win_rate}


def card(name, share, in_deck, played, unplayed, opening=(0, None)):
    return {
        "cardKey": name.lower(), "cardName": name, "deckShare": share,
        "inDeck": rate(*in_deck), "played": rate(*played),
        "openingHand": rate(*opening) if opening[1] is not None else
        {"playerGames": 0, "matches": 0, "wins": None, "winRate": None},
        "inDeckUnplayed": rate(*unplayed),
    }


BODY = {
    "generatedAt": 1790000000000,
    "releasedThrough": "2026-10-31",
    "dataAvailable": True,
    "totalGames": 4800,
    "totalPlayerGames": 9600,
    "cards": [
        # Everyone runs it and it swings games: the clear staple.
        card("Pudge Butcher", 0.40, (3840, 0.54), (2900, 0.58), (940, 0.42), (1200, 0.56)),
        # Very popular but neutral.
        card("Arid Desert", 0.45, (4320, 0.50), (4000, 0.50), (320, 0.50)),
        # Rare but huge win rate: a sleeper, should not top a staples list.
        card("Lucky Charm", 0.02, (190, 0.66), (120, 0.70), (70, 0.60)),
        # Under min_games: left out.
        card("Tiny Sample", 0.004, (30, 0.90), (20, 0.95), (10, 0.80)),
        # Avatar: every deck has one, left out.
        card("Sorcerer", 0.30, (2880, 0.51), (2880, 0.51), (0, 0.5)),
        # Popular trap: worse when played.
        card("Trap Card", 0.25, (2400, 0.47), (1500, 0.44), (900, 0.52)),
    ],
}

CATALOG = [
    {"name": "Pudge Butcher", "type": "Minion", "elements": ["Earth"], "rarity": "Exceptional",
     "imageUrl": "/card-images/pudge_butcher.png"},
    {"name": "Arid Desert", "type": "Site", "elements": ["Fire"], "rarity": "Ordinary", "imageUrl": None},
    {"name": "Lucky Charm", "type": "Artifact", "elements": [], "rarity": "Unique", "imageUrl": None},
    {"name": "Sorcerer", "type": "Avatar", "elements": [], "rarity": "", "imageUrl": None},
    {"name": "Trap Card", "type": "Magic", "elements": ["Water", "Air"], "rarity": "Elite", "imageUrl": None},
]


@pytest.fixture(autouse=True)
def _reset():
    svc.reset_cache()
    ranked_analytics.reset_caches()
    yield
    svc.reset_cache()
    ranked_analytics.reset_caches()


@pytest.fixture()
def pso(monkeypatch):
    calls = []

    def fake_forward(method, route, params=None, body=None):
        calls.append({"method": method, "route": route, "params": params})
        return ranked_analytics.ProxyResult(200, BODY)

    monkeypatch.setattr(ranked_analytics, "forward", fake_forward)
    monkeypatch.setattr(ranked_analytics, "build_catalog", lambda: CATALOG)
    monkeypatch.setenv("META_REPORT_SITE_URL", "https://sorcererssummit.com")
    return calls


class TestScore:
    def test_staple_beats_neutral_popular_and_rare_sleeper(self):
        rows = svc.score_cards(BODY, CATALOG, min_games=50)
        names = [r["name"] for r in rows]
        assert names[0] == "Pudge Butcher"
        assert names.index("Arid Desert") < names.index("Lucky Charm")
        assert "Trap Card" in names

    def test_avatars_and_small_samples_are_left_out(self):
        names = {r["name"] for r in svc.score_cards(BODY, CATALOG, min_games=50)}
        assert "Sorcerer" not in names
        assert "Tiny Sample" not in names

    def test_scores_are_0_to_100_and_sorted(self):
        rows = svc.score_cards(BODY, CATALOG, min_games=50)
        scores = [r["stapleScore"] for r in rows]
        assert scores == sorted(scores, reverse=True)
        assert all(0 <= s <= 100 for s in scores)

    def test_impact_needs_games_on_both_sides(self):
        body = {"cards": [card("Lopsided", 0.3, (1000, 0.6), (995, 0.6), (5, 0.0))]}
        row = svc.score_cards(body, [], min_games=50)[0]
        assert row["_impact"] == 0.0
        assert row["swing"] == pytest.approx(0.6)

    def test_percentiles_share_ties(self):
        assert svc._percentiles([1, 1, 3]) == [25.0, 25.0, 100.0]
        assert svc._percentiles([5]) == [100.0]


class TestWindow:
    def test_default_is_last_90_days(self):
        window = svc.resolve_window(None, None, None, today=date(2026, 11, 3))
        assert window == {"label": "Last 90 days", "from": "2026-08-05", "through": None}

    def test_all_time(self):
        assert svc.resolve_window("all", None, None)["from"] is None

    def test_season_from_the_events_table(self, app):
        conn = sqlite3.connect(str(webapp_config.ELO_DB_PATH))
        conn.execute(
            "INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (?, ?, ?, ?, ?)",
            (8, "Gothic Season 8", "2026-09-01 00:00:00", "2026-10-31 23:59:59", 0),
        )
        conn.commit()
        conn.close()
        window = svc.resolve_window("8", None, None)
        assert window == {"label": "Gothic Season 8", "from": "2026-09-01", "through": "2026-10-31"}

    def test_unknown_season(self, app):
        with pytest.raises(ValueError):
            svc.resolve_window("999", None, None)


class TestRoute:
    def test_open_without_a_key(self, client, pso):
        resp = client.get("/api/staples")
        assert resp.status_code == 200
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    def test_each_visitor_is_throttled(self, client, pso, monkeypatch):
        monkeypatch.setattr(ranked_analytics, "MAX_REQUESTS_PER_WINDOW", 2)
        ranked_analytics.reset_caches()
        assert client.get("/api/staples").status_code == 200
        assert client.get("/api/staples").status_code == 200
        assert client.get("/api/staples").status_code == 429

    def test_returns_ranked_cards(self, client, pso):
        resp = client.get("/api/staples?season=all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 4
        assert data["releasedThrough"] == "2026-10-31"
        first = data["cards"][0]
        assert first["rank"] == 1
        assert first["name"] == "Pudge Butcher"
        assert first["deckShare"] == 40.0
        assert first["playedVsNotPlayed"] == 16.0
        assert first["imageUrl"] == "https://sorcererssummit.com/card-images/pudge_butcher.png"
        assert set(first["components"]) == {"popularity", "impact", "win_rate"}
        assert pso[0]["params"] == {"format": "constructed"}

    def test_only_aggregate_fields(self, client, pso):
        data = client.get("/api/staples").get_json()
        allowed = {"rank", "name", "cardKey", "type", "elements", "rarity", "imageUrl", "stapleScore",
                   "components", "deckShare", "inDeckWinRate", "playedWinRate", "notPlayedWinRate",
                   "playedVsNotPlayed", "openingHandWinRate", "games"}
        for row in data["cards"]:
            assert set(row) == allowed

    def test_limit_and_filters(self, client, pso):
        data = client.get("/api/staples?limit=2").get_json()
        assert data["count"] == 2
        data = client.get("/api/staples?type=site").get_json()
        assert [c["name"] for c in data["cards"]] == ["Arid Desert"]
        data = client.get("/api/staples?element=multi").get_json()
        assert [c["name"] for c in data["cards"]] == ["Trap Card"]
        data = client.get("/api/staples?element=none").get_json()
        assert [c["name"] for c in data["cards"]] == ["Lucky Charm"]

    def test_bad_params(self, client, pso):
        for query in ("limit=0", "limit=101", "min_games=0", "from=yesterday",
                      "from=2026-10-02&through=2026-10-01", "type=<script>"):
            assert client.get(f"/api/staples?{query}").status_code == 400, query

    def test_date_range_is_forwarded_and_cached(self, client, pso):
        url = "/api/staples?from=2026-10-01&through=2026-10-31"
        assert client.get(url).status_code == 200
        assert client.get(url).status_code == 200
        assert len(pso) == 1
        assert pso[0]["params"] == {"format": "constructed", "from": "2026-10-01", "through": "2026-10-31"}

    def test_pso_down_is_a_503(self, client, monkeypatch):
        def down(*args, **kwargs):
            raise ranked_analytics.AnalyticsUnavailable("Ranked analytics is unavailable")

        monkeypatch.setattr(ranked_analytics, "forward", down)
        resp = client.get("/api/staples")
        assert resp.status_code == 503
        assert resp.get_json()["available"] is False
