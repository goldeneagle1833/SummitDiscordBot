"""Card page Match Stats (/api/card/<name>) read from the shared card tally."""

import json
import sqlite3

import pytest


def _deck(spellbook=(), atlas=(), sideboard=(), wrap=False):
    deck = {"avatar": [{"name": "Geomancer"}],
            "spellbook": [{"name": c, "quantity": 2} for c in spellbook],
            "atlas": [{"name": c, "quantity": 1} for c in atlas],
            "sideboard": [{"name": c, "quantity": 1} for c in sideboard]}
    return json.dumps([deck] if wrap else deck)


class _Catalog:
    def get_card(self, name):
        if name == "Grievous Insult":
            return {"name": name, "elements": "Fire", "card_type": "Magic", "rarity": "Ordinary",
                    "sets_json": "[]", "cost": 2, "attack": None, "defence": None, "rules_text": "x"}
        return None


@pytest.fixture()
def cards_client(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(cards, "CardCatalogRepository", _Catalog)
    monkeypatch.setattr(cards, "_build_card_image_lookup", lambda: {})

    conn = sqlite3.connect(str(match_db))
    for table in ("match_records_archive", "season_match_records"):
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM match_records WHERE 0")
    rows = [
        ("match_records", _deck(["Grievous Insult"]), _deck(["Fireball"])),
        # Counted once per deck even when it is in two sections
        ("match_records", _deck(["Fireball"], sideboard=["Grievous Insult", "Fireball"]),
         _deck(["Grievous Insult"], atlas=["Grievous Insult"])),
        ("match_records_archive", _deck(["Grievous Insult"], wrap=True), ""),
        ("season_match_records", "{}", _deck(atlas=["Grievous Insult"])),
        ("season_match_records", "not json", _deck(["Fireball"])),
    ]
    for table, winner, loser in rows:
        conn.execute(f"INSERT INTO {table} (timestamp, json_deck_data_winner, json_deck_data_loser) "
                     "VALUES ('2026-11-01T12:00:00', ?, ?)", (winner, loser))
    conn.commit()
    conn.close()
    return client


def test_tally_matches_old_rules(cards_client):
    body = cards_client.get("/api/card/Grievous%20Insult").get_json()
    assert (body["wins"], body["losses"], body["total_matches"]) == (3, 2, 5)
    assert body["win_rate"] == 60.0
    assert body["element"] == "Fire"

    fireball = cards_client.get("/api/card/Fireball").get_json()
    assert (fireball["wins"], fireball["losses"]) == (1, 2)


def test_unknown_card_is_404(cards_client):
    assert cards_client.get("/api/card/Nope").status_code == 404


def test_tally_is_shared_and_not_rebuilt_per_visit(cards_client, match_db, monkeypatch):
    import routes.api.cards as cards
    cards_client.get("/api/card/Fireball")

    builds = []
    real_build = cards._build_card_match_tally
    monkeypatch.setattr(cards, "_build_card_match_tally", lambda: builds.append(1) or real_build())

    # A new worker (empty memory) reads the saved file instead of rebuilding.
    cards._card_tally_cache.clear()
    body = cards_client.get("/api/card/Fireball").get_json()
    assert builds == []
    assert (body["wins"], body["losses"]) == (1, 2)
