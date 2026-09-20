"""Tests for the Explorer Series host application API."""

import csv
import io
from unittest.mock import patch

import pytest

from repositories.explorer_applications import ExplorerApplicationRepository


@pytest.fixture(autouse=True)
def no_background_geocoding():
    """Keep tests off the network and out of background threads."""
    with patch("routes.api.explorer_applications._geocode_in_background") as mock:
        yield mock


@pytest.fixture()
def applicant_session(client, app):
    """A logged-in Discord user who can submit an application."""
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
        "country": "USA",
        "lgs_name": "Waterloo Games",
        "lgs_url": "https://sorcerytcg.com/stores/abc123",
        "lgs_confirmed": "No",
        "expected_attendance": "25-32",
        "proposed_dates": "3/6/27, 4/10/27, 6/12/27",
        "events_run": "Ran 2 Cornerstone events, drafts and sealed.",
        "events_run_count": 2,
        "avg_headcount": "25-50",
        "motivation": "Growing the game in Virginia.",
        "read_navigator_role": True,
        "reference_contact": "Chris Bailey",
        "anything_else": "Owner conversation pending.",
        "referral": "A few TOs have signed up.",
    }
    payload.update(overrides)
    return payload


class TestSubmitApplication:
    def test_logged_in_discord_user_can_apply(self, applicant_session):
        res = applicant_session.post("/api/explorer/applications", json=valid_application())
        assert res.status_code == 201
        body = res.get_json()
        assert body["success"] is True

        stored = ExplorerApplicationRepository().get_application(body["application_id"])
        assert stored["first_name"] == "Ruben"
        assert stored["discord_user_id"] == "555000111222333444"
        assert stored["city"] == "Mechanicsville"
        assert stored["events_run_count"] == 2
        assert stored["status"] == "pending"
        assert stored["source"] == "application"

    def test_anonymous_visitor_is_rejected(self, client):
        res = client.post("/api/explorer/applications", json=valid_application())
        assert res.status_code in (401, 403)

    def test_google_login_is_accepted(self, client):
        # Requiring Discord turned away organisers who don't use it; see
        # test_explorer_map_and_edit.py for the fuller Google coverage.
        with client.session_transaction() as sess:
            sess["user_id"] = "google_12345"
            sess["username"] = "Googler"
            sess["auth_provider"] = "google"
        res = client.post("/api/explorer/applications", json=valid_application())
        assert res.status_code == 201

    @pytest.mark.parametrize(
        "field", ["first_name", "last_name", "email", "city", "state", "lgs_name"]
    )
    def test_required_fields_are_enforced(self, applicant_session, field):
        res = applicant_session.post(
            "/api/explorer/applications", json=valid_application(**{field: ""})
        )
        assert res.status_code == 400
        assert field in res.get_json()["error"]

    def test_navigator_role_must_be_confirmed(self, applicant_session):
        res = applicant_session.post(
            "/api/explorer/applications",
            json=valid_application(read_navigator_role=False),
        )
        assert res.status_code == 400
        assert "Navigator" in res.get_json()["error"]

    def test_one_application_per_user(self, applicant_session):
        assert applicant_session.post(
            "/api/explorer/applications", json=valid_application()
        ).status_code == 201
        res = applicant_session.post(
            "/api/explorer/applications", json=valid_application()
        )
        assert res.status_code == 409

    def test_geocoding_is_kicked_off(self, applicant_session, no_background_geocoding):
        applicant_session.post("/api/explorer/applications", json=valid_application())
        no_background_geocoding.assert_called_once()
        args = no_background_geocoding.call_args[0]
        assert args[1:] == ("Mechanicsville", "Virginia", "USA")

    def test_applicant_can_read_back_their_own_application(self, applicant_session):
        applicant_session.post("/api/explorer/applications", json=valid_application())
        res = applicant_session.get("/api/explorer/applications/mine")
        assert res.status_code == 200
        assert res.get_json()["application"]["first_name"] == "Ruben"

    def test_mine_is_null_before_applying(self, applicant_session):
        res = applicant_session.get("/api/explorer/applications/mine")
        assert res.get_json()["application"] is None


class TestReviewAccess:
    def test_regular_user_cannot_list_applications(self, user_session):
        assert user_session.get("/api/explorer/applications").status_code == 403

    def test_global_admin_can_list(self, admin_session):
        assert admin_session.get("/api/explorer/applications").status_code == 200

    def test_explorer_admin_can_list(self, explorer_admin_session):
        assert explorer_admin_session.get("/api/explorer/applications").status_code == 200

    def test_regular_user_cannot_vote(self, user_session, app):
        app_id = ExplorerApplicationRepository().create_application(
            None, {"first_name": "Someone"}, source="admin_added"
        )
        res = user_session.post(
            f"/api/explorer/applications/{app_id}/vote", json={"enthusiasm": 5}
        )
        assert res.status_code == 403


class TestVoting:
    @pytest.fixture()
    def application_id(self, app):
        return ExplorerApplicationRepository().create_application(
            "111222333444555666", valid_application(), source="application"
        )

    def test_admin_can_score_an_application(self, admin_session, application_id):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/vote",
            json={"enthusiasm": 5, "track_record": 4, "local_activity": 3},
        )
        assert res.status_code == 200
        votes = res.get_json()["votes"]
        assert len(votes) == 1
        assert votes[0]["enthusiasm"] == 5
        assert votes[0]["voter_user_id"] == "admin_user_1"

    def test_revoting_replaces_the_previous_scorecard(self, admin_session, application_id):
        admin_session.post(
            f"/api/explorer/applications/{application_id}/vote",
            json={"enthusiasm": 1, "track_record": 1, "local_activity": 1},
        )
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/vote",
            json={"enthusiasm": 5, "track_record": 5, "local_activity": 5},
        )
        votes = res.get_json()["votes"]
        assert len(votes) == 1
        assert votes[0]["enthusiasm"] == 5

    def test_average_combines_multiple_reviewers(
        self, admin_session, explorer_admin_session, application_id
    ):
        repo = ExplorerApplicationRepository()
        repo.upsert_vote(application_id, "admin_user_1", "AdminUser",
                         {"enthusiasm": 5, "track_record": 5, "local_activity": 5})
        repo.upsert_vote(application_id, "explorer_admin_1", "ExplorerAdmin",
                         {"enthusiasm": 3, "track_record": 3, "local_activity": 3})

        listing = admin_session.get("/api/explorer/applications").get_json()["applications"]
        row = next(a for a in listing if a["id"] == application_id)
        assert row["vote_count"] == 2
        assert row["avg_enthusiasm"] == 4
        assert row["average_score"] == 4

    def test_blank_criteria_do_not_drag_the_average_down(self, admin_session, application_id):
        ExplorerApplicationRepository().upsert_vote(
            application_id, "admin_user_1", "AdminUser",
            {"enthusiasm": 5, "track_record": None, "local_activity": None},
        )
        listing = admin_session.get("/api/explorer/applications").get_json()["applications"]
        row = next(a for a in listing if a["id"] == application_id)
        assert row["average_score"] == 5

    def test_average_is_null_with_no_votes(self, admin_session, application_id):
        listing = admin_session.get("/api/explorer/applications").get_json()["applications"]
        row = next(a for a in listing if a["id"] == application_id)
        assert row["average_score"] is None
        assert row["vote_count"] == 0

    @pytest.mark.parametrize("score", [0, 6, -1, 99])
    def test_scores_outside_1_to_5_are_rejected(self, admin_session, application_id, score):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/vote",
            json={"enthusiasm": score},
        )
        assert res.status_code == 400

    def test_non_numeric_score_is_rejected(self, admin_session, application_id):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/vote",
            json={"enthusiasm": "great"},
        )
        assert res.status_code == 400

    def test_voting_on_a_missing_application_404s(self, admin_session):
        res = admin_session.post(
            "/api/explorer/applications/9999/vote", json={"enthusiasm": 5}
        )
        assert res.status_code == 404


class TestStatus:
    @pytest.fixture()
    def application_id(self, app):
        return ExplorerApplicationRepository().create_application(
            "111222333444555666", valid_application(), source="application"
        )

    @pytest.mark.parametrize("status", ["pre_approved", "approved", "rejected", "pending"])
    def test_admin_can_set_each_status(self, admin_session, application_id, status):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/status", json={"status": status}
        )
        assert res.status_code == 200
        stored = ExplorerApplicationRepository().get_application(application_id)
        assert stored["status"] == status

    def test_unknown_status_is_rejected(self, admin_session, application_id):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/status", json={"status": "maybe"}
        )
        assert res.status_code == 400

    def test_filter_by_status(self, admin_session, application_id):
        admin_session.post(
            f"/api/explorer/applications/{application_id}/status", json={"status": "approved"}
        )
        approved = admin_session.get(
            "/api/explorer/applications?status=approved"
        ).get_json()["applications"]
        pending = admin_session.get(
            "/api/explorer/applications?status=pending"
        ).get_json()["applications"]
        assert [a["id"] for a in approved] == [application_id]
        assert pending == []


class TestComments:
    @pytest.fixture()
    def application_id(self, app):
        return ExplorerApplicationRepository().create_application(
            "111222333444555666", valid_application(), source="application"
        )

    def test_admin_can_leave_a_note(self, admin_session, application_id):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/comments",
            json={"body": "Spoke with the LGS owner, all good."},
        )
        assert res.status_code == 201
        comments = res.get_json()["comments"]
        assert comments[0]["body"] == "Spoke with the LGS owner, all good."
        assert comments[0]["author_name"] == "AdminUser"

    def test_empty_comment_is_rejected(self, admin_session, application_id):
        res = admin_session.post(
            f"/api/explorer/applications/{application_id}/comments", json={"body": "   "}
        )
        assert res.status_code == 400

    def test_comments_show_in_the_detail_view(self, admin_session, application_id):
        admin_session.post(
            f"/api/explorer/applications/{application_id}/comments", json={"body": "First"}
        )
        detail = admin_session.get(
            f"/api/explorer/applications/{application_id}"
        ).get_json()
        assert [c["body"] for c in detail["comments"]] == ["First"]

    def test_regular_user_cannot_comment(self, user_session, application_id):
        res = user_session.post(
            f"/api/explorer/applications/{application_id}/comments", json={"body": "hi"}
        )
        assert res.status_code == 403


class TestCandidates:
    def test_admin_can_add_a_candidate_by_discord_handle(self, admin_session):
        res = admin_session.post(
            "/api/explorer/applications/candidates",
            json={"discord_handle": "Kevmo", "first_name": "Kevin",
                  "last_name": "Rodriguez", "state": "PNW"},
        )
        assert res.status_code == 201

        stored = ExplorerApplicationRepository().get_application(
            res.get_json()["application_id"]
        )
        assert stored["discord_handle"] == "Kevmo"
        assert stored["source"] == "admin_added"
        assert stored["created_by"] == "AdminUser"
        # No Discord account is tied to a hand-added candidate.
        assert stored["discord_user_id"] is None

    def test_candidate_needs_a_handle_or_a_name(self, admin_session):
        res = admin_session.post("/api/explorer/applications/candidates", json={"state": "OR"})
        assert res.status_code == 400

    def test_candidates_do_not_block_a_later_real_application(
        self, admin_session, applicant_session
    ):
        admin_session.post(
            "/api/explorer/applications/candidates", json={"discord_handle": "Rubonic"}
        )
        # Two admin-added rows both have a NULL discord_user_id and must not collide.
        admin_session.post(
            "/api/explorer/applications/candidates", json={"discord_handle": "SomeoneElse"}
        )
        res = applicant_session.post("/api/explorer/applications", json=valid_application())
        assert res.status_code == 201

    def test_candidates_can_be_scored_like_applications(self, admin_session):
        app_id = admin_session.post(
            "/api/explorer/applications/candidates", json={"discord_handle": "Kevmo"}
        ).get_json()["application_id"]
        res = admin_session.post(
            f"/api/explorer/applications/{app_id}/vote",
            json={"enthusiasm": 5, "track_record": 5, "local_activity": 5},
        )
        assert res.status_code == 200

    def test_regular_user_cannot_add_candidates(self, user_session):
        res = user_session.post(
            "/api/explorer/applications/candidates", json={"discord_handle": "Sneaky"}
        )
        assert res.status_code == 403


class TestDeleteAndGeocode:
    @pytest.fixture()
    def application_id(self, app):
        return ExplorerApplicationRepository().create_application(
            "111222333444555666", valid_application(), source="application"
        )

    def test_admin_can_delete(self, admin_session, application_id):
        assert admin_session.delete(
            f"/api/explorer/applications/{application_id}"
        ).status_code == 200
        assert ExplorerApplicationRepository().get_application(application_id) is None

    def test_deleting_removes_votes_and_comments(self, admin_session, application_id):
        repo = ExplorerApplicationRepository()
        repo.upsert_vote(application_id, "admin_user_1", "AdminUser", {"enthusiasm": 5})
        repo.add_comment(application_id, "admin_user_1", "AdminUser", "note")

        admin_session.delete(f"/api/explorer/applications/{application_id}")
        assert repo.get_votes(application_id) == []
        assert repo.get_comments(application_id) == []

    def test_delete_missing_application_404s(self, admin_session):
        assert admin_session.delete("/api/explorer/applications/9999").status_code == 404

    def test_regeocode_stores_coordinates(self, admin_session, application_id):
        with patch(
            "routes.api.explorer_applications.geocode_location", return_value=(37.6, -77.4)
        ):
            res = admin_session.post(f"/api/explorer/applications/{application_id}/geocode")
        assert res.status_code == 200

        stored = ExplorerApplicationRepository().get_application(application_id)
        assert stored["latitude"] == 37.6
        assert stored["longitude"] == -77.4
        assert stored["geocoded_at"] is not None

    def test_regeocode_reports_a_miss(self, admin_session, application_id):
        with patch("routes.api.explorer_applications.geocode_location", return_value=None):
            res = admin_session.post(f"/api/explorer/applications/{application_id}/geocode")
        assert res.status_code == 404


class TestCsvExport:
    def test_export_contains_applications_and_scores(self, admin_session, app):
        repo = ExplorerApplicationRepository()
        app_id = repo.create_application("111222333444555666", valid_application())
        repo.upsert_vote(app_id, "admin_user_1", "AdminUser",
                         {"enthusiasm": 5, "track_record": 4, "local_activity": 3})

        res = admin_session.get("/api/explorer/applications/export.csv")
        assert res.status_code == 200
        assert res.mimetype == "text/csv"

        rows = list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))
        assert len(rows) == 1
        assert rows[0]["first_name"] == "Ruben"
        assert rows[0]["discord_handle"] == "Rubonic"
        assert rows[0]["average_score"] == "4.0"

    def test_regular_user_cannot_export(self, user_session):
        assert user_session.get(
            "/api/explorer/applications/export.csv"
        ).status_code == 403


class TestGeocodingService:
    def test_builds_a_query_from_the_parts_present(self):
        from services.geocoding import build_query

        assert build_query("Mechanicsville", "Virginia", "USA") == \
            "Mechanicsville, Virginia, USA"
        assert build_query("", "Virginia", None) == "Virginia"
        assert build_query(None, None, None) == ""

    def test_blank_location_skips_the_network(self):
        from services import geocoding

        with patch("services.geocoding.requests.get") as mock_get:
            assert geocoding.geocode_location("", "", "") is None
        mock_get.assert_not_called()

    def test_service_failure_returns_none(self):
        from services import geocoding

        with patch("services.geocoding.requests.get", side_effect=OSError("down")):
            assert geocoding.geocode_location("Nowhere", "NA") is None
