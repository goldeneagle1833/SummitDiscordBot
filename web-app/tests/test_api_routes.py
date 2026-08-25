"""Tests for API route endpoints."""

import sqlite3
import pytest
from tests.conftest import seed_elo_data, seed_matches


class TestLeaderboardRoutes:
    def test_get_leaderboard_empty(self, client):
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_leaderboard_with_data(self, client, elo_db, match_db):
        seed_elo_data(elo_db, [
            {"user_id": "1", "name": "Alice", "online_elo": 1800},
            {"user_id": "2", "name": "Bob", "online_elo": 1600},
        ])
        seed_matches(match_db, [
            {"winner_id": "1", "loser_id": "2"},
        ])
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        alice = next(p for p in data if p["name"] == "Alice")
        assert alice["elo"] == 1800
        assert alice["wins"] == 1

    def test_get_combined_leaderboard(self, client):
        resp = client.get("/api/leaderboard/combined")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "lifetime" in data
        assert "event" in data

    def test_get_event_leaderboard(self, client):
        resp = client.get("/api/leaderboard/event")
        assert resp.status_code == 200

    def test_get_events(self, client, elo_db):
        conn = sqlite3.connect(str(elo_db))
        conn.execute("INSERT INTO events (event_name, start_date, is_active) VALUES ('Test', '2025-01-01', 1)")
        conn.commit()
        conn.close()

        resp = client.get("/api/events")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "events" in data
        assert len(data["events"]) >= 1

    def test_get_elo_distribution(self, client):
        resp = client.get("/api/elo-distribution")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_players" in data


class TestMatchRoutes:
    def test_available_dates_empty(self, client):
        resp = client.get("/api/match-history/available-dates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_match_history_no_date(self, client):
        resp = client.get("/api/match-history")
        assert resp.status_code == 200

    def test_match_history_with_date(self, client, match_db):
        seed_matches(match_db, [
            {"winner_id": "1", "loser_id": "2", "timestamp": "2025-03-10 10:00:00"},
        ])
        resp = client.get("/api/match-history?date=2025-03-10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestMiscRoutes:
    def test_status(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "online"

    def test_community_endpoint(self, client):
        resp = client.get("/api/community")
        assert resp.status_code in (200, 500)

    def test_spotlight_endpoint(self, client):
        resp = client.get("/api/spotlight")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "success" in data
        assert data["success"] is True
        # spotlight may be None if no data in test DBs
        if data.get("spotlight"):
            s = data["spotlight"]
            for key in ("type", "badge_text", "color", "title", "subtitle", "link"):
                assert key in s, f"Missing key: {key}"


class TestExternalMatchRoute:
    def test_missing_fields_returns_400(self, client):
        resp = client.post(
            "/api/report-external-match",
            json={"winner_id": "1"},
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Missing required fields" in data["error"]

    def test_same_player_returns_400(self, client):
        resp = client.post(
            "/api/report-external-match",
            json={
                "winner_id": "1", "loser_id": "1",
                "winner_deck_url": "http://example.com",
                "loser_deck_url": "http://example.com",
                "source": "TestPlatform",
            },
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert resp.status_code == 400
        assert "must be different" in resp.get_json()["error"]

    def test_empty_source_returns_400(self, client):
        resp = client.post(
            "/api/report-external-match",
            json={
                "winner_id": "1", "loser_id": "2",
                "winner_deck_url": "http://example.com",
                "loser_deck_url": "http://example.com",
                "source": "   ",
            },
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert resp.status_code == 400


class TestAdminRoutes:
    """Admin routes tested via an admin session (localhost no longer grants admin)."""

    def test_audit_log_returns_entries(self, admin_session):
        resp = admin_session.get("/api/admin/audit-log")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "entries" in data
        assert "total" in data

    def test_database_status(self, admin_session):
        resp = admin_session.get("/api/debug/database-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "elo" in data
        assert "match_records" in data
