"""Tests for the admin user-profile management endpoints."""

import sqlite3

import pytest

from repositories.user_profiles import UserProfileRepository
from tests.conftest import seed_elo_data, seed_matches


@pytest.fixture()
def profile_repo(app, match_db):
    """Repository bound to the temporary match records database."""
    return UserProfileRepository(match_db)


def _profile_rows(match_db):
    conn = sqlite3.connect(str(match_db))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM user_profiles")]
    conn.close()
    return rows


class TestAddUserProfile:
    def test_creates_profile_for_discord_user(self, admin_session, match_db, profile_repo):
        res = admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "NewPlayer"},
        )
        assert res.status_code == 201
        assert res.get_json()["success"] is True

        rows = _profile_rows(match_db)
        assert len(rows) == 1
        assert rows[0]["user_id"] == "123456789012345678"
        assert rows[0]["display_name"] == "NewPlayer"
        assert rows[0]["provider"] == "discord"
        assert rows[0]["manually_added_by"] == "AdminUser"
        assert rows[0]["manually_added_at"] is not None

    def test_added_profile_is_searchable(self, admin_session, profile_repo):
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "Searchable"},
        )
        res = admin_session.get("/api/admin/search-users?q=Searchable")
        users = res.get_json()["users"]
        assert [u["user_id"] for u in users] == ["123456789012345678"]

    def test_rejects_non_numeric_user_id(self, admin_session, match_db):
        res = admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "not-a-snowflake", "display_name": "Nope"},
        )
        assert res.status_code == 400
        assert "Discord ID" in res.get_json()["error"]
        assert _profile_rows(match_db) == []

    def test_rejects_missing_display_name(self, admin_session):
        res = admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "   "},
        )
        assert res.status_code == 400
        assert "display_name" in res.get_json()["error"]

    def test_rejects_overlong_display_name(self, admin_session):
        res = admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "x" * 101},
        )
        assert res.status_code == 400

    def test_does_not_overwrite_existing_profile(self, admin_session, profile_repo, match_db):
        profile_repo.upsert_profile("123456789012345678", "RealUser", avatar="abc")

        res = admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "Impostor"},
        )
        assert res.status_code == 409

        rows = _profile_rows(match_db)
        assert len(rows) == 1
        assert rows[0]["display_name"] == "RealUser"

    def test_requires_admin(self, user_session, match_db):
        res = user_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "NewPlayer"},
        )
        assert res.status_code in (401, 403)
        assert _profile_rows(match_db) == []

    def test_writes_audit_entry(self, admin_session):
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "123456789012345678", "display_name": "Audited"},
        )
        entries = admin_session.get("/api/admin/audit-log").get_json()["entries"]
        assert any(
            e["action"] == "add_user_profile" and e["target_id"] == "123456789012345678"
            for e in entries
        )


class TestListUserProfiles:
    def test_flags_manual_and_real_profiles(self, admin_session, profile_repo):
        profile_repo.upsert_profile("111111111111111111", "RealUser")
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "222222222222222222", "display_name": "Placeholder"},
        )

        data = admin_session.get("/api/admin/user-profiles").get_json()
        by_id = {p["user_id"]: p for p in data["profiles"]}
        assert data["total"] == 2

        assert by_id["111111111111111111"]["manually_added"] is False
        assert by_id["111111111111111111"]["has_logged_in"] is True

        assert by_id["222222222222222222"]["manually_added"] is True
        assert by_id["222222222222222222"]["has_logged_in"] is False

    def test_marks_manual_profile_as_logged_in_after_login(self, admin_session, profile_repo):
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "222222222222222222", "display_name": "Placeholder"},
        )
        # Their real login later fills in the actual Discord details.
        profile_repo.upsert_profile("222222222222222222", "TheirRealName", avatar="hash")

        data = admin_session.get("/api/admin/user-profiles").get_json()
        profile = data["profiles"][0]
        assert profile["display_name"] == "TheirRealName"
        assert profile["manually_added"] is True
        assert profile["has_logged_in"] is True

    def test_filters_by_name(self, admin_session, profile_repo):
        profile_repo.upsert_profile("111111111111111111", "Alice")
        profile_repo.upsert_profile("222222222222222222", "Bob")

        data = admin_session.get("/api/admin/user-profiles?q=ali").get_json()
        assert data["total"] == 1
        assert data["profiles"][0]["display_name"] == "Alice"

    def test_requires_admin(self, user_session):
        assert user_session.get("/api/admin/user-profiles").status_code in (401, 403)


class TestCandidates:
    def test_finds_match_history_players_without_profiles(self, admin_session, match_db):
        seed_matches(match_db, [
            {
                "winner_id": "333333333333333333", "winner_name": "GhostPlayer",
                "loser_id": "444444444444444444", "loser_name": "OtherPlayer",
            },
        ])
        data = admin_session.get("/api/admin/user-profiles/candidates?q=Ghost").get_json()
        assert [c["user_id"] for c in data["candidates"]] == ["333333333333333333"]
        assert data["candidates"][0]["source"] == "match history"

    def test_finds_elo_players_without_profiles(self, admin_session, elo_db):
        seed_elo_data(elo_db, [{"user_id": "555555555555555555", "name": "LadderOnly"}])
        data = admin_session.get("/api/admin/user-profiles/candidates?q=Ladder").get_json()
        assert [c["user_id"] for c in data["candidates"]] == ["555555555555555555"]
        assert data["candidates"][0]["source"] == "ELO standings"

    def test_excludes_players_that_already_have_profiles(
        self, admin_session, elo_db, match_db, profile_repo
    ):
        seed_elo_data(elo_db, [{"user_id": "555555555555555555", "name": "AlreadyHere"}])
        seed_matches(match_db, [
            {
                "winner_id": "555555555555555555", "winner_name": "AlreadyHere",
                "loser_id": "666666666666666666", "loser_name": "Someone",
            },
        ])
        profile_repo.upsert_profile("555555555555555555", "AlreadyHere")

        data = admin_session.get("/api/admin/user-profiles/candidates?q=Already").get_json()
        assert data["candidates"] == []

    def test_rejects_short_query(self, admin_session):
        assert admin_session.get("/api/admin/user-profiles/candidates?q=a").status_code == 400

    def test_requires_admin(self, user_session):
        res = user_session.get("/api/admin/user-profiles/candidates?q=ghost")
        assert res.status_code in (401, 403)


class TestDeleteUserProfile:
    def test_removes_manually_added_profile(self, admin_session, match_db):
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "222222222222222222", "display_name": "Typo"},
        )
        res = admin_session.delete("/api/admin/user-profiles/222222222222222222")
        assert res.status_code == 200
        assert _profile_rows(match_db) == []

    def test_refuses_to_remove_a_real_login(self, admin_session, profile_repo, match_db):
        profile_repo.upsert_profile("111111111111111111", "RealUser")
        res = admin_session.delete("/api/admin/user-profiles/111111111111111111")
        assert res.status_code == 400
        assert len(_profile_rows(match_db)) == 1

    def test_refuses_once_a_manual_profile_has_logged_in(
        self, admin_session, profile_repo, match_db
    ):
        admin_session.post(
            "/api/admin/user-profiles",
            json={"user_id": "222222222222222222", "display_name": "Placeholder"},
        )
        profile_repo.upsert_profile("222222222222222222", "TheirRealName")

        res = admin_session.delete("/api/admin/user-profiles/222222222222222222")
        assert res.status_code == 400
        assert len(_profile_rows(match_db)) == 1

    def test_missing_profile_returns_404(self, admin_session):
        assert admin_session.delete("/api/admin/user-profiles/999999999999999999").status_code == 404

    def test_requires_admin(self, user_session, profile_repo, match_db):
        profile_repo.create_manual_profile("222222222222222222", "Placeholder", added_by="AdminUser")
        res = user_session.delete("/api/admin/user-profiles/222222222222222222")
        assert res.status_code in (401, 403)
        assert len(_profile_rows(match_db)) == 1
