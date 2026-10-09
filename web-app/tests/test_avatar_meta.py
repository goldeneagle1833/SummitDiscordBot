"""Tests for GET /api/elements/avatar-meta (Elements page Meta chart)."""

import json
import sqlite3

import pytest


def _deck(avatar):
    return json.dumps({"avatar": [{"name": avatar}]})


@pytest.fixture()
def patched(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)

    conn = sqlite3.connect(str(match_db))
    conn.execute("""
        CREATE TABLE match_records_archive (
            event_id INTEGER,
            timestamp TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT
        )
    """)
    live = [
        ("2026-09-01 12:00:00", _deck("Sorcerer"), _deck("Druid"), "Discord"),
        ("2026-09-03 18:30:00", _deck("Sorcerer"), "{}", "Discord"),
        # Paper/web matches are not part of the online meta
        ("2026-09-03 19:00:00", _deck("Druid"), _deck("Druid"), "Paper"),
        # Unparseable timestamp is skipped
        ("not a date", _deck("Druid"), _deck("Druid"), "Discord"),
    ]
    for ts, w, l, src in live:
        conn.execute(
            "INSERT INTO match_records (timestamp, json_deck_data_winner, json_deck_data_loser, source) "
            "VALUES (?, ?, ?, ?)", (ts, w, l, src),
        )
    conn.execute(
        "INSERT INTO match_records_archive (event_id, timestamp, json_deck_data_winner, json_deck_data_loser) "
        "VALUES (7, '2026-08-30 10:00:00', ?, ?)", (_deck("Geomancer"), _deck("Sorcerer")),
    )
    conn.commit()
    conn.close()
    return client


def test_counts_each_deck_by_day_across_live_and_archive(patched):
    data = patched.get("/api/elements/avatar-meta").get_json()
    assert data["dates"] == ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]
    assert data["avatars"] == {
        "Sorcerer": {"2026-08-30": 1, "2026-09-01": 1, "2026-09-03": 1},
        "Druid": {"2026-09-01": 1},
        "Geomancer": {"2026-08-30": 1},
    }
    assert data["daily_totals"] == {"2026-08-30": 2, "2026-09-01": 2, "2026-09-03": 1}


def test_public_without_login(patched):
    assert patched.get("/api/elements/avatar-meta").status_code == 200


def test_empty_database(monkeypatch, match_db, client):
    import routes.api.cards as cards
    monkeypatch.setattr(cards, "MATCH_RECORDS_DB_PATH", match_db)
    data = client.get("/api/elements/avatar-meta").get_json()
    assert data == {"dates": [], "avatars": {}, "daily_totals": {}}
