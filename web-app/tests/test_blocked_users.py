"""Tests for blocked users feature - repository and API routes."""

import sqlite3
import pytest

from repositories.blocked_users_repo import BlockedUsersRepository


# ── Repository tests ────────────────────────────────────────


class TestBlockedUsersRepository:
    def test_get_blocked_users_empty(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        assert repo.get_blocked_users("123") == []

    def test_block_user(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        assert repo.block_user("100", "200") is True
        blocked = repo.get_blocked_users("100")
        assert len(blocked) == 1
        assert blocked[0]["blocked_user_id"] == "200"
        assert blocked[0]["reason"] is None

    def test_block_user_duplicate(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("100", "200")
        assert repo.block_user("100", "200") is False

    def test_block_self_rejected(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        assert repo.block_user("100", "100") is False

    def test_block_user_with_reason(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        assert repo.block_user("100", "200", reason="Toxic behavior") is True
        blocked = repo.get_blocked_users("100")
        assert blocked[0]["reason"] == "Toxic behavior"

    def test_unblock_user(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("100", "200")
        assert repo.unblock_user("100", "200") is True
        assert repo.get_blocked_users("100") == []

    def test_unblock_user_not_blocked(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        assert repo.unblock_user("100", "200") is False

    def test_multiple_blocks(self, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("100", "200")
        repo.block_user("100", "300")
        repo.block_user("100", "400")
        blocked = repo.get_blocked_users("100")
        blocked_ids = {b["blocked_user_id"] for b in blocked}
        assert blocked_ids == {"200", "300", "400"}

    def test_block_is_directional(self, match_db):
        """A blocking B does not mean B has blocked A."""
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("100", "200")
        assert len(repo.get_blocked_users("100")) == 1
        assert repo.get_blocked_users("100")[0]["blocked_user_id"] == "200"
        assert repo.get_blocked_users("200") == []


# ── API route tests ────────────────────────────────────────


class TestBlockedUsersRoutes:
    def _seed_user(self, match_db, user_id, display_name):
        conn = sqlite3.connect(str(match_db))
        conn.execute(
            "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at) VALUES (?, 'discord', ?, datetime('now'), datetime('now'))",
            (user_id, display_name),
        )
        conn.commit()
        conn.close()

    def test_get_blocked_users_unauthenticated(self, client):
        resp = client.get("/api/player/100/blocked-users")
        assert resp.status_code == 401

    def test_get_blocked_users_owner_only(self, user_session):
        """Owner can access their own block list."""
        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        assert resp.status_code == 200

    def test_get_blocked_users_empty(self, user_session):
        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        assert resp.status_code == 200
        assert resp.get_json()["blocked_users"] == []

    def test_block_user_flow(self, user_session, match_db):
        self._seed_user(match_db, "target_user", "TargetPlayer")

        # Block
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "target_user", "reason": "spam"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["added"] is True

        # Verify in list
        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        data = resp.get_json()
        assert len(data["blocked_users"]) == 1
        assert data["blocked_users"][0]["user_id"] == "target_user"
        assert data["blocked_users"][0]["display_name"] == "TargetPlayer"
        assert data["blocked_users"][0]["reason"] == "spam"

    def test_unblock_user(self, user_session, match_db):
        self._seed_user(match_db, "target_user", "TargetPlayer")
        user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "target_user", "reason": "spam"},
        )

        resp = user_session.delete("/api/player/regular_user_1/blocked-users/target_user")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is True

        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        assert resp.get_json()["blocked_users"] == []

    def test_block_self_rejected(self, user_session):
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "regular_user_1", "reason": "test"},
        )
        assert resp.status_code == 400

    def test_block_missing_field(self, user_session):
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={},
        )
        assert resp.status_code == 400

    def test_block_missing_reason(self, user_session, match_db):
        self._seed_user(match_db, "target_user", "TargetPlayer")
        for payload in (
            {"blocked_user_id": "target_user"},
            {"blocked_user_id": "target_user", "reason": ""},
            {"blocked_user_id": "target_user", "reason": "   "},
        ):
            resp = user_session.post(
                "/api/player/regular_user_1/blocked-users", json=payload)
            assert resp.status_code == 400
            assert "reason" in resp.get_json()["error"].lower()

    def test_block_unauthenticated(self, client):
        resp = client.post(
            "/api/player/100/blocked-users",
            json={"blocked_user_id": "200"},
        )
        assert resp.status_code == 401

    def test_unblock_unauthenticated(self, client):
        resp = client.delete("/api/player/100/blocked-users/200")
        assert resp.status_code == 401

    def test_block_with_reason(self, user_session, match_db):
        self._seed_user(match_db, "rude_player", "RudePlayer")
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "rude_player", "reason": "Toxic in chat"},
        )
        assert resp.status_code == 200

        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        data = resp.get_json()
        assert data["blocked_users"][0]["reason"] == "Toxic in chat"

    def test_admin_can_view_others_block_list(self, admin_session, match_db):
        self._seed_user(match_db, "some_user", "SomeUser")
        resp = admin_session.get("/api/player/some_user/blocked-users")
        assert resp.status_code == 200


class TestPlayerReportsRoute:
    def _seed_report(self, match_db, **overrides):
        from repositories.player_reports_repo import PlayerReportsRepository

        PlayerReportsRepository(db_path=match_db)  # creates the table
        row = {
            "reporter_id": "100",
            "reporter_name": "Reporter",
            "reported_id": "200",
            "reported_name": "Opponent",
            "match_type": "ranked",
            "reasons": '["voice_refused", "left_early"]',
            "details": "Left at 3 life",
        }
        row.update(overrides)
        conn = sqlite3.connect(match_db)
        conn.execute(
            "INSERT INTO player_reports (reporter_id, reporter_name, reported_id, reported_name,"
            " match_type, reasons, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(row.values()),
        )
        conn.commit()
        conn.close()

    def test_requires_admin(self, user_session):
        resp = user_session.get("/api/admin/player-reports")
        assert resp.status_code in (401, 403)

    def test_empty(self, admin_session):
        resp = admin_session.get("/api/admin/player-reports")
        assert resp.status_code == 200
        assert resp.get_json() == {"success": True, "entries": [], "total": 0}

    def test_lists_reports_with_reasons(self, admin_session, match_db):
        self._seed_report(match_db)
        data = admin_session.get("/api/admin/player-reports").get_json()
        assert data["total"] == 1
        [entry] = data["entries"]
        assert entry["reporter_name"] == "Reporter"
        assert entry["reported_name"] == "Opponent"
        assert entry["reasons"] == ["voice_refused", "left_early"]
        assert entry["details"] == "Left at 3 life"


# ── Partner (PSO) read API ──────────────────────────────────


class TestPartnerBlocksRoutes:
    HEADERS = {"X-API-Key": "test-api-key-123"}

    def _seed_user(self, match_db, user_id, display_name):
        conn = sqlite3.connect(str(match_db))
        conn.execute(
            "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at) VALUES (?, 'discord', ?, datetime('now'), datetime('now'))",
            (user_id, display_name),
        )
        conn.commit()
        conn.close()

    def test_requires_api_key(self, client):
        assert client.get("/api/blocks/100").status_code == 401
        assert client.get("/api/blocks/check?user_a=1&user_b=2").status_code == 401
        bad = {"X-API-Key": "nope"}
        assert client.get("/api/blocks/100", headers=bad).status_code == 401

    def test_player_blocks_both_directions(self, client, match_db):
        self._seed_user(match_db, "200", "Bob")
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("100", "200", reason="secret")
        repo.block_user("300", "100", reason="secret")

        resp = client.get("/api/blocks/100", headers=self.HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert [e["user_id"] for e in data["blocked"]] == ["200"]
        assert data["blocked"][0]["display_name"] == "Bob"
        assert [e["user_id"] for e in data["blocked_by"]] == ["300"]
        assert "secret" not in resp.get_data(as_text=True)

    def test_player_blocks_matches_google_form(self, client, match_db):
        repo = BlockedUsersRepository(db_path=match_db)
        repo.block_user("google_100", "200", reason="x")
        data = client.get("/api/blocks/100", headers=self.HEADERS).get_json()
        assert [e["user_id"] for e in data["blocked"]] == ["200"]

    def test_player_blocks_empty(self, client):
        data = client.get("/api/blocks/999", headers=self.HEADERS).get_json()
        assert data == {"success": True, "user_id": "999", "blocked": [], "blocked_by": []}

    def test_check_pair(self, client, match_db):
        BlockedUsersRepository(db_path=match_db).block_user("100", "200", reason="x")

        data = client.get("/api/blocks/check?user_a=200&user_b=100", headers=self.HEADERS).get_json()
        assert data["blocked"] is True
        assert data["a_blocked_b"] is False
        assert data["b_blocked_a"] is True

        data = client.get("/api/blocks/check?user_a=100&user_b=300", headers=self.HEADERS).get_json()
        assert data["blocked"] is False

    def test_check_pair_missing_params(self, client):
        resp = client.get("/api/blocks/check?user_a=100", headers=self.HEADERS)
        assert resp.status_code == 400


class TestPartnerPlayerReports:
    HEADERS = {"X-API-Key": "test-api-key-123"}
    URL = "/api/player-reports"

    def _body(self, **overrides):
        body = {
            "reporter_id": "100",
            "reported_id": "200",
            "reporter_name": "Alice",
            "reported_name": "Bob",
            "reasons": ["no_show", "toxic"],
            "details": "Never joined the table",
            "pairing_id": 42,
            "match_type": "ranked",
        }
        body.update(overrides)
        return body

    def test_requires_api_key(self, client):
        assert client.post(self.URL, json=self._body()).status_code == 401

    def test_report_lands_in_admin_list(self, client, admin_session):
        resp = client.post(self.URL, json=self._body(), headers=self.HEADERS)
        assert resp.status_code == 201
        assert resp.get_json()["report_id"]

        entries = admin_session.get("/api/admin/player-reports").get_json()["entries"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["reporter_id"] == "100"
        assert entry["reported_id"] == "200"
        assert entry["reasons"] == ["no_show", "toxic"]
        assert entry["details"] == "Never joined the table"
        assert entry["match_type"] == "ranked"
        assert entry["source"] == "sorcery-online"

    def test_details_only_is_enough(self, client):
        resp = client.post(self.URL, json=self._body(reasons=[]), headers=self.HEADERS)
        assert resp.status_code == 201

    def test_empty_report_rejected(self, client):
        resp = client.post(self.URL, json=self._body(reasons=[], details=""), headers=self.HEADERS)
        assert resp.status_code == 400

    def test_unknown_reason_rejected(self, client):
        resp = client.post(self.URL, json=self._body(reasons=["rude"]), headers=self.HEADERS)
        assert resp.status_code == 400
        assert "toxic" in resp.get_json()["allowed_reasons"]

    def test_self_report_rejected(self, client):
        resp = client.post(self.URL, json=self._body(reported_id="100"), headers=self.HEADERS)
        assert resp.status_code == 400

    def test_missing_ids_rejected(self, client):
        resp = client.post(self.URL, json=self._body(reported_id=""), headers=self.HEADERS)
        assert resp.status_code == 400

    def test_details_too_long_rejected(self, client):
        resp = client.post(self.URL, json=self._body(details="x" * 1001), headers=self.HEADERS)
        assert resp.status_code == 400
