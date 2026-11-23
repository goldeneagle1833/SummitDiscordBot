"""Mod Tools: moderators see reports and can time out / ban, nothing else."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

MOD_ID = "444444444444444444"
TARGET = "222222222222222222"
REPORTER = "333333333333333333"


def _resp(status):
    r = MagicMock()
    r.status_code = status
    return r


@pytest.fixture(autouse=True)
def _no_real_dms():
    with patch("services.discord_moderation.requests.post", return_value=_resp(403)) as post:
        yield post


def _report(match_db, reported_id=TARGET, reasons=("toxic",), reported_name="Opponent", reporter=REPORTER):
    from repositories.player_reports_repo import PlayerReportsRepository
    return PlayerReportsRepository(db_path=match_db).save_report(
        reporter_id=reporter, reported_id=reported_id, reasons=list(reasons),
        reporter_name="Reporter", reported_name=reported_name,
    )


@pytest.fixture()
def mod_session(client, app):
    from repositories.moderation_repo import ModeratorsRepository
    ModeratorsRepository().add(MOD_ID, "ModUser")
    with client.session_transaction() as sess:
        sess["user_id"] = MOD_ID
        sess["username"] = "ModUser"
    return client


class TestAccess:
    def test_regular_users_get_nothing(self, user_session):
        for url in ("/api/mod/reports", "/api/mod/players?q=op", "/api/mod/actions", "/api/mod/moderators"):
            assert user_session.get(url).status_code == 403, url
        assert user_session.post("/api/mod/action", json={"confirm": True}).status_code == 403

    def test_moderator_gets_mod_tools_but_not_admin(self, mod_session, match_db):
        _report(match_db)
        assert mod_session.get("/api/mod/reports").status_code == 200
        assert mod_session.get("/api/mod/actions").status_code == 200
        # Admin-only things stay admin-only
        assert mod_session.get("/api/mod/moderators").status_code == 403
        assert mod_session.post("/api/mod/moderators", json={"discord_id": "555555555555555555"}).status_code == 403
        assert mod_session.get("/api/admin/player-reports").status_code == 403
        assert mod_session.get("/api/admin/audit-log").status_code == 403
        assert mod_session.post("/api/admin/moderation", json={"confirm": True}).status_code == 403

    def test_me_flags_moderator(self, mod_session):
        me = mod_session.get("/api/me").get_json()
        assert me["is_moderator"] is True and me["is_admin"] is False

    def test_admin_is_a_moderator_too(self, admin_session):
        assert admin_session.get("/api/me").get_json()["is_moderator"] is True
        assert admin_session.get("/api/mod/reports").status_code == 200

    def test_removed_moderator_loses_access(self, admin_session, client, app):
        assert admin_session.post("/api/mod/moderators", json={"discord_id": MOD_ID}).status_code == 200
        assert admin_session.delete(f"/api/mod/moderators/{MOD_ID}").status_code == 200
        with client.session_transaction() as sess:
            sess["user_id"] = MOD_ID
        assert client.get("/api/mod/reports").status_code == 403


class TestModeratorList:
    def test_add_list_remove(self, admin_session):
        assert admin_session.post("/api/mod/moderators", json={"discord_id": "abc"}).status_code == 400
        assert admin_session.post("/api/mod/moderators", json={"discord_id": MOD_ID}).status_code == 200
        assert admin_session.post("/api/mod/moderators", json={"discord_id": MOD_ID}).status_code == 400
        mods = admin_session.get("/api/mod/moderators").get_json()["moderators"]
        assert [m["discord_user_id"] for m in mods] == [MOD_ID]
        assert mods[0]["added_by_name"] == "AdminUser"
        assert admin_session.delete(f"/api/mod/moderators/{MOD_ID}").status_code == 200
        assert admin_session.delete(f"/api/mod/moderators/{MOD_ID}").status_code == 404


class TestReports:
    def test_sort_filter_and_search(self, mod_session, match_db):
        other = "666666666666666666"
        _report(match_db, reasons=["toxic"])
        _report(match_db, reasons=["no_show"])
        _report(match_db, reported_id=other, reported_name="Zed", reasons=["stalling"])

        d = mod_session.get("/api/mod/reports?sort=most_reported").get_json()
        assert d["total"] == 3
        assert [e["reported_id"] for e in d["entries"]] == [TARGET, TARGET, other]
        assert d["entries"][0]["reports_against"] == 2

        oldest = mod_session.get("/api/mod/reports?sort=oldest").get_json()["entries"]
        assert oldest[0]["reasons"] == ["toxic"]

        assert mod_session.get("/api/mod/reports?reason=stalling").get_json()["total"] == 1
        assert mod_session.get("/api/mod/reports?q=zed").get_json()["total"] == 1
        assert mod_session.get(f"/api/mod/reports?q={other}").get_json()["total"] == 1
        assert mod_session.get(f"/api/mod/reports?reported_id={TARGET}").get_json()["total"] == 2

    def test_reports_carry_no_profile_or_deck_data(self, mod_session, match_db):
        _report(match_db)
        [e] = mod_session.get("/api/mod/reports").get_json()["entries"]
        assert set(e) <= {
            "id", "reporter_id", "reporter_name", "reported_id", "reported_name", "match_type",
            "reasons", "details", "source", "created_at", "reports_against", "actioned",
            "can_moderate", "moderation", "status",
        }

    def test_open_and_actioned(self, mod_session, match_db):
        _report(match_db)
        assert mod_session.get("/api/mod/reports?state=open").get_json()["total"] == 1
        resp = mod_session.post("/api/mod/action", json={
            "action": "pairing_block", "user_id": TARGET, "duration": "24h",
            "reason": "No show", "source_kind": "report", "source_ref": "1", "confirm": True})
        assert resp.status_code == 200, resp.get_json()
        assert mod_session.get("/api/mod/reports?state=open").get_json()["total"] == 0
        [e] = mod_session.get("/api/mod/reports?state=actioned").get_json()["entries"]
        assert e["status"]["pairing_block"]["duration_label"] == "24 hours"
        assert e["moderation"]["by_name"] == "ModUser (moderator)"


class TestActions:
    BODY = {"user_id": TARGET, "reason": "Toxic in chat", "confirm": True}

    def test_moderator_timeout_and_remove(self, mod_session, match_db):
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.patch", return_value=_resp(200)) as call:
            r = mod_session.post("/api/mod/action", json=dict(self.BODY, action="timeout", minutes=60))
            assert r.status_code == 200, r.get_json()
            assert r.get_json()["status"]["timed_out_until"]
            assert "moderator" in call.call_args.kwargs["headers"]["X-Audit-Log-Reason"]
            r = mod_session.post("/api/mod/action", json={"action": "remove_timeout", "user_id": TARGET, "confirm": True})
            assert r.status_code == 200, r.get_json()
            assert call.call_args.kwargs["json"] == {"communication_disabled_until": None}
            assert r.get_json()["status"]["timed_out_until"] is None

    def test_ban_and_unban(self, mod_session, match_db):
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.put", return_value=_resp(204)), \
             patch("services.discord_moderation.requests.delete", return_value=_resp(204)) as delete:
            r = mod_session.post("/api/mod/action", json=dict(self.BODY, action="ban"))
            assert r.status_code == 200 and r.get_json()["status"]["banned"] is True
            r = mod_session.post("/api/mod/action", json={"action": "unban", "user_id": TARGET, "confirm": True})
            assert r.status_code == 200 and r.get_json()["status"]["banned"] is False
            assert delete.call_args.args[0].endswith(f"/bans/{TARGET}")

    def test_lift_pairing_block(self, mod_session, match_db):
        mod_session.post("/api/mod/action", json=dict(self.BODY, action="pairing_block", duration="lifetime"))
        r = mod_session.post("/api/mod/action", json={"action": "lift_pairing_block", "user_id": TARGET, "confirm": True})
        assert r.status_code == 200 and r.get_json()["status"]["pairing_block"] is None
        conn = sqlite3.connect(match_db)
        assert conn.execute("SELECT COUNT(*) FROM pairing_bans").fetchone()[0] == 0
        conn.close()
        r = mod_session.post("/api/mod/action", json={"action": "lift_pairing_block", "user_id": TARGET, "confirm": True})
        assert r.status_code == 400

    def test_needs_confirm_and_reason_and_not_self(self, mod_session):
        assert mod_session.post("/api/mod/action", json=dict(self.BODY, action="ban", confirm=None)).status_code == 400
        assert mod_session.post("/api/mod/action", json=dict(self.BODY, action="ban", reason="")).status_code == 400
        r = mod_session.post("/api/mod/action", json=dict(self.BODY, action="ban", user_id=MOD_ID))
        assert r.status_code == 400 and "yourself" in r.get_json()["error"]

    def test_recent_actions_list(self, mod_session):
        mod_session.post("/api/mod/action", json=dict(self.BODY, action="pairing_block", duration="24h"))
        [a] = mod_session.get("/api/mod/actions").get_json()["entries"]
        assert a["action"] == "pairing_block" and a["target_id"] == TARGET


class TestPlayerSearch:
    def test_search_by_name_and_id(self, mod_session, match_db):
        _report(match_db)
        _report(match_db, reasons=["no_show"])
        d = mod_session.get("/api/mod/players?q=oppo").get_json()
        [p] = [p for p in d["players"] if p["user_id"] == TARGET]
        assert p["reports_against"] == 2 and p["can_moderate"] is True
        assert set(p) == {"user_id", "name", "reports_against", "reports_filed", "blocked_by",
                          "can_moderate", "moderation", "status"}
        d = mod_session.get(f"/api/mod/players?q={TARGET}").get_json()
        assert d["players"][0]["user_id"] == TARGET
        assert mod_session.get("/api/mod/players?q=a").status_code == 400
