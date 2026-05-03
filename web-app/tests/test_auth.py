"""Tests for authentication and authorization utilities."""

from unittest.mock import patch
import pytest


class TestStatusEndpoint:
    def test_status_returns_online(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "online"


class TestMeEndpoint:
    def test_me_unauthenticated(self, client):
        resp = client.get("/api/me")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "error" in data

    def test_me_authenticated(self, user_session):
        resp = user_session.get("/api/me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "regular_user_1"
        assert data["username"] == "RegularUser"

    def test_me_admin_flag(self, admin_session):
        resp = admin_session.get("/api/me")
        data = resp.get_json()
        assert data["is_admin"] is True

    def test_me_non_admin_flag(self, user_session):
        resp = user_session.get("/api/me")
        data = resp.get_json()
        assert data["is_admin"] is False


class TestLogout:
    def test_logout_clears_session(self, user_session):
        # Verify logged in
        resp = user_session.get("/api/me")
        assert resp.status_code == 200

        # Logout
        resp = user_session.get("/api/logout")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        # Verify logged out
        resp = user_session.get("/api/me")
        assert resp.status_code == 401


class TestAdminAccess:
    """Admin access tests.

    Note: Flask test client runs from 127.0.0.1, which is_admin() treats as
    admin. We patch request.remote_addr to test non-localhost behavior.
    """

    def test_admin_audit_log_requires_admin(self, app):
        """Non-admin user from non-localhost should be denied."""
        with app.test_request_context(
            "/api/admin/audit-log",
            environ_base={"REMOTE_ADDR": "203.0.113.1"},
            headers={"Host": "example.com"},
        ):
            from flask import session as flask_session
            flask_session["user_id"] = "regular_user_1"

            from utils.auth import is_admin
            assert is_admin() is False

    def test_admin_allows_admin_user_from_remote(self, app):
        """Admin user from remote should be allowed."""
        with app.test_request_context():
            from flask import session as flask_session
            flask_session["user_id"] = "admin_user_1"

            with patch("utils.auth.request") as mock_req:
                mock_req.remote_addr = "203.0.113.1"
                mock_req.host = "example.com"
                mock_req.headers = {}

                from utils.auth import is_admin
                assert is_admin() is True

    def test_admin_audit_log_allowed_for_admin(self, admin_session):
        resp = admin_session.get("/api/admin/audit-log")
        assert resp.status_code == 200

    def test_admin_endpoint_with_api_key(self, client):
        resp = client.get(
            "/api/admin/audit-log",
            headers={"X-API-Key": "test-api-key-123"},
        )
        assert resp.status_code == 200

    def test_admin_denies_no_key_from_remote(self, app):
        """No API key and no session from remote should be denied."""
        with app.test_request_context():
            with patch("utils.auth.request") as mock_req:
                mock_req.remote_addr = "203.0.113.1"
                mock_req.host = "example.com"
                mock_req.headers = {}

                from utils.auth import is_admin
                assert is_admin() is False

    def test_localhost_is_always_admin(self, app):
        """Localhost requests always get admin access."""
        with app.test_request_context():
            with patch("utils.auth.request") as mock_req:
                mock_req.remote_addr = "127.0.0.1"
                mock_req.host = "localhost:5000"
                mock_req.headers = {}

                from utils.auth import is_admin
                assert is_admin() is True


class TestApiKeyAuth:
    def test_external_match_requires_api_key(self, client):
        resp = client.post("/api/report-external-match", json={})
        assert resp.status_code == 401

    def test_external_match_accepts_api_key(self, client):
        resp = client.post(
            "/api/report-external-match",
            json={},
            headers={"X-API-Key": "test-api-key-123"},
        )
        # Should be 400 (missing fields) not 401 (unauthorized)
        assert resp.status_code == 400

    def test_external_match_accepts_bearer_token(self, client):
        resp = client.post(
            "/api/report-external-match",
            json={},
            headers={"Authorization": "Bearer test-api-key-123"},
        )
        assert resp.status_code == 400  # past auth, hit validation


class TestCurioEditor:
    def test_curio_editor_check(self, app):
        """Curio editors get curio access but not admin."""
        with app.test_request_context(
            "/api/curios/",
            environ_base={"REMOTE_ADDR": "203.0.113.1"},
            headers={"Host": "example.com"},
        ):
            from flask import session as flask_session
            flask_session["user_id"] = "editor_1"

            from utils.auth import is_curio_editor, is_admin
            assert is_admin() is False
            assert is_curio_editor() is True
