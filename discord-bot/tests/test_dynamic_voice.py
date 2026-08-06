"""Tests for the DynamicVoiceCog."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.dynamic_voice import DynamicVoiceCog, ROOM_NAMES


@pytest.fixture
def bot():
    return MagicMock(spec=discord.ext.commands.Bot)


@pytest.fixture
def cog(bot):
    return DynamicVoiceCog(bot)


def _make_voice_state(channel):
    state = MagicMock(spec=discord.VoiceState)
    state.channel = channel
    return state


def _make_voice_channel(channel_id, name=None, members=None, category=None):
    ch = MagicMock(spec=discord.VoiceChannel)
    ch.id = channel_id
    ch.name = name or f"channel-{channel_id}"
    ch.members = members or []
    ch.category = category
    ch.guild = MagicMock()
    ch.guild.create_voice_channel = AsyncMock()
    ch.delete = AsyncMock()
    return ch


def _make_member(name="TestUser"):
    m = MagicMock(spec=discord.Member)
    m.display_name = name
    m.move_to = AsyncMock()
    return m


def _setup_hub(bot, hub_id=999):
    """Create a hub channel and wire bot.get_channel to return it."""
    category = MagicMock()
    hub = _make_voice_channel(hub_id, name="Create a Room", category=category)
    hub.category = category
    bot.get_channel = lambda cid: hub if cid == hub_id else None
    return hub, category


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_join_hub_creates_channel_and_moves(mock_config, cog):
    """Joining the hub channel creates a new voice room and moves the user."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    hub, category = _setup_hub(cog.bot)

    new_ch = _make_voice_channel(1001, name="The Dungeon", category=category)
    hub.guild.create_voice_channel.return_value = new_ch

    member = _make_member("Alice")
    before = _make_voice_state(None)
    after = _make_voice_state(hub)

    await cog.on_voice_state_update(member, before, after)

    call_kwargs = hub.guild.create_voice_channel.call_args.kwargs
    assert call_kwargs["name"] in ROOM_NAMES
    assert call_kwargs["category"] == hub.category
    assert call_kwargs["reason"] == "Dynamic voice room"
    member.move_to.assert_awaited_once_with(new_ch)


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_empty_dynamic_channel_deleted(mock_config, cog):
    """Leaving a dynamic channel that becomes empty deletes it."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    hub, category = _setup_hub(cog.bot)

    ch = _make_voice_channel(2000, name="The Dungeon", members=[], category=category)

    before = _make_voice_state(ch)
    after = _make_voice_state(None)
    member = _make_member()

    await cog.on_voice_state_update(member, before, after)

    ch.delete.assert_awaited_once_with(reason="Dynamic voice room empty")


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_non_empty_dynamic_channel_not_deleted(mock_config, cog):
    """A dynamic channel with remaining members is NOT deleted."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    hub, category = _setup_hub(cog.bot)

    remaining = _make_member("Bob")
    ch = _make_voice_channel(2000, name="The Dungeon", members=[remaining], category=category)

    before = _make_voice_state(ch)
    after = _make_voice_state(None)
    member = _make_member()

    await cog.on_voice_state_update(member, before, after)

    ch.delete.assert_not_awaited()


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_leaving_non_dynamic_channel_ignored(mock_config, cog):
    """Leaving a channel with a non-room name does nothing even if empty."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    hub, category = _setup_hub(cog.bot)

    ch = _make_voice_channel(3000, name="General Voice", members=[], category=category)

    before = _make_voice_state(ch)
    after = _make_voice_state(None)
    member = _make_member()

    await cog.on_voice_state_update(member, before, after)

    ch.delete.assert_not_awaited()


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_switching_channels_no_create(mock_config, cog):
    """Switching to a non-hub channel does NOT create a room."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    _setup_hub(cog.bot)

    regular = _make_voice_channel(4000)
    before = _make_voice_state(None)
    after = _make_voice_state(regular)
    member = _make_member()

    await cog.on_voice_state_update(member, before, after)

    regular.guild.create_voice_channel.assert_not_awaited()


@pytest.mark.asyncio
@patch("cogs.dynamic_voice.config")
async def test_on_ready_cleans_up_empty_leftovers(mock_config, cog):
    """On startup, empty dynamic channels in the hub category are deleted."""
    mock_config.DYNAMIC_VOICE_HUB_ID = 999
    hub, category = _setup_hub(cog.bot)

    leftover = _make_voice_channel(5000, name="The Summit", members=[], category=category)
    occupied = _make_voice_channel(5001, name="The Dungeon", members=[_make_member()], category=category)
    non_dynamic = _make_voice_channel(5002, name="General Voice", members=[], category=category)

    category.voice_channels = [hub, leftover, occupied, non_dynamic]

    await cog.on_ready()

    leftover.delete.assert_awaited_once()
    occupied.delete.assert_not_awaited()
    non_dynamic.delete.assert_not_awaited()
    hub.delete.assert_not_awaited()
