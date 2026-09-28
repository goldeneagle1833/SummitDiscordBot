"""Deck links from Play Sorcery Online are accepted alongside sorcerytcg.com ones.

PSO share links keep the deck id in the query string
(https://playsorceryonline.com/?deck=<id>), so the old "strip the ? and
everything after it" normalisation collapsed every PSO deck into one URL and
the host allow-list dropped them from the profile entirely.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.curiosa import (
    PSO_DECK_EXPORT_URL,
    CuriosaService,
    deck_url_source,
    get_curiosa_deck_id,
    get_pso_deck_id,
    is_deck_url,
    normalize_deck_url,
)

PSO_URL = "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"
CURIOSA_URL = "https://sorcerytcg.com/decks/clx1abc23"

PSO_EXPORT = {
    "id": "pD-1gXa3cg8c",
    "name": "Earth/Fire",
    "username": "Lucas",
    "visibility": "Public",
    "format": "Constructed",
    "legality": {"isLegal": True, "context": ""},
    "avatar": [{"identifier": "sorcerer", "name": "Sorcerer", "quantity": 1,
                "elements": "None", "cost": None, "power": 1, "type": "Avatar", "rarity": None}],
    "spellbook": [{"identifier": "war_horse", "name": "War Horse", "quantity": 3,
                   "elements": "Fire", "fireThreshold": 1, "cost": 2, "power": 2,
                   "type": "Minion", "rarity": "Exceptional"}],
    "atlas": [{"identifier": "rift_valley", "name": "Rift Valley", "quantity": 2,
               "elements": "Earth", "cost": None, "type": "Site", "rarity": "Elite"}],
    "sideboard": [],
}


def _response(status=200, payload=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = text
    return resp


class TestDeckLinkHelpers:
    @pytest.mark.parametrize("url,expected", [
        (PSO_URL, "pD-1gXa3cg8c"),
        ("https://www.playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c", "pD-1gXa3cg8c"),
        ("http://playsorceryonline.com/?deck=abc_DEF-123", "abc_DEF-123"),
        ("https://playsorceryonline.com/?table=abc123", None),
        ("https://playsorceryonline.com/?deck=", None),
        ("https://playsorceryonline.com/?deck=ab", None),
        ("https://sorcerytcg.com/?deck=pD-1gXa3cg8c", None),
        ("https://evil.com/playsorceryonline.com/?deck=pD-1gXa3cg8c", None),
        ("not a url", None),
        ("", None),
        (None, None),
    ])
    def test_get_pso_deck_id(self, url, expected):
        assert get_pso_deck_id(url) == expected

    @pytest.mark.parametrize("url,expected", [
        (CURIOSA_URL, "clx1abc23"),
        ("https://curiosa.io/decks/clx1abc23?tab=view", "clx1abc23"),
        ("https://sorcerytcg.com/decks/clx1abc23/edit", "clx1abc23"),
        ("https://sorcerytcg.com/events/abc", None),
        (PSO_URL, None),
        ("https://sorcerytcg.com/decks/", None),
    ])
    def test_get_curiosa_deck_id(self, url, expected):
        assert get_curiosa_deck_id(url) == expected

    def test_is_deck_url_accepts_both_services(self):
        assert is_deck_url(PSO_URL)
        assert is_deck_url(CURIOSA_URL)
        assert is_deck_url("https://curiosa.io/decks/clx1abc23")
        assert not is_deck_url("https://playsorceryonline.com/?table=abc123")
        assert not is_deck_url("https://draftsorcery.com/?deck=abc123")
        assert not is_deck_url("No URL provided")
        assert not is_deck_url("")

    def test_deck_url_source(self):
        assert deck_url_source(PSO_URL) == "sorcery_online"
        assert deck_url_source(CURIOSA_URL) == "curiosa"
        assert deck_url_source("https://draftsorcery.com/?deck=abc123") is None

    def test_normalize_keeps_the_pso_deck_id(self):
        # This is the bug: split("?")[0] turned every PSO deck into the homepage.
        assert normalize_deck_url("https://www.playsorceryonline.com/?a=1&deck=pD-1gXa3cg8c") == PSO_URL
        assert normalize_deck_url(PSO_URL) == PSO_URL

    def test_normalize_curiosa_drops_query_and_edit_suffix(self):
        assert normalize_deck_url("https://sorcerytcg.com/decks/clx1abc23/edit?tab=view") == CURIOSA_URL
        assert normalize_deck_url("https://curiosa.io/decks/clx1abc23?x=1") == "https://curiosa.io/decks/clx1abc23"

    def test_normalize_other_urls_behaves_as_before(self):
        assert normalize_deck_url("https://example.com/x?y=1") == "https://example.com/x"
        assert normalize_deck_url("") == ""
        assert normalize_deck_url(None) is None


class TestFetchPsoDeck:
    def test_fetch_deck_data_uses_the_pso_exporter(self):
        service = CuriosaService()
        with patch("services.curiosa.requests.get", return_value=_response(200, PSO_EXPORT)) as get:
            raw = service.fetch_deck_data("https://playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c")

        get.assert_called_once()
        args, kwargs = get.call_args
        assert args[0] == PSO_DECK_EXPORT_URL
        assert kwargs["params"] == {"input": PSO_URL}

        deck = json.loads(raw)
        assert deck["id"] == "pD-1gXa3cg8c"
        assert deck["name"] == "Earth/Fire"
        assert deck["username"] == "Lucas"
        assert deck["source"] == "sorcery_online"
        assert deck["avatar"][0]["name"] == "Sorcerer"
        assert deck["spellbook"] == [{
            "name": "War Horse", "quantity": 3, "type": "Minion", "rarity": "Exceptional",
            "cost": 2, "elements": "Fire", "image": "",
        }]
        assert deck["atlas"][0]["type"] == "Site"
        assert deck["sideboard"] == []

    def test_pso_fetch_does_not_wait_on_the_curiosa_rate_limit(self):
        service = CuriosaService()
        service._last_request_time = 10**12  # a Curiosa call "just happened"
        with patch("services.curiosa.requests.get", return_value=_response(200, PSO_EXPORT)), \
                patch("services.curiosa.time.sleep") as sleep:
            service.fetch_deck_data(PSO_URL)
        sleep.assert_not_called()

    def test_missing_pso_deck_is_empty(self):
        service = CuriosaService()
        with patch("services.curiosa.requests.get", return_value=_response(404, None, "Deck not found")):
            assert service.fetch_deck_data("https://playsorceryonline.com/?deck=notarealdeck") == "{}"

    def test_curiosa_links_still_go_to_sorcerytcg(self):
        service = CuriosaService()
        with patch("services.curiosa.requests.get", return_value=_response(404, None)) as get, \
                patch("services.curiosa.time.sleep"):
            service.fetch_deck_data(CURIOSA_URL)
        assert "sorcerytcg.com/api/trpc/deck.get" in get.call_args[0][0]

    def test_batch_fetch_mixes_both_services(self):
        service = CuriosaService()
        trpc = {"result": {"data": {"json": {
            "id": "clx1abc23", "name": "Curiosa Deck", "owner": {"username": "a"},
            "decklist": [{"board": "Avatar", "quantity": 1,
                          "card": {"name": "Sorcerer", "engine": {"type": "Avatar"}}}],
        }}}}

        def fake_get(url, **kwargs):
            if url == PSO_DECK_EXPORT_URL:
                return _response(200, PSO_EXPORT)
            return _response(200, trpc)

        with patch("services.curiosa.requests.get", side_effect=fake_get), \
                patch("services.curiosa.time.sleep"):
            decks, errors = service.fetch_decks_batch([PSO_URL, CURIOSA_URL, "   "])

        assert errors == []
        assert [d["id"] for d in decks] == ["pD-1gXa3cg8c", "clx1abc23"]


class TestMatchReportValidation:
    def _service(self):
        from services.match_confirmation import MatchConfirmationService
        return MatchConfirmationService(repository=MagicMock(), user_repo=MagicMock())

    def test_pso_deck_links_are_accepted(self):
        result = self._service().validate_match_report_input(
            "111", "222", "won", "submitter",
            submitter_deck_url=PSO_URL, opponent_deck_url=CURIOSA_URL,
        )
        assert result["valid"], result["errors"]

    def test_non_deck_links_are_still_rejected(self):
        result = self._service().validate_match_report_input(
            "111", "222", "won", "submitter",
            submitter_deck_url="https://playsorceryonline.com/?table=abc123",
        )
        assert not result["valid"]
        assert "playsorceryonline.com/?deck=" in result["errors"]["submitter_deck_url"]


class TestProfileRecentDecks:
    """A player's PSO decks show up on their profile, one entry per deck."""

    def _record(self, conn, match_id, winner, loser, winner_url, loser_url, ts):
        conn.execute(
            """INSERT INTO match_records (match_id, winner_id, winner_display_name, losser_id,
               losser_display_name, timestamp, winner_elo_change, loser_elo_change,
               curiosa_url, curiosa_url_winner, curiosa_url_loser,
               json_deck_data_winner, json_deck_data_loser)
               VALUES (?, ?, ?, ?, ?, ?, 10, -10, ?, ?, ?, ?, ?)""",
            (match_id, winner, f"P{winner}", loser, f"P{loser}", ts,
             winner_url, winner_url, loser_url,
             json.dumps({"name": "Earth/Fire", "avatar": [{"name": "Sorcerer", "type": "Avatar"}],
                         "spellbook": [], "atlas": [], "sideboard": []}),
             "{}"),
        )

    def test_pso_decks_group_by_deck_id(self, client, match_db, elo_db):
        import sqlite3
        conn = sqlite3.connect(str(match_db))
        deck_a = "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"
        deck_b = "https://playsorceryonline.com/?deck=zZ9-otherDeck"
        self._record(conn, "m1", "111", "222", deck_a, None, "2026-09-01 10:00:00")
        self._record(conn, "m2", "111", "333", deck_a + "&tab=view", None, "2026-09-02 10:00:00")
        self._record(conn, "m3", "111", "444", deck_b, None, "2026-09-03 10:00:00")
        conn.commit()
        conn.close()

        with client.session_transaction() as sess:
            sess["user_id"] = "111"
            sess["username"] = "P111"
        resp = client.get("/api/player/111")
        assert resp.status_code == 200, resp.get_json()
        decks = {d["url"]: d for d in resp.get_json()["recent_decks"]}

        assert set(decks) == {deck_a, deck_b}
        assert decks[deck_a]["wins"] == 2
        assert decks[deck_b]["wins"] == 1
        assert decks[deck_a]["deck_name"] == "Earth/Fire"

    def test_deck_stats_matches_pso_link_by_deck_id(self, client, match_db, elo_db):
        import sqlite3
        conn = sqlite3.connect(str(match_db))
        deck = "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"
        self._record(conn, "m1", "111", "222", deck, None, "2026-09-01 10:00:00")
        self._record(conn, "m2", "333", "111", None, deck, "2026-09-02 10:00:00")
        conn.commit()
        conn.close()

        with client.session_transaction() as sess:
            sess["user_id"] = "111"
            sess["username"] = "P111"
        resp = client.get("/api/players/111/deck-stats?url=" + deck.replace("?", "%3F").replace("=", "%3D"))
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["wins"] == 1
        assert body["losses"] == 1
