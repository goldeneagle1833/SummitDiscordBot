"""Curiosa's Maybeboard is not part of the Collection.

The tRPC converter used to fold Maybeboard, Collection and Sideboard cards into
one sideboard list, so deck snapshots showed a 40-odd card "Collection" made
mostly of cards the owner was only considering.
"""

from services.curiosa import _convert_trpc_to_legacy


def _entry(board, name, quantity=1, card_type="Minion"):
    return {
        "board": board,
        "quantity": quantity,
        "card": {"name": name, "engine": {"type": card_type}},
        "printing": {"meta": {}},
    }


def _response(decklist):
    return {"result": {"data": {"json": {"id": "d1", "name": "Deck", "decklist": decklist}}}}


def test_maybeboard_is_kept_out_of_the_collection():
    deck = _convert_trpc_to_legacy(_response([
        _entry("Main", "Spell"),
        _entry("Collection", "Collected", 2),
        _entry("Sideboard", "Sided"),
        _entry("Maybeboard", "Maybe", 3),
    ]))

    assert [c["name"] for c in deck["sideboard"]] == ["Collected", "Sided"]
    assert [c["name"] for c in deck["maybeboard"]] == ["Maybe"]
    assert [c["name"] for c in deck["spellbook"]] == ["Spell"]


def test_deck_without_maybeboard_has_an_empty_one():
    deck = _convert_trpc_to_legacy(_response([_entry("Collection", "Collected")]))

    assert deck["maybeboard"] == []
