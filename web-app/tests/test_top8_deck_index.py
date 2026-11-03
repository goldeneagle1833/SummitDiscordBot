"""Deck index + card search behind the Top 8 page filters."""

import json

from repositories.events import EventRepository


def _deck(i, user, avatar, cards, atlas=()):
    return {
        "id": f"deck{i}",
        "username": user,
        "avatar": [{"name": avatar}],
        "spellbook": [{"name": c, "elements": "Fire", "quantity": 1} for c in cards],
        "atlas": [{"name": a, "elements": "None", "quantity": 1} for a in atlas],
        "sideboard": [{"name": "Collection Only Card"}],
    }


def _setup(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    ev = tmp_path / "Cold Foil Heros 3 30 2026"
    ev.mkdir()
    top8 = [_deck(1, "alice", "Sparkmage", ["Blink"]), _deck(2, "bob", "Druid", ["Askelon Phoenix"], ["Arid Desert"])]
    full = top8 + [_deck(3, "carol", "Sparkmage", ["Blink", "Askelon Phoenix"])]
    (ev / "Cold Foil Heros 3 30 2026top8.json").write_text(json.dumps(top8))
    (ev / "Cold Foil Heros 3 30 2026.json").write_text(json.dumps(full))

    only_full = tmp_path / "Every one at Con 2026"
    only_full.mkdir()
    (only_full / "Every one at Con 2026.json").write_text(json.dumps([_deck(4, "dave", "Seer", ["Blink"])]))
    return EventRepository(events_dir=tmp_path)


def test_index_has_places_for_top8_and_dedupes_full_list(tmp_path):
    idx = _setup(tmp_path).get_deck_index()
    rows = idx["events"]["Cold Foil Heros 3 30 2026"]
    assert [(r[0], r[1], r[2], r[4]) for r in rows] == [
        (1, "alice", "Sparkmage", "deck1"),
        (2, "bob", "Druid", "deck2"),
        (None, "carol", "Sparkmage", "deck3"),
    ]
    assert rows[0][3] == ["Fire"]
    assert idx["events"]["Every one at Con 2026"][0][0] is None
    assert idx["avatars"] == ["Druid", "Seer", "Sparkmage"]
    # Spellbook + atlas only; never the collection/sideboard
    assert "Arid Desert" in idx["cards"] and "Collection Only Card" not in idx["cards"]
    # No card lists in the payload
    assert all(len(r) == 5 for rows in idx["events"].values() for r in rows)


def test_card_search_is_case_insensitive_and_returns_positions(tmp_path):
    repo = _setup(tmp_path)
    assert repo.find_decks_with_card("blink") == {
        "Cold Foil Heros 3 30 2026": [0, 2],
        "Every one at Con 2026": [0],
    }
    assert repo.find_decks_with_card("Arid Desert") == {"Cold Foil Heros 3 30 2026": [1]}
    assert repo.find_decks_with_card("Collection Only Card") == {}
    assert repo.find_decks_with_card("  ") == {}


def test_index_rebuilds_when_an_event_file_changes(tmp_path):
    repo = _setup(tmp_path)
    assert "Witch" not in repo.get_deck_index()["avatars"]
    new = tmp_path / "Local Night 2026"
    new.mkdir()
    (new / "Local Night 2026top8.json").write_text(json.dumps([_deck(9, "erin", "Witch", ["Blink"])]))
    assert "Witch" in repo.get_deck_index()["avatars"]


def test_routes(client, tmp_path, monkeypatch):
    import routes.api.events as events_routes

    repo = _setup(tmp_path / "events")
    monkeypatch.setattr(events_routes, "EventRepository", lambda: repo)
    r = client.get("/api/top-8-events/deck-index")
    assert r.status_code == 200 and "Sparkmage" in r.get_json()["avatars"]
    r = client.get("/api/top-8-events/card-search?card=Blink")
    assert r.get_json()["matches"]["Every one at Con 2026"] == [0]
    assert client.get("/api/top-8-events/card-search").get_json() == {"matches": {}}
