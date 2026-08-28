"""External match reports for Summit-queued games go through the bot pipeline."""

import sqlite3
from unittest.mock import Mock, patch

import requests
import webapp_config

HEADERS = {"X-API-Key": "test-api-key-123"}


def _seed_pairing(db_path, *, guild_id=1, p1=10, p2=20, status="active",
                  match_type="ranked", created_at="2026-08-27T10:00:00", limited=False):
    conn = sqlite3.connect(str(db_path))
    if limited:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS limited_active_pairings (
                pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL, player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL, player1_deck_url TEXT, player2_deck_url TEXT,
                player1_run_id INTEGER, player2_run_id INTEGER,
                created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active')"""
        )
        cur = conn.execute(
            """INSERT INTO limited_active_pairings
               (guild_id, player1_id, player2_id, created_at, status)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, p1, p2, created_at, status),
        )
    else:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS active_pairings (
                pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL, player1_id INTEGER NOT NULL,
                player2_id INTEGER NOT NULL, player1_deck_url TEXT, player2_deck_url TEXT,
                created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                match_type TEXT DEFAULT 'ranked')"""
        )
        cur = conn.execute(
            """INSERT INTO active_pairings
               (guild_id, player1_id, player2_id, created_at, status, match_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, p1, p2, created_at, status, match_type),
        )
    pairing_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pairing_id


def _external_rows(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT winner_id, loser_id, source FROM external_matches").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _payload(**overrides):
    base = {
        "winner_id": "10",
        "loser_id": "20",
        "winner_deck_url": "https://curiosa.io/decks/a",
        "loser_deck_url": "https://curiosa.io/decks/b",
        "source": "Sorcery Online",
    }
    base.update(overrides)
    return base


def _bot_ok(match_id=77, duplicate=False):
    upstream = Mock(status_code=200)
    upstream.json.return_value = {
        "recorded": not duplicate, "duplicate": duplicate,
        "match_id": None if duplicate else match_id,
    }
    return upstream


class TestSummitPairedResultsUseBotPipeline:
    def test_active_pairing_is_relayed_to_bot_not_external_table(self, client, match_db):
        pairing_id = _seed_pairing(match_db)
        with patch("routes.api.matchmaking.requests.request", return_value=_bot_ok()) as req, \
             patch("routes.api.external_matches.ExternalMatchService") as service:
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)

        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["success"] is True
        assert body["pipeline"] == "bot"
        assert body["match_id"] == 77
        assert body["pairing_id"] == pairing_id
        service.assert_not_called()
        assert _external_rows(match_db) == []

        method, url = req.call_args.args[:2]
        assert (method, url) == ("POST", f"http://127.0.0.1:8765/matches/1/{pairing_id}/results")
        sent = req.call_args.kwargs["json"]
        assert sent["queue_type"] == "ranked"
        assert sent["outcome"] == "decided"
        assert sent["winner_id"] == "10"
        assert sent["loser_id"] == "20"
        assert sent["reporter_id"] == "10"  # defaults to the winner

    def test_reversed_player_order_still_matches_pairing(self, client, match_db):
        _seed_pairing(match_db, p1=20, p2=10)
        with patch("routes.api.matchmaking.requests.request", return_value=_bot_ok()) as req:
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["pipeline"] == "bot"
        assert req.call_args.kwargs["json"]["winner_id"] == "10"

    def test_limited_pairing_uses_limited_queue_type(self, client, match_db):
        pairing_id = _seed_pairing(match_db, limited=True)
        with patch("routes.api.matchmaking.requests.request", return_value=_bot_ok()) as req:
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["queue_type"] == "limited"
        assert req.call_args.args[1].endswith(f"/matches/1/{pairing_id}/results")
        assert req.call_args.kwargs["json"]["queue_type"] == "limited"

    def test_explicit_pairing_id_is_used(self, client, match_db):
        older = _seed_pairing(match_db, created_at="2026-08-27T09:00:00", match_type="testing")
        _seed_pairing(match_db, created_at="2026-08-27T11:00:00")
        with patch("routes.api.matchmaking.requests.request", return_value=_bot_ok()) as req:
            resp = client.post(
                "/api/report-external-match",
                json=_payload(pairing_id=older, reporter_id="20"),
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert req.call_args.args[1].endswith(f"/matches/1/{older}/results")
        assert req.call_args.kwargs["json"]["queue_type"] == "testing"
        assert req.call_args.kwargs["json"]["reporter_id"] == "20"

    def test_duplicate_from_bot_is_success_without_external_row(self, client, match_db):
        _seed_pairing(match_db)
        with patch("routes.api.matchmaking.requests.request", return_value=_bot_ok(duplicate=True)):
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["pipeline"] == "bot"
        assert body["duplicate"] is True
        assert _external_rows(match_db) == []

    def test_bot_unavailable_returns_503_and_does_not_fall_back(self, client, match_db):
        _seed_pairing(match_db)
        with patch(
            "routes.api.matchmaking.requests.request",
            side_effect=requests.ConnectionError("bot offline"),
        ):
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["success"] is False
        assert body["pipeline"] == "bot"
        assert _external_rows(match_db) == []

    def test_bot_rejection_is_passed_through(self, client, match_db):
        _seed_pairing(match_db)
        upstream = Mock(status_code=400, text="Queue type does not match this pairing")
        upstream.json.side_effect = ValueError
        with patch("routes.api.matchmaking.requests.request", return_value=upstream):
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 400
        assert "Queue type" in resp.get_json()["error"]
        assert _external_rows(match_db) == []


class TestNonSummitResultsStayExternal:
    def test_no_pairing_stores_external_match(self, client, match_db):
        with patch("routes.api.matchmaking.requests.request") as req, \
             patch("routes.api.external_matches.ExternalMatchService") as service:
            service.return_value.report_match.return_value = {"report_id": 1}
            resp = client.post(
                "/api/report-external-match",
                json=_payload(source="SomeOtherApp"),
                headers=HEADERS,
            )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["pipeline"] == "external"
        req.assert_not_called()
        service.return_value.report_match.assert_called_once()

    def test_closed_pairing_does_not_route_to_bot(self, client, match_db):
        _seed_pairing(match_db, status="reported")
        with patch("routes.api.matchmaking.requests.request") as req, \
             patch("routes.api.external_matches.ExternalMatchService") as service:
            service.return_value.report_match.return_value = {"report_id": 1}
            resp = client.post("/api/report-external-match", json=_payload(), headers=HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["pipeline"] == "external"
        req.assert_not_called()
        service.return_value.report_match.assert_called_once()

    def test_pairing_id_for_other_players_is_ignored(self, client, match_db):
        pairing_id = _seed_pairing(match_db, p1=30, p2=40)
        with patch("routes.api.matchmaking.requests.request") as req, \
             patch("routes.api.external_matches.ExternalMatchService") as service:
            service.return_value.report_match.return_value = {"report_id": 1}
            resp = client.post(
                "/api/report-external-match",
                json=_payload(pairing_id=pairing_id),
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.get_json()["pipeline"] == "external"
        req.assert_not_called()
        service.return_value.report_match.assert_called_once()
