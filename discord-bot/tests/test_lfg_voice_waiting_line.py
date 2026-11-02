"""LFG status board calls out players waiting for a voice game (never no-voice)."""

import datetime
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg import state as lfg_state
from cogs.lfg.cog import LFGCog
from cogs.lfg.queue_definitions import QUEUE_DEFINITIONS
from cogs.lfg.state import lfg_queue
from cogs.lfg.voice import NO_VOICE, VOICE, count_waiting_for_voice, voice_waiting_line


def queue_entry(voice=VOICE, flexible=False):
    entry = {
        "timestamp": datetime.datetime.now(),
        "timeframe": 30,
        "deck_url": "https://deck.test/1",
        "origin": "discord",
        "voice": voice,
    }
    if flexible:
        entry["voice_flexible"] = True
    return entry


@pytest.fixture(autouse=True)
def clear_queue():
    lfg_queue.clear()
    yield
    lfg_queue.clear()


def test_counts_everyone_who_would_play_voice():
    entries = [
        queue_entry(VOICE),
        queue_entry(NO_VOICE),
        queue_entry(VOICE, flexible=True),
        queue_entry(NO_VOICE, flexible=True),
        None,
    ]
    assert count_waiting_for_voice(entries) == 3


def test_line_text():
    assert voice_waiting_line(0) == ""
    assert voice_waiting_line(1) == "🔊 **1 player waiting for a voice game!**"
    assert voice_waiting_line(2) == "🔊 **2 players waiting for a voice game!**"


async def _board_fields():
    cog = object.__new__(LFGCog)
    cog.lfg_channel_id = 1
    cog.clean_expired_lfg = MagicMock()
    channel = Mock()
    channel.send = AsyncMock(return_value=Mock(id=5))
    cog.bot = Mock()
    cog.bot.get_channel = Mock(return_value=channel)
    lfg_state.lfg_status_message_id = None
    with patch("cogs.lfg.cog.ActiveQueueButtons"), patch("cogs.lfg.cog.JoinQueueButtons"), patch(
        "cogs.lfg.cog.enabled_queue_definitions", return_value=QUEUE_DEFINITIONS
    ):
        await cog._update_lfg_status_inner()
    embed = channel.send.call_args.kwargs["embed"]
    return {field.name: field.value for field in embed.fields}


def _field(fields, label):
    return next(value for name, value in fields.items() if f"{label} Queue" in name)


@pytest.mark.asyncio
async def test_board_shows_voice_line_only_for_voice_players():
    lfg_queue[1] = {"queues": {"ranked": queue_entry(VOICE)}}
    lfg_queue[2] = {"queues": {"testing": queue_entry(NO_VOICE)}}
    fields = await _board_fields()
    assert _field(fields, "Ranked") == "`1 waiting`\n🔊 **1 player waiting for a voice game!**"
    casual = _field(fields, "Casual")
    assert casual == "`1 waiting`"
    assert "voice" not in casual.lower()


@pytest.mark.asyncio
async def test_limited_never_gets_a_voice_line():
    lfg_queue[1] = {"queues": {"limited": queue_entry(VOICE)}}
    fields = await _board_fields()
    assert _field(fields, "Limited") == "`1 waiting`"
