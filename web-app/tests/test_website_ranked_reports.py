"""Ranked games reported with the website's "Report a Game" button.

Paper ELO is gone: once the opponent confirms, a ranked website report is
handed to the bot and recorded on the main ranked ladder, the same as a
Discord queue game, whether the players log in with Discord, Google or
email. Casual website games stay website records with no rating change.
"""

import sqlite3
from unittest.mock import Mock, patch

import pytest

from services import summit_player_numbers as numbers

DISCORD = "123456789012345678"
OTHER_DISCORD = "223456789012345678"
GOOGLE = "google_108234567890123456789"
FIRST_NUMBER = "1000000000000001"


@pytest.fixture(autouse=True)
def fresh_numbers():
    numbers.clear_cache()
    yield
    numbers.clear_cache()


def _profile(match_db, user_id, provider, name):
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        """INSERT INTO user_profiles (user_id, provider, display_name, email, email_verified,
                                      first_login_at, last_login_at)
           VALUES (?, ?, ?, ?, 1, '2026-11-01', '2026-11-01')""",
        (user_id, provider, name, f"{name.lower()}@example.com"),
    )
    conn.commit()
    conn.close()


def _login(client, user_id, provider="discord"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Player"
        sess["auth_provider"] = provider


def _submit(client, opponent, match_type="ranked"):
    resp = client.post("/api/match-report/submit", json={
        "opponent_user_id": opponent,
        "result": "won",
        "went_first": "submitter",
        "final_life_submitter": 0,
        "final_life_opponent": 0,
        "match_type": match_type,
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["confirmation_id"]


def _bot_recorded(match_id=701):
    upstream = Mock(status_code=200)
    upstream.json.return_value = {"recorded": True, "duplicate": False, "match_id": match_id}
    return upstream


def _paper_rows(elo_db):
    conn = sqlite3.connect(str(elo_db))
    try:
        return conn.execute("SELECT COUNT(*) FROM paper_standings").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _web_records(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM match_reports_web")]
    finally:
        conn.close()


def test_confirmed_ranked_website_report_goes_on_the_ranked_ladder(client, match_db, elo_db):
    _profile(match_db, DISCORD, "discord", "Dee")
    _profile(match_db, OTHER_DISCORD, "discord", "Oh")
    _login(client, DISCORD)
    confirmation_id = _submit(client, OTHER_DISCORD)

    _login(client, OTHER_DISCORD)
    with patch("routes.api.matchmaking.requests.request", return_value=_bot_recorded()) as req:
        resp = client.post(f"/api/match-report/confirm/{confirmation_id}", json={})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["pipeline"] == "bot"
    assert resp.get_json()["match_id"] == 701
    method, url = req.call_args.args[:2]
    assert (method, url) == ("POST", "http://127.0.0.1:8765/standalone-results")
    sent = req.call_args.kwargs["json"]
    assert sent["report_key"] == confirmation_id
    assert (sent["winner_id"], sent["loser_id"]) == (DISCORD, OTHER_DISCORD)
    assert sent["winner_went_first"] is True
    assert sent["played_on"] == "the Summit website"
    assert sent["match_comment"] == "Reported on the Summit website"
    assert _web_records(match_db) == []  # the bot records it, not a Paper record
    assert _paper_rows(elo_db) == 0


def test_google_login_ranked_report_is_recorded_under_its_player_number(client, match_db, elo_db):
    _profile(match_db, GOOGLE, "google", "Gee")
    _profile(match_db, DISCORD, "discord", "Dee")
    _login(client, GOOGLE, "google")
    confirmation_id = _submit(client, DISCORD)

    _login(client, DISCORD)
    with patch("routes.api.matchmaking.requests.request", return_value=_bot_recorded()) as req:
        resp = client.post(f"/api/match-report/confirm/{confirmation_id}", json={})

    assert resp.status_code == 200, resp.get_json()
    sent = req.call_args.kwargs["json"]
    assert sent["winner_id"] == FIRST_NUMBER
    assert sent["loser_id"] == DISCORD
    assert _paper_rows(elo_db) == 0


def _real_web_records_table(match_db):
    """match_reports_web as the live database has it (migrations/create_match_reports_web.py
    plus the later season and lifetime-rating columns)."""
    conn = sqlite3.connect(str(match_db))
    conn.execute("DROP TABLE IF EXISTS match_reports_web")
    conn.execute("""
        CREATE TABLE match_reports_web (
            match_id TEXT PRIMARY KEY, reporter_id TEXT,
            winner_id TEXT NOT NULL, losser_id TEXT NOT NULL,
            winner_display_name TEXT NOT NULL, losser_display_name TEXT NOT NULL,
            did_win INTEGER NOT NULL, timestamp TEXT NOT NULL,
            first_player TEXT, match_time INTEGER, match_comment TEXT,
            curiosa_url TEXT, curiosa_url_winner TEXT, curiosa_url_loser TEXT,
            json_deck_data TEXT, json_deck_data_winner TEXT, json_deck_data_loser TEXT,
            winner_elo_change INTEGER, loser_elo_change INTEGER,
            winner_went_first TEXT, loser_went_first TEXT,
            source TEXT DEFAULT 'Web', match_type TEXT DEFAULT 'ranked',
            season_id INTEGER DEFAULT NULL,
            winner_lifetime_elo_after INTEGER, loser_lifetime_elo_after INTEGER
        )""")
    conn.commit()
    conn.close()


def test_casual_website_report_stays_a_website_record_with_no_rating(client, match_db, elo_db):
    _real_web_records_table(match_db)
    _profile(match_db, DISCORD, "discord", "Dee")
    _profile(match_db, OTHER_DISCORD, "discord", "Oh")
    _login(client, DISCORD)
    confirmation_id = _submit(client, OTHER_DISCORD, match_type="casual")

    _login(client, OTHER_DISCORD)
    with patch("routes.api.matchmaking.requests.request") as req, \
            patch("services.curiosa.CuriosaService.fetch_deck_data", return_value="{}"):
        resp = client.post(f"/api/match-report/confirm/{confirmation_id}", json={})

    assert resp.status_code == 200, resp.get_json()
    req.assert_not_called()
    [record] = _web_records(match_db)
    assert record["match_type"] == "casual"
    assert (record["winner_elo_change"], record["loser_elo_change"]) == (0, 0)
    assert _paper_rows(elo_db) == 0
