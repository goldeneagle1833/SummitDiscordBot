"""GET /api/avatars reads only each deck's avatar, and reuses rows until the DB changes."""

import json
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _fresh_rows_cache():
    import routes.api.avatars as avatars
    avatars.reset_rows_cache()
    yield
    avatars.reset_rows_cache()


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}], "spellbook": [{"name": "Fireball", "quantity": 4}]})


def _add(db, winner, loser, w_deck, l_deck):
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO match_records (winner_id, winner_display_name, losser_id, losser_display_name,"
        " timestamp, json_deck_data_winner, json_deck_data_loser, source)"
        " VALUES (?, ?, ?, ?, '2026-09-01 12:00:00', ?, ?, 'Discord')",
        (winner, f"P{winner}", loser, f"P{loser}", w_deck, l_deck),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def avatars_client(monkeypatch, match_db, client):
    import routes.api.avatars as avatars
    monkeypatch.setattr(avatars, "MATCH_RECORDS_DB_PATH", match_db)
    _add(match_db, "1", "2", _deck("Sorcerer"), _deck("Druid"))
    # Broken and avatar-less decks count for nobody
    _add(match_db, "1", "2", "not json", json.dumps({"spellbook": []}))
    return client


def _by_name(data):
    return {a["name"]: (a["wins"], a["losses"]) for a in data}


def test_counts_avatars_from_trimmed_decks(avatars_client):
    data = avatars_client.get("/api/avatars?source=discord").get_json()
    assert _by_name(data) == {"Sorcerer": (1, 0), "Druid": (0, 1)}
    assert data[0]["top_player"]["name"] in ("P1", "P2")


def test_new_match_shows_up_on_next_request(avatars_client, match_db):
    avatars_client.get("/api/avatars?source=discord")
    _add(match_db, "2", "1", _deck("Druid"), _deck("Sorcerer"))
    data = avatars_client.get("/api/avatars?source=discord").get_json()
    assert _by_name(data) == {"Sorcerer": (1, 1), "Druid": (1, 1)}


def test_unchanged_database_is_not_scanned_again(avatars_client, monkeypatch):
    import routes.api.avatars as avatars
    first = avatars_client.get("/api/avatars?source=discord").get_json()
    calls = []
    real = avatars._query_discord_rows_with_players
    monkeypatch.setattr(avatars, "_query_discord_rows_with_players",
                        lambda *a, **k: calls.append(a[1:]) or real(*a, **k))
    assert avatars_client.get("/api/avatars?source=discord").get_json() == first
    assert calls == []
