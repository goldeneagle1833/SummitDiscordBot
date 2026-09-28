"""Tests for the Play Sorcery Online ranked analytics proxy."""

import json

import pytest
import requests

import webapp_config
from services import ranked_analytics as svc


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


CARDS_OK = {
    "generatedAt": 1790000000000,
    "releasedThrough": "2026-09-27",
    "dataAvailable": True,
    "totalGames": 4812,
    "totalPlayerGames": 9624,
    "cards": [],
}


@pytest.fixture(autouse=True)
def _reset():
    svc.reset_caches()
    yield
    svc.reset_caches()


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "shared-test-key")
    monkeypatch.delenv("SORCERY_ONLINE_ANALYTICS_URL", raising=False)


@pytest.fixture()
def upstream(monkeypatch):
    """Capture the outbound request and answer with a canned response."""
    captured = {}
    state = {"response": FakeResponse(payload=CARDS_OK)}

    def fake_request(method, url, params=None, data=None, headers=None, timeout=None, allow_redirects=True):
        captured.update(method=method, url=url, params=params, data=data,
                        headers=headers, timeout=timeout, allow_redirects=allow_redirects)
        result = state["response"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(svc.requests, "request", fake_request)
    captured["answer_with"] = lambda r: state.__setitem__("response", r)
    return captured


class TestCardsRoute:
    def test_forwards_selection_with_the_server_key(self, client, configured, upstream):
        resp = client.get("/api/ranked-analytics/cards?format=constructed&from=2026-09-01")

        assert resp.status_code == 200
        assert resp.get_json()["totalGames"] == 4812
        assert resp.headers["Cache-Control"] == "private, no-store"
        assert upstream["method"] == "GET"
        assert upstream["url"] == "https://playsorceryonline.com/api/summit/game-analytics/cards"
        assert upstream["params"] == {"format": "constructed", "from": "2026-09-01"}
        assert upstream["headers"]["X-API-Key"] == "shared-test-key"
        assert upstream["allow_redirects"] is False

    def test_key_never_appears_in_the_response(self, client, configured, upstream):
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert "shared-test-key" not in resp.get_data(as_text=True)
        assert "shared-test-key" not in str(resp.headers)

    def test_requires_a_valid_format(self, client, configured, upstream):
        assert client.get("/api/ranked-analytics/cards").status_code == 400
        assert client.get("/api/ranked-analytics/cards?format=casual").status_code == 400
        assert client.get("/api/ranked-analytics/cards?format=limited").status_code == 400
        assert "url" not in upstream

    def test_rejects_extra_and_repeated_parameters(self, client, configured, upstream):
        assert client.get("/api/ranked-analytics/cards?format=constructed&queueType=all").status_code == 400
        assert client.get("/api/ranked-analytics/cards?format=constructed&format=limited").status_code == 400
        assert client.get("/api/ranked-analytics/cards?format=constructed&from=yesterday").status_code == 400
        assert "url" not in upstream

    def test_unconfigured_key_is_a_503(self, client, upstream, monkeypatch):
        monkeypatch.setattr(webapp_config, "DRAFT_SORCERY_API_KEY", "")
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 503
        assert resp.get_json()["available"] is False
        assert "url" not in upstream

    def test_upstream_404_while_route_is_disabled_is_a_503(self, client, configured, upstream):
        upstream["answer_with"](FakeResponse(404, {"message": "Route not found"}))
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 503
        assert "Route not found" not in resp.get_data(as_text=True)

    def test_upstream_403_does_not_leak_auth_details(self, client, configured, upstream):
        upstream["answer_with"](FakeResponse(403, {"error": "bad key"}))
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 503
        assert "bad key" not in resp.get_data(as_text=True)

    def test_network_failure_is_a_503(self, client, configured, upstream):
        upstream["answer_with"](requests.ConnectionError("down"))
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 503

    def test_upstream_400_is_a_generic_400(self, client, configured, upstream):
        upstream["answer_with"](FakeResponse(400, {"error": "queue_type is admin only"}))
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 400
        assert resp.get_json() == {"error": "Invalid analytics query"}


class TestReplaysRoute:
    def test_encodes_the_card_key(self, client, configured, upstream):
        upstream["answer_with"](FakeResponse(payload={"replays": []}))
        resp = client.get("/api/ranked-analytics/cards/temple%20of%20moloch/replays?format=constructed")
        assert resp.status_code == 200
        assert upstream["url"].endswith("/cards/temple%20of%20moloch/replays")
        assert resp.headers["Cache-Control"] == "private, no-store"


class TestCohortRoute:
    QUERY = {
        "selection": {"format": "constructed"},
        "filter": {"kind": "condition", "field": "avatar", "value": "Imposter"},
    }

    def test_forwards_the_json_body_unchanged(self, client, configured, upstream):
        upstream["answer_with"](FakeResponse(payload={
            "dataAvailable": True, "releasedThrough": "2026-09-27",
            "cohort": {"playerGames": 12, "matches": 12, "wins": 7, "winRate": 0.5833},
        }))
        resp = client.post("/api/ranked-analytics/cohort", json=self.QUERY)
        assert resp.status_code == 200
        assert resp.get_json()["cohort"]["wins"] == 7
        assert upstream["method"] == "POST"
        assert upstream["params"] is None
        assert json.loads(upstream["data"]) == self.QUERY
        assert upstream["headers"]["Content-Type"] == "application/json"

    def test_requires_json(self, client, configured, upstream):
        resp = client.post("/api/ranked-analytics/cohort", data="format=constructed",
                           content_type="application/x-www-form-urlencoded")
        assert resp.status_code == 415
        assert "url" not in upstream

    def test_rejects_bodies_over_16_kib(self, client, configured, upstream):
        big = dict(self.QUERY, padding="x" * (16 * 1024))
        resp = client.post("/api/ranked-analytics/cohort", json=big)
        assert resp.status_code == 413
        assert "url" not in upstream

    def test_rejects_a_body_without_a_selection(self, client, configured, upstream):
        resp = client.post("/api/ranked-analytics/cohort", json={"filter": {}})
        assert resp.status_code == 400
        assert "url" not in upstream

    def test_rejects_query_string_parameters(self, client, configured, upstream):
        resp = client.post("/api/ranked-analytics/cohort?format=constructed", json=self.QUERY)
        assert resp.status_code == 400
        assert "url" not in upstream


class TestThrottle:
    def test_a_client_is_cut_off_after_the_budget(self, client, configured, upstream, monkeypatch):
        monkeypatch.setattr(svc, "MAX_REQUESTS_PER_WINDOW", 3)
        for _ in range(3):
            assert client.get("/api/ranked-analytics/cards?format=constructed").status_code == 200
        resp = client.get("/api/ranked-analytics/cards?format=constructed")
        assert resp.status_code == 429

    def test_clients_are_tracked_separately(self, monkeypatch):
        monkeypatch.setattr(svc, "MAX_REQUESTS_PER_WINDOW", 1)
        assert svc.claim_request("ip:1.1.1.1") is True
        assert svc.claim_request("ip:1.1.1.1") is False
        assert svc.claim_request("ip:2.2.2.2") is True


class TestCatalog:
    @pytest.fixture(autouse=True)
    def _no_pso_catalog(self, monkeypatch):
        monkeypatch.setattr(svc, "fetch_pso_catalog", lambda: [])

    def test_shapes_catalog_rows_for_the_ui(self, client, monkeypatch):
        class FakeRepo:
            def get_all_cards(self):
                return [
                    {"name": "Whirling Blades", "card_type": "Magic", "rarity": "Exceptional", "elements": "Air"},
                    {"name": "Templar", "card_type": "Avatar", "rarity": "Elite", "elements": "None"},
                    {"name": "Bridge Troll", "card_type": "Minion", "rarity": "Ordinary", "elements": "Earth, Water"},
                    {"name": "", "card_type": "Minion", "rarity": "Ordinary", "elements": ""},
                ]

        monkeypatch.setattr(svc, "CardCatalogRepository", FakeRepo)
        monkeypatch.setattr(svc, "resolve_card_image", lambda name: "alp-whirling_blades-b-s.png" if name == "Whirling Blades" else None)

        resp = client.get("/api/ranked-analytics/catalog")

        assert resp.status_code == 200
        rows = resp.get_json()
        assert [r["name"] for r in rows] == ["Whirling Blades", "Templar", "Bridge Troll"]
        assert rows[0] == {"name": "Whirling Blades", "type": "Magic", "elements": ["Air"],
                           "rarity": "Exceptional", "imageUrl": "/card-images/alp-whirling_blades-b-s.png"}
        assert rows[1]["elements"] == []
        assert rows[1]["imageUrl"] is None
        assert rows[2]["elements"] == ["Earth", "Water"]

    def test_catalog_is_cached(self, client, monkeypatch):
        calls = {"n": 0}

        class FakeRepo:
            def get_all_cards(self):
                calls["n"] += 1
                return []

        monkeypatch.setattr(svc, "CardCatalogRepository", FakeRepo)
        client.get("/api/ranked-analytics/catalog")
        client.get("/api/ranked-analytics/catalog")
        assert calls["n"] == 1


class TestPsoCatalogMerge:
    PSO = [
        {"name": "Imposter", "type": "Avatar", "elements": [], "rarity": "Unique", "imageUrl": "https://playsorceryonline.com/images/got-imposter-b-s.png"},
        {"name": "Whirling Blades", "type": "Magic", "elements": ["Air"], "rarity": "Exceptional", "imageUrl": "https://playsorceryonline.com/images/alp-whirling_blades-b-s.png"},
        {"name": "Realm-Eater", "type": "Avatar", "elements": [], "rarity": "Unique", "imageUrl": "https://playsorceryonline.com/images/got-realm_eater-b-s.png"},
    ]

    def test_fills_in_names_the_local_catalog_lacks(self, client, monkeypatch):
        class FakeRepo:
            def get_all_cards(self):
                return [{"name": "Whirling Blades", "card_type": "Magic", "rarity": "Exceptional", "elements": "Air"}]

        monkeypatch.setattr(svc, "CardCatalogRepository", FakeRepo)
        monkeypatch.setattr(svc, "fetch_pso_catalog", lambda: list(self.PSO))
        monkeypatch.setattr(svc, "resolve_card_image", lambda name: "got-imposter-b-s.png" if name == "Imposter" else None)

        rows = client.get("/api/ranked-analytics/catalog").get_json()

        assert [r["name"] for r in rows] == ["Whirling Blades", "Imposter", "Realm-Eater"]
        # Local art wins; PSO's own image is the fallback.
        assert rows[1]["imageUrl"] == "/card-images/got-imposter-b-s.png"
        assert rows[2]["imageUrl"] == "https://playsorceryonline.com/images/got-realm_eater-b-s.png"
        assert rows[1]["type"] == "Avatar"

    def test_fetch_dedupes_printings_and_resolves_relative_images(self, monkeypatch):
        payload = [
            {"name": "Battlemage", "type": "Avatar", "rarity": "Unique", "elements": [], "imageUrl": "/images/alp-battlemage-b-s.png"},
            {"name": "Battlemage", "type": "Avatar", "rarity": "Unique", "elements": [], "imageUrl": "/images/bet-battlemage-b-s.png"},
            {"name": "", "type": "Minion"},
            "junk",
        ]
        monkeypatch.setattr(svc.requests, "get", lambda url, timeout=None, headers=None: FakeResponse(payload=payload))

        cards = svc.fetch_pso_catalog()

        assert cards == [{"name": "Battlemage", "type": "Avatar", "elements": [], "rarity": "Unique",
                          "imageUrl": "https://playsorceryonline.com/images/alp-battlemage-b-s.png"}]

    def test_fetch_failure_is_empty_and_not_retried_immediately(self, monkeypatch):
        calls = {"n": 0}

        def failing_get(url, timeout=None, headers=None):
            calls["n"] += 1
            raise requests.ConnectionError("down")

        monkeypatch.setattr(svc.requests, "get", failing_get)

        assert svc.fetch_pso_catalog() == []
        assert svc.fetch_pso_catalog() == []
        assert calls["n"] == 1

    def test_fills_empty_local_metadata_from_pso(self, client, monkeypatch):
        """Production's synced table has names but blank type/rarity/elements."""
        class FakeRepo:
            def get_all_cards(self):
                return [
                    {"name": "Imposter", "card_type": "", "rarity": "", "elements": ""},
                    {"name": "Whirling Blades", "card_type": "", "rarity": "", "elements": ""},
                    {"name": "Bridge Troll", "card_type": "Minion", "rarity": "Ordinary", "elements": "None"},
                ]

        monkeypatch.setattr(svc, "CardCatalogRepository", FakeRepo)
        monkeypatch.setattr(svc, "fetch_pso_catalog", lambda: list(self.PSO) + [
            {"name": "Bridge Troll", "type": "Minion", "elements": ["Water"], "rarity": "Ordinary",
             "imageUrl": "https://playsorceryonline.com/images/alp-bridge_troll-b-s.png"},
        ])
        monkeypatch.setattr(svc, "resolve_card_image", lambda name: None)

        rows = {r["name"]: r for r in client.get("/api/ranked-analytics/catalog").get_json()}

        assert rows["Imposter"]["type"] == "Avatar"
        assert rows["Imposter"]["rarity"] == "Unique"
        assert rows["Imposter"]["imageUrl"] == "https://playsorceryonline.com/images/got-imposter-b-s.png"
        assert rows["Whirling Blades"]["type"] == "Magic"
        assert rows["Whirling Blades"]["elements"] == ["Air"]
        # An explicit local "None" is a real value, not a gap.
        assert rows["Bridge Troll"]["elements"] == []
        assert rows["Bridge Troll"]["type"] == "Minion"
