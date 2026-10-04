"""A bracket game's top cut note shows on both players' match history."""

import sqlite3

import pytest

import routes.api.players as players_routes


@pytest.fixture
def top_cut_match(match_db, elo_db, monkeypatch):
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change,
            losser_id, losser_display_name, loser_elo_change,
            timestamp, match_type, source, match_comment, reporter_id)
           VALUES ('100', 'Alice', 0, '200', 'Bob', 0, '2026-10-03T12:00:00',
                   'ranked', 'Bracket', 'Top cut game - Test Cup - Final', 'admin')"""
    )
    conn.commit()
    conn.close()


@pytest.mark.parametrize("player_id", ["100", "200"])
def test_both_players_see_the_top_cut_note(client, top_cut_match, player_id):
    resp = client.get(f"/api/player/{player_id}")
    assert resp.status_code == 200
    [match] = resp.get_json()["matches"]
    assert match["match_comment"] == "Top cut game - Test Cup - Final"
    assert match["elo_change"] == 0
