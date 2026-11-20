"""Store Discord role products: the bot gives or takes back the role."""

import sys
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.store_notifications import (  # noqa: E402
    RoleGrantProblem, StoreNotificationsCog,
)

ROLE_ID = 123456789012345678
BUYER_ID = 111111111111111111


def _cog(member=None, role=None):
    cog = StoreNotificationsCog.__new__(StoreNotificationsCog)
    guild = MagicMock()
    guild.get_role.return_value = role
    guild.get_member.return_value = member
    guild.fetch_member = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "Unknown Member")
    )
    cog.bot = MagicMock()
    cog.bot.get_guild.return_value = guild
    cog._mark = MagicMock()
    cog._send_admin = AsyncMock()
    return cog


def _row(channel="discord_role_add", attempts=0):
    return {"id": 7, "channel": channel, "recipient": str(BUYER_ID),
            "body": str(ROLE_ID), "attempts": attempts,
            "subject": "Give Season 9 Ticket role for order SS-1"}


def _member(roles=()):
    member = MagicMock()
    member.roles = list(roles)
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


@pytest.mark.asyncio
async def test_gives_role():
    role, member = MagicMock(), _member()
    cog = _cog(member, role)
    await cog._deliver_role(_row())
    member.add_roles.assert_awaited_once()
    assert member.add_roles.await_args.args == (role,)
    cog._mark.assert_called_once_with(7, success=True)


@pytest.mark.asyncio
async def test_already_has_role_is_success():
    role = MagicMock()
    member = _member([role])
    cog = _cog(member, role)
    await cog._deliver_role(_row())
    member.add_roles.assert_not_awaited()
    cog._mark.assert_called_once_with(7, success=True)


@pytest.mark.asyncio
async def test_removes_role_after_refund():
    role = MagicMock()
    member = _member([role])
    cog = _cog(member, role)
    await cog._deliver_role(_row("discord_role_remove"))
    member.remove_roles.assert_awaited_once()
    cog._mark.assert_called_once_with(7, success=True)


@pytest.mark.asyncio
async def test_buyer_not_in_server_alerts_admins():
    cog = _cog(member=None, role=MagicMock())
    await cog._deliver_role(_row())
    args = cog._mark.call_args
    assert args.kwargs["final"] is True
    assert "isn't in the Summit Discord" in args.kwargs["error"]
    alert = cog._send_admin.await_args.args[0]
    assert alert["subject"].startswith("Couldn't give")
    assert str(BUYER_ID) in alert["body"]


@pytest.mark.asyncio
async def test_unknown_role_alerts_admins():
    cog = _cog(member=_member(), role=None)
    with pytest.raises(RoleGrantProblem):
        await cog._change_role(_row())
    await cog._deliver_role(_row())
    cog._send_admin.assert_awaited_once()


@pytest.mark.asyncio
async def test_temporary_error_retries_quietly():
    member = _member()
    member.add_roles.side_effect = RuntimeError("gateway hiccup")
    cog = _cog(member, MagicMock())
    await cog._deliver_role(_row(attempts=0))
    assert cog._mark.call_args.kwargs["final"] is False
    cog._send_admin.assert_not_awaited()


# ── Leaderboard redraw after a ticket purchase ──


@pytest.mark.asyncio
async def test_role_given_redraws_the_leaderboard(monkeypatch):
    """A new ticket holder moves onto the leaderboard without waiting for a match."""
    import cogs.store_notifications as store

    monkeypatch.setattr(store, "LEADERBOARD_REFRESH_DELAY", 0)
    role, member = MagicMock(), _member()
    cog = _cog(member=member, role=role)
    cog._fetch_pending = MagicMock(return_value=[_row()])
    lfg = MagicMock(update_leaderboard=AsyncMock())
    cog.bot.get_cog.side_effect = lambda name: lfg if name == "LFGCog" else None
    await StoreNotificationsCog.deliver_notifications.coro(cog)
    member.add_roles.assert_awaited_once()
    lfg.update_leaderboard.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_role_change_leaves_the_leaderboard_alone(monkeypatch):
    import cogs.store_notifications as store

    monkeypatch.setattr(store, "LEADERBOARD_REFRESH_DELAY", 0)
    cog = _cog(member=_member(), role=None)  # no such role
    cog._fetch_pending = MagicMock(return_value=[_row()])
    lfg = MagicMock(update_leaderboard=AsyncMock())
    cog.bot.get_cog.return_value = lfg
    await StoreNotificationsCog.deliver_notifications.coro(cog)
    lfg.update_leaderboard.assert_not_awaited()
