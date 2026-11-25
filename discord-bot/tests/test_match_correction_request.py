"""Player match corrections (!correct_match for non-admins and the website's Correct button)."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.lfg import persistent_confirm as pc

ME, OPP = 111111111111111111, 222222222222222222
PLAYERS = {"winner_id": ME, "loser_id": OPP, "winner_name": "Me", "loser_name": "Opp"}


def _bot(dm_side_effect=None):
    bot = MagicMock()
    user = MagicMock()
    user.send = AsyncMock(side_effect=dm_side_effect)
    bot.fetch_user = AsyncMock(return_value=user)
    bot.get_channel.return_value = None
    return bot, user


def _pending():
    conn = sqlite3.connect("match_records.db")
    rows = conn.execute("SELECT match_id, requester_id, other_player_id FROM pending_corrections").fetchall()
    conn.close()
    return rows


@pytest.mark.asyncio
async def test_dms_the_other_player_with_confirm_and_deny():
    bot, user = _bot()
    with patch("utils.database.get_match_players", return_value=PLAYERS):
        result = await pc.send_correction_request(bot, 5, ME, "Me", from_website=True)
    assert result["status"] == "sent" and result["other_player_name"] == "Opp"
    bot.fetch_user.assert_awaited_with(OPP)
    kwargs = user.send.await_args.kwargs
    assert "from the Summit website" in kwargs["embed"].description
    labels = [c.item.label for c in kwargs["view"].children]
    assert labels == ["Confirm Correction", "Deny Correction"]
    assert _pending() == [(5, ME, OPP)]


@pytest.mark.asyncio
async def test_loser_can_ask_and_the_winner_gets_the_dm():
    bot, _ = _bot()
    with patch("utils.database.get_match_players", return_value=PLAYERS):
        result = await pc.send_correction_request(bot, 5, OPP, "Opp")
    assert result["status"] == "sent" and result["other_player_name"] == "Me"
    bot.fetch_user.assert_awaited_with(ME)


@pytest.mark.asyncio
async def test_one_waiting_request_per_match():
    bot, user = _bot()
    with patch("utils.database.get_match_players", return_value=PLAYERS):
        await pc.send_correction_request(bot, 5, ME, "Me")
        again = await pc.send_correction_request(bot, 5, ME, "Me")
    assert again["status"] == "already_pending"
    assert user.send.await_count == 1 and len(_pending()) == 1


@pytest.mark.asyncio
async def test_not_in_match_and_not_found():
    bot, user = _bot()
    with patch("utils.database.get_match_players", return_value=PLAYERS):
        assert (await pc.send_correction_request(bot, 5, 333, "X"))["status"] == "not_in_match"
    with patch("utils.database.get_match_players", side_effect=ValueError("Match ID #5 not found.")):
        assert (await pc.send_correction_request(bot, 5, ME, "Me"))["status"] == "not_found"
    user.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_dms_off_and_no_fallback_channel_leaves_nothing_waiting():
    bot, _ = _bot(dm_side_effect=discord.Forbidden(MagicMock(status=403), "nope"))
    with patch("utils.database.get_match_players", return_value=PLAYERS):
        result = await pc.send_correction_request(bot, 5, ME, "Me")
    assert result["status"] == "cannot_dm"
    assert _pending() == []
