"""Tests for Explorer application preferred dates: parser, table and API."""

from unittest.mock import patch

import pytest

from repositories.explorer_applications import ExplorerApplicationRepository
from services.explorer_dates import (
    backfill_missing_dates,
    format_picked_dates,
    parse,
    parse_picked_dates,
)
from tests.test_explorer_applications import valid_application


@pytest.fixture(autouse=True)
def no_background_work():
    with patch("routes.api.explorer_applications._geocode_in_background"), \
         patch("routes.api.explorer_applications.lookup_attendance_in_background"), \
         patch("routes.api.explorer_applications.notify_new_application_in_background"):
        yield


@pytest.fixture()
def applicant_session(client, app):
    with client.session_transaction() as sess:
        sess["user_id"] = "555000111222333444"
        sess["username"] = "Rubonic"
        sess["auth_provider"] = "discord"
    return client


def spans(text):
    return [(w["start"], w["end"], w["precision"], w["confidence"]) for w in parse(text)]


class TestParser:
    def test_numeric_dates_with_year(self):
        assert spans("3/6/27, 4/10/27, 6/12/27") == [
            ("2027-03-06", "2027-03-06", "day", "high"),
            ("2027-04-10", "2027-04-10", "day", "high"),
            ("2027-06-12", "2027-06-12", "day", "high"),
        ]

    def test_year_assumed_is_medium(self):
        assert spans("4/10, 9/18")[0] == ("2027-04-10", "2027-04-10", "day", "medium")

    def test_month_names_and_ordinals(self):
        assert [s[0] for s in spans("April 10th, Sept 18 or 25, March 13, 2027")] == [
            "2027-03-13", "2027-04-10", "2027-09-18", "2027-09-25",
        ]

    def test_ranges(self):
        assert spans("Apr 10-11") == [("2027-04-10", "2027-04-11", "range", "medium")]
        assert spans("5/15/2027 - 5/16/2027") == [("2027-05-15", "2027-05-16", "range", "high")]

    def test_vague_answers_are_low_confidence(self):
        assert spans("mid-June") == [("2027-06-11", "2027-06-20", "week", "low")]
        assert spans("sometime in summer") == [("2027-06-01", "2027-08-31", "season", "low")]
        assert spans("May or June")[0][2:] == ("month", "low")

    def test_may_as_a_verb_is_not_a_month(self):
        assert [s[2] for s in spans("We may be able to do fall")] == ["season"]

    def test_unparseable(self):
        assert parse("TBD")[0]["precision"] == "unparsed"
        assert parse("") == []


class TestPickedDates:
    def test_valid_dates_keep_order_and_drop_blanks(self):
        days = parse_picked_dates(["2027-06-12", "", "2027-04-10", "2027-06-12"])
        assert [d.isoformat() for d in days] == ["2027-06-12", "2027-04-10"]
        assert format_picked_dates(days) == "6/12/27, 4/10/27"

    @pytest.mark.parametrize("bad", [["not a date"], ["2027-02-30"], "2027-04-10",
                                     ["2027-01-01", "2027-01-02", "2027-01-03", "2027-01-04"]])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            parse_picked_dates(bad)


class TestApi:
    def test_free_text_answer_is_parsed(self, applicant_session):
        res = applicant_session.post("/api/explorer/applications", json=valid_application())
        app_id = res.get_json()["application_id"]
        rows = ExplorerApplicationRepository().get_dates(app_id)
        assert [r["start_date"] for r in rows] == ["2027-03-06", "2027-04-10", "2027-06-12"]
        assert {r["source"] for r in rows} == {"parser"}

    def test_date_pickers_are_stored_as_applicant_dates(self, applicant_session):
        res = applicant_session.post("/api/explorer/applications", json=valid_application(
            proposed_dates="", proposed_date_list=["2027-04-10", "2027-06-12", ""],
            proposed_dates_notes="Any weekend in June works too",
        ))
        assert res.status_code == 201
        app_id = res.get_json()["application_id"]
        repo = ExplorerApplicationRepository()
        stored = repo.get_application(app_id)
        assert stored["proposed_dates"] == "4/10/27, 6/12/27"
        assert stored["proposed_dates_notes"] == "Any weekend in June works too"
        rows = repo.get_dates(app_id)
        assert [(r["start_date"], r["source"], r["confidence"]) for r in rows] == [
            ("2027-04-10", "applicant", "high"), ("2027-06-12", "applicant", "high"),
        ]

    def test_bad_picked_date_is_rejected(self, applicant_session):
        res = applicant_session.post("/api/explorer/applications", json=valid_application(
            proposed_date_list=["soon"],
        ))
        assert res.status_code == 400

    def test_notes_only_answer_is_parsed(self, applicant_session):
        res = applicant_session.post("/api/explorer/applications", json=valid_application(
            proposed_date_list=[], proposed_dates_notes="Mid-June",
        ))
        rows = ExplorerApplicationRepository().get_dates(res.get_json()["application_id"])
        assert [(r["precision"], r["source"]) for r in rows] == [("week", "parser")]

    def test_editing_dates_replaces_rows_and_prefills_pickers(self, applicant_session):
        app_id = applicant_session.post(
            "/api/explorer/applications", json=valid_application()
        ).get_json()["application_id"]
        res = applicant_session.put(f"/api/explorer/applications/mine/{app_id}", json={
            "proposed_date_list": ["2027-09-18"],
        })
        assert res.status_code == 200
        view = res.get_json()["application"]
        assert view["proposed_date_list"] == ["2027-09-18"]
        assert view["proposed_dates"] == "9/18/27"

    def test_old_vague_answer_carries_into_notes_when_editing(self, applicant_session):
        app_id = applicant_session.post("/api/explorer/applications", json=valid_application(
            proposed_dates="4/10/27 or sometime in summer",
        )).get_json()["application_id"]
        mine = applicant_session.get("/api/explorer/applications/mine").get_json()
        view = next(a for a in mine["applications"] if a["id"] == app_id)
        assert view["proposed_date_list"] == ["2027-04-10"]
        assert view["proposed_dates_notes"] == "4/10/27 or sometime in summer"

    def test_council_fixes_are_never_overwritten(self, applicant_session):
        app_id = applicant_session.post(
            "/api/explorer/applications", json=valid_application()
        ).get_json()["application_id"]
        repo = ExplorerApplicationRepository()
        repo.replace_dates(app_id, [{"start": "2027-05-01", "end": "2027-05-01",
                                     "precision": "day", "confidence": "high",
                                     "raw": "fixed"}], source="admin")
        applicant_session.put(f"/api/explorer/applications/mine/{app_id}",
                              json={"proposed_date_list": ["2027-09-18"]})
        assert [r["start_date"] for r in repo.get_dates(app_id)] == ["2027-05-01"]

    def test_admin_detail_includes_dates(self, applicant_session, admin_session):
        app_id = applicant_session.post(
            "/api/explorer/applications", json=valid_application()
        ).get_json()["application_id"]
        body = admin_session.get(f"/api/explorer/applications/{app_id}").get_json()
        assert len(body["dates"]) == 3


class TestBackfill:
    def test_fills_only_applications_without_rows(self, app):
        repo = ExplorerApplicationRepository()
        old = repo.create_application("1", {"proposed_dates": "June 12, 2027"})
        blank = repo.create_application("2", {"proposed_dates": ""})
        assert backfill_missing_dates(repo) == 1
        assert [r["start_date"] for r in repo.get_dates(old)] == ["2027-06-12"]
        assert repo.get_dates(blank) == []
        assert backfill_missing_dates(repo) == 0
