"""Voice flag on player profile match history."""

import sqlite3

import pytest

import routes.api.players as players_routes


@pytest.fixture
def voice_matches(match_db, elo_db, monkeypatch):
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(players_routes, "VOICE_TRACKING_STARTED", "2026-09-21T14:22:34")
    conn = sqlite3.connect(str(match_db))
    conn.execute("ALTER TABLE match_records ADD COLUMN voice INTEGER NOT NULL DEFAULT 0")
    for timestamp, voice in [
        ("2026-09-10T12:00:00", 0),  # before tracking: every game was voice
        ("2026-09-22T12:00:00", 1),
        ("2026-09-22T13:00:00", 0),
    ]:
        conn.execute(
            """INSERT INTO match_records
               (winner_id, winner_display_name, winner_elo_change,
                losser_id, losser_display_name, loser_elo_change,
                timestamp, match_type, voice)
               VALUES ('100', 'Alice', 16, '200', 'Bob', -16, ?, 'ranked', ?)""",
            (timestamp, voice),
        )
    conn.commit()
    conn.close()


def test_match_history_reports_voice(client, voice_matches):
    resp = client.get("/api/player/100")
    assert resp.status_code == 200
    by_date = {m["date"]: m["voice"] for m in resp.get_json()["matches"]}
    assert by_date == {
        "2026-09-10T12:00:00": True,
        "2026-09-22T12:00:00": True,
        "2026-09-22T13:00:00": False,
    }
