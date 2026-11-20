"""Deck pages for event decks built from sorcerytcg.com's frozen event lists.

Those decks are keyed by registration id and have no sorcerytcg.com deck page,
so the deck page must serve the saved copy instead of asking Curiosa.
"""

import json

import pytest

from repositories.deck_rec_repo import DeckRecRepository
from routes.api import deck_recommendations as deck_rec_routes
from services.curiosa import EVENT_SNAPSHOT_DECK_SOURCE


def _card(name, card_type="Minion", qty=1):
    return {"name": name, "quantity": qty, "type": card_type, "rarity": "Ordinary",
            "cost": 2, "elements": "Water", "image": ""}


SNAP = {
    "id": "cmw6lbjkl000l08l76n3a7g70",
    "name": "Thirst Trap",
    "username": "jams",
    "source": EVENT_SNAPSHOT_DECK_SOURCE,
    "registration_id": "cmw6lbjkl000l08l76n3a7g70",
    "avatar": [{"name": "Avatar of Water"}],
    "spellbook": [_card("Poison Nova", "Magic", 2)],
    "atlas": [_card("Spring River", "Site")],
    "sideboard": [],
}
REAL = dict(SNAP, id="cmrealdeck000001", name="Old Import", source=None)


@pytest.fixture()
def events_dir(tmp_path, monkeypatch):
    root = tmp_path / "events"
    folder = root / "Trials"
    folder.mkdir(parents=True)
    # Top cut only in the top8 file, the rest in the full file, as an import writes them
    (folder / "Trialstop8.json").write_text(json.dumps([SNAP]))
    (folder / "Trials.json").write_text(json.dumps([REAL]))
    monkeypatch.setattr(DeckRecRepository, "__init__",
                        lambda self, top8_dir=None, db_path=None: setattr(self, "_top8_dir", root)
                        or setattr(self, "_db_path", tmp_path / "none.db"))
    monkeypatch.setattr(deck_rec_routes, "_load_seeds", lambda: (DeckRecRepository(), []))
    return root


def test_find_event_deck_looks_in_every_event_file(events_dir):
    repo = DeckRecRepository()
    assert repo.find_event_deck(SNAP["id"]) == (SNAP, "Trials")
    assert repo.find_event_deck(REAL["id"])[1] == "Trials"
    assert repo.find_event_deck("nope") is None


def test_snapshot_decks_have_no_sorcerytcg_link(events_dir):
    repo = DeckRecRepository()
    assert repo.deck_url(SNAP) == ""
    assert repo.deck_url(REAL) == "https://sorcerytcg.com/decks/cmrealdeck000001"
    record = repo._parse_tournament_deck(SNAP, "Trials")
    assert record.curiosa_url == ""


def test_deck_page_serves_the_saved_event_deck(client, events_dir, monkeypatch):
    def no_curiosa(url):
        raise AssertionError(f"asked Curiosa for {url}")

    monkeypatch.setattr(deck_rec_routes, "_fetch_live_deck", no_curiosa)

    resp = client.get(f"/api/deck-rec/{SNAP['id']}/info")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["seed"]["deck_name"] == "Thirst Trap"
    assert body["seed"]["player_name"] == "jams"
    assert body["seed"]["avatar_name"] == "Avatar of Water"
    assert body["seed"]["event_name"] == "Trials"
    assert body["seed"]["curiosa_url"] == ""
    assert {c["name"] for c in body["seed_spellbook"]} == {"Poison Nova", "Spring River"}


def test_unsaved_decks_still_come_from_curiosa(client, events_dir, monkeypatch):
    asked = []

    def fake_live(url):
        asked.append(url)
        return {"name": "Live", "username": "x", "avatar": [], "spellbook": [], "atlas": []}

    monkeypatch.setattr(deck_rec_routes, "_fetch_live_deck", fake_live)
    resp = client.get("/api/deck-rec/cmunknown0000001/info")
    assert resp.status_code == 200
    assert asked == ["https://sorcerytcg.com/decks/cmunknown0000001"]


def test_try_this_deck_refuses_snapshot_decks(events_dir):
    assert deck_rec_routes._resolve_deck_url(SNAP["id"])[0] is None
    assert deck_rec_routes._resolve_deck_url(REAL["id"]) == (
        "https://sorcerytcg.com/decks/cmrealdeck000001", "Old Import")
