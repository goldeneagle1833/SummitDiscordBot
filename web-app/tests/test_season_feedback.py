"""Tests for the post-season feedback survey."""

import csv
import io

import pytest

import webapp_config
from services import season_feedback
from services.season_feedback import validate_answers


@pytest.fixture(autouse=True)
def feedback_db(tmp_path, monkeypatch):
    """Keep survey responses in a throwaway feedback.db."""
    monkeypatch.setattr(webapp_config, "FEEDBACK_DB_PATH", tmp_path / "feedback.db")


@pytest.fixture()
def admin_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
        sess["username"] = "Admin"
    return client


def full_answers(**overrides):
    answers = {
        "seasons_played": "This is my first",
        "games_played": "6-15",
        "region": "Europe",
        "english_first_language": "No",
        "discord_name": "newbie#1",
        "welcome_rating": 4,
        "hardest_to_learn": ["Voice rules", "Other: Which channel to be in"],
        "match_balance": 3,
        "voice_mode": "A mix",
        "voice_games_rating": 5,
        "no_voice_games_rating": None,
        "voice_awkward": "Yes",
        "voice_awkward_detail": "Opponent spoke very quickly.",
        "negative_interactions": "Yes, minor",
        "negative_kinds": ["Slow play or stalling"],
        "reported_it": "Didn't know how",
        "bot_uses": ["Queueing for games", "Reporting results"],
        "enjoyment": 9,
        "recommend": 10,
        "final_thoughts": "Great season.",
    }
    answers.update(overrides)
    return answers


class TestSchema:
    def test_keys_are_unique(self):
        keys = [q["key"] for q in season_feedback.QUESTIONS]
        assert len(keys) == len(set(keys))

    def test_show_if_points_at_real_questions_and_options(self):
        for q in season_feedback.QUESTIONS:
            cond = q.get("show_if")
            if not cond:
                continue
            parent = season_feedback.QUESTIONS_BY_KEY[cond["key"]]
            assert set(cond["values"]) <= set(parent["options"])


class TestValidateAnswers:
    def test_keeps_valid_answers_and_fills_missing_with_null(self):
        cleaned = validate_answers(full_answers())
        assert cleaned["enjoyment"] == 9
        assert cleaned["hardest_to_learn"] == ["Voice rules", "Other: Which channel to be in"]
        assert cleaned["play_times"] is None
        assert set(cleaned) == {q["key"] for q in season_feedback.QUESTIONS}

    def test_drops_unknown_keys(self):
        cleaned = validate_answers(full_answers(evil="<script>"))
        assert "evil" not in cleaned

    def test_hidden_questions_are_nulled(self):
        cleaned = validate_answers(full_answers(seasons_played="4+", welcome_rating=2))
        assert cleaned["welcome_rating"] is None
        cleaned = validate_answers(full_answers(voice_awkward="No"))
        assert cleaned["voice_awkward_detail"] is None

    def test_required_questions(self):
        with pytest.raises(ValueError, match="enjoy"):
            validate_answers(full_answers(enjoyment=None))
        with pytest.raises(ValueError, match="seasons"):
            validate_answers(full_answers(seasons_played=""))

    def test_scale_bounds_and_types(self):
        with pytest.raises(ValueError):
            validate_answers(full_answers(enjoyment=11))
        with pytest.raises(ValueError):
            validate_answers(full_answers(enjoyment="lots"))
        assert validate_answers(full_answers(enjoyment="7"))["enjoyment"] == 7

    def test_choice_must_be_an_option(self):
        with pytest.raises(ValueError):
            validate_answers(full_answers(region="Mars"))
        with pytest.raises(ValueError):
            validate_answers(full_answers(bot_uses=["Hacking"]))

    def test_other_only_where_allowed(self):
        with pytest.raises(ValueError):
            validate_answers(full_answers(play_times=["Other: never"]))
        cleaned = validate_answers(full_answers(bot_uses=["Other:   "]))
        assert cleaned["bot_uses"] is None

    def test_text_limits(self):
        with pytest.raises(ValueError):
            validate_answers(full_answers(final_thoughts="x" * 2001))
        with pytest.raises(ValueError):
            validate_answers(full_answers(discord_name="x" * 201))
        assert validate_answers(full_answers(discord_name="   "))["discord_name"] is None


class TestSubmit:
    def test_anonymous_submission(self, client):
        res = client.post("/api/feedback/season", json={"answers": full_answers()})
        assert res.status_code == 201
        assert res.get_json()["id"] == 1

    def test_form_schema_is_public(self, client):
        res = client.get("/api/feedback/season/form")
        assert res.status_code == 200
        body = res.get_json()
        assert body["season"] == season_feedback.CURRENT_SEASON
        assert body["sections"][0]["questions"][0]["key"] == "seasons_played"

    def test_rejects_bad_answers(self, client):
        res = client.post("/api/feedback/season", json={"answers": full_answers(enjoyment=0)})
        assert res.status_code == 400
        assert "enjoyment" in res.get_json()["error"]

    def test_attaches_logged_in_user(self, client):
        with client.session_transaction() as sess:
            sess["user_id"] = 123
            sess["username"] = "Rubonic"
        client.post("/api/feedback/season", json={"answers": full_answers()})

        with client.session_transaction() as sess:
            sess["user_id"] = "admin_user_1"
        res = client.get("/api/feedback/season/responses")
        response = res.get_json()["responses"][0]
        assert response["user_id"] == "123"
        assert response["username"] == "Rubonic"


class TestAdminReview:
    def test_responses_require_admin(self, client):
        assert client.get("/api/feedback/season/responses").status_code == 403
        assert client.get("/api/feedback/season/export.csv").status_code == 403
        assert client.delete("/api/feedback/season/1").status_code == 403

    def test_responses_and_summary(self, admin_client):
        admin_client.post("/api/feedback/season", json={"answers": full_answers()})
        admin_client.post(
            "/api/feedback/season",
            json={"answers": full_answers(seasons_played="4+", enjoyment=5, bot_uses=["The shop"])},
        )

        res = admin_client.get("/api/feedback/season/responses")
        assert res.status_code == 200
        body = res.get_json()
        assert body["season"] == season_feedback.CURRENT_SEASON
        assert body["seasons"] == [season_feedback.CURRENT_SEASON]
        assert len(body["responses"]) == 2
        assert body["responses"][0]["answers"]["enjoyment"] == 5  # newest first

        summary = body["summary"]
        assert summary["enjoyment"] == {
            "type": "scale", "count": 2, "average": 7.0, "min": 1, "max": 10,
        }
        assert summary["seasons_played"]["counts"] == {"This is my first": 1, "2-3": 0, "4+": 1}
        assert summary["bot_uses"]["counts"]["Queueing for games"] == 1
        assert summary["bot_uses"]["counts"]["The shop"] == 1
        assert summary["hardest_to_learn"]["counts"]["Other"] == 1
        assert summary["final_thoughts"] == {"type": "text", "count": 2}

    def test_filter_by_season(self, admin_client):
        admin_client.post("/api/feedback/season", json={"answers": full_answers()})
        res = admin_client.get("/api/feedback/season/responses?season=Nope")
        assert res.get_json()["responses"] == []

    def test_csv_export(self, admin_client):
        admin_client.post("/api/feedback/season", json={"answers": full_answers()})
        res = admin_client.get("/api/feedback/season/export.csv")
        assert res.status_code == 200
        assert res.mimetype == "text/csv"
        assert "season-feedback-gothic-summit-season-7.csv" in res.headers["Content-Disposition"] or \
            "season-feedback-all-seasons.csv" in res.headers["Content-Disposition"]

        rows = list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))
        assert len(rows) == 1
        row = rows[0]
        assert row["season"] == season_feedback.CURRENT_SEASON
        assert row["enjoyment"] == "9"
        assert row["hardest_to_learn"] == "Voice rules; Other: Which channel to be in"
        assert row["play_times"] == ""
        assert list(row) == season_feedback.csv_columns()

    def test_csv_export_filtered_by_season(self, admin_client):
        admin_client.post("/api/feedback/season", json={"answers": full_answers()})
        res = admin_client.get("/api/feedback/season/export.csv?season=Gothic%20Summit%20Season%207")
        assert "season-feedback-gothic-summit-season-7.csv" in res.headers["Content-Disposition"]
        assert len(list(csv.DictReader(io.StringIO(res.get_data(as_text=True))))) == 1

    def test_delete(self, admin_client):
        admin_client.post("/api/feedback/season", json={"answers": full_answers()})
        assert admin_client.delete("/api/feedback/season/1").status_code == 200
        assert admin_client.delete("/api/feedback/season/1").status_code == 404
        assert admin_client.get("/api/feedback/season/responses").get_json()["responses"] == []
