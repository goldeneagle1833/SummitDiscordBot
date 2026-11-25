"""Admin Most Pinned Pages tile: saved top bar picks, no user ids."""

from repositories.user_profiles import UserProfileRepository


URL = "/api/admin/nav-picks"


def _login(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = uid


def test_admin_only(client, match_db):
    assert client.get(URL).status_code in (401, 403)
    _login(client, "someone")
    assert client.get(URL).status_code == 403


def test_returns_saved_lists_without_ids(client, match_db):
    repo = UserProfileRepository(match_db)
    for uid in ("111", "222", "333"):
        repo.upsert_profile(uid, f"Player {uid}")
    repo.set_nav_preferences("111", ["Feedback", "Community", "__v2"])
    repo.set_nav_preferences("222", ["Feedback", "__v2"])
    _login(client, "admin_user_1")
    body = client.get(URL).get_json()
    assert body["profiles"] == 3
    assert sorted(body["saves"]) == [["Feedback", "Community", "__v2"], ["Feedback", "__v2"]]
    assert "111" not in str(body) and "Player" not in str(body)
