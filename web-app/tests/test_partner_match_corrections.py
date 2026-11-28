"""Partner (Play Sorcery Online) match corrections: POST/GET /api/partner/correct-match."""

import sqlite3
from datetime import datetime

KEY = {"X-API-Key": "test-api-key-123"}
URL = "/api/partner/correct-match"
WIN, LOSE, OTHER = "111111111111111111", "222222222222222222", "333333333333333333"


def _add_pairing_column(db):
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    if "pairing_id" not in cols:
        conn.execute("ALTER TABLE match_records ADD COLUMN pairing_id INTEGER")
    conn.commit()
    conn.close()


def _match(db, winner=WIN, loser=LOSE, pairing_id=None):
    _add_pairing_column(db)
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        "INSERT INTO match_records (winner_id, winner_display_name, losser_id, losser_display_name, "
        "timestamp, match_type, pairing_id) VALUES (?, 'Winner', ?, 'Loser', ?, 'ranked', ?)",
        (winner, loser, datetime.now().isoformat(), pairing_id),
    )
    mid = cur.lastrowid  # the match ID is the rowid, as in production
    conn.commit()
    conn.close()
    return mid


def _flips(db):
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT match_id, target_id, requested_by_id, requested_by_name, status FROM moderation_match_flips"
    ).fetchall()
    conn.close()
    return rows


def test_needs_the_api_key(client):
    assert client.post(URL, json={"match_id": 1, "winner_id": LOSE}).status_code == 401
    assert client.get(f"{URL}/1").status_code == 401


def test_queues_a_flip_by_match_id(client, match_db):
    mid = _match(match_db)
    r = client.post(URL, json={"match_id": mid, "winner_id": LOSE, "reason": "Disconnect bug"}, headers=KEY)
    assert r.status_code == 202, r.get_json()
    body = r.get_json()
    assert body["status"] == "queued" and body["match_id"] == mid
    assert _flips(match_db) == [(mid, LOSE, "sorcery-online", "Play Sorcery Online", "pending")]

    # Status check
    s = client.get(f"{URL}/{body['request_id']}", headers=KEY).get_json()
    assert s["status"] == "queued" and s["match_id"] == mid

    # Sending it again doesn't queue a second flip
    again = client.post(URL, json={"match_id": mid, "winner_id": LOSE}, headers=KEY)
    assert again.status_code == 202 and again.get_json()["request_id"] == body["request_id"]
    assert len(_flips(match_db)) == 1


def test_by_pairing_id(client, match_db):
    mid = _match(match_db, pairing_id=77)
    r = client.post(URL, json={"pairing_id": 77, "winner_id": LOSE}, headers=KEY)
    assert r.status_code == 202 and r.get_json()["match_id"] == mid


def test_already_correct_changes_nothing(client, match_db):
    mid = _match(match_db)
    r = client.post(URL, json={"match_id": mid, "winner_id": WIN}, headers=KEY)
    assert r.status_code == 200 and r.get_json()["status"] == "already_correct"
    assert _flips(match_db) == []


def test_conflicting_request_while_one_is_queued(client, match_db):
    mid = _match(match_db)
    client.post(URL, json={"match_id": mid, "winner_id": LOSE}, headers=KEY)
    r = client.post(URL, json={"match_id": mid, "winner_id": WIN}, headers=KEY)
    assert r.status_code == 409


def test_unknown_match_or_player_not_in_it(client, match_db):
    mid = _match(match_db)
    assert client.post(URL, json={"match_id": mid + 50, "winner_id": LOSE}, headers=KEY).status_code == 404
    assert client.post(URL, json={"match_id": mid, "winner_id": OTHER}, headers=KEY).status_code == 404
    assert client.post(URL, json={"pairing_id": 999, "winner_id": LOSE}, headers=KEY).status_code == 404
    assert _flips(match_db) == []


def test_pairing_with_two_matches_needs_match_id(client, match_db):
    _match(match_db, pairing_id=5)
    _match(match_db, pairing_id=5)
    r = client.post(URL, json={"pairing_id": 5, "winner_id": LOSE}, headers=KEY)
    assert r.status_code == 409 and len(r.get_json()["match_ids"]) == 2


def test_validation(client, match_db):
    assert client.post(URL, data="nope", headers=KEY).status_code == 400
    assert client.post(URL, json={"match_id": 1}, headers=KEY).status_code == 400
    assert client.post(URL, json={"winner_id": LOSE}, headers=KEY).status_code == 400
    assert client.post(URL, json={"match_id": "abc", "winner_id": LOSE}, headers=KEY).status_code == 400


def test_status_only_shows_partner_requests(client, admin_session, match_db):
    mid = _match(match_db)
    admin_session.post(f"/api/mod/players/{WIN}/flip-matches", json={"match_ids": [mid], "confirm": True})
    assert client.get(f"{URL}/1", headers=KEY).status_code == 404


def test_works_with_the_production_match_records_layout(tmp_path):
    """Production's match_records has no match_id column and INTEGER player IDs."""
    from repositories.mod_record_repo import ModRequestsRepository

    db = tmp_path / "prod_layout.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE match_records (reporter_id INTEGER, winner_id INTEGER, winner_display_name TEXT, "
        "losser_id INTEGER, losser_display_name TEXT, timestamp TEXT, match_type TEXT, "
        "source TEXT, pairing_id INTEGER)"
    )
    conn.execute(
        "INSERT INTO match_records (winner_id, losser_id, timestamp, match_type, pairing_id) "
        "VALUES (?, ?, ?, 'ranked', 9)",
        (int(WIN), int(LOSE), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    repo = ModRequestsRepository(db)
    [m] = repo.find_match("match_records", pairing_id=9)
    assert m["id"] == 1 and m["winner_id"] == WIN and m["loser_id"] == LOSE
    assert repo.find_match("match_records", match_id=1)[0]["pairing_id"] == 9


# ── Corrections and repeats sent to /api/report-external-match ──────────

REPORT = "/api/report-external-match"


def _add_replay_column(db):
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    if "replay_url" not in cols:
        conn.execute("ALTER TABLE match_records ADD COLUMN replay_url TEXT")
    conn.commit()
    conn.close()


def _set_replay(db, mid, url):
    _add_replay_column(db)
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE match_records SET replay_url = ? WHERE rowid = ?", (url, mid))
    conn.commit()
    conn.close()


def _external_rows(db):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT winner_id, loser_id FROM external_matches").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _report(**over):
    body = {"winner_id": LOSE, "loser_id": WIN, "winner_deck_url": "", "loser_deck_url": "",
            "source": "Sorcery Online"}
    body.update(over)
    return body


def test_correction_flag_on_the_report_link_corrects_the_recorded_match(client, match_db):
    _add_replay_column(match_db)
    mid = _match(match_db, pairing_id=41)
    r = client.post(REPORT, json=_report(correction=True, pairing_id=41), headers=KEY)
    assert r.status_code == 202, r.get_json()
    assert r.get_json()["pipeline"] == "correction" and r.get_json()["match_id"] == mid
    assert _flips(match_db) == [(mid, LOSE, "sorcery-online", "Play Sorcery Online", "pending")]
    assert _external_rows(match_db) == []


def test_correction_action_without_ids_uses_the_latest_match_between_them(client, match_db):
    _add_replay_column(match_db)
    _match(match_db)
    newest = _match(match_db)
    r = client.post(REPORT, json={"action": "correct_match", "winner_id": LOSE, "loser_id": WIN}, headers=KEY)
    assert r.status_code == 202 and r.get_json()["match_id"] == newest
    assert _external_rows(match_db) == []


def test_repeat_report_of_a_recorded_game_is_not_an_external_match(client, match_db):
    mid = _match(match_db)
    _set_replay(match_db, mid, "https://playsorceryonline.com/replay/abc")
    r = client.post(REPORT, json=_report(winner_id=WIN, loser_id=LOSE,
                                         replay_url="https://playsorceryonline.com/replay/abc"), headers=KEY)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["duplicate"] is True and r.get_json()["match_id"] == mid
    assert _external_rows(match_db) == [] and _flips(match_db) == []


def test_report_of_a_recorded_game_with_the_other_winner_corrects_it(client, match_db):
    mid = _match(match_db)
    _set_replay(match_db, mid, "https://playsorceryonline.com/replay/xyz")
    r = client.post(REPORT, json=_report(replay_url="https://playsorceryonline.com/replay/xyz"), headers=KEY)
    assert r.status_code == 202 and r.get_json()["match_id"] == mid
    assert _external_rows(match_db) == [] and len(_flips(match_db)) == 1


def test_a_new_game_between_the_same_players_is_still_external(client, match_db):
    from unittest.mock import patch
    mid = _match(match_db)
    _set_replay(match_db, mid, "https://playsorceryonline.com/replay/old")
    with patch("services.external_match.ExternalMatchService.report_match",
               return_value={"report_id": 1}) as report:
        r = client.post(REPORT, json=_report(replay_url="https://playsorceryonline.com/replay/new",
                                             match_time=1795718282), headers=KEY)
    assert r.status_code == 200 and r.get_json()["pipeline"] == "external"
    # A timestamp sent as the game length is dropped
    assert report.call_args.kwargs["match_time"] is None
    assert _flips(match_db) == []


def test_partner_endpoint_accepts_a_replay_link(client, match_db):
    mid = _match(match_db)
    _set_replay(match_db, mid, "https://playsorceryonline.com/replay/r1")
    r = client.post(URL, json={"replay_url": "https://playsorceryonline.com/replay/r1", "winner_id": LOSE}, headers=KEY)
    assert r.status_code == 202 and r.get_json()["match_id"] == mid
