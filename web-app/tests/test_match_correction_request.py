"""Correct button on the profile match history: POST /api/match-report/request-correction."""

import sqlite3
from datetime import datetime
from unittest.mock import patch

URL = "/api/match-report/request-correction"
ME, OPP = "111111111111111111", "222222222222222222"


def _match(db, winner=ME, loser=OPP):
    conn = sqlite3.connect(str(db))
    cur = conn.execute(
        "INSERT INTO match_records (winner_id, winner_display_name, losser_id, losser_display_name, timestamp) "
        "VALUES (?, 'Me', ?, 'Opp', ?)",
        (winner, loser, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def _login(client, user_id=ME, provider="discord"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Me"
        sess["auth_provider"] = provider
    return client


def test_needs_login(client):
    assert client.post(URL, json={"match_id": 1}).status_code == 401


def test_sends_to_the_bot_and_reports_back(client, match_db):
    mid = _match(match_db)
    _login(client)
    with patch("routes.api.matchmaking.relay_to_bot",
               return_value=({"status": "sent", "other_player_name": "Opp"}, 200)) as relay:
        r = client.post(URL, json={"match_id": mid})
    assert r.status_code == 200, r.get_json()
    assert "Opp" in r.get_json()["message"]
    method, path, payload = relay.call_args[0][:3]
    assert (method, path) == ("POST", "/match-correction-request")
    assert payload == {"match_id": mid, "requester_id": ME, "requester_name": "Me"}


def test_the_loser_can_ask_too(client, match_db):
    mid = _match(match_db, winner=OPP, loser=ME)
    _login(client)
    with patch("routes.api.matchmaking.relay_to_bot", return_value=({"status": "sent_to_channel"}, 200)):
        assert client.post(URL, json={"match_id": mid}).status_code == 200


def test_only_players_in_the_match(client, match_db):
    mid = _match(match_db)
    _login(client, user_id="333333333333333333")
    with patch("routes.api.matchmaking.relay_to_bot") as relay:
        assert client.post(URL, json={"match_id": mid}).status_code == 403
        relay.assert_not_called()


def test_bad_or_old_match_ids(client, match_db):
    _login(client)
    with patch("routes.api.matchmaking.relay_to_bot") as relay:
        assert client.post(URL, json={}).status_code == 400
        assert client.post(URL, json={"match_id": 1_000_000_005}).status_code == 400
        assert client.post(URL, json={"match_id": 999}).status_code == 404
        relay.assert_not_called()


def test_google_login_cannot(client, match_db):
    mid = _match(match_db)
    _login(client, provider="google")
    assert client.post(URL, json={"match_id": mid}).status_code == 403


def test_bot_answers_are_passed_on(client, match_db):
    mid = _match(match_db)
    _login(client)
    cases = [
        ({"status": "already_pending", "message": "already waiting"}, 200, 409),
        ({"status": "cannot_dm", "message": "DMs off"}, 200, 422),
        ({"status": "unavailable"}, 503, 503),
    ]
    for body, bot_status, expected in cases:
        with patch("routes.api.matchmaking.relay_to_bot", return_value=(body, bot_status)):
            r = client.post(URL, json={"match_id": mid})
        assert r.status_code == expected, body
        assert r.get_json()["success"] is False
