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


def test_matchmaking_relay_reports_bot_unavailable(client):
    webapp_config.DRAFT_SORCERY_API_KEY = "partner-test-key"
    with patch("routes.api.matchmaking.requests.request", side_effect=requests.ConnectionError("offline")):
        response = client.get(
            "/api/matchmaking/users/123/status",
            headers={"X-API-Key": "partner-test-key"},
        )
    assert response.status_code == 503
    assert response.get_json()["membership"] == "unavailable"
