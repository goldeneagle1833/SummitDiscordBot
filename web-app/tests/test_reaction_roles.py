"""Tests for the reaction roles admin API and the bot job queue it fills."""

import sqlite3

import pytest

from repositories import reaction_roles as rr_repo


@pytest.fixture(autouse=True)
def rr_db(tmp_path, monkeypatch):
    path = tmp_path / "match_records.db"
    monkeypatch.setattr(rr_repo, "MATCH_RECORDS_DB_PATH", path)
    return path


@pytest.fixture()
def admin_client(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin_user_1"
        sess["username"] = "Admin"
    return client


def queue(path):
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT action, message_id, channel_id, post_id FROM reaction_role_queue ORDER BY id"
    ).fetchall()
    conn.close()
    return rows


def track(client, message_id="200", channel_id="100"):
    resp = client.post("/api/reaction-roles/messages", json={
        "channel_id": channel_id, "message_id": message_id, "label": "Roles",
    })
    assert resp.status_code == 201


def add_role(client, message_id="200", emoji="🌊", role_id="300"):
    return client.post("/api/reaction-roles/mappings", json={
        "message_id": message_id, "emoji": emoji, "role_id": role_id, "role_name": "Cove",
    })


def test_requires_admin(client):
    assert client.post("/api/reaction-roles/posts", json={}).status_code in (401, 403)


def test_adding_message_and_role_queue_a_sync(admin_client, rr_db):
    track(admin_client)
    assert add_role(admin_client).status_code == 201
    assert queue(rr_db) == [("sync", "200", None, None), ("sync", "200", None, None)]


def test_removing_a_role_queues_a_sync_for_its_message(admin_client, rr_db):
    track(admin_client)
    mapping_id = add_role(admin_client).get_json()["mapping"]["id"]
    assert admin_client.delete(f"/api/reaction-roles/mappings/{mapping_id}").status_code == 200
    assert queue(rr_db)[-1] == ("sync", "200", None, None)


def test_twenty_role_limit(admin_client):
    track(admin_client)
    for i in range(20):
        assert add_role(admin_client, emoji=f"e{i}", role_id=str(i)).status_code == 201
    resp = add_role(admin_client, emoji="one-too-many", role_id="99")
    assert resp.status_code == 400
    assert "20" in resp.get_json()["error"]


def test_untracking_a_normal_message_only_clears_bot_reactions(admin_client, rr_db):
    track(admin_client)
    assert admin_client.delete("/api/reaction-roles/messages/200").status_code == 200
    assert queue(rr_db)[-1] == ("clear", "200", "100", None)


def test_create_post_queues_a_post_and_lists_it(admin_client, rr_db):
    resp = admin_client.post("/api/reaction-roles/posts", json={
        "channel_id": "100", "title": "Pick your clubs", "body": "React below.",
    })
    assert resp.status_code == 201
    post_id = resp.get_json()["post"]["id"]
    assert queue(rr_db) == [("post", None, "100", post_id)]

    listing = admin_client.get("/api/reaction-roles/messages").get_json()
    assert [p["title"] for p in listing["posts"]] == ["Pick your clubs"]
    assert listing["posts"][0]["status"] == "pending"


@pytest.mark.parametrize("payload", [
    {"channel_id": "abc", "title": "Roles"},
    {"channel_id": "100", "title": ""},
    {"channel_id": "100", "title": "x" * 257},
])
def test_create_post_validation(admin_client, payload):
    assert admin_client.post("/api/reaction-roles/posts", json=payload).status_code == 400


def _mark_posted(path, message_id="555"):
    """What the bot does after posting: track the message as bot-managed."""
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO reaction_role_messages (channel_id, message_id, label, title, body, managed) "
        "VALUES ('100', ?, 'Old', 'Old', 'Old text', 1)",
        (message_id,),
    )
    conn.commit()
    conn.close()


def test_edit_text_only_for_bot_posts(admin_client, rr_db):
    track(admin_client)
    resp = admin_client.patch("/api/reaction-roles/messages/200", json={"title": "New"})
    assert resp.status_code == 404

    _mark_posted(rr_db)
    resp = admin_client.patch("/api/reaction-roles/messages/555", json={"title": "New", "body": "Hi"})
    assert resp.status_code == 200
    msg = next(m for m in admin_client.get("/api/reaction-roles/messages").get_json()["messages"]
               if m["message_id"] == "555")
    assert (msg["title"], msg["body"], msg["label"]) == ("New", "Hi", "New")
    assert queue(rr_db)[-1] == ("sync", "555", None, None)


def test_deleting_a_bot_post_deletes_it_from_discord(admin_client, rr_db):
    rr_repo.ReactionRolesRepository()  # create tables
    _mark_posted(rr_db)
    assert admin_client.delete("/api/reaction-roles/messages/555").status_code == 200
    assert queue(rr_db)[-1] == ("delete_post", "555", "100", None)


def test_dismiss_failed_post(admin_client, rr_db):
    post_id = admin_client.post("/api/reaction-roles/posts", json={
        "channel_id": "100", "title": "Roles",
    }).get_json()["post"]["id"]
    assert admin_client.delete(f"/api/reaction-roles/posts/{post_id}").status_code == 200
    assert admin_client.get("/api/reaction-roles/messages").get_json()["posts"] == []


def test_existing_table_gets_new_columns(tmp_path):
    """Production already has reaction_role_messages without title/body/managed."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reaction_role_messages (id INTEGER PRIMARY KEY, channel_id TEXT NOT NULL, "
        "message_id TEXT NOT NULL UNIQUE, label TEXT NOT NULL DEFAULT '', created_at TEXT)"
    )
    conn.execute("INSERT INTO reaction_role_messages (channel_id, message_id) VALUES ('1', '2')")
    conn.commit()
    conn.close()
    repo = rr_repo.ReactionRolesRepository(path)
    msg = repo.get_message("2")
    assert msg["managed"] == 0 and msg["title"] == ""


def test_discord_options_lists_roles_highest_first(admin_client, rr_db):
    rr_repo.ReactionRolesRepository()
    conn = sqlite3.connect(rr_db)
    conn.executemany(
        "INSERT INTO reaction_role_guild_roles (role_id, name, color, position, assignable) VALUES (?, ?, ?, ?, ?)",
        [("1", "Low", 0, 1, 1), ("2", "High", 16711680, 9, 1), ("3", "Mod", 0, 20, 0)],
    )
    conn.execute("INSERT INTO reaction_role_guild_emojis (emoji_id, name) VALUES ('77', 'HATE')")
    conn.commit()
    conn.close()

    data = admin_client.get("/api/reaction-roles/discord-options").get_json()
    assert [r["name"] for r in data["roles"]] == ["Mod", "High", "Low"]
    assert data["roles"][0]["assignable"] == 0
    assert data["emojis"] == [{"emoji_id": "77", "name": "HATE", "animated": 0}]
    assert data["updated_at"]


def test_check_discord_queues_a_refresh(admin_client, rr_db):
    assert admin_client.post("/api/reaction-roles/discord-options/refresh", json={}).status_code == 200
    assert queue(rr_db) == [("refresh_roles", None, None, None)]
