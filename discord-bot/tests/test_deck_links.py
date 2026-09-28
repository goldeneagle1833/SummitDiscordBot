"""Play Sorcery Online deck links are fetched and stored like sorcerytcg.com ones.

The LFG modals already accepted PSO links, but the deck scraper only knew
sorcerytcg.com, so a PSO deck never got its JSON stored and the website's
profile had nothing to show for it.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from utils.deck_checker import (
    PSO_DECK_EXPORT_URL,
    _convert_pso_export_to_legacy,
    clean_deck_url,
    fetch_deck_by_url,
    get_pso_deck_id,
    scrape_Curosa,
    scrape_curosa_async,
)
from services.elo_service import _is_valid_deck_url

PSO_URL = "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"

PSO_EXPORT = {
    "id": "pD-1gXa3cg8c",
    "name": "Earth/Fire",
    "username": "Lucas",
    "visibility": "Public",
    "avatar": [{"identifier": "sorcerer", "name": "Sorcerer", "quantity": 1,
                "elements": "None", "cost": None, "type": "Avatar", "rarity": None}],
    "spellbook": [{"identifier": "war_horse", "name": "War Horse", "quantity": 3,
                   "elements": "Fire", "fireThreshold": 1, "cost": 2, "power": 2,
                   "type": "Minion", "rarity": "Exceptional"}],
    "atlas": [{"identifier": "rift_valley", "name": "Rift Valley", "quantity": 2,
               "elements": "Earth", "cost": None, "type": "Site", "rarity": "Elite"}],
    "sideboard": [],
}


def _response(status=200, payload=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = json.dumps(payload) if payload is not None else ""
    return resp


@pytest.mark.parametrize("url,expected", [
    (PSO_URL, "pD-1gXa3cg8c"),
    ("https://www.playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c", "pD-1gXa3cg8c"),
    ("https://playsorceryonline.com/?table=abc123", None),
    ("https://playsorceryonline.com/?deck=", None),
    ("https://sorcerytcg.com/?deck=pD-1gXa3cg8c", None),
    ("https://draftsorcery.com/?deck=pD-1gXa3cg8c", None),
    ("", None),
    (None, None),
])
def test_get_pso_deck_id(url, expected):
    assert get_pso_deck_id(url) == expected


def test_clean_deck_url_canonicalises_pso_links():
    assert clean_deck_url("https://www.playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c") == PSO_URL
    assert clean_deck_url(PSO_URL) == PSO_URL


def test_clean_deck_url_leaves_other_links_alone():
    # DraftSorcery keeps its query string; Curiosa loses it as before.
    assert clean_deck_url("https://draftsorcery.com/?deck=abc") == "https://draftsorcery.com/?deck=abc"
    assert clean_deck_url("https://sorcerytcg.com/decks/abc/edit?x=1") == "https://sorcerytcg.com/decks/abc"
    assert clean_deck_url("https://playsorceryonline.com/?table=abc") == "https://playsorceryonline.com/?table=abc"


def test_is_valid_deck_url_accepts_pso_decks():
    assert _is_valid_deck_url(PSO_URL)
    assert _is_valid_deck_url("https://sorcerytcg.com/decks/abc123")
    assert not _is_valid_deck_url("https://playsorceryonline.com/?table=abc123")
    assert not _is_valid_deck_url("https://draftsorcery.com/?deck=abc123")
    assert not _is_valid_deck_url("No URL provided")


def test_pso_export_is_trimmed_to_the_legacy_shape():
    deck = _convert_pso_export_to_legacy(PSO_EXPORT)
    assert deck["id"] == "pD-1gXa3cg8c"
    assert deck["name"] == "Earth/Fire"
    assert deck["username"] == "Lucas"
    assert deck["source"] == "sorcery_online"
    assert deck["spellbook"] == [{
        "name": "War Horse", "quantity": 3, "type": "Minion", "rarity": "Exceptional",
        "cost": 2, "elements": "Fire", "image": "",
    }]
    assert deck["atlas"][0]["type"] == "Site"
    assert _convert_pso_export_to_legacy({"id": "x"}) == {}
    assert _convert_pso_export_to_legacy("Deck not found") == {}


def test_fetch_deck_by_url_routes_pso_links_to_the_exporter():
    with patch("utils.deck_checker.requests.get", return_value=_response(200, PSO_EXPORT)) as get:
        deck = fetch_deck_by_url("https://playsorceryonline.com/?foo=1&deck=pD-1gXa3cg8c")

    args, kwargs = get.call_args
    assert args[0] == PSO_DECK_EXPORT_URL
    assert kwargs["params"] == {"input": PSO_URL}
    assert deck["avatar"][0]["name"] == "Sorcerer"


def test_fetch_deck_by_url_still_uses_sorcerytcg_for_curiosa_links():
    with patch("utils.deck_checker.requests.get", return_value=_response(404, None)) as get:
        assert fetch_deck_by_url("https://sorcerytcg.com/decks/abc123") is None
    assert "sorcerytcg.com/api/trpc/deck.get" in get.call_args[0][0]


async def test_scrape_curosa_async_returns_pso_deck_json():
    with patch("utils.deck_checker.requests.get", return_value=_response(200, PSO_EXPORT)):
        raw = await scrape_curosa_async(PSO_URL)
    deck = json.loads(raw)
    assert deck["source"] == "sorcery_online"
    assert deck["avatar"][0]["name"] == "Sorcerer"


async def test_scrape_curosa_async_missing_pso_deck_is_empty():
    with patch("utils.deck_checker.requests.get", return_value=_response(404, None)):
        assert await scrape_curosa_async("https://playsorceryonline.com/?deck=notarealdeck") == "{}"


async def test_backfill_recovers_pso_decks_in_live_and_archived_matches():
    """Ended events move matches into match_records_archive; the profile reads
    both tables, so the startup backfill has to repair both."""
    import sqlite3
    from unittest.mock import AsyncMock
    from repositories.elo_repo import create_match_records_archive
    from services.elo_service import backfill_deck_data

    create_match_records_archive()
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        """INSERT INTO match_records (winner_id, losser_id, timestamp, curiosa_url_winner,
           curiosa_url_loser, json_deck_data_winner, json_deck_data_loser)
           VALUES (1, 2, '2026-09-01', ?, NULL, '{}', '{}')""",
        (PSO_URL,),
    )
    conn.execute(
        """INSERT INTO match_records_archive (event_id, winner_id, losser_id, timestamp,
           curiosa_url_winner, curiosa_url_loser, json_deck_data_winner, json_deck_data_loser)
           VALUES (7, 3, 4, '2026-08-01', 'https://sorcerytcg.com/decks/abc123', ?, '{"name":"kept"}', '{}')""",
        (PSO_URL,),
    )
    conn.commit()
    conn.close()

    fetched = json.dumps({"name": "Earth/Fire", "source": "sorcery_online", "avatar": [{"name": "Sorcerer"}]})
    with patch("services.elo_service.scrape_curosa_async", new=AsyncMock(return_value=fetched)) as scrape, \
            patch("asyncio.sleep", new=AsyncMock()):
        await backfill_deck_data()

    # Only the two missing PSO decks were fetched; the archived winner's kept JSON was left alone.
    assert scrape.await_count == 2
    conn = sqlite3.connect("match_records.db")
    live = conn.execute("SELECT json_deck_data_winner FROM match_records").fetchone()[0]
    archived = conn.execute(
        "SELECT json_deck_data_winner, json_deck_data_loser FROM match_records_archive"
    ).fetchone()
    conn.close()
    assert json.loads(live)["name"] == "Earth/Fire"
    assert archived == ('{"name":"kept"}', fetched)


def test_scrape_curosa_sync_logs_pso_decks_to_file(tmp_path):
    log = tmp_path / "deck_data_test.json"
    with patch("utils.deck_checker.requests.get", return_value=_response(200, PSO_EXPORT)):
        raw = scrape_Curosa(PSO_URL, str(log))
    assert json.loads(raw)["name"] == "Earth/Fire"
    assert json.loads(log.read_text())[0]["id"] == "pD-1gXa3cg8c"
