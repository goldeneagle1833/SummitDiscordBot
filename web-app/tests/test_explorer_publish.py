"""Tests for publishing Explorer application decisions to applicants."""

from unittest.mock import patch

import pytest

from repositories.explorer_applications import ExplorerApplicationRepository
from repositories.store import StoreRepository

APPLICANT_ID = "555000111222333444"


@pytest.fixture()
def store(tmp_path):
    """A store.db of the test's own, standing in for the notification outbox."""
    repo = StoreRepository(tmp_path / "store.db")
    with patch("services.explorer_publish.StoreRepository", return_value=repo):
        yield repo


def make_application(discord_user_id=APPLICANT_ID, status="pending", **fields):
    repo = ExplorerApplicationRepository()
    application_id = repo.create_application(
        discord_user_id,
        {"first_name": "Ruben", "last_name": "Sanchez", "lgs_name": "Waterloo Games", **fields},
    )
    if status != "pending":
        repo.update_status(application_id, status)
    return application_id


def as_applicant(client, user_id=APPLICANT_ID):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = user_id
        sess["username"] = "Rubonic"
        sess["auth_provider"] = "discord"
    return client


def queued_dms(store):
    return store.fetch_pending_notifications(("discord_dm",))


def publish(client, confirm="publish"):
    return client.post("/api/explorer/applications/publish", json={"confirm": confirm})


class TestApplicantSeesOnlyPublishedDecisions:
    @pytest.mark.parametrize("status", ["pre_approved", "approved", "rejected"])
    def test_an_unpublished_status_reads_as_pending(self, client, app, status):
        make_application(status=status)
        application = as_applicant(client).get(
            "/api/explorer/applications/mine"
        ).get_json()["application"]
        assert application["status"] == "pending"
        assert "published_status" not in application

    def test_a_decided_application_stays_editable_until_published(self, client, app):
        make_application(status="approved")
        application = as_applicant(client).get(
            "/api/explorer/applications/mine"
        ).get_json()["application"]
        assert application["editable"] is True

        res = client.put("/api/explorer/applications/mine", json={"city": "Richmond"})
        assert res.status_code == 200
        assert res.get_json()["application"]["status"] == "pending"

    def test_publishing_locks_the_application(self, admin_session, app, store):
        make_application(status="rejected")
        publish(admin_session)

        client = as_applicant(admin_session)
        application = client.get("/api/explorer/applications/mine").get_json()["application"]
        assert application["editable"] is False
        res = client.put("/api/explorer/applications/mine", json={"city": "Richmond"})
        assert res.status_code == 409

    def test_withdrawing_a_published_decision_reopens_editing(self, admin_session, app, store):
        application_id = make_application(status="approved")
        publish(admin_session)
        ExplorerApplicationRepository().update_status(application_id, "pending")
        publish(admin_session)

        client = as_applicant(admin_session)
        res = client.put("/api/explorer/applications/mine", json={"city": "Richmond"})
        assert res.status_code == 200

    def test_a_pending_application_is_editable(self, client, app):
        make_application()
        application = as_applicant(client).get(
            "/api/explorer/applications/mine"
        ).get_json()["application"]
        assert application["editable"] is True

    def test_the_decision_shows_once_published(self, admin_session, app, store):
        make_application(status="approved")
        assert publish(admin_session).status_code == 200

        application = as_applicant(admin_session).get(
            "/api/explorer/applications/mine"
        ).get_json()["application"]
        assert application["status"] == "approved"


class TestPublishing:
    def test_requires_the_typed_confirmation(self, admin_session, app, store):
        make_application(status="approved")
        for confirm in (None, "", "yes", "publis"):
            assert publish(admin_session, confirm).status_code == 400
        assert queued_dms(store) == []

    def test_confirmation_ignores_case_and_spaces(self, admin_session, app, store):
        make_application(status="approved")
        assert publish(admin_session, "  Publish ").status_code == 200

    def test_only_explorer_admins_can_publish(self, user_session, app, store):
        make_application(status="approved")
        assert publish(user_session).status_code == 403
        assert user_session.get("/api/explorer/applications/publish").status_code == 403

    def test_explorer_admins_can_publish(self, explorer_admin_session, app, store):
        make_application(status="approved")
        assert publish(explorer_admin_session).status_code == 200

    def test_dms_and_notifies_each_decided_applicant(self, admin_session, app, store):
        make_application("111", status="approved")
        make_application("222", status="rejected")
        make_application("333", status="pending")
        make_application("444", status="pre_approved")

        result = publish(admin_session).get_json()["published"]
        assert result["approved"] == 1
        assert result["rejected"] == 1
        assert result["dms_queued"] == 2

        dms = {n["recipient"]: n for n in queued_dms(store)}
        assert set(dms) == {"111", "222"}
        assert "approved" in dms["111"]["subject"]
        assert "not able to accept" in dms["222"]["body"]

        assert len(store.list_web_notifications("111")) == 1
        assert store.list_web_notifications("111")[0]["type"] == "explorer_application"
        assert store.list_web_notifications("333") == []

    def test_publishing_twice_does_not_message_twice(self, admin_session, app, store):
        make_application(status="approved")
        publish(admin_session)
        result = publish(admin_session).get_json()["published"]
        assert result["total"] == 0
        assert len(queued_dms(store)) == 1

    def test_a_changed_decision_is_sent_again(self, admin_session, app, store):
        application_id = make_application(status="rejected")
        publish(admin_session)
        ExplorerApplicationRepository().update_status(application_id, "approved")
        publish(admin_session)
        subjects = [n["subject"] for n in queued_dms(store)]
        assert len(subjects) == 2
        assert "approved" in subjects[-1]

    def test_a_decision_taken_back_to_review_is_hidden_quietly(self, admin_session, app, store):
        application_id = make_application(status="approved")
        publish(admin_session)
        ExplorerApplicationRepository().update_status(application_id, "pending")

        preview = admin_session.get("/api/explorer/applications/publish").get_json()["pending"]
        assert preview["withdrawn"] == 1

        publish(admin_session)
        assert len(queued_dms(store)) == 1  # only the original approval
        application = as_applicant(admin_session).get(
            "/api/explorer/applications/mine"
        ).get_json()["application"]
        assert application["status"] == "pending"

    def test_google_applicants_get_a_site_notification_but_no_dm(self, admin_session, app, store):
        make_application("google_998877", status="approved")
        result = publish(admin_session).get_json()["published"]
        assert result["dms_queued"] == 0
        assert result["web_notifications"] == 1
        assert len(store.list_web_notifications("google_998877")) == 1

    def test_admin_added_candidates_are_published_without_messages(self, admin_session, app, store):
        make_application(None, status="approved")
        preview = admin_session.get("/api/explorer/applications/publish").get_json()["pending"]
        assert preview["no_account"] == 1

        result = publish(admin_session).get_json()["published"]
        assert result["approved"] == 1
        assert result["dms_queued"] == 0

    def test_preview_counts_pending_changes(self, admin_session, app, store):
        make_application("111", status="approved")
        make_application("222", status="rejected")
        make_application("333", status="pre_approved")
        preview = admin_session.get("/api/explorer/applications/publish").get_json()["pending"]
        assert preview == {
            "approved": 1, "rejected": 1, "withdrawn": 0, "no_account": 0, "total": 2,
        }
