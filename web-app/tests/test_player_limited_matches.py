"""Limited tab: recent Limited matches carry the same details as Match History."""

import json
import sqlite3

import pytest

import repositories.limited_repo as limited_repo
import routes.api.players as players_routes
import webapp_config

ME, OPP = "100", "200"


def _deck(avatar, elements="Fire"):
    return json.dumps({
        "avatar": [{"name": avatar, "type": "Avatar"}],
        "spellbook": [{"name": "Card", "elements": elements}],
    })


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    """Real Limited table layout from limited_repo.create_limited_tables()."""
    elo_db = tmp_path / "elo.db"
    match_db = tmp_path / "match_records.db"
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(players_routes, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(players_routes, "MATCH_RECORDS_DB_PATH", match_db)
    limited_repo.create_limited_tables()
    limited_repo.create_limited_archive_tables()

    conn = sqlite3.connect(str(match_db))
    # Arena runs: the deck JSON lives on the run, not on the match
    conn.execute(
        """INSERT INTO limited_arena_runs (run_id, user_id, user_display_name, deck_url,
               json_deck_data, wins, losses, status, created_at)
           VALUES (1, ?, 'Me', 'https://curiosa.io/decks/mine', ?, 1, 1, 'active', '2026-11-20')""",
        (int(ME), _deck("Sparkmage", "Fire")),
    )
    conn.execute(
        """INSERT INTO limited_arena_runs (run_id, user_id, user_display_name, deck_url,
               json_deck_data, wins, losses, status, created_at)
           VALUES (2, ?, 'Opp', 'https://curiosa.io/decks/theirs', ?, 1, 1, 'active', '2026-11-20')""",
        (int(OPP), _deck("Geomancer", "Earth")),
    )
    rows = [
        # winner, loser, winner_went_first, loser_went_first, reporter, comment, time
        (ME, OPP, "y", "n", ME, "good game | Opponent: gg | Winner deck: x | Loser deck: y", 25),
        (OPP, ME, "n", "n", 999, "Admin reported limited match", 0),
    ]
    for i, (w, l, wf, lf, rep, comment, mt) in enumerate(rows, start=1):
        conn.execute(
            """INSERT INTO limited_match_records
               (match_id, reporter_id, winner_id, winner_display_name, loser_id, loser_display_name,
                did_win, timestamp, first_player, match_time, curiosa_url_winner, curiosa_url_loser,
                match_comment, json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change, winner_went_first, loser_went_first,
                winner_run_id, loser_run_id)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'y', ?, ?, ?, ?, '{}', '{}', 17, -15, ?, ?, ?, ?)""",
            (
                i, int(rep), int(w), "Me" if w == ME else "Opp", int(l), "Me" if l == ME else "Opp",
                f"2026-11-2{i}T12:00:00", mt,
                f"https://curiosa.io/decks/{'mine' if w == ME else 'theirs'}",
                f"https://curiosa.io/decks/{'mine' if l == ME else 'theirs'}",
                comment, wf, lf, 1 if w == ME else 2, 1 if l == ME else 2,
            ),
        )
    conn.commit()
    conn.close()
    return elo_db, match_db


def _matches(**kw):
    return {m["match_id"]: m for m in players_routes._get_limited_stats(ME, **kw)["recent_matches"]}


def test_owner_sees_match_history_details(dbs):
    m = _matches(is_owner=True)
    win, loss = m[1], m[2]
    assert win["result"] == "Win" and loss["result"] == "Loss"
    assert win["opponent"] == "Opp" and win["opponent_id"] == OPP
    assert win["elo_change"] == 17 and loss["elo_change"] == -15
    assert win["match_type"] == "limited"
    # Avatars and elements come from the arena run decks
    assert win["player_avatar"] == "Sparkmage" and win["deck_elements"] == ["Fire"]
    assert win["opponent_avatar"] == "Geomancer" and win["opponent_elements"] == ["Earth"]
    assert win["first_player"] == "Play"
    assert loss["first_player"] is None  # admin report: both "n" means unknown
    assert win["match_time"] == 25 and loss["match_time"] is None
    assert win["player_deck_url"] == "https://curiosa.io/decks/mine"
    assert win["has_deck_json"] is True
    assert win["match_comment"] == "good game"  # own half only, deck tail stripped
    assert loss["match_comment"] is None
    assert win["match_source"] == "limited"
    assert "voice" not in win and "replay_url" not in win
    # Old fields kept
    assert win["winner_id"] == ME and win["winner_elo_change"] == 17


def test_visitor_follows_profile_privacy(dbs):
    hidden = _matches(is_owner=False, visibility={})
    assert hidden[1]["player_deck_url"] is None
    assert hidden[1]["has_deck_json"] is False
    assert hidden[1]["match_comment"] is None
    assert hidden[1]["match_source"] is None
    shown = _matches(is_owner=False, visibility={"deck_urls": True, "deck_snapshots": True})
    assert shown[1]["player_deck_url"] == "https://curiosa.io/decks/mine"
    assert shown[1]["has_deck_json"] is True


def test_archived_matches_are_read_only(dbs):
    _, match_db = dbs
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO limited_match_records_archive
           (event_id, original_match_id, reporter_id, winner_id, winner_display_name, loser_id,
            loser_display_name, timestamp, winner_elo_change, loser_elo_change,
            json_deck_data_winner, json_deck_data_loser, winner_run_id, loser_run_id)
           VALUES (1, 1, 100, 100, 'Me', 200, 'Opp', '2026-01-01T00:00:00', 10, -10, ?, '{}', 1, 2)""",
        (_deck("Pathfinder", "Air"),),
    )
    conn.commit()
    conn.close()
    stats = players_routes._get_limited_stats(ME, "lifetime", is_owner=True)
    archived = [m for m in stats["recent_matches"] if m["archived"]]
    assert len(archived) == 1
    a = archived[0]
    assert a["player_avatar"] == "Pathfinder"
    # Archived run ids can repeat, so the live run's deck is never borrowed
    assert a["opponent_avatar"] is None
    assert a["match_source"] is None
    assert a["has_deck_json"] is False


def test_limited_snapshot_uses_run_deck(dbs):
    snap = players_routes._limited_deck_snapshot(1, ME)
    assert snap["result"] == "Win"
    assert snap["deck"]["avatar"][0]["name"] == "Sparkmage"
    assert players_routes._limited_deck_snapshot(1, "999") == {"error": "Player not found in this match"}
    assert players_routes._limited_deck_snapshot(42, ME) is None


@pytest.fixture()
def me_client(client, dbs, monkeypatch):
    import routes.api.match_reporting as mr
    _, match_db = dbs
    monkeypatch.setattr(mr, "MATCH_RECORDS_DB_PATH", match_db)
    with client.session_transaction() as s:
        s["user_id"] = ME
    return client, match_db


def _row(match_db, match_id):
    conn = sqlite3.connect(str(match_db))
    row = conn.execute(
        "SELECT match_time, match_comment FROM limited_match_records WHERE match_id = ?", (match_id,)
    ).fetchone()
    conn.close()
    return row


def test_owner_edits_limited_time_and_note(me_client):
    c, match_db = me_client
    r = c.post("/api/match-report/edit-match-time", json={"match_id": 1, "match_source": "limited", "match_time": 40})
    assert r.status_code == 200, r.get_json()
    assert _row(match_db, 1)[0] == 40
    r = c.post("/api/match-report/edit-comment", json={"match_id": 1, "match_source": "limited", "new_comment": "close one"})
    assert r.status_code == 200, r.get_json()
    # Opponent's half and the bot's deck tail are kept
    assert _row(match_db, 1)[1] == "close one | Opponent: gg | Winner deck: x | Loser deck: y"


def test_cannot_edit_someone_elses_limited_game(me_client, dbs):
    c, match_db = me_client
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO limited_match_records (match_id, winner_id, loser_id, match_time) VALUES (9, 300, 400, 5)"
    )
    conn.commit()
    conn.close()
    r = c.post("/api/match-report/edit-match-time", json={"match_id": 9, "match_source": "limited", "match_time": 40})
    assert r.status_code == 403
    assert _row(match_db, 9)[0] == 5
