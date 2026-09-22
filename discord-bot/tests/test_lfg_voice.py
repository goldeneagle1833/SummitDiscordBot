"""Voice preferences on the Ranked and Casual queues."""

import datetime
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg.cog import LFGCog
from cogs.lfg.queue import DeckURLModal, match_delivery_extras, provision_match_and_publish_results
from cogs.lfg.state import lfg_queue, pending_web_matches
from cogs.lfg.voice import (
    ANY_VOICE,
    NO_VOICE,
    VOICE,
    normalize_voice_preference,
    resolve_match_voice,
    voice_preferences_compatible,
)
from repositories.elo_repo import get_pairing_by_id, get_pairing_voice, save_pairing
from services.elo_service import record_match
from services.matchmaking_api import _status


def entry(queue_type, minutes_ago, voice=None):
    queue_entry = {
        "timestamp": datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago),
        "timeframe": 30,
        "deck_url": None,
    }
    if voice is not None:
        queue_entry["voice"] = voice
    return {"queues": {queue_type: queue_entry}}


@pytest.fixture
def lfg_cog():
    cog = object.__new__(LFGCog)
    cog.bot = Mock()
    cog.lfg_channel_id = 1
    cog.check_last_match_opponent = MagicMock(return_value=False)
    return cog


@pytest.fixture
def ctx():
    ctx = Mock()
    ctx.author = Mock()
    ctx.author.id = 999
    return ctx


@pytest.fixture(autouse=True)
def clear_queue():
    lfg_queue.clear()
    pending_web_matches.clear()
    yield
    lfg_queue.clear()
    pending_web_matches.clear()


class TestVoiceRules:
    @pytest.mark.parametrize(
        "raw, expected",
        [(None, ANY_VOICE), ("", ANY_VOICE), ("voice", VOICE), ("No-Voice", NO_VOICE),
         (" any ", ANY_VOICE), ("maybe", None), (True, None)],
    )
    def test_normalize(self, raw, expected):
        assert normalize_voice_preference(raw) == expected

    def test_only_voice_and_no_voice_clash(self):
        assert not voice_preferences_compatible(VOICE, NO_VOICE)
        assert not voice_preferences_compatible(NO_VOICE, VOICE)
        for a, b in [(VOICE, VOICE), (VOICE, ANY_VOICE), (NO_VOICE, NO_VOICE),
                     (NO_VOICE, ANY_VOICE), (ANY_VOICE, ANY_VOICE), (VOICE, None)]:
            assert voice_preferences_compatible(a, b)

    def test_match_is_voice_when_either_player_asked(self):
        assert resolve_match_voice(VOICE, ANY_VOICE)
        assert resolve_match_voice(ANY_VOICE, VOICE)
        assert not resolve_match_voice(ANY_VOICE, ANY_VOICE)
        assert not resolve_match_voice(NO_VOICE, ANY_VOICE)


class TestVoiceMatching:
    def test_voice_player_skips_no_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10, NO_VOICE)
        lfg_queue[222] = entry("ranked", 5, ANY_VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) == 222

    def test_no_voice_player_skips_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("testing", 10, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "testing", voice=NO_VOICE) is None

    def test_any_matches_oldest_regardless_of_voice(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10, NO_VOICE)
        lfg_queue[222] = entry("ranked", 5, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=ANY_VOICE) == 111

    def test_legacy_entries_without_voice_count_as_any(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) == 111

    def test_other_queues_ignore_voice(self, lfg_cog, ctx):
        lfg_queue[111] = entry("rumble", 10, NO_VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "rumble", voice=VOICE) == 111

    def test_add_to_queue_stores_voice(self, lfg_cog, ctx):
        lfg_cog.add_to_lfg_queue(ctx, 30, None, "ranked", voice=NO_VOICE)
        assert lfg_queue[999]["queues"]["ranked"]["voice"] == NO_VOICE


class TestVoiceMessages:
    def test_voice_match_always_gets_voice_link(self):
        assert "Join To Make a Room" in match_delivery_extras({}, 1, 2, "ranked", True)[4]

    def test_no_voice_match_has_no_room_link_even_with_seats(self):
        seats = {1: "a", 2: "b"}
        for queue_type in ("ranked", "testing"):
            assert match_delivery_extras(seats, 1, 2, queue_type, False)[4] == ""

    def test_other_queues_keep_legacy_voice_reminder(self):
        extras = match_delivery_extras({1: "a", 2: "b"}, 1, 2, "rumble", False)
        assert "Join To Make a Room" in extras[4]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("voice, tag, has_link", [
        (True, "(🔊 Voice match)", True),
        (False, "(🔇 No-voice match)", False),
    ])
    async def test_both_players_dm_says_voice_or_no_voice(self, voice, tag, has_link):
        from cogs.lfg.pairing_messages import PairingPlayer, send_pairing_messages

        def player(user_id):
            user = MagicMock()
            user.mention = f"<@{user_id}>"
            user.send = AsyncMock(return_value=MagicMock())
            return PairingPlayer(user_id, f"P{user_id}", user)

        reporter, other = player(1), player(2)
        with patch("cogs.lfg.pairing_messages.update_match_card_message_ref"):
            await send_pairing_messages(
                MagicMock(), reporter=reporter, other=other,
                match_card_view=MagicMock(), match_type="ranked", voice=voice,
            )
        for p in (reporter, other):
            text = p.user.send.await_args.args[0]
            assert f"**Ranked Match Found!** {tag}" in text
            assert ("Join To Make a Room" in text) is has_link

    @pytest.mark.asyncio
    async def test_direct_challenges_get_no_voice_tag(self):
        from cogs.lfg.pairing_messages import PairingPlayer, send_pairing_messages

        user = MagicMock()
        user.send = AsyncMock(return_value=MagicMock())
        reporter, other = PairingPlayer(1, "A", user), PairingPlayer(2, "B", user)
        with patch("cogs.lfg.pairing_messages.update_match_card_message_ref"):
            await send_pairing_messages(
                MagicMock(), reporter=reporter, other=other,
                match_card_view=MagicMock(), headline="Challenge Accepted!",
            )
        text = user.send.await_args.args[0]
        assert "Voice match" not in text and "No-voice match" not in text


class TestVoicePersistence:
    def test_pairing_stores_voice(self):
        voice_id = save_pairing(1, 10, 20, "", "", "ranked", voice=True)
        quiet_id = save_pairing(1, 30, 40, "", "", "ranked")
        assert get_pairing_voice(voice_id) is True
        assert get_pairing_voice(quiet_id) is False
        assert get_pairing_voice(None) is False
        assert get_pairing_by_id(1, voice_id)["voice"] == 1

    @pytest.mark.asyncio
    async def test_record_match_copies_voice_from_pairing(self):
        pairing_id = save_pairing(1, 10, 20, "", "", "ranked", voice=True)
        with patch("services.elo_service.scrape_Curosa", return_value="{}"), \
             patch("services.elo_service.get_active_event", return_value=None):
            voiced = await record_match(10, 10, "A", 20, "B", "y", 20, "", None, None,
                                        "y", "n", pairing_id=pairing_id)
            unvoiced = await record_match(10, 10, "A", 20, "B", "y", 20, "", None, None,
                                          "y", "n")
        conn = sqlite3.connect("match_records.db")
        rows = dict(conn.execute(
            "SELECT match_id, voice FROM match_records WHERE match_id IN (?, ?)",
            (voiced[0], unvoiced[0]),
        ).fetchall())
        stored_pairing = conn.execute(
            "SELECT pairing_id FROM match_records WHERE match_id = ?", (voiced[0],)
        ).fetchone()[0]
        conn.close()
        assert rows == {voiced[0]: 1, unvoiced[0]: 0}
        assert stored_pairing == pairing_id


class TestVoiceWebsite:
    @pytest.mark.asyncio
    async def test_status_reports_voice_counts_and_own_preference(self):
        lfg_queue[1] = entry("ranked", 5, VOICE)
        lfg_queue[2] = entry("ranked", 5, NO_VOICE)
        lfg_queue[3] = entry("ranked", 5)
        lfg_queue[3]["queues"]["rumble"] = entry("rumble", 5)["queues"]["rumble"]
        definitions = [
            {"type": "ranked", "label": "Ranked", "emoji": "x", "deck_mode": "required"},
            {"type": "rumble", "label": "Rumble", "emoji": "y", "deck_mode": "required"},
        ]
        bot = MagicMock()
        bot.get_cog.return_value = None
        with patch("services.matchmaking_api._summit_member", return_value=(None, object())), \
             patch("services.matchmaking_api.enabled_queue_definitions", return_value=definitions):
            status = await _status(bot, 2)
        ranked, rumble = status["queues"]
        assert ranked["voice_options"] is True
        assert ranked["waiting_by_voice"] == {VOICE: 1, NO_VOICE: 1, ANY_VOICE: 1}
        assert ranked["voice"] == NO_VOICE
        assert rumble["voice_options"] is False
        assert "waiting_by_voice" not in rumble

    @pytest.mark.asyncio
    async def test_website_result_carries_voice_flag(self):
        players = [
            {"discord_user_id": 10, "origin": "sorcery_online", "opponent_name": "B"},
            {"discord_user_id": 20, "origin": "discord", "opponent_name": "A"},
        ]
        with patch("cogs.lfg.queue.provision_sorcery_online_match",
                   return_value={10: "https://so.test/10", 20: "https://so.test/20"}):
            await provision_match_and_publish_results(1, 2, "ranked", players, voice=True)
        assert pending_web_matches[10]["voice"] is True


class TestVoiceModal:
    def test_ranked_and_casual_modals_have_required_voice_dropdown(self):
        for queue_type in ("ranked", "testing"):
            modal = DeckURLModal(MagicMock(), queue_type=queue_type)
            labels = [item for item in modal.children if isinstance(item, discord.ui.Label)]
            assert len(labels) == 1
            select = labels[0].component
            assert [o.value for o in select.options] == [VOICE, NO_VOICE, ANY_VOICE]
            assert select.required
            # Voice is preselected so joining needs no extra clicks.
            assert [o.value for o in select.options if o.default] == [VOICE]
            # Deck URL, then voice, then duration
            assert modal.children.index(labels[0]) == 1
            assert modal.children[-1] is modal.timeframe

    def test_other_queues_have_no_voice_dropdown(self):
        modal = DeckURLModal(MagicMock(), queue_type="rumble")
        assert modal.voice_select is None
        assert not any(isinstance(item, discord.ui.Label) for item in modal.children)
