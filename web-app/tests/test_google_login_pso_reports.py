"""Google logins in Play Sorcery Online reports, and PSO games on the ranked ladder.

A Google login gets a Summit player number (16 digits, never a Discord id)
the first time a game is reported for it. PSO finds the id to report with by
email. Standalone PSO Ranked reports wait out the dispute window, then the
bot records them like a queued ranked game instead of Paper ELO.
"""

import json
import sqlite3
import time
from unittest.mock import Mock, patch

import pytest

from services import summit_player_numbers as numbers
from utils.player_ids import is_summit_player_number

HEADERS = {"X-API-Key": "test-api-key-123"}
GOOGLE = "google_108234567890123456789"
DISCORD = "123456789012345678"
FIRST_NUMBER = "1000000000000001"


@pytest.fixture(autouse=True)
def fresh_numbers():
    numbers.clear_cache()
    yield
    numbers.clear_cache()


def _profile(match_db, user_id, provider, email, *, verified=1, name="Player"):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO user_profiles (user_id, provider, display_name, email, email_verified,
                                      first_login_at, last_login_at)
           VALUES (?, ?, ?, ?, ?, '2026-11-01', '2026-11-01')""",
        (user_id, provider, name, email, verified),
    )
    conn.commit()
    conn.close()


def _confirmations(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM match_confirmations ORDER BY id")]
    except sqlite3.OperationalError:
        return []  # nothing was ever held
    finally:
        conn.close()


def _report(client, **overrides):
    body = {
        "winner_id": "gplayer@example.com",
        "loser_id": DISCORD,
        "winner_deck_url": "https://curiosa.io/decks/a",
        "loser_deck_url": "https://curiosa.io/decks/b",
        "source": "PSO Ranked",
        "winner_went_first": True,
    }
    body.update(overrides)
    return client.post("/api/report-external-match", json=body, headers=HEADERS)


def _bot_recorded(match_id=501, duplicate=False):
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"recorded": not duplicate, "duplicate": duplicate, "match_id": match_id}
    return upstream


# ── player numbers ───────────────────────────────────────────────────────


def test_number_range_never_overlaps_discord_ids():
    assert is_summit_player_number(FIRST_NUMBER)
    assert not is_summit_player_number(DISCORD)  # 18-digit Discord id
    assert not is_summit_player_number("81384788765712384")  # one of Discord's first users
    assert not is_summit_player_number("google_1")


def test_numbers_are_stable_and_map_both_ways(app, match_db):
    first = numbers.number_for_google(GOOGLE, create=True)
    assert str(first) == FIRST_NUMBER
    assert numbers.number_for_google(GOOGLE, create=True) == first
    assert numbers.number_for_google("google_999", create=True) == first + 1
    numbers.clear_cache()
    assert numbers.google_for_number(FIRST_NUMBER) == GOOGLE
    assert numbers.bot_player_id(GOOGLE) == FIRST_NUMBER
    assert numbers.account_id(FIRST_NUMBER) == GOOGLE
    assert numbers.same_player(GOOGLE, FIRST_NUMBER)
    assert not numbers.same_player(DISCORD, FIRST_NUMBER)


def test_google_login_without_a_number_keeps_the_old_bare_id(app, match_db):
    assert numbers.bot_player_id("google_555") == "555"
    assert numbers.bot_player_id(DISCORD) == DISCORD


# ── PSO account lookup ───────────────────────────────────────────────────


def test_lookup_finds_google_login_and_gives_it_a_number(client, match_db):
    _profile(match_db, GOOGLE, "google", "GPlayer@Example.com", name="Gee")
    resp = client.post("/api/partner/summit-account", json={"email": "gplayer@example.com "}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["found"] is True
    assert body["login"] == "google"
    assert body["summit_user_id"] == FIRST_NUMBER
    assert body["display_name"] == "Gee"
    assert body["profile_url"].endswith(f"/player/{FIRST_NUMBER}")
    again = client.post("/api/partner/summit-account", json={"email": "gplayer@example.com"}, headers=HEADERS)
    assert again.get_json()["summit_user_id"] == FIRST_NUMBER


def test_lookup_prefers_the_discord_login_for_a_shared_email(client, match_db):
    _profile(match_db, GOOGLE, "google", "both@example.com")
    _profile(match_db, DISCORD, "discord", "both@example.com")
    body = client.post("/api/partner/summit-account", json={"email": "both@example.com"}, headers=HEADERS).get_json()
    assert body["login"] == "discord"
    assert body["summit_user_id"] == DISCORD


def test_lookup_ignores_unverified_and_unknown_emails(client, match_db):
    _profile(match_db, GOOGLE, "google", "unverified@example.com", verified=0)
    for email in ("unverified@example.com", "nobody@example.com"):
        body = client.post("/api/partner/summit-account", json={"email": email}, headers=HEADERS).get_json()
        assert body == {"success": True, "found": False}


def test_lookup_needs_key_and_email(client, match_db):
    assert client.post("/api/partner/summit-account", json={"email": "a@b.c"}).status_code == 401
    assert client.post("/api/partner/summit-account", json={"email": "nope"}, headers=HEADERS).status_code == 400
    assert client.post("/api/partner/summit-account", json={}, headers=HEADERS).status_code == 400


# ── reports naming Google logins ─────────────────────────────────────────


def test_report_by_email_is_held_under_the_player_number(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com", name="Gee")
    resp = _report(client, players=[
        {"player_id": "gplayer@example.com", "playedCards": ["Spire"]},
        {"player_id": DISCORD, "playedCards": ["Lava Salamander"]},
    ])
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["pipeline"] == "pso_ranked"
    [held] = _confirmations(match_db)
    assert held["winner_discord_id"] == FIRST_NUMBER
    assert held["loser_discord_id"] == DISCORD
    assert held["status"] == "pending"
    assert json.loads(held["played_cards"]) == {FIRST_NUMBER: ["Spire"], DISCORD: ["Lava Salamander"]}


def test_report_by_google_id_or_number_works_too(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com")
    assert _report(client, winner_id=GOOGLE).status_code == 200
    assert _report(client, winner_id="223456789012345678", loser_id=FIRST_NUMBER).status_code == 200
    ids = [(c["winner_discord_id"], c["loser_discord_id"]) for c in _confirmations(match_db)]
    assert ids == [(FIRST_NUMBER, DISCORD), ("223456789012345678", FIRST_NUMBER)]


def test_unknown_email_or_number_is_refused_not_filed_as_a_new_player(client, match_db):
    resp = _report(client, winner_id="ghost@example.com")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "UNKNOWN_PLAYER"
    assert _report(client, winner_id="1000000000000999").status_code == 404
    assert _report(client, winner_id="google_404").status_code == 404
    assert _confirmations(match_db) == []


def test_discord_reports_are_unchanged(client, match_db):
    resp = _report(client, winner_id="223456789012345678")
    assert resp.status_code == 200
    [held] = _confirmations(match_db)
    assert held["winner_discord_id"] == "223456789012345678"


# ── recording on the ranked ladder ───────────────────────────────────────


def _expire(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE match_confirmations SET expires_at = ?", (int(time.time()) - 60,))
    conn.commit()
    conn.close()


def _paper_rows(match_db, elo_db):
    conn = sqlite3.connect(str(elo_db))
    try:
        return conn.execute("SELECT COUNT(*) FROM paper_standings").fetchone()[0]
    finally:
        conn.close()


def test_auto_confirm_hands_the_game_to_the_bot_not_paper_elo(client, match_db, elo_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com", name="Gee")
    _report(client)
    [held] = _confirmations(match_db)
    _expire(match_db)

    with patch("routes.api.matchmaking.requests.request", return_value=_bot_recorded()) as req:
        resp = client.post(f"/api/match-report/auto-confirm/{held['id']}", headers=HEADERS)

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["pipeline"] == "bot"
    assert body["match_id"] == 501
    method, url = req.call_args.args[:2]
    assert (method, url) == ("POST", "http://127.0.0.1:8765/standalone-results")
    sent = req.call_args.kwargs["json"]
    assert sent["report_key"] == held["id"]
    assert sent["winner_id"] == FIRST_NUMBER
    assert sent["loser_id"] == DISCORD
    assert sent["winner_name"] == "Gee"
    assert sent["winner_went_first"] is True
    assert _confirmations(match_db)[0]["status"] == "auto_confirmed"
    assert _paper_rows(match_db, elo_db) == 0


def test_bot_down_leaves_the_report_pending_for_a_retry(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com")
    _report(client)
    [held] = _confirmations(match_db)
    _expire(match_db)
    upstream = Mock(status_code=409)
    upstream.json.return_value = {"error": "Match result could not be recorded"}
    with patch("routes.api.matchmaking.requests.request", return_value=upstream):
        resp = client.post(f"/api/match-report/auto-confirm/{held['id']}", headers=HEADERS)
    assert resp.status_code == 500
    assert _confirmations(match_db)[0]["status"] == "pending"


def test_unknown_turn_order_is_not_recorded_as_winner_first(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com")
    body = {"winner_id": DISCORD, "loser_id": "gplayer@example.com"}
    resp = client.post("/api/report-external-match", headers=HEADERS, json={
        **body, "winner_deck_url": "", "loser_deck_url": "", "source": "PSO Ranked",
    })
    assert resp.status_code == 200, resp.get_json()
    [held] = _confirmations(match_db)
    assert held["went_first"] is None
    _expire(match_db)
    with patch("routes.api.matchmaking.requests.request", return_value=_bot_recorded()) as req:
        client.post(f"/api/match-report/auto-confirm/{held['id']}", headers=HEADERS)
    assert req.call_args.kwargs["json"]["winner_went_first"] is None


def test_google_login_confirms_its_own_report_on_the_website(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com")
    _report(client, winner_id=DISCORD, loser_id="gplayer@example.com")
    [held] = _confirmations(match_db)
    assert held["opponent_discord_id"] == FIRST_NUMBER
    with client.session_transaction() as sess:
        sess["user_id"] = GOOGLE
        sess["username"] = "Gee"
        sess["auth_provider"] = "google"

    pending = client.get("/api/match-report/pending")
    assert pending.status_code == 200, pending.get_json()
    assert [c["id"] for c in pending.get_json()["pending_confirmations"]] == [held["id"]]

    with patch("routes.api.matchmaking.requests.request", return_value=_bot_recorded(612)):
        resp = client.post(f"/api/match-report/confirm/{held['id']}", json={})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["match_id"] == 612
    assert _confirmations(match_db)[0]["status"] == "confirmed"


# ── profiles ─────────────────────────────────────────────────────────────


def _bot_layout_match_records(match_db):
    """match_records as the bot creates it: INTEGER player ids (plus the web columns)."""
    conn = sqlite3.connect(str(match_db))
    conn.execute("DROP TABLE match_records")
    conn.execute("""
        CREATE TABLE match_records (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER, winner_id INTEGER, winner_display_name TEXT,
            losser_id INTEGER, losser_display_name TEXT, did_win BOOLEAN,
            timestamp TEXT, first_player TEXT, match_time INTEGER, curiosa_url TEXT,
            match_comment TEXT, json_deck_data TEXT, winner_elo_change INTEGER,
            loser_elo_change INTEGER, curiosa_url_winner TEXT, curiosa_url_loser TEXT,
            json_deck_data_winner TEXT, json_deck_data_loser TEXT, winner_went_first TEXT,
            loser_went_first TEXT, winner_lifetime_elo_after INTEGER,
            loser_lifetime_elo_after INTEGER, source TEXT DEFAULT 'Discord',
            match_type TEXT DEFAULT 'ranked'
        )""")
    conn.execute(
        """INSERT INTO match_records (reporter_id, winner_id, winner_display_name, losser_id,
               losser_display_name, did_win, timestamp, winner_elo_change, loser_elo_change,
               source, match_type)
           VALUES (?, ?, 'Gee', ?, 'Dee', 1, '2026-11-27T12:00:00', 16, -16, 'PSO Ranked', 'ranked')""",
        (int(FIRST_NUMBER), int(FIRST_NUMBER), int(DISCORD)),
    )
    conn.commit()
    conn.close()


def test_google_login_profile_shows_its_ranked_games(client, match_db):
    _profile(match_db, GOOGLE, "google", "gplayer@example.com", name="Gee")
    numbers.number_for_google(GOOGLE, create=True)
    _bot_layout_match_records(match_db)

    for player_url in (GOOGLE, FIRST_NUMBER):
        resp = client.get(f"/api/player/{player_url}?source=bot")
        assert resp.status_code == 200, (player_url, resp.get_json())
        assert "Dee" in json.dumps(resp.get_json()), player_url
