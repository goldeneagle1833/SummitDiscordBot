"""Tests for the events map toggle, applicant self-edit and LGS attendance."""

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from repositories.explorer import ExplorerRepository
from repositories.explorer_applications import ExplorerApplicationRepository
from services import lgs_attendance


@pytest.fixture(autouse=True)
def quiet_background(app):
    """Keep submissions off the network."""
    with (
        patch("routes.api.explorer_applications._geocode_in_background"),
        patch("routes.api.explorer_applications.notify_new_application_in_background"),
        patch("routes.api.explorer_applications.lookup_attendance_in_background"),
    ):
        yield


@pytest.fixture()
def applicant_session(client, app):
    with client.session_transaction() as sess:
        sess["user_id"] = "555000111222333444"
        sess["username"] = "Rubonic"
        sess["auth_provider"] = "discord"
    return client


@pytest.fixture()
def google_session(client, app):
    with client.session_transaction() as sess:
        sess["user_id"] = "google_998877"
        sess["username"] = "Some Googler"
        sess["auth_provider"] = "google"
    return client


def login_as(client, user_id, username, provider="discord"):
    """Swap the session on an existing client.

    admin_session and applicant_session are the same underlying client, so a
    test must not request both — the later fixture just overwrites the session.
    """
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["auth_provider"] = provider


def valid_application(**overrides):
    payload = {
        "first_name": "Ruben", "last_name": "Sanchez", "email": "r@example.com",
        "city": "Mechanicsville", "state": "Virginia", "lgs_name": "Waterloo Games",
        "read_navigator_role": True,
    }
    payload.update(overrides)
    return payload


class TestEventsMapToggle:
    def test_map_is_off_until_an_admin_turns_it_on(self, client):
        assert client.get("/api/explorer/settings").get_json()["events_map_enabled"] is False

    def test_admin_can_turn_it_on_and_off(self, admin_session):
        on = admin_session.post("/api/explorer/settings", json={"events_map_enabled": True})
        assert on.get_json()["events_map_enabled"] is True
        assert admin_session.get("/api/explorer/settings").get_json()["events_map_enabled"] is True

        off = admin_session.post("/api/explorer/settings", json={"events_map_enabled": False})
        assert off.get_json()["events_map_enabled"] is False

    def test_regular_user_cannot_toggle_it(self, user_session):
        res = user_session.post("/api/explorer/settings", json={"events_map_enabled": True})
        assert res.status_code == 403

    def test_missing_field_is_rejected(self, admin_session):
        assert admin_session.post("/api/explorer/settings", json={}).status_code == 400

    def test_events_map_returns_nothing_while_off(self, client, admin_session, elo_db):
        body = client.get("/api/explorer/events-map").get_json()
        assert body == {"enabled": False, "events": []}

    def test_events_map_serves_geocoded_events_when_on(self, client, admin_session):
        repo = ExplorerRepository()
        season = repo.create_season("Test Series", None, "{}")
        event = repo.create_event(
            season_id=season["id"], event_external_id="evt-1", event_name="Cornerstone",
            event_date="2026-05-01", total_players=24, play_format="Constructed",
            venue_name="Waterloo Games", source_url="https://sorcerytcg.com/events/1",
        )
        repo.set_event_coordinates(event["id"], 37.6, -77.4)
        admin_session.post("/api/explorer/settings", json={"events_map_enabled": True})

        body = client.get("/api/explorer/events-map").get_json()
        assert body["enabled"] is True
        assert [e["event_name"] for e in body["events"]] == ["Cornerstone"]
        assert body["events"][0]["latitude"] == 37.6

    def test_ungeocoded_events_are_listed_for_admins(self, admin_session):
        repo = ExplorerRepository()
        season = repo.create_season("Test Series", None, "{}")
        repo.create_event(
            season_id=season["id"], event_external_id="evt-2", event_name="Unplaced",
            event_date="2026-05-01", total_players=8, play_format=None,
            venue_name="Somewhere", source_url=None,
        )
        body = admin_session.get("/api/explorer/events/unmapped").get_json()
        assert [e["event_name"] for e in body["events"]] == ["Unplaced"]

    def test_admin_can_place_an_event(self, admin_session):
        repo = ExplorerRepository()
        season = repo.create_season("Test Series", None, "{}")
        event = repo.create_event(
            season_id=season["id"], event_external_id="evt-3", event_name="Placeable",
            event_date=None, total_players=None, play_format=None,
            venue_name="Waterloo Games", source_url=None,
        )
        with patch("services.geocoding.geocode_location", return_value=(1.5, 2.5)):
            res = admin_session.post(f"/api/explorer/events/{event['id']}/geocode")
        assert res.status_code == 200
        assert repo.get_event(event["id"])["latitude"] == 1.5

    def test_placing_an_event_with_no_venue_is_rejected(self, admin_session):
        repo = ExplorerRepository()
        season = repo.create_season("Test Series", None, "{}")
        event = repo.create_event(
            season_id=season["id"], event_external_id="evt-4", event_name="No venue",
            event_date=None, total_players=None, play_format=None,
            venue_name=None, source_url=None,
        )
        assert admin_session.post(
            f"/api/explorer/events/{event['id']}/geocode"
        ).status_code == 400


class TestGoogleApplicants:
    def test_a_google_user_can_apply(self, google_session):
        res = google_session.post("/api/explorer/applications", json=valid_application())
        assert res.status_code == 201

        stored = ExplorerApplicationRepository().get_by_discord_user("google_998877")
        assert stored["first_name"] == "Ruben"

    def test_a_google_display_name_is_not_taken_as_a_discord_handle(self, google_session):
        google_session.post("/api/explorer/applications", json=valid_application())
        stored = ExplorerApplicationRepository().get_by_discord_user("google_998877")
        assert not stored["discord_handle"]

    def test_a_discord_handle_is_still_filled_in_for_discord_users(self, applicant_session):
        applicant_session.post("/api/explorer/applications", json=valid_application())
        stored = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        assert stored["discord_handle"] == "Rubonic"


class TestApplicantEdit:
    def _apply(self, session):
        session.post("/api/explorer/applications", json=valid_application())
        return ExplorerApplicationRepository().get_by_discord_user("555000111222333444")

    def test_applicant_can_correct_their_answers(self, applicant_session):
        self._apply(applicant_session)
        res = applicant_session.put(
            "/api/explorer/applications/mine", json={"city": "Richmond", "motivation": "Updated"}
        )
        assert res.status_code == 200

        stored = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        assert stored["city"] == "Richmond"
        assert stored["motivation"] == "Updated"
        # Untouched answers survive a partial edit.
        assert stored["lgs_name"] == "Waterloo Games"

    def test_editing_cannot_blank_a_required_answer(self, applicant_session):
        self._apply(applicant_session)
        res = applicant_session.put("/api/explorer/applications/mine", json={"city": ""})
        assert res.status_code == 400
        stored = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        assert stored["city"] == "Mechanicsville"

    def test_editing_cannot_change_status_or_provenance(self, applicant_session):
        application = self._apply(applicant_session)
        applicant_session.put(
            "/api/explorer/applications/mine",
            json={"status": "approved", "source": "admin_added", "city": "Richmond"},
        )
        stored = ExplorerApplicationRepository().get_application(application["id"])
        assert stored["status"] == "pending"
        assert stored["source"] == "application"

    def test_a_pre_approved_application_is_still_editable(self, applicant_session):
        application = self._apply(applicant_session)
        ExplorerApplicationRepository().update_status(application["id"], "pre_approved")
        assert applicant_session.put(
            "/api/explorer/applications/mine", json={"city": "Richmond"}
        ).status_code == 200

    @pytest.mark.parametrize("status", ["approved", "rejected"])
    def test_a_decided_application_is_locked(self, applicant_session, status):
        application = self._apply(applicant_session)
        ExplorerApplicationRepository().update_status(application["id"], status)
        res = applicant_session.put(
            "/api/explorer/applications/mine", json={"city": "Richmond"}
        )
        assert res.status_code == 409

    def test_moving_town_re_places_the_pin(self, applicant_session):
        self._apply(applicant_session)
        with patch("routes.api.explorer_applications._geocode_in_background") as geocode:
            applicant_session.put("/api/explorer/applications/mine", json={"city": "Richmond"})
        geocode.assert_called_once()

    def test_an_edit_that_does_not_move_skips_geocoding(self, applicant_session):
        self._apply(applicant_session)
        with patch("routes.api.explorer_applications._geocode_in_background") as geocode:
            applicant_session.put(
                "/api/explorer/applications/mine", json={"motivation": "Just tidying up"}
            )
        geocode.assert_not_called()

    def test_editing_without_an_application_404s(self, applicant_session):
        assert applicant_session.put(
            "/api/explorer/applications/mine", json={"city": "Richmond"}
        ).status_code == 404

    def test_anonymous_visitors_cannot_edit(self, client):
        assert client.put(
            "/api/explorer/applications/mine", json={"city": "Richmond"}
        ).status_code in (401, 403)

    def test_one_applicant_cannot_edit_another(self, applicant_session, client):
        self._apply(applicant_session)
        with client.session_transaction() as sess:
            sess["user_id"] = "999888777666555444"
            sess["username"] = "Someone Else"
            sess["auth_provider"] = "discord"
        # They have no application of their own, and /mine is scoped to them.
        assert client.put(
            "/api/explorer/applications/mine", json={"city": "Hacked"}
        ).status_code == 404
        stored = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        assert stored["city"] == "Mechanicsville"


def venue_payload(days_ago_counts):
    today = date.today()
    return {
        "store_name": "Waterloo Games",
        "events": [
            {"date": (today - timedelta(days=days)).isoformat(), "player_count": count}
            for days, count in days_ago_counts
        ],
    }


class TestLgsAttendance:
    def test_median_over_the_window(self):
        summary = lgs_attendance.summarise(
            venue_payload([(10, 20), (40, 30), (70, 25)])
        )
        assert summary["lgs_median_players"] == 25
        assert summary["lgs_event_count"] == 3
        assert summary["lgs_store_name"] == "Waterloo Games"

    def test_events_older_than_nine_months_are_ignored(self):
        summary = lgs_attendance.summarise(
            venue_payload([(10, 10), (400, 100)])
        )
        assert summary["lgs_event_count"] == 1
        assert summary["lgs_median_players"] == 10

    def test_events_without_a_headcount_are_ignored(self):
        payload = venue_payload([(10, 20)])
        payload["events"].append({"date": date.today().isoformat(), "player_count": None})
        assert lgs_attendance.summarise(payload)["lgs_event_count"] == 1

    def test_a_store_with_no_recent_events_reports_why(self):
        summary = lgs_attendance.summarise(venue_payload([(400, 50)]))
        assert summary["lgs_median_players"] is None
        assert "9 months" in summary["lgs_lookup_error"]

    def test_history_is_stored_oldest_first_for_the_chart(self):
        summary = lgs_attendance.summarise(venue_payload([(10, 5), (100, 9), (50, 7)]))
        history = json.loads(summary["lgs_history"])
        assert [h["player_count"] for h in history] == [9, 7, 5]

    def test_a_non_url_is_skipped_entirely(self, app):
        # Applicants are told to type "not registered" when there is no page.
        assert lgs_attendance.lookup_attendance(1, "not registered") is None

    def test_submission_kicks_off_the_lookup(self, applicant_session):
        with patch(
            "routes.api.explorer_applications.lookup_attendance_in_background"
        ) as lookup:
            applicant_session.post(
                "/api/explorer/applications",
                json=valid_application(lgs_url="https://sorcerytcg.com/stores/abc"),
            )
        lookup.assert_called_once()
        assert lookup.call_args[0][1] == "https://sorcerytcg.com/stores/abc"

    def test_admin_can_recheck_a_store(self, applicant_session):
        applicant_session.post(
            "/api/explorer/applications",
            json=valid_application(lgs_url="https://sorcerytcg.com/stores/abc"),
        )
        application = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        admin_session = applicant_session
        login_as(admin_session, "admin_user_1", "AdminUser")

        with patch(
            "services.explorer.ExplorerService.fetch_venue_attendance",
            return_value=venue_payload([(10, 20), (40, 30)]),
        ):
            res = admin_session.post(
                f"/api/explorer/applications/{application['id']}/lgs-attendance"
            )
        assert res.status_code == 200
        assert res.get_json()["application"]["lgs_median_players"] == 25

    def test_rechecking_without_a_store_link_is_rejected(self, applicant_session):
        applicant_session.post("/api/explorer/applications", json=valid_application())
        application = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        admin_session = applicant_session
        login_as(admin_session, "admin_user_1", "AdminUser")
        res = admin_session.post(
            f"/api/explorer/applications/{application['id']}/lgs-attendance"
        )
        assert res.status_code == 400

    def test_an_unreachable_store_is_recorded_not_raised(self, applicant_session):
        applicant_session.post(
            "/api/explorer/applications",
            json=valid_application(lgs_url="https://sorcerytcg.com/stores/abc"),
        )
        application = ExplorerApplicationRepository().get_by_discord_user("555000111222333444")
        admin_session = applicant_session
        login_as(admin_session, "admin_user_1", "AdminUser")

        with patch(
            "services.explorer.ExplorerService.fetch_venue_attendance",
            side_effect=OSError("network down"),
        ):
            res = admin_session.post(
                f"/api/explorer/applications/{application['id']}/lgs-attendance"
            )
        assert res.status_code == 200
        assert res.get_json()["application"]["lgs_lookup_error"]

    def test_regular_users_cannot_recheck(self, user_session):
        assert user_session.post(
            "/api/explorer/applications/1/lgs-attendance"
        ).status_code == 403
