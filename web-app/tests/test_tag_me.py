"""Tag me queue setting: repository and owner-only API."""

from repositories.tag_me_repo import TagMeRepository
from repositories.voice_only_repo import VoiceOnlyRepository


def _discord_user(client, user_id="123456789"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "TagPlayer"
    return client


class TestTagMeRepository:
    def test_on_by_default_and_round_trip(self, match_db):
        repo = TagMeRepository(db_path=match_db)
        assert repo.wants_tag("1") is True
        repo.set_tag_me("1", False)
        repo.set_tag_me("1", False)
        assert repo.wants_tag("1") is False
        repo.set_tag_me("1", True)
        assert repo.wants_tag("1") is True


class TestTagMeApi:
    def test_default_is_on(self, client):
        c = _discord_user(client)
        assert c.get("/api/player/123456789/queue-settings").get_json() == {
            "voice_only": False, "tag_me": True, "skill_match": False,
        }

    def test_turn_off_and_on_leaves_voice_only_alone(self, client):
        c = _discord_user(client)
        c.post("/api/player/123456789/queue-settings", json={"voice_only": True})
        resp = c.post("/api/player/123456789/queue-settings", json={"tag_me": False})
        assert resp.status_code == 200
        assert resp.get_json() == {"success": True, "tag_me": False}
        assert TagMeRepository().wants_tag("123456789") is False
        assert VoiceOnlyRepository().is_voice_only("123456789") is True
        c.post("/api/player/123456789/queue-settings", json={"tag_me": True, "voice_only": False})
        assert c.get("/api/player/123456789/queue-settings").get_json() == {
            "voice_only": False, "tag_me": True, "skill_match": False,
        }

    def test_other_players_cannot_change_it(self, client):
        c = _discord_user(client, "111")
        resp = c.post("/api/player/123456789/queue-settings", json={"tag_me": False})
        assert resp.status_code == 403
        assert TagMeRepository().wants_tag("123456789") is True

    def test_bad_bodies(self, client):
        c = _discord_user(client)
        assert c.post("/api/player/123456789/queue-settings", json={"tag_me": "no"}).status_code == 400
        assert c.post("/api/player/123456789/queue-settings", json={}).status_code == 400


class TestSkillMatchSetting:
    def test_off_by_default_and_round_trip(self, match_db):
        from repositories.skill_match_repo import SkillMatchRepository

        repo = SkillMatchRepository(db_path=match_db)
        assert repo.wants_skill_match("1") is False
        repo.set_skill_match("1", True)
        repo.set_skill_match("1", True)
        assert repo.wants_skill_match("1") is True
        repo.set_skill_match("1", False)
        assert repo.wants_skill_match("1") is False

    def test_api_turns_it_on_and_off_without_touching_other_settings(self, client):
        c = _discord_user(client)
        resp = c.post("/api/player/123456789/queue-settings", json={"skill_match": True})
        assert resp.get_json() == {"success": True, "skill_match": True}
        assert c.get("/api/player/123456789/queue-settings").get_json() == {
            "voice_only": False, "tag_me": True, "skill_match": True,
        }
        c.post("/api/player/123456789/queue-settings", json={"skill_match": False})
        assert c.get("/api/player/123456789/queue-settings").get_json()["skill_match"] is False

    def test_rejects_non_boolean_and_other_players(self, client):
        c = _discord_user(client)
        assert c.post("/api/player/123456789/queue-settings", json={"skill_match": "yes"}).status_code == 400
        c = _discord_user(client, "111")
        assert c.post("/api/player/123456789/queue-settings", json={"skill_match": True}).status_code == 403
