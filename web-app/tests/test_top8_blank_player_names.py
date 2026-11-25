"""Decks whose sorcerytcg.com owner has no handle still show a player name."""

import json

from repositories.events import EventRepository, deck_player_name, usable_username

FOLDER = "Cornerstone at Gold Glory Gaming"


def _deck(i, user, avatar="Necromancer"):
    return {"id": f"deck{i}", "username": user, "avatar": [{"name": avatar}],
            "spellbook": [], "atlas": []}


def _setup(tmp_path, with_history=True):
    ev = tmp_path / FOLDER
    ev.mkdir(parents=True)
    decks = [_deck(1, ""), _deck(2, "10bposey"), _deck(3, "Discord"), _deck(4, None)]
    (ev / f"{FOLDER}top8.json").write_text(json.dumps(decks))
    (ev / f"{FOLDER}.json").write_text(json.dumps(decks))
    if with_history:
        (ev / "_match_history.json").write_text(json.dumps({"players": [
            {"deck_id": "deck1", "display_name": "Kirsten M", "matches": []},
            {"deck_id": "deck2", "display_name": "Brandon P", "matches": []},
            {"deck_id": "deck3", "display_name": "Kody M", "matches": []},
        ]}))
    return EventRepository(events_dir=tmp_path)


def test_usable_username_drops_blanks_and_placeholders():
    assert usable_username("") == ""
    assert usable_username(None) == ""
    assert usable_username("Discord") == ""
    assert usable_username(" ianm ") == "ianm"


def test_deck_player_name_prefers_handle_then_event_name():
    names = {"deck1": "Kirsten M"}
    assert deck_player_name(_deck(1, ""), names) == "Kirsten M"
    assert deck_player_name(_deck(1, "ianm"), names) == "ianm"
    assert deck_player_name(_deck(9, ""), names) == "Unknown"


def test_event_page_fills_blank_names_from_match_history(tmp_path):
    decks = _setup(tmp_path).get_event_decks(FOLDER)
    assert [d["player"] for d in decks["top8_decks"]] == [
        "Kirsten M", "10bposey", "Kody M", "Unknown"]


def test_event_page_without_history_says_unknown(tmp_path):
    decks = _setup(tmp_path, with_history=False).get_event_decks(FOLDER)
    assert [d["player"] for d in decks["top8_decks"]] == [
        "Unknown", "10bposey", "Unknown", "Unknown"]


def test_event_list_winner_and_deck_index_use_fallback(tmp_path):
    repo = _setup(tmp_path)
    event = next(e for e in repo.get_all_events() if e["folder"] == FOLDER)
    assert event["winner_username"] == "Kirsten M"
    rows = repo.get_deck_index()["events"][FOLDER]
    assert rows[0][1] == "Kirsten M"
