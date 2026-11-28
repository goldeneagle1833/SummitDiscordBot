"""Feedback auto PR: intake from Discord, claim/result API for the GitHub Action."""

import datetime
import sqlite3

import pytest

import webapp_config
from repositories.feedback import FeedbackRepository

KEY = "automation-key-abc"
API_KEY = "test-api-key-123"


@pytest.fixture(autouse=True)
def feedback_db(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_config, "FEEDBACK_DB_PATH", tmp_path / "feedback.db")
    import repositories.feedback as feedback_module
    monkeypatch.setattr(feedback_module, "FEEDBACK_DB_PATH", tmp_path / "feedback.db")
    monkeypatch.setattr(webapp_config, "FEEDBACK_AUTOMATION_KEY", KEY)
    return tmp_path / "feedback.db"


@pytest.fixture()
def admin_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
        sess["username"] = "Admin"
    return client


def claim(client, limit=3, key=KEY):
    return client.post(
        "/api/feedback/automation/claim",
        json={"limit": limit},
        headers={"X-Feedback-Automation-Key": key},
    )


def result(client, fid, **body):
    return client.post(
        f"/api/feedback/automation/{fid}/result",
        json=body,
        headers={"X-Feedback-Automation-Key": KEY},
    )


class TestMigration:
    def test_old_table_gets_new_columns(self, feedback_db):
        conn = sqlite3.connect(feedback_db)
        conn.execute("""CREATE TABLE feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL, description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'backlog', user_id TEXT, username TEXT,
            admin_notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            resolved_at TEXT, notified INTEGER NOT NULL DEFAULT 0)""")
        conn.execute("""INSERT INTO feedback (title, description, created_at, updated_at)
                        VALUES ('old', 'old item', '2026-01-01', '2026-01-01')""")
        conn.commit()
        conn.close()
        repo = FeedbackRepository(feedback_db)
        old = repo.get_by_id(1)
        assert old["source"] == "site"
        assert old["auto_status"] is None  # old items are not auto-processed
        assert repo.claim_for_automation(5) == []


class TestClaimAndResult:
    def test_new_site_feedback_waits_for_the_action(self, client):
        resp = client.post("/api/feedback/feedback", json={
            "type": "bug_report", "title": "Button broken", "description": "It does nothing",
        })
        assert resp.status_code == 201
        data = claim(client).get_json()
        assert [i["title"] for i in data["items"]] == ["Button broken"]
        item = data["items"][0]
        assert "username" not in item and "user_id" not in item
        # Claimed items are not handed out twice.
        assert claim(client).get_json()["items"] == []

    def test_wrong_key_is_refused(self, client):
        assert claim(client, key="nope").status_code == 401

    def test_no_key_configured_means_off(self, client, monkeypatch):
        monkeypatch.setattr(webapp_config, "FEEDBACK_AUTOMATION_KEY", "")
        assert claim(client).status_code == 404

    def test_closed_items_are_skipped(self, client):
        repo = FeedbackRepository()
        fid = repo.create("general", "Done already", "x")
        repo.update_status(fid, "not_planned")
        assert claim(client).get_json()["items"] == []

    def test_stale_claim_is_handed_out_again(self, client, feedback_db):
        repo = FeedbackRepository()
        fid = repo.create("general", "Retry me", "x")
        assert claim(client).get_json()["items"][0]["id"] == fid
        old = (datetime.datetime.now() - datetime.timedelta(hours=7)).isoformat()
        conn = sqlite3.connect(feedback_db)
        conn.execute("UPDATE feedback SET auto_updated_at = ? WHERE id = ?", (old, fid))
        conn.commit()
        conn.close()
        assert claim(client).get_json()["items"][0]["id"] == fid

    def test_limit_is_capped(self, client):
        repo = FeedbackRepository()
        for n in range(15):
            repo.create("general", f"item {n}", "x")
        assert len(claim(client, limit=50).get_json()["items"]) == 10

    def test_recent_list_for_dedupe(self, client):
        repo = FeedbackRepository()
        first = repo.create("general", "Dark mode", "please")
        claim(client, limit=1)
        repo.create("general", "Dark mode please", "again")
        data = claim(client, limit=1).get_json()
        assert any(r["id"] == first for r in data["recent"])

    def test_result_saves_pr_link(self, client, admin_client):
        fid = FeedbackRepository().create("general", "Add a thing", "x")
        claim(client)
        resp = result(client, fid, status="drafted",
                      pr_url="https://github.com/o/r/pull/9", note="Drafted")
        assert resp.status_code == 200
        item = FeedbackRepository().get_by_id(fid)
        assert item["auto_status"] == "drafted"
        assert item["auto_pr_url"] == "https://github.com/o/r/pull/9"
        # The admin board gets the new fields.
        items = admin_client.get("/api/feedback/feedback").get_json()["items"]
        assert items[0]["auto_pr_url"] == "https://github.com/o/r/pull/9"

    def test_result_rejects_bad_values(self, client):
        fid = FeedbackRepository().create("general", "x", "x")
        assert result(client, fid, status="merged").status_code == 400
        assert result(client, fid, status="drafted",
                      pr_url="https://evil.example/x").status_code == 400
        assert result(client, 999, status="failed").status_code == 404

    def test_admin_can_queue_an_old_item(self, admin_client, client):
        repo = FeedbackRepository()
        fid = repo.create("general", "Old", "x")
        repo.set_auto_result(fid, "failed", note="broke")
        resp = admin_client.post(f"/api/feedback/feedback/{fid}/auto-queue")
        assert resp.status_code == 200
        assert resp.get_json()["item"]["auto_status"] == "pending"
        assert claim(client).get_json()["items"][0]["id"] == fid

    def test_queue_needs_admin(self, client):
        fid = FeedbackRepository().create("general", "Old", "x")
        assert client.post(f"/api/feedback/feedback/{fid}/auto-queue").status_code in (401, 403)


class TestDiscordIntake:
    def post(self, client, **body):
        return client.post("/api/feedback/feedback/intake", json=body,
                           headers={"X-API-Key": API_KEY})

    def test_discord_post_lands_on_the_board(self, client):
        resp = self.post(client, title="Bot ignores me", description="When I !lfg",
                         type="bug_report", source="discord", source_ref="123",
                         username="player1", user_id="42")
        assert resp.status_code == 201
        item = FeedbackRepository().get_by_id(resp.get_json()["id"])
        assert item["source"] == "discord"
        assert item["auto_status"] == "pending"
        assert item["username"] == "player1"

    def test_same_message_is_saved_once(self, client):
        first = self.post(client, title="a", description="b", source_ref="777")
        again = self.post(client, title="a", description="b", source_ref="777")
        assert again.get_json()["duplicate"] is True
        assert again.get_json()["id"] == first.get_json()["id"]

    def test_needs_bot_key(self, client):
        resp = client.post("/api/feedback/feedback/intake", json={"title": "a", "description": "b"})
        assert resp.status_code == 401

    def test_unknown_type_becomes_general(self, client):
        resp = self.post(client, title="a", description="b", type="weird")
        assert FeedbackRepository().get_by_id(resp.get_json()["id"])["type"] == "general"
