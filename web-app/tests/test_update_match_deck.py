"""Editing a deck link from the profile Match History.

Past-season games come back from the player page as
match_records_archive.rowid + 1_000_000_000, so saving a deck link on one
must undo that offset and write to the archive, not the live table.
"""

import sqlite3

import pytest

import routes.api.games as games

DECK = "https://sorcerytcg.com/decks/cmwmoypnu014c08jpp9jtiu"


def _make_archive(conn):
    """match_records_archive in the live layout, plus the archive's own column."""
    conn.execute("CREATE TABLE match_records_archive AS SELECT * FROM match_records WHERE 0")
    conn.execute("ALTER TABLE match_records_archive ADD COLUMN original_match_id INTEGER")


def _insert(conn, table, winner, loser):
    cur = conn.execute(
        f"INSERT INTO {table} (winner_id, winner_display_name, losser_id, losser_display_name,"
        " winner_elo_change, loser_elo_change, timestamp, source, match_type)"
        " VALUES (?, 'W', ?, 'L', 16, -16, '2026-11-10T12:00:00', 'Discord', 'ranked')",
        (winner, loser),
    )
    return cur.lastrowid


@pytest.fixture()
def matches(match_db, monkeypatch):
    monkeypatch.setattr(games, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(games.CuriosaService, "fetch_deck_data", lambda self, url: '{"deck": 1}')
    conn = sqlite3.connect(str(match_db))
    _make_archive(conn)
    # Pad the archive so its rowids don't line up with the live table's
    for _ in range(5):
        _insert(conn, "match_records_archive", "someone", "else")
    archived = _insert(conn, "match_records_archive", "other_player", "regular_user_1")
    live = _insert(conn, "match_records", "regular_user_1", "other_player")
    conn.commit()
    conn.close()
    return {"archived": archived, "live": live}


def _row(match_db, table, rowid):
    conn = sqlite3.connect(str(match_db))
    try:
        return conn.execute(
            f"SELECT curiosa_url_winner, curiosa_url_loser, json_deck_data_loser FROM {table} WHERE rowid = ?",
            (rowid,),
        ).fetchone()
    finally:
        conn.close()


def test_saves_deck_link_on_past_season_game(user_session, matches, match_db):
    resp = user_session.put("/api/update-match-deck", json={
        "match_id": matches["archived"] + games.ARCHIVE_ID_OFFSET, "deck_url": DECK, "source": "bot",
    })
    assert resp.status_code == 200, resp.get_json()
    winner_url, loser_url, loser_json = _row(match_db, "match_records_archive", matches["archived"])
    assert loser_url and "cmwmoypnu014c08jpp9jtiu" in loser_url
    assert winner_url is None
    assert loser_json == '{"deck": 1}'


def test_current_season_game_still_saves(user_session, matches, match_db):
    resp = user_session.put("/api/update-match-deck", json={
        "match_id": matches["live"], "deck_url": DECK, "source": "bot",
    })
    assert resp.status_code == 200, resp.get_json()
    winner_url, loser_url, _ = _row(match_db, "match_records", matches["live"])
    assert winner_url and "cmwmoypnu014c08jpp9jtiu" in winner_url
    assert loser_url is None


def test_cannot_edit_someone_elses_past_season_game(user_session, matches, match_db):
    resp = user_session.put("/api/update-match-deck", json={
        "match_id": 1 + games.ARCHIVE_ID_OFFSET, "deck_url": DECK, "source": "bot",
    })
    assert resp.status_code == 403
    assert _row(match_db, "match_records_archive", 1)[1] is None


def test_unknown_past_season_game_is_not_found(user_session, matches):
    resp = user_session.put("/api/update-match-deck", json={
        "match_id": 999 + games.ARCHIVE_ID_OFFSET, "deck_url": DECK, "source": "bot",
    })
    assert resp.status_code == 404
