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
            json={"blocked_user_id": "target_user"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["added"] is True

        # Verify in list
        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        data = resp.get_json()
        assert len(data["blocked_users"]) == 1
        assert data["blocked_users"][0]["user_id"] == "target_user"
        assert data["blocked_users"][0]["display_name"] == "TargetPlayer"
        assert data["blocked_users"][0]["reason"] is None

    def test_unblock_user(self, user_session, match_db):
        self._seed_user(match_db, "target_user", "TargetPlayer")
        user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "target_user"},
        )

        resp = user_session.delete("/api/player/regular_user_1/blocked-users/target_user")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is True

        resp = user_session.get("/api/player/regular_user_1/blocked-users")
        assert resp.get_json()["blocked_users"] == []

    def test_block_self_rejected(self, user_session):
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={"blocked_user_id": "regular_user_1"},
        )
        assert resp.status_code == 400

    def test_block_missing_field(self, user_session):
        resp = user_session.post(
            "/api/player/regular_user_1/blocked-users",
            json={},
        )
        assert resp.status_code == 400

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
