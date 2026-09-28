"""Voice preferences on every LFG queue: voice or no voice, nothing in between."""

import datetime
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg.cog import LFGCog
from cogs.lfg.queue import (
    DeckURLModal,
    LimitedQueueModal,
    PointsQueueModal,
    match_delivery_extras,
    provision_match_and_publish_results,
)
from cogs.lfg.state import lfg_queue, pending_web_matches
from cogs.lfg.voice import (
    NO_VOICE,
    VOICE,
    VOICE_PREFERENCES,
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
        [(None, VOICE), ("", VOICE), ("voice", VOICE), ("No-Voice", NO_VOICE),
         (" any ", None), ("either", None), ("maybe", None), (True, None)],
    )
    def test_normalize(self, raw, expected):
        assert normalize_voice_preference(raw) == expected

    def test_there_is_no_either_option(self):
        assert VOICE_PREFERENCES == (VOICE, NO_VOICE)

    def test_only_the_same_choice_pairs(self):
        assert not voice_preferences_compatible(VOICE, NO_VOICE)
        assert not voice_preferences_compatible(NO_VOICE, VOICE)
        for a, b in [(VOICE, VOICE), (NO_VOICE, NO_VOICE), (VOICE, None), (None, None)]:
            assert voice_preferences_compatible(a, b)

    def test_match_is_voice_when_players_asked(self):
        assert resolve_match_voice(VOICE, VOICE)
        assert resolve_match_voice(VOICE, None)
        assert not resolve_match_voice(NO_VOICE, NO_VOICE)


class TestVoiceMatching:
    def test_voice_player_skips_no_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10, NO_VOICE)
        lfg_queue[222] = entry("ranked", 5, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) == 222

    def test_no_voice_player_skips_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("testing", 10, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "testing", voice=NO_VOICE) is None

    def test_default_preference_is_voice(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10, NO_VOICE)
        lfg_queue[222] = entry("ranked", 5, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 222

    def test_entries_without_voice_count_as_voice(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 10)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) == 111
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=NO_VOICE) is None

    @pytest.mark.parametrize("queue_type", ["points", "ranked", "testing", "limited", "rumble"])
    def test_every_queue_respects_voice(self, lfg_cog, ctx, queue_type):
        lfg_queue[111] = entry(queue_type, 10, NO_VOICE)
        lfg_queue[222] = entry(queue_type, 5, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, queue_type, voice=VOICE) == 222
        assert lfg_cog.check_if_someone_is_lfg(ctx, queue_type, voice=NO_VOICE) == 111

    def test_add_to_queue_stores_voice(self, lfg_cog, ctx):
        lfg_cog.add_to_lfg_queue(ctx, 30, None, "ranked", voice=NO_VOICE)
        assert lfg_queue[999]["queues"]["ranked"]["voice"] == NO_VOICE

    def test_add_to_queue_defaults_and_rejects_either(self, lfg_cog, ctx):
        lfg_cog.add_to_lfg_queue(ctx, 30, None, "rumble")
        assert lfg_queue[999]["queues"]["rumble"]["voice"] == VOICE
        lfg_cog.add_to_lfg_queue(ctx, 30, None, "limited", voice="any")
        assert lfg_queue[999]["queues"]["limited"]["voice"] == VOICE


class TestVoiceMessages:
    def test_voice_match_always_gets_voice_link(self):
        assert "Join To Make a Room" in match_delivery_extras({}, 1, 2, is_voice_match=True)[4]

    def test_no_voice_match_has_no_room_link_even_with_seats(self):
        seats = {1: "a", 2: "b"}
        assert match_delivery_extras(seats, 1, 2, is_voice_match=False)[4] == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("match_type, label", [("ranked", "Ranked"), ("rumble", "Rumble")])
    @pytest.mark.parametrize("voice, tag, has_link", [
        (True, "(🔊 Voice match)", True),
        (False, "(🔇 No-voice match)", False),
    ])
    async def test_both_players_dm_says_voice_or_no_voice(self, voice, tag, has_link, match_type, label):
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
                match_card_view=MagicMock(), match_type=match_type, voice=voice,
            )
        for p in (reporter, other):
            text = p.user.send.await_args.args[0]
            assert f"**{label} Match Found!** {tag}" in text
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
        for queue in (ranked, rumble):
            assert queue["voice_options"] is True
            assert queue["voice_choices"] == [VOICE, NO_VOICE]
            assert queue["default_voice"] == VOICE
        assert ranked["waiting_by_voice"] == {VOICE: 2, NO_VOICE: 1}
        assert ranked["voice"] == NO_VOICE
        assert rumble["waiting_by_voice"] == {VOICE: 1, NO_VOICE: 0}
        assert rumble["voice"] is None

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
    @staticmethod
    def assert_voice_dropdown(modal):
        labels = [item for item in modal.children if isinstance(item, discord.ui.Label)]
        assert len(labels) == 1
        select = labels[0].component
        assert select is modal.voice_select
        assert [o.value for o in select.options] == [VOICE, NO_VOICE]
        assert select.required
        # Voice is preselected so joining needs no extra clicks.
        assert [o.value for o in select.options if o.default] == [VOICE]
        # Voice sits just above the duration field, which stays last.
        assert modal.children.index(labels[0]) == len(modal.children) - 2
        assert modal.children[-1] is modal.timeframe

    @pytest.mark.parametrize("queue_type", ["ranked", "testing", "rumble"])
    def test_deck_url_modal_has_required_voice_dropdown(self, queue_type):
        modal = DeckURLModal(MagicMock(), queue_type=queue_type)
        self.assert_voice_dropdown(modal)
        assert modal.children[0] is modal.deck_url

    def test_limited_modal_has_voice_dropdown(self):
        modal = LimitedQueueModal(MagicMock())
        self.assert_voice_dropdown(modal)
        assert modal.children[0] is modal.draft_url

    def test_points_modal_has_voice_dropdown(self):
        modal = PointsQueueModal(MagicMock())
        self.assert_voice_dropdown(modal)
        assert modal.children[0] is modal.deck_url
