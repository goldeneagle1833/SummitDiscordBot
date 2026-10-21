"""Season ticket roles: on sale for next season, active once it starts."""

import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

import repositories.ticket_roles_repo as repo  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_NAME", str(tmp_path / "elo.db"))


def test_config_roles_until_a_season_has_its_own():
    assert repo.ticket_holder_role_ids({1, 2}) == {1, 2}
    repo.put_role_on_sale(99, "Season 9 Ticket")
    # On sale doesn't count yet
    assert repo.ticket_holder_role_ids({1, 2}) == {1, 2}


def test_start_event_switches_to_the_new_role():
    repo.put_role_on_sale(98, "Season 8 Ticket")
    assert repo.activate_on_sale_role(8)["role_id"] == "98"
    repo.put_role_on_sale(99, "Season 9 Ticket")
    assert repo.ticket_holder_role_ids({1}) == {98}

    activated = repo.activate_on_sale_role(9)
    assert activated["role_id"] == "99" and activated["event_id"] == 9
    assert repo.ticket_holder_role_ids({1}) == {99}
    assert repo.get_role("on_sale") is None


def test_season_without_a_new_role_falls_back_to_config():
    repo.put_role_on_sale(98, "Season 8 Ticket")
    repo.activate_on_sale_role(8)
    assert repo.activate_on_sale_role(9) is None
    assert repo.ticket_holder_role_ids({1}) == {1}


def test_newer_on_sale_role_replaces_older():
    repo.put_role_on_sale(99, "Season 9 Ticket")
    repo.put_role_on_sale(100, "Season 9 Ticket v2")
    assert repo.get_role("on_sale")["role_id"] == "100"


# ── !ticket_role ────────────────────────────────────────────

from unittest.mock import AsyncMock, patch  # noqa: E402

import discord  # noqa: E402

from cogs.lfg.cog import LFGCog  # noqa: E402


def _ctx(role_mentions=()):
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.message.role_mentions = list(role_mentions)
    ctx.author.id = 5
    ctx.author.display_name = "Bruce"
    return ctx


@pytest.mark.asyncio
async def test_ticket_role_creates_and_puts_on_sale():
    ctx = _ctx()
    new_role = MagicMock(id=999000000000000001)
    new_role.name = "Season 9 Ticket"
    ctx.guild.create_role = AsyncMock(return_value=new_role)
    with patch("cogs.lfg.cog.log_admin_action"):
        await LFGCog.ticket_role.callback(MagicMock(), ctx, name_or_role="Season 9 Ticket")
    ctx.guild.create_role.assert_awaited_once()
    assert ctx.guild.create_role.await_args.kwargs["name"] == "Season 9 Ticket"
    assert repo.get_role("on_sale")["role_id"] == str(new_role.id)


@pytest.mark.asyncio
async def test_ticket_role_without_manage_roles():
    ctx = _ctx()
    ctx.guild.create_role = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "Missing Permissions"))
    await LFGCog.ticket_role.callback(MagicMock(), ctx, name_or_role="Season 9 Ticket")
    assert "Manage Roles" in ctx.send.await_args.args[0]
    assert repo.get_role("on_sale") is None


@pytest.mark.asyncio
async def test_ticket_role_uses_mentioned_role():
    role = MagicMock(id=999000000000000002)
    role.name = "Season 9"
    role.__ge__ = MagicMock(return_value=False)
    ctx = _ctx([role])
    with patch("cogs.lfg.cog.log_admin_action"):
        await LFGCog.ticket_role.callback(MagicMock(), ctx, name_or_role="@Season 9")
    ctx.guild.create_role.assert_not_called()
    assert repo.get_role("on_sale")["role_id"] == str(role.id)
