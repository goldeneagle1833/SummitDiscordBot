"""Tests for reaction role live sync: job queue, bot posts and reaction upkeep."""

import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if "config" not in sys.modules:
    try:
        import config  # noqa: F401
    except ImportError:
        fake_config = ModuleType("config")
        fake_config.GUILD_ID = 1
        sys.modules["config"] = fake_config

from cogs import reaction_roles as rr  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "match_records.db")
    monkeypatch.setattr(rr, "DB_PATH", path)
    rr._ensure_tables()
    return path


def _exec(path, sql, args=()):
    conn = sqlite3.connect(path)
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def _track(path, message_id="200", managed=0, title="", body=""):
    _exec(path,
          "INSERT INTO reaction_role_messages (channel_id, message_id, label, title, body, managed) "
          "VALUES ('100', ?, 'Roles', ?, ?, ?)", (message_id, title, body, managed))


def _map(path, emoji, role_id, emoji_id=None, message_id="200"):
    _exec(path,
          "INSERT INTO reaction_role_mappings (message_id, emoji, emoji_id, role_id) VALUES (?, ?, ?, ?)",
          (message_id, emoji, emoji_id, role_id))


def test_take_queue_returns_jobs_once(db):
    _exec(db, "INSERT INTO reaction_role_queue (action, message_id) VALUES ('sync', '200')")
    _exec(db, "INSERT INTO reaction_role_queue (action, message_id) VALUES ('clear', '201')")
    assert [j["action"] for j in rr._take_queue()] == ["sync", "clear"]
    assert rr._take_queue() == []


def test_role_embed_lists_each_role():
    embed = rr.build_role_embed("Clubs", "React below.", [
        {"emoji": "🌊", "emoji_id": None, "role_id": "300"},
        {"emoji": "HATE", "emoji_id": "999", "role_id": "301"},
    ])
    assert embed.title == "Clubs"
    assert embed.description == "React below.\n\n🌊  <@&300>\n<:HATE:999>  <@&301>"


def test_role_embed_without_roles_says_coming_soon():
    assert "coming soon" in rr.build_role_embed("Clubs", "", []).description


def test_finish_post_tracks_new_message(db):
    _exec(db, "INSERT INTO reaction_role_posts (channel_id, title, body) VALUES ('100', 'Clubs', 'Hi')")
    post = rr._get_post(1)
    rr._finish_post(post, 777)
    row = rr._get_message_row(777)
    assert (row["managed"], row["title"], row["label"]) == (1, "Clubs", "Clubs")
    assert rr._get_post(1)["status"] == "posted"


def test_finish_post_records_failure(db):
    _exec(db, "INSERT INTO reaction_role_posts (channel_id, title) VALUES ('100', 'Clubs')")
    rr._finish_post(rr._get_post(1), None, "Channel not found")
    post = rr._get_post(1)
    assert (post["status"], post["error"]) == ("failed", "Channel not found")


def _reaction(emoji, me):
    return SimpleNamespace(emoji=emoji, me=me)


def _cog(db):
    bot = MagicMock()
    bot.user = object()
    with patch.object(rr, "_seed_if_empty"):
        cog = rr.ReactionRolesCog(bot)
    return cog


async def test_sync_adds_missing_emojis_and_removes_stale_ones(db):
    _track(db, managed=1, title="Clubs")
    _map(db, "🌊", "300")
    _map(db, "🔥", "301")
    cog = _cog(db)

    message = MagicMock()
    message.author = cog.bot.user
    message.reactions = [_reaction("🌊", True), _reaction("💧", True), _reaction("🐻", False)]
    message.edit = AsyncMock()
    message.add_reaction = AsyncMock()
    message.remove_reaction = AsyncMock()
    cog._fetch_message = AsyncMock(return_value=message)
    cog._backfill_roles = AsyncMock()

    with patch.object(rr.asyncio, "sleep", AsyncMock()):
        await cog._sync_message(MagicMock(), 200)

    message.add_reaction.assert_awaited_once_with("🔥")
    message.remove_reaction.assert_awaited_once_with("💧", cog.bot.user)
    embed = message.edit.await_args.kwargs["embed"]
    assert "<@&300>" in embed.description and "<@&301>" in embed.description
    cog._backfill_roles.assert_awaited_once()


async def test_sync_does_not_edit_messages_the_bot_did_not_post(db):
    _track(db, managed=0)
    _map(db, "🌊", "300")
    cog = _cog(db)
    message = MagicMock()
    message.reactions = []
    message.edit = AsyncMock()
    message.add_reaction = AsyncMock()
    cog._fetch_message = AsyncMock(return_value=message)
    cog._backfill_roles = AsyncMock()

    with patch.object(rr.asyncio, "sleep", AsyncMock()):
        await cog._sync_message(MagicMock(), 200)

    message.edit.assert_not_awaited()
    message.add_reaction.assert_awaited_once_with("🌊")


def test_role_embed_shows_member_counts():
    embed = rr.build_role_embed("Clubs", "", [
        {"emoji": "🌊", "emoji_id": None, "role_id": "300"},
        {"emoji": "🐻", "emoji_id": None, "role_id": "301"},
        {"emoji": "🔥", "emoji_id": None, "role_id": "302"},
    ], {300: 42, 301: 1})
    assert embed.description.splitlines() == [
        "🌊  <@&300> · 42 members",
        "🐻  <@&301> · 1 member",
        "🔥  <@&302>",
    ]


async def test_role_change_marks_only_bot_posts_listing_that_role(db):
    _track(db, "200", managed=1, title="Clubs")
    _track(db, "201", managed=0)
    _map(db, "🌊", "300", message_id="200")
    _map(db, "🌊", "300", message_id="201")
    cog = _cog(db)

    role = MagicMock(id=300)
    other = MagicMock(id=999)
    await cog.on_member_update(SimpleNamespace(roles=[]), SimpleNamespace(roles=[role]))
    assert cog._dirty_posts == {200}

    cog._dirty_posts.clear()
    await cog.on_member_update(SimpleNamespace(roles=[]), SimpleNamespace(roles=[other]))
    assert cog._dirty_posts == set()


async def test_post_is_not_edited_when_nothing_changed(db):
    _track(db, managed=1, title="Clubs")
    _map(db, "🌊", "300")
    cog = _cog(db)
    guild = MagicMock()
    guild.get_role.return_value = SimpleNamespace(id=300, members=[1, 2])
    row = rr._get_message_row(200)
    mappings = rr._get_mapping_rows(200)
    message = MagicMock()
    message.author = cog.bot.user
    message.embeds = [rr.build_role_embed("Clubs", "", mappings, {300: 2})]
    message.edit = AsyncMock()

    await cog._update_post_embed(guild, message, row, mappings)
    message.edit.assert_not_awaited()

    guild.get_role.return_value = SimpleNamespace(id=300, members=[1, 2, 3])
    await cog._update_post_embed(guild, message, row, mappings)
    assert "3 members" in message.edit.await_args.kwargs["embed"].description


def test_guild_snapshot_saves_roles_and_emojis(db):
    def role(i, name, assignable, default=False):
        r = MagicMock(id=i, position=i)
        r.name = name
        r.color.value = 255
        r.is_assignable.return_value = assignable
        r.is_default.return_value = default
        return r
    emoji = MagicMock(id=77, animated=False)
    emoji.name = "HATE"
    guild = SimpleNamespace(
        roles=[role(1, "@everyone", False, default=True), role(2, "Cove", True), role(3, "Mod", False)],
        emojis=[emoji],
    )
    rr.save_guild_snapshot(guild)
    rr.save_guild_snapshot(guild)  # replaces, never duplicates

    conn = sqlite3.connect(db)
    roles = conn.execute("SELECT role_id, name, assignable FROM reaction_role_guild_roles ORDER BY role_id").fetchall()
    emojis = conn.execute("SELECT emoji_id, name FROM reaction_role_guild_emojis").fetchall()
    conn.close()
    assert roles == [("2", "Cove", 1), ("3", "Mod", 0)]
    assert emojis == [("77", "HATE")]
