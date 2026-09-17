"""Tests for "Try this Deck" — one-sided Sorcery Online table provisioning."""

import pytest
import requests

import webapp_config
from routes.api import deck_recommendations as deck_rec_routes
from services import sorcery_online_table as pso


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def raise_unavailable(*_args, **_kwargs):
    raise pso.TableUnavailable("Sorcery Online said no")


@pytest.fixture(autouse=True)
def _reset_throttle():
    pso._recent_requests.clear()
    yield
    pso._recent_requests.clear()


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "shared-test-key")
    monkeypatch.delenv("SORCERY_ONLINE_MATCHMAKING_URL", raising=False)


@pytest.fixture()
def seed_deck(monkeypatch):
    """Make one seed deck resolvable without loading the real deck archive."""
    class FakeSeed:
        deck_id = "cmtestdeck00000001"
        deck_name = "Test Troll Magic"
        curiosa_url = "https://curiosa.io/decks/cmtestdeck00000001"

    monkeypatch.setattr(
        deck_rec_routes, "_load_and_cluster", lambda: (None, [FakeSeed()], [], {})
    )

    class FakeRepo:
        def get_hidden_deck_ids(self):
            return set()

    monkeypatch.setattr(deck_rec_routes, "DeckRecRepository", FakeRepo)
    return FakeSeed


class TestProvisionSoloTable:
    def test_sends_single_player_with_deck_url(self, configured, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse(payload={
                "players": [
                    {"discordUserId": "7", "gameUrl": "https://playsorceryonline.com/?m=seat"}
                ]
            })

        monkeypatch.setattr(pso.requests, "post", fake_post)

        game_url = pso.provision_solo_table(
            "https://curiosa.io/decks/abc123", display_name="Alice", player_id="7"
        )

        assert game_url == "https://playsorceryonline.com/?m=seat"
        assert captured["url"] == pso.DEFAULT_ENDPOINT
        assert captured["headers"]["X-API-Key"] == "shared-test-key"
        players = captured["json"]["players"]
        assert len(players) == 1
        assert players[0]["deckUrl"] == "https://curiosa.io/decks/abc123"
        assert players[0]["discordUserId"] == "7"
        assert players[0]["displayName"] == "Alice"

    def test_anonymous_visitor_gets_a_generated_seat_id(self, configured, monkeypatch):
        captured = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return FakeResponse(payload={
                "players": [{"gameUrl": "https://playsorceryonline.com/?m=x"}]
            })

        monkeypatch.setattr(pso.requests, "post", fake_post)

        pso.provision_solo_table(
            "https://curiosa.io/decks/abc123", display_name="Summit Player"
        )

        assert captured["json"]["players"][0]["discordUserId"].startswith("web-")

    def test_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "")
        assert not pso.is_configured()
        with pytest.raises(pso.TableUnavailable):
            pso.provision_solo_table("https://curiosa.io/decks/abc", display_name="x")

    def test_error_status_raises(self, configured, monkeypatch):
        monkeypatch.setattr(
            pso.requests, "post",
            lambda *a, **k: FakeResponse(status_code=400, text="two players required"),
        )
        with pytest.raises(pso.TableUnavailable):
            pso.provision_solo_table("https://curiosa.io/decks/abc", display_name="x")

    def test_network_failure_raises(self, configured, monkeypatch):
        def boom(*a, **k):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(pso.requests, "post", boom)
        with pytest.raises(pso.TableUnavailable):
            pso.provision_solo_table("https://curiosa.io/decks/abc", display_name="x")

    def test_response_without_seat_link_raises(self, configured, monkeypatch):
        monkeypatch.setattr(
            pso.requests, "post",
            lambda *a, **k: FakeResponse(payload={"players": [{"discordUserId": "7"}]}),
        )
        with pytest.raises(pso.TableUnavailable):
            pso.provision_solo_table("https://curiosa.io/decks/abc", display_name="x")


class TestThrottle:
    def test_second_request_is_rejected_then_released(self):
        assert pso.claim_slot("ip:1.2.3.4") == 0
        assert pso.claim_slot("ip:1.2.3.4") > 0
        pso.release_slot("ip:1.2.3.4")
        assert pso.claim_slot("ip:1.2.3.4") == 0

    def test_clients_are_tracked_separately(self):
        assert pso.claim_slot("ip:1.1.1.1") == 0
        assert pso.claim_slot("ip:2.2.2.2") == 0


class TestPsoTableRoute:
    def test_returns_game_url(self, client, configured, seed_deck, monkeypatch):
        monkeypatch.setattr(
            deck_rec_routes, "provision_solo_table",
            lambda deck_url, **kw: "https://playsorceryonline.com/?m=ok",
        )

        resp = client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")

        assert resp.status_code == 200
        assert resp.get_json()["game_url"] == "https://playsorceryonline.com/?m=ok"

    def test_passes_the_decks_curiosa_url_through(self, client, configured, seed_deck, monkeypatch):
        captured = {}

        def fake_provision(deck_url, **kwargs):
            captured["deck_url"] = deck_url
            captured.update(kwargs)
            return "https://playsorceryonline.com/?m=ok"

        monkeypatch.setattr(deck_rec_routes, "provision_solo_table", fake_provision)

        client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")

        assert captured["deck_url"] == seed_deck.curiosa_url

    def test_discord_session_seats_the_real_user(self, client, configured, seed_deck, monkeypatch):
        captured = {}

        def fake_provision(deck_url, **kwargs):
            captured.update(kwargs)
            return "https://playsorceryonline.com/?m=ok"

        monkeypatch.setattr(deck_rec_routes, "provision_solo_table", fake_provision)
        with client.session_transaction() as sess:
            sess["user_id"] = 123456789012345678
            sess["username"] = "Bruce"

        client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")

        assert captured["player_id"] == "123456789012345678"
        assert captured["display_name"] == "Bruce"

    def test_google_session_does_not_pose_as_a_discord_user(self, client, configured, seed_deck, monkeypatch):
        captured = {}

        def fake_provision(deck_url, **kwargs):
            captured.update(kwargs)
            return "https://playsorceryonline.com/?m=ok"

        monkeypatch.setattr(deck_rec_routes, "provision_solo_table", fake_provision)
        with client.session_transaction() as sess:
            sess["user_id"] = "google_998877"
            sess["username"] = "Googler"

        client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")

        assert captured["player_id"] is None

    def test_rejects_bad_deck_id(self, client, configured):
        resp = client.post("/api/deck-rec/nope!/pso-table")
        assert resp.status_code in (400, 404)

    def test_unconfigured_returns_503(self, client, monkeypatch, seed_deck):
        monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "")
        resp = client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")
        assert resp.status_code == 503

    def test_hidden_deck_is_not_launchable(self, client, configured, seed_deck, monkeypatch):
        class HiddenRepo:
            def get_hidden_deck_ids(self):
                return {seed_deck.deck_id}

        monkeypatch.setattr(deck_rec_routes, "DeckRecRepository", HiddenRepo)
        resp = client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")
        assert resp.status_code == 404

    def test_provisioning_failure_returns_502(self, client, configured, seed_deck, monkeypatch):
        monkeypatch.setattr(deck_rec_routes, "provision_solo_table", raise_unavailable)
        resp = client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")
        assert resp.status_code == 502
        assert "Sorcery Online" in resp.get_json()["error"]

    def test_failure_does_not_consume_the_cooldown(self, client, configured, seed_deck, monkeypatch):
        monkeypatch.setattr(deck_rec_routes, "provision_solo_table", raise_unavailable)
        assert client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table").status_code == 502

        monkeypatch.setattr(
            deck_rec_routes, "provision_solo_table",
            lambda *a, **k: "https://playsorceryonline.com/?m=ok",
        )
        assert client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table").status_code == 200

    def test_rapid_second_request_is_throttled(self, client, configured, seed_deck, monkeypatch):
        monkeypatch.setattr(
            deck_rec_routes, "provision_solo_table",
            lambda *a, **k: "https://playsorceryonline.com/?m=ok",
        )
        assert client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table").status_code == 200
        resp = client.post(f"/api/deck-rec/{seed_deck.deck_id}/pso-table")
        assert resp.status_code == 429
        assert resp.get_json()["retry_after"] > 0
