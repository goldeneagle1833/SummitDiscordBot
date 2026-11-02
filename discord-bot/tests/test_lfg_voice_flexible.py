"""First voice choice plus "also OK with the other": voice holds and voice-first pairing."""

import datetime
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg.cog import LFGCog
from cogs.lfg.state import lfg_queue, matching_web_users, pending_web_matches
from cogs.lfg.voice import (
    NO_VOICE,
    VOICE,
    VOICE_HOLD_SECONDS,
    holding_for_voice,
    normalize_voice_flexible,
    resolve_match_voice,
    voice_choice_from_checkboxes,
    voice_choice_label,
    voice_preferences_compatible,
)
from cogs.lfg.voice_hold import held_players_ready, release_voice_holds
from cogs.lfg.voice_offer import waiting_voice_players
from services.matchmaking_api import _status


def entry(queue_type, seconds_ago, voice=VOICE, flexible=False, origin="discord"):
    queue_entry = {
        "timestamp": datetime.datetime.now() - datetime.timedelta(seconds=seconds_ago),
        "timeframe": 30,
        "deck_url": "https://deck.test/1",
        "origin": origin,
        "voice": voice,
    }
    if flexible:
        queue_entry["voice_flexible"] = True
    return {"queues": {queue_type: queue_entry}}


@pytest.fixture
def lfg_cog():
    cog = object.__new__(LFGCog)
    cog.bot = Mock()
    cog.lfg_channel_id = 1
    cog.check_last_match_opponent = MagicMock(return_value=False)
    cog.clean_expired_lfg = MagicMock()
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
    matching_web_users.clear()
    yield
    lfg_queue.clear()
    pending_web_matches.clear()
    matching_web_users.clear()


class TestFlexibleRules:
    def test_strict_players_behave_as_before(self):
        assert voice_preferences_compatible(VOICE, VOICE)
        assert not voice_preferences_compatible(VOICE, NO_VOICE)
        assert not resolve_match_voice(NO_VOICE, NO_VOICE)

    def test_flexible_players_pair_with_either_choice(self):
        assert voice_preferences_compatible(VOICE, NO_VOICE, True, False)
        assert voice_preferences_compatible(NO_VOICE, VOICE, True, False)
        assert voice_preferences_compatible(NO_VOICE, NO_VOICE, True, True)

    def test_match_is_on_voice_whenever_both_would_play_voice(self):
        # A no-voice-first player who is OK with voice plays a voice player on voice
        assert resolve_match_voice(NO_VOICE, VOICE, True, False)
        # Two no-voice-first players who are both OK with voice play on voice
        assert resolve_match_voice(NO_VOICE, NO_VOICE, True, True)
        # Someone who only plays without voice makes it a no-voice game
        assert not resolve_match_voice(VOICE, NO_VOICE, True, False)

    def test_only_voice_first_flexible_players_hold(self):
        now = datetime.datetime.now()
        just_now = now - datetime.timedelta(seconds=5)
        long_ago = now - datetime.timedelta(seconds=VOICE_HOLD_SECONDS + 1)
        assert holding_for_voice(VOICE, True, just_now, now)
        assert not holding_for_voice(VOICE, True, long_ago, now)
        assert not holding_for_voice(VOICE, False, just_now, now)
        assert not holding_for_voice(NO_VOICE, True, just_now, now)

    @pytest.mark.parametrize(
        "ticked, expected",
        [([], (VOICE, False)), (None, (VOICE, False)), ([VOICE], (VOICE, False)),
         ([VOICE, NO_VOICE], (VOICE, True)), ([NO_VOICE, VOICE], (VOICE, True)), ([NO_VOICE], (NO_VOICE, False))],
    )
    def test_modal_choices(self, ticked, expected):
        assert voice_choice_from_checkboxes(ticked) == expected

    def test_labels_and_flag_parsing(self):
        assert voice_choice_label(VOICE, True) == "🤝 Voice or no voice (voice first)"
        assert normalize_voice_flexible(True) is True
        assert normalize_voice_flexible("true") is True
        assert normalize_voice_flexible(None) is False
        assert normalize_voice_flexible("nope") is False


class TestFlexibleMatching:
    def test_voice_first_joiner_holds_instead_of_taking_a_no_voice_game(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 60, NO_VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE, voice_flexible=True) is None
        # Once the hold is over (the sweep re-joining them) they take it
        assert lfg_cog.check_if_someone_is_lfg(
            ctx, "ranked", voice=VOICE, voice_flexible=True, voice_hold=False
        ) == 111

    def test_voice_first_joiner_takes_a_voice_partner_at_once(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 60, NO_VOICE)
        lfg_queue[222] = entry("ranked", 10, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE, voice_flexible=True) == 222

    def test_no_voice_joiner_waits_out_a_holding_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 5, VOICE, flexible=True)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=NO_VOICE) is None
        lfg_queue[111] = entry("ranked", VOICE_HOLD_SECONDS + 5, VOICE, flexible=True)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=NO_VOICE) == 111

    def test_voice_joiner_pairs_with_a_holding_voice_player(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 5, VOICE, flexible=True)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) == 111

    def test_flexible_no_voice_joiner_prefers_a_voice_game(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 120, NO_VOICE)
        lfg_queue[222] = entry("ranked", 10, VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=NO_VOICE, voice_flexible=True) == 222

    def test_strict_players_still_never_cross(self, lfg_cog, ctx):
        lfg_queue[111] = entry("ranked", 120, NO_VOICE)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", voice=VOICE) is None

    def test_limited_ignores_voice(self, lfg_cog, ctx):
        lfg_queue[111] = entry("limited", 5, VOICE, flexible=True)
        assert lfg_cog.check_if_someone_is_lfg(ctx, "limited", voice=NO_VOICE) == 111

    def test_flexible_voice_players_are_not_sent_no_voice_offers(self):
        lfg_queue[111] = entry("ranked", 60, VOICE, flexible=True)
        lfg_queue[222] = entry("ranked", 60, VOICE)
        assert waiting_voice_players("ranked", 333) == [222]


class TestVoiceHoldSweep:
    def test_finds_only_players_past_the_hold_with_a_partner(self, lfg_cog):
        lfg_queue[111] = entry("ranked", VOICE_HOLD_SECONDS + 5, VOICE, flexible=True)
        lfg_queue[222] = entry("ranked", 5, VOICE, flexible=True)
        lfg_queue[333] = entry("ranked", 90, NO_VOICE)
        ready = held_players_ready(lfg_cog)
        assert [(user_id, queue_type) for user_id, queue_type, _ in ready] == [(111, "ranked")]
        # The held player leaves the queue; the re-join puts them back or pairs them
        assert 111 not in lfg_queue
        assert 333 in lfg_queue and 222 in lfg_queue

    def test_nothing_happens_without_a_no_voice_partner(self, lfg_cog):
        lfg_queue[111] = entry("ranked", VOICE_HOLD_SECONDS + 5, VOICE, flexible=True)
        assert held_players_ready(lfg_cog) == []
        assert 111 in lfg_queue

    @pytest.mark.asyncio
    async def test_rejoins_with_the_hold_over(self, lfg_cog):
        lfg_queue[111] = entry("ranked", VOICE_HOLD_SECONDS + 5, VOICE, flexible=True, origin="sorcery_online")
        lfg_queue[333] = entry("ranked", 90, NO_VOICE)
        bot = MagicMock()
        bot.get_cog.return_value = lfg_cog
        guild = MagicMock()
        guild.get_member.return_value = Mock(id=111)
        bot.get_guild.return_value = guild
        with patch("cogs.lfg.queue._process_queue_join", AsyncMock()) as join:
            await release_voice_holds(bot)
        kwargs = join.await_args.kwargs
        assert join.await_args.args[2] == "ranked"
        assert kwargs["voice"] == VOICE
        assert kwargs["voice_flexible"] is True
        assert kwargs["voice_hold"] is False
        assert kwargs["origin"] == "sorcery_online"


class TestFlexibleStatus:
    @pytest.mark.asyncio
    async def test_status_reports_flexible_support_and_willing_counts(self):
        lfg_queue[1] = entry("ranked", 5, VOICE, flexible=True)
        lfg_queue[2] = entry("ranked", 5, NO_VOICE)
        lfg_queue[3] = entry("ranked", 5, NO_VOICE, flexible=True)
        definitions = [{"type": "ranked", "label": "Ranked", "emoji": "x", "deck_mode": "required"}]
        bot = MagicMock()
        bot.get_cog.return_value = None
        with patch("services.matchmaking_api._summit_member", return_value=(None, object())), \
             patch("services.matchmaking_api.enabled_queue_definitions", return_value=definitions):
            status = await _status(bot, 3)
        (ranked,) = status["queues"]
        assert ranked["voice_flexible_supported"] is True
        assert ranked["voice_hold_seconds"] == VOICE_HOLD_SECONDS
        # First choices are counted as before
        assert ranked["waiting_by_voice"] == {VOICE: 1, NO_VOICE: 2}
        assert ranked["waiting_willing"] == {VOICE: 2, NO_VOICE: 3}
        assert ranked["voice"] == NO_VOICE
        assert ranked["voice_flexible"] is True


class TestRememberedVoiceAnswers:
    def test_first_join_starts_with_nothing_ticked(self):
        from cogs.lfg.queue import build_voice_select

        select = build_voice_select(None)
        assert [o.default for o in select.options] == [False, False]

    def test_last_answers_are_ticked(self):
        from cogs.lfg.queue import build_voice_select

        select = build_voice_select((True, True))
        assert [o.default for o in select.options] == [True, True]
        select = build_voice_select((False, True))
        assert [o.default for o in select.options] == [False, True]

    def test_answers_round_trip_through_the_database(self):
        from cogs.lfg.queue import load_voice_answers, remember_voice_answers

        assert load_voice_answers(4242) is None
        remember_voice_answers(4242, VOICE, True)
        assert load_voice_answers(4242) == (True, True)
        remember_voice_answers(4242, NO_VOICE, False)
        assert load_voice_answers(4242) == (False, True)
        remember_voice_answers(4242, VOICE, False)
        assert load_voice_answers(4242) == (True, False)

    def test_join_modal_uses_the_last_answers(self):
        from cogs.lfg.queue import DeckURLModal

        modal = DeckURLModal(MagicMock(), queue_type="ranked", voice_answers=(True, False))
        assert [o.default for o in modal.voice_select.options] == [True, False]
