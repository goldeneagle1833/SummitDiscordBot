"""Voice-only queue setting: repository and owner-only API."""

from repositories.voice_only_repo import VoiceOnlyRepository


def _discord_user(client, user_id="123456789"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "VoicePlayer"
    return client


class TestVoiceOnlyRepository:
    def test_round_trip(self, match_db):
        repo = VoiceOnlyRepository(db_path=match_db)
        assert repo.is_voice_only("1") is False
        repo.set_voice_only("1", True)
        repo.set_voice_only("1", True)
        assert repo.is_voice_only("1") is True
        repo.set_voice_only("1", False)
        assert repo.is_voice_only("1") is False


class TestQueueSettingsApi:
    def test_requires_login(self, client):
        assert client.get("/api/player/123456789/queue-settings").status_code == 401

    def test_owner_turns_voice_only_on_and_off(self, client):
        c = _discord_user(client)
        assert c.get("/api/player/123456789/queue-settings").get_json() == {"voice_only": False}
        resp = c.post("/api/player/123456789/queue-settings", json={"voice_only": True})
        assert resp.status_code == 200
        assert VoiceOnlyRepository().is_voice_only("123456789") is True
        assert c.get("/api/player/123456789/queue-settings").get_json() == {"voice_only": True}
        c.post("/api/player/123456789/queue-settings", json={"voice_only": False})
        assert VoiceOnlyRepository().is_voice_only("123456789") is False

    def test_other_players_cannot_change_it(self, client):
        c = _discord_user(client, "111")
        resp = c.post("/api/player/123456789/queue-settings", json={"voice_only": True})
        assert resp.status_code == 403
        assert VoiceOnlyRepository().is_voice_only("123456789") is False

    def test_google_accounts_have_no_queue_settings(self, client):
        c = _discord_user(client, "google_555")
        assert c.get("/api/player/google_555/queue-settings").status_code == 403

    def test_bad_body(self, client):
        c = _discord_user(client)
        resp = c.post("/api/player/123456789/queue-settings", json={"voice_only": "yes"})
        assert resp.status_code == 400
