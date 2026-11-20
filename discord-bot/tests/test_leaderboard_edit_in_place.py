"""The leaderboard is one message that gets edited, not reposted."""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg import state as lfg_state  # noqa: E402
from cogs.lfg.cog import LFGCog  # noqa: E402

BOT_ID = 42


def _msg(mid, title="Gothic Season 9 Leaderboard", author=BOT_ID):
    m = MagicMock(id=mid)
    m.author.id = author
    m.embeds = [MagicMock(title=title)]
    m.edit = AsyncMock()
    m.delete = AsyncMock()
    return m


def _channel(history, fetched=None):
    ch = MagicMock()

    async def hist(limit=50):
        for m in history:
            yield m

    ch.history = MagicMock(side_effect=hist)
    ch.fetch_message = AsyncMock(side_effect=lambda i: fetched if fetched and fetched.id == i else (_ for _ in ()).throw(Exception("gone")))
    ch.send = AsyncMock(return_value=MagicMock(id=999))
    return ch


def _cog():
    cog = LFGCog.__new__(LFGCog)
    cog.bot = MagicMock()
    cog.bot.user.id = BOT_ID
    return cog


def _is_board(e):
    return "Leaderboard" in str(e.title) and "Limited Leaderboard" not in str(e.title)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setattr(lfg_state, "leaderboard_message_id", None)


@pytest.mark.asyncio
async def test_edits_the_known_message_instead_of_posting():
    kept = _msg(10)
    lfg_state.leaderboard_message_id = 10
    ch = _channel([kept], fetched=kept)
    await _cog()._post_or_edit_board(ch, ["E"], "leaderboard_message_id", _is_board)
    kept.edit.assert_awaited_once_with(embeds=["E"])
    ch.send.assert_not_called()
    kept.delete.assert_not_called()
    assert lfg_state.leaderboard_message_id == 10


@pytest.mark.asyncio
async def test_after_a_restart_finds_its_message_and_removes_extra_copies():
    newest, older = _msg(20), _msg(15)
    someone_else = _msg(18, author=7)
    limited = _msg(17, title="Limited Leaderboard")
    ch = _channel([newest, someone_else, limited, older])
    await _cog()._post_or_edit_board(ch, ["E"], "leaderboard_message_id", _is_board)
    newest.edit.assert_awaited_once_with(embeds=["E"])
    ch.send.assert_not_called()
    older.delete.assert_awaited_once()
    someone_else.delete.assert_not_called()
    limited.delete.assert_not_called()
    assert lfg_state.leaderboard_message_id == 20


@pytest.mark.asyncio
async def test_posts_once_when_there_is_no_leaderboard_yet():
    ch = _channel([])
    await _cog()._post_or_edit_board(ch, ["E"], "leaderboard_message_id", _is_board)
    ch.send.assert_awaited_once_with(embeds=["E"])
    assert lfg_state.leaderboard_message_id == 999
