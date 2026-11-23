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
