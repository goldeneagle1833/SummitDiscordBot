"""Admin Queue Settings counts: on/off per setting, defaults for players who never changed it."""

import sqlite3

import pytest


@pytest.fixture
def admin(client, elo_db, match_db, monkeypatch):
    import routes.api.admin as admin_routes

    monkeypatch.setattr(admin_routes, "ELO_DB_PATH", elo_db)
    monkeypatch.setattr(admin_routes, "MATCH_RECORDS_DB_PATH", match_db)
    conn = sqlite3.connect(str(elo_db))
    conn.executemany(
        "INSERT OR REPLACE INTO overall_standings (user_id, user_display_name) VALUES (?, ?)",
        [("100", "A"), ("200", "B"), ("300", "C"), ("google_x", "G")],
    )
    conn.commit()
    conn.close()
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
        sess["username"] = "Admin"
    return client


def _counts(resp):
    data = resp.get_json()
    return data["players"], {s["key"]: (s["on"], s["off"]) for s in data["settings"]}


def test_defaults_when_nobody_changed_anything(admin):
    players, counts = _counts(admin.get("/api/admin/queue-settings"))
    assert players == 3  # Discord ids only
    assert counts == {"voice_only": (0, 3), "tag_me": (3, 0), "skill_match": (0, 3)}


def test_counts_follow_the_saved_settings(admin):
    from repositories.skill_match_repo import SkillMatchRepository
    from repositories.tag_me_repo import TagMeRepository
    from repositories.voice_only_repo import VoiceOnlyRepository

    SkillMatchRepository().set_skill_match("100", True)
    SkillMatchRepository().set_skill_match("200", True)
    TagMeRepository().set_tag_me("300", False)
    VoiceOnlyRepository().set_voice_only("100", True)

    resp = admin.get("/api/admin/queue-settings")
    players, counts = _counts(resp)
    assert counts == {"voice_only": (1, 2), "tag_me": (2, 1), "skill_match": (2, 1)}
    skill = next(s for s in resp.get_json()["settings"] if s["key"] == "skill_match")
    assert {p["user_id"] for p in skill["players"]} == {"100", "200"}
    assert skill["changed_last_7_days"] == 2


def test_admin_only(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "123"
    assert client.get("/api/admin/queue-settings").status_code in (401, 403)
