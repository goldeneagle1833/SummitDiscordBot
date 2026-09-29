"""Tests for converting Sorcery TCG API cards to the legacy catalog shape."""

from utils.card_api import to_legacy_card


def _new_format_card(**engine_overrides):
    engine = {
        "type": "Minion",
        "category": "Spell",
        "rarity": "Ordinary",
        "slot": "Ordinary",
        "rules": "Spellcaster\r\nGenesis → Draw a spell.",
        "cost": 3,
        "attack": 1,
        "defense": 1,
        "life": None,
        "air": 1,
        "earth": 0,
        "fire": 0,
        "water": 0,
        "elements": ["Air"],
        "subtypes": ["Mortal"],
    }
    engine.update(engine_overrides)
    return {
        "id": "abc",
        "name": "Apprentice Wizard",
        "slug": "apprentice_wizard",
        "engine": engine,
        "printings": [
            {
                "slug": "999-apprentice_wizard-wk-s",
                "printedAt": "2025-08-01T07:00:00.000Z",
                "set": {"name": "Promo"},
                "meta": {"finish": "Standard", "product": "WelcomeKit", "typeline": "Promo line",
                         "flavor": None, "artist": {"name": "Someone Else"}},
            },
            {
                "slug": "001-apprentice_wizard-b-s",
                "printedAt": "2023-04-19T00:00:00.000Z",
                "set": {"name": "Alpha"},
                "meta": {"finish": "Standard", "product": "Booster", "typeline": "An Ordinary Mortal new to power",
                         "flavor": "Flavor", "artist": {"name": "Ossi Hiekkala"}},
            },
            {
                "slug": "001-apprentice_wizard-b-f",
                "printedAt": "2023-04-19T00:00:00.000Z",
                "set": {"name": "Alpha"},
                "meta": {"finish": "Foil", "product": "Booster", "typeline": "An Ordinary Mortal new to power",
                         "flavor": "Flavor", "artist": {"name": "Ossi Hiekkala"}},
            },
        ],
    }


def test_maps_engine_to_guardian():
    card = to_legacy_card(_new_format_card())
    assert card["name"] == "Apprentice Wizard"
    assert card["guardian"] == {
        "type": "Minion",
        "rarity": "Ordinary",
        "cost": 3,
        "attack": 1,
        "defence": 1,
        "life": None,
        "rulesText": "Spellcaster\r\nGenesis → Draw a spell.",
        "thresholds": {"air": 1, "earth": 0, "fire": 0, "water": 0},
    }
    assert card["elements"] == "Air"
    assert card["subTypes"] == "Mortal"


def test_groups_printings_into_sets_oldest_first():
    card = to_legacy_card(_new_format_card())
    assert [s["name"] for s in card["sets"]] == ["Alpha", "Promo"]
    alpha = card["sets"][0]
    assert [v["finish"] for v in alpha["variants"]] == ["Standard", "Foil"]
    assert alpha["variants"][0] == {
        "slug": "001-apprentice_wizard-b-s",
        "finish": "Standard",
        "product": "Booster",
        "artist": "Ossi Hiekkala",
        "flavorText": "Flavor",
        "typeText": "An Ordinary Mortal new to power",
    }
    assert card["sets"][1]["variants"][0]["flavorText"] == ""


def test_elements_use_legacy_order_and_none():
    assert to_legacy_card(_new_format_card(elements=["Air", "Earth", "Fire", "Water"]))["elements"] == (
        "Earth, Fire, Water, Air"
    )
    assert to_legacy_card(_new_format_card(elements=["Air", "Water"]))["elements"] == "Water, Air"
    assert to_legacy_card(_new_format_card(elements=["None"]))["elements"] == "None"
    assert to_legacy_card(_new_format_card(elements=[]))["elements"] == "None"


def test_rarity_falls_back_to_slot_then_ordinary():
    assert to_legacy_card(_new_format_card(type="Avatar", rarity=None, slot="Unique"))["guardian"]["rarity"] == "Unique"
    assert to_legacy_card(_new_format_card(rarity=None, slot=None))["guardian"]["rarity"] == "Ordinary"


def test_legacy_card_passes_through():
    legacy = {"name": "Arid Desert", "elements": "Fire", "guardian": {"type": "Site"}, "sets": []}
    assert to_legacy_card(legacy) is legacy
