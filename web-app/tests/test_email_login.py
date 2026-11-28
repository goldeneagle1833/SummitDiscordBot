"""Email-code sign-in: no Discord or Google, just a code sent to the player's email."""

import re
import sqlite3
from unittest.mock import patch

import pytest

from services import summit_player_numbers as numbers

HEADERS = {"X-API-Key": "test-api-key-123"}


@pytest.fixture(autouse=True)
def fresh_numbers():
    numbers.clear_cache()
    yield
    numbers.clear_cache()


@pytest.fixture()
def outbox():
    sent = []
    with patch("services.meta_report.email_configured", return_value=True), \
         patch("services.meta_report.send_email", side_effect=lambda to, subject, text, html=None: sent.append((to, text))):
        yield sent


def _code(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1][1]).group(1)


def _start(client, email="gee@example.com"):
    return client.post("/auth/email/start", json={"email": email, "next": "/store"})


def _verify(client, code, email="gee@example.com"):
    return client.post("/auth/email/verify", json={"email": email, "code": code})


def _profile(match_db, user_id, provider, email, name="Player"):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO user_profiles (user_id, provider, display_name, email, email_verified,
                                      first_login_at, last_login_at)
           VALUES (?, ?, ?, ?, 1, '2026-11-01', '2026-11-01')""",
        (user_id, provider, name, email),
    )
    conn.commit()
    conn.close()


def test_new_email_player_signs_in_with_a_player_number(client, match_db, outbox):
    resp = _start(client, " Gee@Example.com ")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["email"] == "gee@example.com"
    assert outbox[0][0] == "gee@example.com"

    resp = _verify(client, _code(outbox))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["redirect"] == "/store"
    with client.session_transaction() as sess:
        assert sess["user_id"] == "1000000000000001"
        assert sess["auth_provider"] == "email"
        assert sess["username"] == "Player 0001"

    me = client.get("/api/me").get_json()
    assert me["user_id"] == "1000000000000001" and me["auth_provider"] == "email"

    # PSO finds them by email, and the same person signing in again keeps the number
    found = client.post("/api/partner/summit-account", json={"email": "gee@example.com"}, headers=HEADERS).get_json()
    assert (found["summit_user_id"], found["login"]) == ("1000000000000001", "email")
    client.get("/auth/logout")
    _start(client)
    _verify(client, _code(outbox))
    with client.session_transaction() as sess:
        assert sess["user_id"] == "1000000000000001"


def test_email_player_games_can_be_reported(client, match_db, outbox):
    _start(client)
    _verify(client, _code(outbox))
    resp = client.post("/api/report-external-match", headers=HEADERS, json={
        "winner_id": "gee@example.com", "loser_id": "123456789012345678",
        "winner_deck_url": "", "loser_deck_url": "", "source": "PSO Ranked",
    })
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["winner"]["user_id"] == "1000000000000001"


def test_email_of_an_existing_google_login_signs_into_that_account(client, match_db, outbox):
    _profile(match_db, "google_108234567890123456789", "google", "gee@example.com", name="Gee")
    _start(client)
    assert _verify(client, _code(outbox)).status_code == 200
    with client.session_transaction() as sess:
        assert sess["user_id"] == "google_108234567890123456789"
        assert sess["auth_provider"] == "google"
        assert sess["username"] == "Gee"


def test_email_of_an_existing_discord_login_signs_into_that_account(client, match_db, outbox):
    _profile(match_db, "123456789012345678", "discord", "gee@example.com", name="Dee")
    _start(client)
    assert _verify(client, _code(outbox)).status_code == 200
    with client.session_transaction() as sess:
        assert sess["user_id"] == 123456789012345678
        assert sess["auth_provider"] == "discord"


def test_admin_discord_account_is_refused(client, match_db, outbox, monkeypatch):
    import webapp_config
    monkeypatch.setattr(webapp_config, "ADMINS", ["123456789012345678"])
    _profile(match_db, "123456789012345678", "discord", "boss@example.com")
    _start(client, "boss@example.com")
    resp = _verify(client, _code(outbox), "boss@example.com")
    assert resp.status_code == 403
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_wrong_codes_run_out(client, match_db, outbox):
    _start(client)
    good = _code(outbox)
    bad = "000000" if good != "000000" else "111111"
    messages = [_verify(client, bad).get_json()["error"] for _ in range(5)]
    assert messages[0] == "That code isn't right. 4 tries left."
    assert messages[3] == "That code isn't right. 1 try left."
    assert messages[4] == "That code has expired. Ask for a new one."
    assert _verify(client, good).status_code == 400  # used up


def test_only_the_newest_code_works_and_only_once(client, match_db, outbox):
    _start(client)
    first = _code(outbox)
    _start(client)
    second = _code(outbox)
    if first != second:
        assert _verify(client, first).status_code == 400
    assert _verify(client, second).status_code == 200
    client.get("/auth/logout")
    assert _verify(client, second).status_code == 400


def test_codes_per_email_are_limited(client, match_db, outbox):
    for _ in range(5):
        assert _start(client).status_code == 200
    resp = _start(client)
    assert resp.status_code == 429
    assert len(outbox) == 5


def test_bad_email_and_switched_off_email(client, match_db):
    assert _start(client, "not-an-email").status_code == 400
    with patch("services.meta_report.email_configured", return_value=False):
        resp = _start(client)
    assert resp.status_code == 503
    assert "Discord or Google" in resp.get_json()["error"]
