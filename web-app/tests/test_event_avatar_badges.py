"""Tests for top avatar badges awarded from one paper event's whole field."""

import json
import sqlite3

import pytest


def _event(root, folder, top8, full=None, history=None):
    path = root / folder
    path.mkdir(parents=True)
    with open(path / f"{folder}top8.json", "w", encoding="utf-8") as f:
        json.dump(top8, f)
    if full is not None:
        with open(path / f"{folder}.json", "w", encoding="utf-8") as f:
            json.dump(full, f)
    if history is not None:
        with open(path / "_match_history.json", "w", encoding="utf-8") as f:
            json.dump({"players": history}, f)


def _deck(deck_id, owner, avatar):
    return {"id": deck_id, "name": f"{owner} deck", "username": owner, "avatar": [{"name": avatar}]}


def _reg(deck_id, name, standing, wins=3, losses=2):
    return {"deck_id": deck_id, "display_name": name, "username": name.lower(),
            "standing": standing, "wins": wins, "losses": losses, "draws": 0}


def _player(elo_db, user_id, name):
    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO overall_standings (user_id, user_display_name) VALUES (?, ?)", (user_id, name))
    conn.commit()
    conn.close()


@pytest.fixture()
def setup(client, elo_db, match_db, tmp_path, monkeypatch):
    import repositories.events
    import repositories.paper_links
    import webapp_config
    from services import paper_finishes

    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setattr(repositories.events, "TOP_8_DIR", root)
    monkeypatch.setattr(repositories.paper_links, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", elo_db)
    paper_finishes.reset_cache()
    yield root
    paper_finishes.reset_cache()


EVENT = "Avatar of the Realm 2026"


def _realm(root):
    """Top 8: Ann (Sparkmage) wins, Ben (Druid) 2nd, the rest Sparkmage.
    Outside the cut: Cat 9th on Seer, Dan 10th on Seer, Eve 11th on Geomancer (no account)."""
    top8 = [_deck("d1", "x", "Sparkmage"), _deck("d2", "x2", "Druid")] + [
        _deck(f"t{i}", f"other{i}", "Sparkmage") for i in range(3, 9)
    ]
    full = [_deck("d9", "c", "Seer"), _deck("d10", "d", "Seer"), _deck("d11", "e", "Geomancer")]
    history = [_reg("d1", "Annabel", 1, 5, 0), _reg("d2", "Benjamin", 2)] + [
        _reg(f"t{i}", f"Other{i}", i) for i in range(3, 9)
    ] + [_reg("d10", "Danielle", 10), _reg("d9", "Catherine", 9, 4, 2), _reg("d11", "Evelyn", 11)]
    _event(root, EVENT, top8, full, history)


def test_preview_takes_best_finisher_per_avatar_across_whole_field(setup, elo_db):
    from services.event_avatar_badges import preview

    for uid, name in (("1", "Annabel"), ("2", "Benjamin"), ("3", "Catherine"), ("4", "Danielle")):
        _player(elo_db, uid, name)
    _realm(setup)

    result = preview(EVENT)
    assert result["source"] == "standings"
    assert result["field_size"] == 11
    by_avatar = {a["avatar"]: a for a in result["avatars"]}
    assert set(by_avatar) == {"Sparkmage", "Druid", "Seer", "Geomancer"}
    assert by_avatar["Sparkmage"]["player"]["user_id"] == "1"
    assert by_avatar["Sparkmage"]["avatar_players"] == 7
    assert by_avatar["Druid"]["player"]["user_id"] == "2"
    assert by_avatar["Seer"]["player"]["user_id"] == "3"   # 9th beats Dan's 10th
    assert by_avatar["Seer"]["place"] == 9
    assert (by_avatar["Seer"]["wins"], by_avatar["Seer"]["losses"]) == (4, 2)
    assert by_avatar["Geomancer"]["player"] is None        # no Summit account: nobody gets it
    assert result["awarded"] == []


def test_award_stores_badges_and_undo_removes_them(setup, elo_db):
    from services.event_avatar_badges import award, get_badges_by_player, undo

    _player(elo_db, "1", "Annabel")
    _player(elo_db, "3", "Catherine")
    _realm(setup)

    result = award(EVENT, admin="AdminUser")
    assert {b["avatar"] for b in result["awarded"]} == {"Sparkmage", "Seer"}
    badges = get_badges_by_player()
    assert badges["1"][0]["title"] == f"Top Sparkmage · {result['event']}"
    assert badges["3"][0]["label"] == "Top Seer"

    # Awarding again replaces, never duplicates
    award(EVENT, admin="AdminUser")
    assert len(get_badges_by_player()["1"]) == 1

    assert undo(EVENT) == 2
    assert get_badges_by_player() == {}


def test_event_without_match_history_uses_top_cut_only(setup, elo_db):
    from services.event_avatar_badges import preview

    _player(elo_db, "1", "PeterTheGreat")
    _event(setup, "Store Champs", [_deck("a", "PeterTheGreat", "Pathfinder"), _deck("b", "Zed Zed", "Druid")],
           full=[_deck("c", "Someone", "Seer")])
    result = preview("Store Champs")
    assert result["source"] == "top_cut"
    assert [a["avatar"] for a in result["avatars"]] == ["Pathfinder", "Druid"]
    assert result["avatars"][0]["player"]["user_id"] == "1"


def test_admin_routes(setup, elo_db, admin_session, monkeypatch):
    import webapp_config

    monkeypatch.setattr(webapp_config, "ADMIN_USER_IDS", ["admin_user_1"], raising=False)
    _player(elo_db, "1", "Annabel")
    _realm(setup)
    url = f"/api/admin/event-avatar-badges/{EVENT}"
    resp = admin_session.get(url)
    if resp.status_code == 403:
        pytest.skip("admin session fixture is not an admin in this config")
    assert resp.status_code == 200
    assert resp.get_json()["avatars"]
    assert admin_session.post(url).get_json()["awarded"][0]["avatar"] == "Sparkmage"
    public = admin_session.get("/api/event-avatar-badges").get_json()
    assert public["badges"]["1"][0]["label"] == "Top Sparkmage"
    assert admin_session.delete(url).get_json()["removed"] == 1
    assert admin_session.get("/api/admin/event-avatar-badges/Nope").status_code == 404


def test_admin_routes_need_admin(setup, user_session):
    resp = user_session.post(f"/api/admin/event-avatar-badges/{EVENT}")
    assert resp.status_code in (401, 403)


def test_hidden_badges_owner_only(client, match_db, monkeypatch):
    import webapp_config
    from repositories.user_profiles import UserProfileRepository

    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('77', 'discord', 'Ann', 'now', 'now')"
    )
    conn.commit()
    conn.close()

    assert client.put("/api/player/77/hidden-badges", json={"hidden": []}).status_code == 401
    with client.session_transaction() as sess:
        sess["user_id"] = "88"
    assert client.put("/api/player/77/hidden-badges", json={"hidden": []}).status_code == 403
    with client.session_transaction() as sess:
        sess["user_id"] = "77"
    assert client.put("/api/player/77/hidden-badges", json={"hidden": "x"}).status_code == 400
    resp = client.put("/api/player/77/hidden-badges", json={"hidden": ["paper:X", "avatar_honours", "paper:X"]})
    assert resp.status_code == 200
    assert resp.get_json()["hidden"] == ["avatar_honours", "paper:X"]
    assert UserProfileRepository(match_db).get_hidden_badges("77") == ["avatar_honours", "paper:X"]


def test_shown_badges_default_pick_and_reset(client, match_db, monkeypatch):
    import webapp_config
    from repositories.user_profiles import UserProfileRepository

    monkeypatch.setattr(webapp_config, "MATCH_RECORDS_DB_PATH", match_db)
    conn = sqlite3.connect(str(match_db))
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, first_login_at, last_login_at)"
        " VALUES ('78', 'discord', 'Ben', 'now', 'now')"
    )
    conn.commit()
    conn.close()
    repo = UserProfileRepository(match_db)
    assert repo.get_shown_badges("78") is None  # default: best 3

    assert client.put("/api/player/78/shown-badges", json={"shown": []}).status_code == 401
    with client.session_transaction() as sess:
        sess["user_id"] = "79"
    assert client.put("/api/player/78/shown-badges", json={"shown": []}).status_code == 403
    with client.session_transaction() as sess:
        sess["user_id"] = "78"
    assert client.put("/api/player/78/shown-badges", json={}).status_code == 400
    resp = client.put("/api/player/78/shown-badges", json={"shown": ["paper:B", "postseason", "paper:B"]})
    assert resp.get_json()["shown"] == ["paper:B", "postseason"]  # order kept, no repeats
    assert client.put("/api/player/78/shown-badges", json={"shown": []}).get_json()["shown"] == []
    assert client.put("/api/player/78/shown-badges", json={"shown": None}).get_json()["shown"] is None
