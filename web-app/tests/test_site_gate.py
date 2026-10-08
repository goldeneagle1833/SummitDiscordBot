"""Tests for utils/site_gate.py: no API data without an API key or site token."""

import time
from unittest.mock import patch

import pytest

import webapp_config
from utils import site_gate
from utils.site_gate import COOKIE_NAME, EXEMPT_ENDPOINTS, HEADER_NAME, issue_site_token

API_KEY = "test-api-key-123"
DRAFT_KEY = "draft-sorcery-key-xyz"

# A handful of routes that are "public" in test_endpoint_auth.py and were the
# kind of thing anyone could scrape before the gate.
SAMPLE_DATA_ROUTES = [
    "/api/status",
    "/api/leaderboard",
    "/api/match-history",
    "/api/avatars",
    "/api/events",
    "/api/streamers",
]


@pytest.fixture()
def gated(app):
    """The shared ``app`` fixture turns the gate off; this turns it on."""
    app.config["SITE_GATE_ENABLED"] = True
    webapp_config.DRAFT_SORCERY_API_KEY = DRAFT_KEY
    yield app.test_client()
    webapp_config.DRAFT_SORCERY_API_KEY = ""


def _same_site(**extra):
    return {"Sec-Fetch-Site": "same-origin", **extra}


class TestRejectsAnonymous:
    @pytest.mark.parametrize("path", SAMPLE_DATA_ROUTES)
    def test_no_key_no_token_is_401(self, gated, path):
        resp = gated.get(path)
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "api_key_required"
        assert "WWW-Authenticate" in resp.headers

    def test_wrong_key_is_401(self, gated):
        resp = gated.get("/api/status", headers={"X-API-Key": "nope"})
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "invalid_api_key"

    def test_garbage_token_is_401(self, gated):
        gated.set_cookie(COOKIE_NAME, "not-a-real-token")
        assert gated.get("/api/status").status_code == 401

    def test_token_signed_with_other_secret_is_401(self, gated):
        with patch.object(webapp_config, "SECRET_KEY", "some-other-secret"):
            forged = issue_site_token()
        gated.set_cookie(COOKIE_NAME, forged)
        assert gated.get("/api/status").status_code == 401

    def test_expired_token_is_401(self, gated):
        token = issue_site_token()
        gated.set_cookie(COOKIE_NAME, token)
        future = time.time() + webapp_config.SITE_TOKEN_MAX_AGE + 60
        with patch("utils.site_gate.time.time", return_value=future), patch(
            "itsdangerous.timed.time.time", return_value=future
        ):
            assert gated.get("/api/status").status_code == 401

    def test_every_gated_route_rejects_anonymous(self, app, gated):
        """Walk the whole URL map: nothing under /api/ answers without credentials."""
        leaks = []
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/") or rule.endpoint in EXEMPT_ENDPOINTS:
                continue
            if "GET" not in rule.methods or rule.arguments:
                continue  # parametrised routes are covered by the before_request hook anyway
            resp = gated.get(rule.rule)
            if resp.status_code != 401 or resp.get_json().get("code") != "api_key_required":
                leaks.append(f"{rule.rule} -> {resp.status_code}")
        assert leaks == [], "Routes reachable without an API key:\n" + "\n".join(leaks)


class TestApiKeyPasses:
    def test_x_api_key_header(self, gated):
        resp = gated.get("/api/status", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200

    def test_bearer_header(self, gated):
        resp = gated.get("/api/status", headers={"Authorization": f"Bearer {API_KEY}"})
        assert resp.status_code == 200

    def test_draft_sorcery_key_also_accepted(self, gated):
        resp = gated.get("/api/status", headers={"X-API-Key": DRAFT_KEY})
        assert resp.status_code == 200

    def test_gate_does_not_replace_per_route_auth(self, gated):
        """A valid key gets through the gate; session-only routes still say no."""
        resp = gated.get("/api/me", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 401
        assert resp.get_json() == {"error": "Not authenticated"}


class TestSiteToken:
    def test_token_endpoint_refuses_cross_site(self, gated):
        resp = gated.get("/api/site-token", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "not_same_site"
        assert COOKIE_NAME not in (resp.headers.get("Set-Cookie") or "")

    def test_token_endpoint_refuses_foreign_origin(self, gated):
        resp = gated.get("/api/site-token", headers={"Origin": "https://evil.example"})
        assert resp.status_code == 401

    def test_token_endpoint_refuses_bare_script(self, gated):
        """curl with no browser headers at all gets nothing."""
        assert gated.get("/api/site-token").status_code == 401

    def test_token_endpoint_accepts_same_origin(self, gated):
        resp = gated.get("/api/site-token", headers=_same_site())
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        cookie = resp.headers["Set-Cookie"]
        assert cookie.startswith(f"{COOKIE_NAME}=")
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Path=/api/" in cookie
        assert resp.headers["Cache-Control"] == "no-store"

    def test_token_endpoint_accepts_configured_host_via_referer(self, gated):
        resp = gated.get(
            "/api/site-token",
            headers={"Referer": "https://www.sorcererssummit.com/leaderboard"},
        )
        assert resp.status_code == 200

    def test_cookie_from_token_endpoint_unlocks_api(self, gated):
        gated.get("/api/site-token", headers=_same_site())  # client keeps the cookie
        for path in SAMPLE_DATA_ROUTES:
            assert gated.get(path).status_code == 200, path

    def test_header_token_also_accepted(self, gated):
        resp = gated.get("/api/status", headers={HEADER_NAME: issue_site_token()})
        assert resp.status_code == 200

    def test_old_token_is_refreshed_on_response(self, gated):
        gated.set_cookie(COOKIE_NAME, issue_site_token())
        later = time.time() + webapp_config.SITE_TOKEN_MAX_AGE * 0.75
        with patch("utils.site_gate.time.time", return_value=later), patch(
            "itsdangerous.timed.time.time", return_value=later
        ):
            resp = gated.get("/api/status")
        assert resp.status_code == 200
        assert (resp.headers.get("Set-Cookie") or "").startswith(f"{COOKIE_NAME}=")

    def test_fresh_token_is_not_refreshed(self, gated):
        gated.set_cookie(COOKIE_NAME, issue_site_token())
        resp = gated.get("/api/status")
        assert resp.status_code == 200
        assert COOKIE_NAME not in (resp.headers.get("Set-Cookie") or "")


class TestExemptions:
    def test_health_is_reachable(self, gated):
        assert gated.get("/api/health").status_code in (200, 503)

    def test_non_api_paths_are_not_gated(self, gated):
        # OAuth entry points live under /auth and must stay reachable.
        resp = gated.get("/auth/discord")
        assert resp.status_code != 401

    def test_exempt_list_is_tiny_and_known(self):
        assert EXEMPT_ENDPOINTS == {
            "api.site_token",
            "api.store.stripe_webhook",
            "api.monitoring.health",
        }

    def test_gate_can_be_disabled_by_config(self, app):
        app.config["SITE_GATE_ENABLED"] = False
        assert app.test_client().get("/api/status").status_code == 200
