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


@pytest.fixture
def archived_top_cut_match(match_db, elo_db, monkeypatch):
    """A bracket game as it is logged now: in the archive, not the season."""
    from repositories.matches import MatchRepository

    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    MatchRepository(db_path=match_db).insert_match(
        {
            "event_id": 7, "source": "Bracket", "match_type": "ranked",
            "winner_id": "100", "winner_display_name": "Alice",
            "losser_id": "200", "losser_display_name": "Bob",
            "winner_elo_change": 0, "loser_elo_change": 0,
            "timestamp": "2026-10-03 12:00:00", "reporter_id": "admin",
            "match_comment": "Top cut game - Test Cup - Final",
        },
        table="match_records_archive",
    )


def test_an_archived_top_cut_game_is_in_lifetime_history(client, archived_top_cut_match):
    [match] = client.get("/api/player/200").get_json()["matches"]
    assert match["match_comment"] == "Top cut game - Test Cup - Final"
    assert match["result"] == "Loss"


def test_an_archived_top_cut_game_is_not_in_the_current_season(
    client, archived_top_cut_match, match_db
):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO match_records
           (winner_id, winner_display_name, winner_elo_change,
            losser_id, losser_display_name, loser_elo_change, timestamp, match_type)
           VALUES ('100', 'Alice', 16, '300', 'Cara', -16, '2026-10-04T12:00:00', 'ranked')"""
    )
    conn.commit()
    conn.close()

    current = client.get("/api/player/100?event=current").get_json()["matches"]
    lifetime = client.get("/api/player/100").get_json()["matches"]

    assert [m["opponent"] for m in current] == ["Cara"]
    assert sorted(m["opponent"] for m in lifetime) == ["Bob", "Cara"]
