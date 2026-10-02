"""Tests for auto-assigning the fart player role on fart game commands."""

import sys
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
    ),
)

import cogs.fun as fun  # noqa: E402

ROLE_ID = 1555565625278205982


def _ctx(cog_name="FunCog", command_name="fart", roles=(), bot=False):
    member = MagicMock(spec=discord.Member)
    member.bot = bot
    member.roles = [MagicMock(id=r) for r in roles]
    member.add_roles = AsyncMock()
    role = MagicMock(id=ROLE_ID)
    ctx = MagicMock()
    ctx.author = member
    ctx.guild.get_role.return_value = role
    ctx.command.cog_name = cog_name
    ctx.command.name = command_name
    return ctx, member, role


@pytest.fixture()
def cog(monkeypatch):
    monkeypatch.setattr(fun, "FART_PLAYER_ROLE_ID", ROLE_ID)
    return fun.FunCog(MagicMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("cog_name,command_name", [("FunCog", "fart"), ("ShopCog", "fart_shop"), ("ShopCog", "banana")])
async def test_fart_commands_grant_role(cog, cog_name, command_name):
    ctx, member, role = _ctx(cog_name, command_name)
    await cog.on_command(ctx)
    member.add_roles.assert_awaited_once()
    assert member.add_roles.await_args.args[0] is role


@pytest.mark.asyncio
async def test_non_fart_command_ignored(cog):
    ctx, member, _ = _ctx("EloCog", "elo")
    await cog.on_command(ctx)
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_has_role_skipped(cog):
    ctx, member, _ = _ctx(roles=(ROLE_ID,))
    await cog.on_command(ctx)
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_reset_command_exempt(cog):
    ctx, member, _ = _ctx(command_name="reset_fart_cooldown")
    await cog.on_command(ctx)
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_roles_failure_is_swallowed(cog):
    ctx, member, _ = _ctx()
    member.add_roles.side_effect = discord.Forbidden(MagicMock(status=403), "no perms")
    await cog.on_command(ctx)  # must not raise
