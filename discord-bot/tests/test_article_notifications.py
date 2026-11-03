"""Bot delivery of player-article DMs queued by the web app.

The queue table is created by the web app's own ArticleRepository (loaded by
file path) so this test always runs against the real table layout.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

sys.modules.setdefault("config", MagicMock(WEB_APP_URL="https://sorcererssummit.com"))

from cogs import article_notifications as an  # noqa: E402

WEB_REPO = Path(__file__).resolve().parents[2] / "web-app" / "repositories" / "articles.py"


def _web_repo(db_path):
    with patch.dict(sys.modules, {"webapp_config": MagicMock()}):
        spec = importlib.util.spec_from_file_location("web_articles_repo", WEB_REPO)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.ArticleRepository(db_path=db_path)


@pytest.fixture(autouse=True)
def site(monkeypatch):
    # Other tests may have stubbed config already; pin the site URL here.
    monkeypatch.setattr(an, "config", MagicMock(WEB_APP_URL="https://sorcererssummit.com"))


@pytest.fixture()
def queue(tmp_path):
    db = tmp_path / "articles.db"
    repo = _web_repo(db)
    repo.enqueue_notification(recipient="111", subject="New player article to review",
                              body="**Frogs** by Kate", link_path="/admin/articles?id=1",
                              article_id=1, audience="reviewer")
    repo.enqueue_notification(recipient="333", subject="Your article is live!",
                              body="Thanks", link_path="/articles/1-frogs",
                              article_id=1, audience="author")
    return db, repo


def _bot(user):
    bot = MagicMock()
    bot.get_user = MagicMock(return_value=user)
    bot.fetch_user = AsyncMock(return_value=user)
    return bot


async def test_delivers_and_marks_sent(queue):
    db, repo = queue
    user = MagicMock()
    user.send = AsyncMock()
    pending = an.fetch_pending(db)
    assert len(pending) == 2
    for n in pending:
        await an.deliver(_bot(user), n, db_path=db)
    assert user.send.await_count == 2
    embed = user.send.await_args_list[0].kwargs["embed"]
    assert embed.url == "https://sorcererssummit.com/admin/articles?id=1"
    view = user.send.await_args_list[0].kwargs["view"]
    assert view.children[0].label == "Review on the site"
    assert all(n["status"] == "sent" for n in repo.notifications())
    assert an.fetch_pending(db) == []


async def test_closed_dms_fail_once(queue):
    db, repo = queue
    user = MagicMock()
    user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "closed"))
    n = an.fetch_pending(db)[0]
    await an.deliver(_bot(user), n, db_path=db)
    row = [r for r in repo.notifications() if r["id"] == n["id"]][0]
    assert row["status"] == "failed"


async def test_network_error_retries(queue):
    db, repo = queue
    user = MagicMock()
    user.send = AsyncMock(side_effect=RuntimeError("blip"))
    n = an.fetch_pending(db)[0]
    await an.deliver(_bot(user), n, db_path=db)
    row = [r for r in repo.notifications() if r["id"] == n["id"]][0]
    assert row["status"] == "pending" and row["attempts"] == 1


def test_missing_db_is_quiet(tmp_path):
    assert an.fetch_pending(tmp_path / "nope.db") == []
