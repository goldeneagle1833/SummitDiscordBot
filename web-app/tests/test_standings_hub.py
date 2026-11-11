"""The /standings hub: every system on one page, and the viewer's place in each."""

from unittest.mock import patch

import pytest

import webapp_config
from repositories.brackets import BracketRepository
from services.standings_hub import StandingsHubService, TOP_CUT_SIZE


class FakeEloRepo:
    def __init__(self, event):
        self.event = event

    def get_active_event(self):
        return self.event

    def get_display_names(self, ids):
        return {i: f"P{i[1:]}" for i in ids}


class FakeProfiles:
    def get_custom_display_names(self, ids):
        return {}


class FakeLeaderboard:
    def __init__(self, players, event=None):
        self.players = players
        self.event = event if event is not None else {"event_id": 9, "event_name": "Season 9", "end_date": "2026-12-31"}
        self._elo_repo = FakeEloRepo(self.event)
        self._profile_repo = FakeProfiles()

    def get_event_leaderboard(self):
        return {"event": self.event, "leaderboard": self.players}


class FakeBrackets:
    def list_brackets(self):
        return []

    def get_player_open_matches(self, user_id):
        return []

    def _site_names(self, ids):
        return {}


def entry(i, elo, voice=5):
    return {"id": f"u{i}", "name": f"P{i}", "event_elo": elo, "wins": 6, "losses": 4, "voice_games": voice}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(webapp_config, "DISCORD_BOT_TOKEN", "")
    monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", set())


@pytest.fixture()
def repo(tmp_path):
    r = BracketRepository(db_path=tmp_path / "b.db")
    r.ensure_tables()
    return r


def hub(repo, players, viewer=None):
    service = StandingsHubService(FakeLeaderboard(players), repo, FakeBrackets())
    # Only the season card is under test here; the rest read other databases.
    with patch.object(service, "_underdog", return_value=(None, None)), \
         patch.object(service, "_limited", return_value=(None, None)), \
         patch.object(service, "_explorer", return_value=(None, None)):
        return service.get_hub(viewer)


def season(result):
    return next(s for s in result["systems"] if s["key"] == "season")


def test_logged_out_gets_cards_without_a_you_block(repo):
    result = hub(repo, [entry(i, 2000 - i) for i in range(1, 5)])
    keys = [s["key"] for s in result["systems"]]
    assert keys[0] == "season" and "precon" in keys and "brackets" in keys
    assert "you" not in season(result)
    assert season(result)["top"][0]["name"] == "P1"


def test_ticket_holder_inside_the_cut(repo):
    players = [entry(i, 2000 - i) for i in range(1, 40)]
    repo.replace_ticket_holders([{"user_id": f"u{i}"} for i in range(1, 40)])
    you = season(hub(repo, players, "u3"))["you"]
    assert you["state"] == "in"
    assert f"#3 of {TOP_CUT_SIZE}" in you["headline"]


def test_ticket_holder_outside_the_cut_sees_the_gap(repo):
    players = [entry(i, 2000 - i * 10) for i in range(1, 40)]
    repo.replace_ticket_holders([{"user_id": f"u{i}"} for i in range(1, 40)])
    you = season(hub(repo, players, "u35"))["you"]
    assert you["state"] == "out"
    # #32 sits on 1680, #35 on 1650.
    assert "30 ELO behind #32" in you["notes"]


def test_player_without_a_ticket_is_told_so(repo):
    players = [entry(i, 2000 - i) for i in range(1, 5)]
    repo.replace_ticket_holders([{"user_id": "u1"}])
    you = season(hub(repo, players, "u2"))["you"]
    assert you["state"] == "no_ticket"
    assert you["action"]["to"] == "/store"


def test_player_with_no_games_this_season(repo):
    you = season(hub(repo, [entry(1, 1600)], "u99"))["you"]
    assert you["state"] == "none"


def test_precon_card_is_coming_soon_until_the_ladder_exists(repo):
    precon = next(s for s in hub(repo, [])["systems"] if s["key"] == "precon")
    assert precon["status"] == "coming_soon"
    assert "Frostmage" in precon["title"]


def test_one_broken_system_does_not_take_the_page_down(repo):
    service = StandingsHubService(FakeLeaderboard([entry(1, 1600)]), repo, FakeBrackets())
    with patch.object(service, "_underdog", side_effect=RuntimeError("boom")), \
         patch.object(service, "_limited", return_value=(None, None)), \
         patch.object(service, "_explorer", return_value=(None, None)):
        keys = [s["key"] for s in service.get_hub()["systems"]]
    assert "season" in keys and "underdog" not in keys


def test_endpoint_is_public(client):
    with patch("routes.api.standings_hub.get_service") as get:
        get.return_value.get_hub.return_value = {"systems": [], "logged_in": False, "built_at": 0}
        res = client.get("/api/standings")
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_precon_card_fills_in_from_the_precon_hub(repo, monkeypatch):
    import sys
    import types

    fake = types.ModuleType("services.precon_hub")
    fake.hub_summary = lambda: {
        "system": {"title": "Precon Ladder", "status": "live", "blurb": "LM vs FM",
                   "link": "/?ladder=precon#leaderboard", "ends_at": "2026-12-09"},
        "players": [
            {"user_id": "u1", "display_name": "P1", "rating": 1612.4, "rank": 1, "games": 9, "provisional": False},
            {"user_id": "u2", "display_name": "P2", "rating": 1540, "rank": 2, "games": 3, "provisional": True},
        ],
    }
    monkeypatch.setitem(sys.modules, "services.precon_hub", fake)
    import services
    monkeypatch.setattr(services, "precon_hub", fake, raising=False)

    result = hub(repo, [], "u2")
    precon = next(s for s in result["systems"] if s["key"] == "precon")
    assert precon["status"] == "live"
    assert precon["top"][0] == {"rank": 1, "name": "P1", "value": 1612, "unit": "rating"}
    assert precon["you"]["headline"] == "Rank #2"
    assert "provisional" in precon["you"]["detail"]
