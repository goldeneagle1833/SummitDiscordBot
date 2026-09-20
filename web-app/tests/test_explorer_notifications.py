"""Tests for Explorer application Discord notifications."""

from unittest.mock import patch

import pytest

from repositories.explorer import ExplorerRepository
from services import explorer_notifications


@pytest.fixture()
def no_geocoding():
    with patch("routes.api.explorer_applications._geocode_in_background"):
        yield


@pytest.fixture()
def applicant_session(client, app):
    with client.session_transaction() as sess:
        sess["user_id"] = "555000111222333444"
        sess["username"] = "Rubonic"
        sess["auth_provider"] = "discord"
    return client


def valid_application(**overrides):
    payload = {
        "first_name": "Ruben",
        "last_name": "Sanchez",
        "email": "rubonic@example.com",
        "discord_handle": "Rubonic",
        "city": "Mechanicsville",
        "state": "Virginia",
        "lgs_name": "Waterloo Games",
        "read_navigator_role": True,
    }
    payload.update(overrides)
    return payload


class TestRecipients:
    def test_notifies_the_explorer_admins(self, app):
        ExplorerRepository().add_explorer_admin("111111111111111111", "Council")
        ExplorerRepository().add_explorer_admin("222222222222222222", "Council Two")
        assert sorted(explorer_notifications.recipient_ids()) == [
            "111111111111111111",
            "222222222222222222",
        ]

    def test_excludes_global_admins_who_are_not_explorer_admins(self, app):
        ExplorerRepository().add_explorer_admin("111111111111111111", "Council")
        # admin_user_1 is a global admin in webapp_config.ADMINS and can open
        # the review board, but is not on the Council and is not DMed.
        assert "admin_user_1" not in explorer_notifications.recipient_ids()

    def test_includes_a_global_admin_who_is_also_an_explorer_admin(self, app):
        ExplorerRepository().add_explorer_admin("admin_user_1", "Bruce")
        assert explorer_notifications.recipient_ids() == ["admin_user_1"]

    def test_nobody_to_notify_when_the_council_is_empty(self, app):
        assert explorer_notifications.recipient_ids() == []

    def test_survives_an_unreadable_explorer_admin_table(self, app):
        with patch.object(
            ExplorerRepository, "get_explorer_admins", side_effect=OSError("locked")
        ):
            assert explorer_notifications.recipient_ids() == []


class TestPayload:
    def test_summarises_the_application(self, app):
        payload = explorer_notifications.build_payload(
            valid_application(), ["111111111111111111"]
        )
        assert payload["applicant_name"] == "Ruben Sanchez"
        assert payload["discord_handle"] == "Rubonic"
        assert payload["location"] == "Mechanicsville, Virginia"
        assert payload["lgs_name"] == "Waterloo Games"
        assert payload["admin_discord_ids"] == ["111111111111111111"]
        assert payload["review_url"].endswith("/admin/explorer-applications")

    def test_falls_back_to_the_discord_handle_when_unnamed(self, app):
        payload = explorer_notifications.build_payload(
            {"discord_handle": "Kevmo"}, ["1"]
        )
        assert payload["applicant_name"] == "Kevmo"

    def test_tolerates_a_missing_location(self, app):
        payload = explorer_notifications.build_payload({"first_name": "Solo"}, ["1"])
        assert payload["location"] == ""
        assert payload["applicant_name"] == "Solo"


class TestNotify:
    def test_relays_to_the_bot(self, app):
        ExplorerRepository().add_explorer_admin("111111111111111111", "Council")
        with patch(
            "routes.api.matchmaking.relay_to_bot", return_value=({"sent": 2}, 200)
        ) as relay:
            result = explorer_notifications.notify_new_application(valid_application())

        assert result == {"sent": 2}
        method, path, payload = relay.call_args[0]
        assert method == "POST"
        assert path == "/explorer-application-notify"
        assert payload["applicant_name"] == "Ruben Sanchez"
        assert "111111111111111111" in payload["admin_discord_ids"]

    def test_skips_the_call_when_there_is_nobody_to_tell(self, app):
        # No Explorer admins configured, so the bot is never bothered.
        with patch("routes.api.matchmaking.relay_to_bot") as relay:
            assert explorer_notifications.notify_new_application(valid_application()) is None
        relay.assert_not_called()

    def test_a_down_bot_does_not_raise(self, app):
        ExplorerRepository().add_explorer_admin("111111111111111111", "Council")
        with patch(
            "routes.api.matchmaking.relay_to_bot",
            return_value=({"sent": 0, "reason": "bot_unavailable"}, 503),
        ):
            result = explorer_notifications.notify_new_application(valid_application())
        assert result["reason"] == "bot_unavailable"

    def test_an_exploding_relay_does_not_raise(self, app):
        ExplorerRepository().add_explorer_admin("111111111111111111", "Council")
        with patch(
            "routes.api.matchmaking.relay_to_bot", side_effect=RuntimeError("boom")
        ):
            assert explorer_notifications.notify_new_application(valid_application()) is None


class TestSubmissionTriggersNotification:
    def test_submitting_notifies_admins(self, applicant_session, no_geocoding):
        with patch(
            "routes.api.explorer_applications.notify_new_application_in_background"
        ) as notify:
            res = applicant_session.post(
                "/api/explorer/applications", json=valid_application()
            )
        assert res.status_code == 201
        notify.assert_called_once()
        assert notify.call_args[0][0]["first_name"] == "Ruben"

    def test_a_rejected_submission_notifies_nobody(self, applicant_session, no_geocoding):
        with patch(
            "routes.api.explorer_applications.notify_new_application_in_background"
        ) as notify:
            res = applicant_session.post(
                "/api/explorer/applications", json=valid_application(city="")
            )
        assert res.status_code == 400
        notify.assert_not_called()

    def test_an_admin_added_candidate_notifies_nobody(self, admin_session, no_geocoding):
        with patch(
            "routes.api.explorer_applications.notify_new_application_in_background"
        ) as notify:
            res = admin_session.post(
                "/api/explorer/applications/candidates", json={"discord_handle": "Kevmo"}
            )
        assert res.status_code == 201
        notify.assert_not_called()

    def test_a_failing_notification_still_lets_the_application_through(
        self, applicant_session, no_geocoding
    ):
        # The real call is backgrounded, but be explicit that the route does
        # not depend on it succeeding.
        with patch(
            "routes.api.explorer_applications.notify_new_application_in_background",
            side_effect=RuntimeError("bot exploded"),
        ):
            with pytest.raises(RuntimeError):
                applicant_session.post(
                    "/api/explorer/applications", json=valid_application()
                )

        # The row was still written before the notification was attempted.
        from repositories.explorer_applications import ExplorerApplicationRepository
        assert ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
