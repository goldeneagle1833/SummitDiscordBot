from unittest.mock import Mock, patch

import requests
import webapp_config


def test_matchmaking_relay_requires_partner_api_key(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    response = client.get("/api/matchmaking/users/123/status")
    assert response.status_code == 401


def test_matchmaking_relay_forwards_status_with_timeout(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"membership": "member", "queues": [], "result": None}
    with patch("routes.api.matchmaking.requests.request", return_value=upstream) as request_mock:
        response = client.get(
            "/api/matchmaking/users/123/status",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 200
    assert response.get_json()["membership"] == "member"
    assert request_mock.call_args.kwargs["timeout"] == 9.0
    assert request_mock.call_args.kwargs["headers"] == {"X-API-Key": "partner-test-key"}


def test_matchmaking_relay_reports_bot_unavailable(client, caplog):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    with patch("routes.api.matchmaking.requests.request", side_effect=requests.ConnectionError("offline")):
        response = client.get(
            "/api/matchmaking/users/123/status",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 503
    assert response.get_json()["membership"] == "unavailable"
    assert "method=GET path=/users/123/status" in caplog.text
    assert "offline" in caplog.text


def test_matchmaking_relay_logs_bot_error_body(client, caplog):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    upstream = Mock(status_code=500, text="match transaction failed")
    with patch("routes.api.matchmaking.requests.request", return_value=upstream):
        response = client.get(
            "/api/matchmaking/users/123/status",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 503
    assert response.get_json()["membership"] == "unavailable"
    assert "match transaction failed" in caplog.text


def test_matchmaking_relay_forwards_idempotent_result(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"recorded": True, "duplicate": False, "match_id": 42}
    payload = {
        "queue_type": "ranked",
        "reporter_id": "10",
        "winner_id": "10",
        "loser_id": "20",
    }
    with patch("routes.api.matchmaking.requests.request", return_value=upstream) as request_mock:
        response = client.post(
            "/api/matchmaking/matches/1/2/results",
            headers={"X-API-Key": "partner-test-key"},
            json=payload,
        )
    assert response.status_code == 200
    assert response.get_json()["match_id"] == 42
    assert request_mock.call_args.args[:2] == (
        "POST",
        "http://127.0.0.1:8765/matches/1/2/results",
    )
    assert request_mock.call_args.kwargs["json"] == payload


def test_voice_relay_requires_partner_api_key(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    response = client.get("/api/matchmaking/voice?user_ids=10,20")
    assert response.status_code == 401


def test_voice_relay_forwards_repeated_user_ids(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    upstream = Mock(status_code=200)
    upstream.json.return_value = {
        "status": "together",
        "channel": {"name": "The Dungeon", "spectator_count": 6},
        "players": [],
    }
    with patch("routes.api.matchmaking.requests.request", return_value=upstream) as request_mock:
        response = client.get(
            "/api/matchmaking/voice?user_ids=10&user_ids=20",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 200
    assert response.get_json()["channel"]["spectator_count"] == 6
    assert request_mock.call_args.args[:2] == (
        "GET",
        "http://127.0.0.1:8765/voice?user_ids=10%2C20",
    )


def test_voice_relay_reports_bot_unavailable(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    with patch("routes.api.matchmaking.requests.request", side_effect=requests.ConnectionError("offline")):
        response = client.get(
            "/api/matchmaking/voice?user_ids=10,20",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable", "channel": None, "players": []}


def test_voice_relay_passes_through_bad_request(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    upstream = Mock(status_code=400, text="'abc' is not a Discord user id")
    upstream.json.side_effect = ValueError
    with patch("routes.api.matchmaking.requests.request", return_value=upstream):
        response = client.get(
            "/api/matchmaking/voice?user_ids=abc",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 400
    assert "not a Discord user id" in response.get_json()["error"]
