"""Admin panel Timeout / Ban for blocked and reported players."""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

DISCORD_ID = "222222222222222222"


def _report(match_db, reported_id=DISCORD_ID):
    from repositories.player_reports_repo import PlayerReportsRepository

    PlayerReportsRepository(db_path=match_db).save_report(
        reporter_id="333333333333333333", reported_id=reported_id, reasons=["toxic"],
        reporter_name="Reporter", reported_name="Opponent",
    )


def _block(match_db, blocked=DISCORD_ID):
    from repositories.blocked_users_repo import BlockedUsersRepository

    BlockedUsersRepository(db_path=match_db).block_user("333333333333333333", blocked, reason="rude")


def _resp(status):
    resp = MagicMock()
    resp.status_code = status
    return resp


class TestModerationRoute:
    URL = "/api/admin/moderation"

    def _body(self, **kw):
        body = {"action": "timeout", "user_id": DISCORD_ID, "minutes": 1440,
                "reason": "toxic", "source_kind": "report", "source_ref": "1", "confirm": True}
        body.update(kw)
        return body

    def test_requires_admin(self, user_session):
        assert user_session.post(self.URL, json=self._body()).status_code in (401, 403)

    def test_requires_confirmation(self, admin_session):
        with patch("services.discord_moderation.requests.patch") as call:
            resp = admin_session.post(self.URL, json=self._body(confirm=None))
        assert resp.status_code == 400
        call.assert_not_called()

    def test_timeout_calls_discord_and_shows_on_the_report(self, admin_session, match_db):
        _report(match_db)
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.patch", return_value=_resp(200)) as call:
            resp = admin_session.post(self.URL, json=self._body())
        assert resp.status_code == 200, resp.get_json()
        url = call.call_args.args[0]
        assert url.endswith(f"/members/{DISCORD_ID}")
        assert "communication_disabled_until" in call.call_args.kwargs["json"]
        assert "X-Audit-Log-Reason" in call.call_args.kwargs["headers"]

        [entry] = admin_session.get("/api/admin/player-reports").get_json()["entries"]
        assert entry["can_moderate"] is True
        assert entry["moderation"]["action"] == "timeout"
        assert entry["moderation"]["duration_minutes"] == 1440
        assert entry["moderation"]["by_name"] == "AdminUser"

    def test_ban_shows_on_the_block(self, admin_session, match_db):
        _block(match_db)
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.put", return_value=_resp(204)) as call:
            resp = admin_session.post(self.URL, json=self._body(action="ban", source_kind="block"))
        assert resp.status_code == 200
        assert call.call_args.args[0].endswith(f"/bans/{DISCORD_ID}")
        [entry] = admin_session.get("/api/admin/blocked-users").get_json()["entries"]
        assert entry["moderation"]["action"] == "ban"

    def test_discord_refusing_is_shown_and_not_logged(self, admin_session, match_db):
        _report(match_db)
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.put", return_value=_resp(403)):
            resp = admin_session.post(self.URL, json=self._body(action="ban"))
        assert resp.status_code == 400
        assert "Ban Members" in resp.get_json()["error"]
        [entry] = admin_session.get("/api/admin/player-reports").get_json()["entries"]
        assert entry["moderation"] is None

    def test_odd_durations_and_google_accounts_are_rejected(self, admin_session, match_db):
        with patch("webapp_config.DISCORD_BOT_TOKEN", "tok"), \
             patch("services.discord_moderation.requests.patch") as call:
            assert admin_session.post(self.URL, json=self._body(minutes=99999)).status_code == 400
            assert admin_session.post(self.URL, json=self._body(user_id="google_123")).status_code == 400
        call.assert_not_called()

    def test_google_accounts_cant_be_moderated_in_the_list(self, admin_session, match_db):
        _block(match_db, blocked="google_555")
        [entry] = admin_session.get("/api/admin/blocked-users").get_json()["entries"]
        assert entry["can_moderate"] is False

    def test_pairing_block_stores_the_block_and_asks_the_bot_to_follow_up(self, admin_session, match_db):
        _report(match_db)
        resp = admin_session.post(self.URL, json=self._body(
            action="pairing_block", duration="72h", reason="Reported after a match: no show"))
        assert resp.status_code == 200, resp.get_json()
        conn = sqlite3.connect(match_db)
        ban = conn.execute("SELECT duration_label, reason, expires_at FROM pairing_bans WHERE user_id = ?",
                           (DISCORD_ID,)).fetchone()
        bot_done = conn.execute("SELECT bot_done FROM moderation_actions").fetchone()[0]
        conn.close()
        assert ban[0] == "72 hours" and ban[1].endswith("no show") and ban[2]
        assert bot_done == 0
        [entry] = admin_session.get("/api/admin/player-reports").get_json()["entries"]
        assert entry["moderation"]["action"] == "pairing_block"
        assert entry["moderation"]["duration_label"] == "72 hours"

    def test_pairing_block_needs_a_reason_and_a_real_duration(self, admin_session, match_db):
        assert admin_session.post(self.URL, json=self._body(action="pairing_block", duration="72h",
                                                            reason="")).status_code == 400
        assert admin_session.post(self.URL, json=self._body(action="pairing_block", duration="1y",
                                                            reason="no show")).status_code == 400
