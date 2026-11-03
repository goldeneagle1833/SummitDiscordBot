"""Article discussion sync between the site and a Discord forum thread.

The tables come from the web app's own ArticleRepository (loaded by file
path), so the bot is always tested against the real layout.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

try:
    import config  # noqa: F401
except ImportError:
    sys.modules["config"] = MagicMock()

from cogs import article_discussions as ad  # noqa: E402

WEB_REPO = Path(__file__).resolve().parents[2] / "web-app" / "repositories" / "articles.py"


def _web_repo(db_path):
    with patch.dict(sys.modules, {"webapp_config": MagicMock()}):
        spec = importlib.util.spec_from_file_location("web_articles_repo_disc", WEB_REPO)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.ArticleRepository(db_path=db_path)


@pytest.fixture(autouse=True)
def site(monkeypatch):
    monkeypatch.setattr(ad, "config", MagicMock(ARTICLES_FORUM_CHANNEL_ID=900))
    import cogs.article_notifications as an
    monkeypatch.setattr(an, "config", MagicMock(WEB_APP_URL="https://sorcererssummit.com"))


@pytest.fixture()
def setup(tmp_path):
    repo = _web_repo(tmp_path / "articles.db")
    aid = repo.create(title="Frog Tempo", summary="How to pilot frogs.", category="Deck Guide",
                      tags=["frogs"], body_md="x", body_html="<p>x</p>", word_count=1,
                      reading_minutes=1, author_id="1", author_name="Kate",
                      author_provider="discord", slug="frog-tempo")
    repo.set_status(aid, "approved", "admin")

    thread = MagicMock(spec=discord.Thread)
    thread.id = 777
    thread.archived = False
    thread.locked = False
    thread.send = AsyncMock(return_value=MagicMock(id=5001))
    thread.edit = AsyncMock()
    partial = MagicMock()
    partial.delete = AsyncMock()
    thread.get_partial_message = MagicMock(return_value=partial)

    forum = MagicMock(spec=discord.ForumChannel)
    forum.create_thread = AsyncMock(return_value=MagicMock(thread=thread))

    bot = MagicMock()
    bot.get_channel = MagicMock(side_effect=lambda cid: {900: forum, 777: thread}.get(cid))
    with patch("discord.ext.tasks.Loop.start"):
        cog = ad.ArticleDiscussionsCog(bot, store=ad.ArticleStore(tmp_path / "articles.db"))
    return repo, aid, cog, forum, thread, partial


def _member_message(thread, msg_id, text, bot=False):
    m = MagicMock(spec=discord.Message)
    m.id = msg_id
    m.channel = thread
    m.webhook_id = None
    m.author = MagicMock(bot=bot, id=42, display_name="Disco")
    m.author.display_avatar.url = "https://cdn.discordapp.com/a.png"
    m.clean_content = text
    m.attachments = []
    return m


async def test_full_round_trip(setup):
    repo, aid, cog, forum, thread, partial = setup

    # Published article -> forum thread
    await cog.sync_threads()
    forum.create_thread.assert_awaited_once()
    kwargs = forum.create_thread.await_args.kwargs
    assert kwargs["name"] == "Frog Tempo"
    assert "https://sorcererssummit.com/articles/1-frog-tempo" in kwargs["content"]
    assert repo.get(aid)["forum_thread_id"] == "777"

    # Site comment -> Discord
    cid = repo.add_public_comment(aid, source="site", user_id="9", username="Sam",
                                  avatar=None, body="Great read")
    await cog.mirror_site_comments()
    thread.send.assert_awaited_once()
    assert thread.send.await_args.args[0] == "**Sam** on the site:\nGreat read"
    assert repo.get_public_comment(cid)["discord_message_id"] == "5001"

    # Discord member -> site; the bot's own posts and the opening post are skipped
    await cog.on_message(_member_message(thread, 6001, "Agree, frogs rule"))
    await cog.on_message(_member_message(thread, 6002, "mirror", bot=True))
    await cog.on_message(_member_message(thread, 777, "opening post"))
    bodies = [c["body"] for c in repo.discussion(aid)]
    assert bodies == ["Great read", "Agree, frogs rule"]
    assert repo.discussion(aid)[1]["source"] == "discord"

    # Discord delete -> gone on the site
    await cog.on_raw_message_delete(MagicMock(message_id=6001))
    assert [c["body"] for c in repo.discussion(aid)] == ["Great read"]

    # Site delete -> Discord copy removed
    repo.delete_public_comment(cid)
    await cog.mirror_deletions()
    thread.get_partial_message.assert_called_with(5001)
    partial.delete.assert_awaited_once()
    assert repo.get_public_comment(cid)["mirror_deleted"] == 1


async def test_takedown_locks_thread(setup):
    repo, aid, cog, forum, thread, partial = setup
    await cog.sync_threads()
    repo.set_status(aid, "rejected", "admin")
    await cog.sync_threads()
    thread.edit.assert_awaited_with(locked=True, archived=True)
    assert repo.get(aid)["forum_locked"] == 1
    # Comments in a locked article's thread are not imported
    await cog.on_message(_member_message(thread, 6100, "late comment"))
    assert repo.discussion(aid) == []


async def test_no_forum_channel_is_quiet(setup, monkeypatch):
    repo, aid, cog, forum, thread, partial = setup
    monkeypatch.setattr(ad, "config", MagicMock(ARTICLES_FORUM_CHANNEL_ID=0, SUMMIT_GUILD_ID=0, GUILD_ID=0))
    cog.bot.guilds = []
    await cog.sync_threads()
    forum.create_thread.assert_not_awaited()
    assert repo.get(aid)["forum_thread_id"] is None


def test_missing_db_never_created(tmp_path):
    store = ad.ArticleStore(tmp_path / "nope.db")
    assert store.discord_message_deleted(1) == 0
    assert not (tmp_path / "nope.db").exists()
