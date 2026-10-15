"""Tests for the public Popular Cards API (formerly creator-only)."""

import json
import sqlite3

import pytest


def _deck(*cards):
    return json.dumps({"avatar": [{"name": "Geomancer"}],
                       "spellbook": [{"name": c, "quantity": 2} for c in cards]})


class _EmptyCatalog:
    def get_all_cards(self):
        return []


@pytest.fixture()
def patched(monkeypatch, elo_db, match_db, client):
    import routes.api.creator as creator
    monkeypatch.setattr(creator, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(creator, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(creator, "CardCatalogRepository", _EmptyCatalog)
    monkeypatch.setattr(creator, "_build_card_image_lookup", lambda: {})
    monkeypatch.setattr(creator, "_find_card_image", lambda name, lookup: None)
    creator._cache.clear()

    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) "
                 "VALUES (7, 'Past Season', '2026-03-01', '2026-06-01', 0)")
    conn.execute("INSERT INTO events (event_id, event_name, start_date, end_date, is_active) "
                 "VALUES (9, 'Running Season', '2026-09-01', '2026-12-01', 1)")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE match_records_archive (
            event_id INTEGER, timestamp TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT
        )
    """)
    conn.execute("INSERT INTO match_records (timestamp, json_deck_data_winner, json_deck_data_loser, source) "
                 "VALUES ('2026-09-10 12:00:00', ?, ?, 'Discord')", (_deck("Fireball"), _deck("Frost Bolt")))
    conn.execute("INSERT INTO match_records_archive (event_id, timestamp, json_deck_data_winner, json_deck_data_loser) "
                 "VALUES (7, '2026-04-10 12:00:00', ?, '')", (_deck("Fireball"),))
    conn.commit()
    conn.close()
    yield client
    creator._cache.clear()


def test_open_without_login(patched):
    cards = patched.get("/api/creator/popular-cards").get_json()
    by_name = {c["name"]: c for c in cards}
    assert by_name["Fireball"]["decks_with_card"] == 2
    assert by_name["Fireball"]["total_decks"] == 3
    assert by_name["Frost Bolt"]["decks_with_card"] == 1


def test_running_season_hidden_from_public(patched):
    events = patched.get("/api/creator/filters").get_json()["events"]
    assert 9 not in [e["event_id"] for e in events]
    assert patched.get("/api/creator/popular-cards?event=current").status_code == 403
    assert patched.get("/api/creator/popular-cards?event=9").status_code == 403


def test_admin_can_see_running_season(patched, admin_session):
    events = patched.get("/api/creator/filters").get_json()["events"]
    assert 9 in [e["event_id"] for e in events]
    cards = patched.get("/api/creator/popular-cards?event=current").get_json()
    assert {c["name"] for c in cards} >= {"Fireball", "Frost Bolt"}


def test_past_event_only_counts_that_event(patched):
    cards = patched.get("/api/creator/popular-cards?event=7").get_json()
    assert [c["name"] for c in cards if c["name"] != "Geomancer"] == ["Fireball"]


def test_card_history_by_month(patched):
    rows = patched.get("/api/creator/card-history?card=Fireball").get_json()
    assert rows == [
        {"month": "2026-04", "total_decks": 1, "decks_with_card": 1, "percent_of_decks": 100.0},
        {"month": "2026-09", "total_decks": 2, "decks_with_card": 1, "percent_of_decks": 50.0},
    ]
