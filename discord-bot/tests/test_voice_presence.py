import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

import discord

from services import voice_presence
from services.voice_presence import parse_user_ids, voice_session


@pytest.fixture(autouse=True)
def clear_invite_cache():
    voice_presence._invite_cache.clear()
    yield
    voice_presence._invite_cache.clear()


def make_member(user_id, name, channel=None, streaming=False, bot=False):
    member = MagicMock()
    member.id = user_id
    member.display_name = name
    member.bot = bot
    member.display_avatar.url = f"https://cdn.test/{user_id}.png"
    if channel is None:
        member.voice = None
    else:
        member.voice = MagicMock(channel=channel, self_stream=streaming)
        channel.members.append(member)
    return member


def make_channel(channel_id, name, invite_url="https://discord.gg/listen"):
    channel = MagicMock()
    channel.id = channel_id
    channel.name = name
    channel.members = []
    invite = MagicMock(url=invite_url)
    channel.create_invite = AsyncMock(return_value=invite)
    return channel


def make_bot(members, guild_id=1, ready=True):
    guild = MagicMock()
    guild.id = guild_id
    guild.get_member.side_effect = lambda user_id: members.get(user_id)
    bot = MagicMock()
    bot.is_ready.return_value = ready
    bot.get_guild.side_effect = lambda gid: guild if gid == guild_id else None
    return bot


def test_parse_user_ids_dedupes_and_validates():
    assert parse_user_ids("10, 20, 10") == [10, 20]
    with pytest.raises(ValueError):
        parse_user_ids("")
    with pytest.raises(ValueError):
        parse_user_ids("10,abc")
    with pytest.raises(ValueError):
        parse_user_ids(",".join(str(i) for i in range(20)))


@pytest.mark.asyncio
async def test_players_together_reports_spectators_and_listen_link():
    channel = make_channel(500, "The Dungeon")
    members = {}
    for user_id, name in [(10, "Bruce"), (20, "Aadu")]:
        members[user_id] = make_member(user_id, name, channel, streaming=user_id == 10)
    for user_id, name in [(30, "CJ"), (40, "Jules")]:
        make_member(user_id, name, channel)
    make_member(99, "SummitBot", channel, bot=True)

    payload = await voice_session(make_bot(members), [10, 20])

    assert payload["status"] == "together"
    assert payload["channel"]["name"] == "The Dungeon"
    assert payload["channel"]["listen_url"] == "https://discord.gg/listen"
    assert payload["channel"]["channel_url"] == "https://discord.com/channels/1/500"
    assert payload["channel"]["member_count"] == 4  # bot excluded
    assert payload["channel"]["player_count"] == 2
    assert payload["channel"]["spectator_count"] == 2
    assert [s["display_name"] for s in payload["channel"]["spectators"]] == ["CJ", "Jules"]
    assert all(s["is_player"] is False for s in payload["channel"]["spectators"])
    assert [p["streaming"] for p in payload["players"]] == [True, False]


@pytest.mark.asyncio
async def test_only_one_player_in_voice_is_split():
    channel = make_channel(500, "Grassy Gnoll")
    members = {
        10: make_member(10, "Bruce", channel),
        20: make_member(20, "Aadu"),
    }
    payload = await voice_session(make_bot(members), [10, 20])

    assert payload["status"] == "split"
    assert payload["channel"]["id"] == "500"
    assert payload["players"][1] == {
        "user_id": "20",
        "display_name": "Aadu",
        "in_voice": False,
        "channel_id": None,
        "streaming": False,
    }


@pytest.mark.asyncio
async def test_busiest_channel_wins_when_players_are_apart():
    quiet = make_channel(500, "The Dungeon")
    busy = make_channel(600, "The Summit")
    members = {
        10: make_member(10, "Bruce", quiet),
        20: make_member(20, "Aadu", busy),
        30: make_member(30, "CJ", busy),
    }
    payload = await voice_session(make_bot(members), [10, 20, 30])

    assert payload["status"] == "split"
    assert payload["channel"]["id"] == "600"


@pytest.mark.asyncio
async def test_nobody_in_voice_still_offers_the_summit_invite():
    members = {10: make_member(10, "Bruce"), 20: None}
    payload = await voice_session(make_bot(members), [10, 20])

    assert payload["status"] == "not_in_voice"
    assert payload["channel"] is None
    assert payload["players"][1]["display_name"] is None
    assert payload["summit_invite_url"]
    assert payload["voice_hub_url"]


@pytest.mark.asyncio
async def test_unknown_guild_returns_none_for_a_503():
    bot = make_bot({}, ready=False)
    assert await voice_session(bot, [10]) is None


@pytest.mark.asyncio
async def test_invite_is_cached_per_channel_and_expires():
    channel = make_channel(500, "The Dungeon")
    members = {10: make_member(10, "Bruce", channel)}
    bot = make_bot(members)

    await voice_session(bot, [10])
    await voice_session(bot, [10])
    assert channel.create_invite.await_count == 1

    voice_presence._invite_cache[500] = ("https://discord.gg/stale", time.time() - 1)
    payload = await voice_session(bot, [10])
    assert channel.create_invite.await_count == 2
    assert payload["channel"]["listen_url"] == "https://discord.gg/listen"


@pytest.mark.asyncio
async def test_missing_invite_permission_falls_back_to_the_channel_link():
    channel = make_channel(500, "The Dungeon")
    channel.create_invite = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "no invites")
    )
    members = {10: make_member(10, "Bruce", channel)}

    payload = await voice_session(make_bot(members), [10])

    assert payload["channel"]["invite_url"] is None
    assert payload["channel"]["listen_url"] == "https://discord.com/channels/1/500"
