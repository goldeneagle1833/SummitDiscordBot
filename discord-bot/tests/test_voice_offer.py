"""Waiting voice players are asked whether they'd play a new no-voice player."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.lfg import voice_offer
from cogs.lfg.state import lfg_queue
from cogs.lfg.voice import NO_VOICE, VOICE
from cogs.lfg.voice_offer import (
    NoVoiceOfferView,
    VoiceOnlyToggleView,
    offer_no_voice_game,
    waiting_voice_players,
)
from repositories.voice_only_repo import is_voice_only, set_voice_only, voice_only_ids

NO_VOICE_ID = 500


def entry(minutes_ago, voice, **extra):
    return {
        "timestamp": datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago),
        "timeframe": 30,
        "deck_url": "https://curiosa.io/decks/x",
        "origin": "discord",
        "voice": voice,
        **extra,
    }


def queue(user_id, queue_type, queue_entry):
    lfg_queue.setdefault(user_id, {"queues": {}})["queues"][queue_type] = queue_entry


@pytest.fixture(autouse=True)
def clean_state():
    lfg_queue.clear()
    voice_offer.sent_offers.clear()
    yield
    lfg_queue.clear()
    voice_offer.sent_offers.clear()


@pytest.fixture
def bot():
    bot = MagicMock()
    users = {}

    def get_user(user_id):
        return users.setdefault(user_id, MagicMock(id=user_id, send=AsyncMock()))

    bot.get_user.side_effect = get_user
    bot.users = users
    return bot


def click(view, button_name):
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction, getattr(view, button_name).callback(interaction)


class TestWhoIsAsked:
    def test_waiting_voice_players_oldest_first(self):
        queue(1, "ranked", entry(5, VOICE))
        queue(2, "ranked", entry(10, VOICE))
        queue(3, "ranked", entry(12, NO_VOICE))
        queue(4, "testing", entry(15, VOICE))
        queue(5, "ranked", entry(20, VOICE, ladder_info={"challenger_id": 5}))
        queue(6, "ranked", entry(40, VOICE))  # queue time ran out
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))
        assert waiting_voice_players("ranked", NO_VOICE_ID) == [2, 1]

    def test_old_either_entry_counts_as_voice(self):
        queue(1, "testing", entry(5, "either"))
        assert waiting_voice_players("testing", NO_VOICE_ID) == [1]


class TestSendingOffers:
    @pytest.mark.asyncio
    async def test_each_voice_player_is_asked_once(self, bot):
        queue(1, "ranked", entry(5, VOICE))
        queue(2, "ranked", entry(10, VOICE))
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))

        await offer_no_voice_game(bot, "ranked", NO_VOICE_ID)
        for user_id in (1, 2):
            send = bot.users[user_id].send
            send.assert_awaited_once()
            assert "no-voice" in send.await_args.args[0]
            assert isinstance(send.await_args.kwargs["view"], NoVoiceOfferView)

        await offer_no_voice_game(bot, "ranked", NO_VOICE_ID)
        assert bot.users[1].send.await_count == 1
        assert bot.users[2].send.await_count == 1

    @pytest.mark.asyncio
    async def test_limited_never_asks(self, bot):
        queue(1, "limited", entry(5, VOICE))
        await offer_no_voice_game(bot, "limited", NO_VOICE_ID)
        assert not bot.users

    @pytest.mark.asyncio
    async def test_a_failed_dm_does_not_stop_the_others(self, bot):
        queue(1, "testing", entry(10, VOICE))
        queue(2, "testing", entry(5, VOICE))
        bot.get_user(1).send.side_effect = Exception("DMs closed")
        await offer_no_voice_game(bot, "testing", NO_VOICE_ID)
        bot.users[2].send.assert_awaited_once()


class TestAnsweringTheOffer:
    @pytest.mark.asyncio
    async def test_accept_rejoins_as_no_voice(self, bot):
        queue(1, "ranked", entry(10, VOICE, run_id=None))
        queue(1, "testing", entry(10, VOICE))
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))
        member = MagicMock(id=1)
        bot.get_guild.return_value.get_member.return_value = member

        view = NoVoiceOfferView(bot, "ranked", 1, NO_VOICE_ID)
        with patch("cogs.lfg.queue._process_queue_join", AsyncMock()) as join:
            interaction, pending = click(view, "accept")
            await pending

        join.assert_awaited_once()
        args, kwargs = join.await_args
        assert args[1].user is member
        assert args[2] == "ranked"
        assert args[3] == 20  # minutes left in their queue
        assert args[4] == "https://curiosa.io/decks/x"
        assert kwargs["voice"] == NO_VOICE
        # Only the ranked entry was taken out to re-join; casual stays
        assert "ranked" not in lfg_queue[1]["queues"]
        assert "testing" in lfg_queue[1]["queues"]
        assert all(item.disabled for item in view.children)

    @pytest.mark.asyncio
    async def test_accept_after_the_no_voice_player_left(self, bot):
        queue(1, "ranked", entry(10, VOICE))
        view = NoVoiceOfferView(bot, "ranked", 1, NO_VOICE_ID)
        with patch("cogs.lfg.queue._process_queue_join", AsyncMock()) as join:
            interaction, pending = click(view, "accept")
            await pending

        join.assert_not_awaited()
        assert lfg_queue[1]["queues"]["ranked"]["voice"] == VOICE
        assert "already found a game" in interaction.edit_original_response.await_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_decline_keeps_them_queued_for_voice(self, bot):
        queue(1, "ranked", entry(10, VOICE))
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))
        view = NoVoiceOfferView(bot, "ranked", 1, NO_VOICE_ID)
        interaction, pending = click(view, "decline")
        await pending

        assert lfg_queue[1]["queues"]["ranked"]["voice"] == VOICE
        assert "still in the" in interaction.edit_original_response.await_args.kwargs["content"]


class TestVoiceOnly:
    def test_setting_round_trip(self):
        assert not is_voice_only(1)
        set_voice_only(1, True)
        set_voice_only(1, True)
        assert is_voice_only(1)
        assert voice_only_ids([1, 2]) == {1}
        set_voice_only(1, False)
        assert not is_voice_only(1)
        assert voice_only_ids([]) == set()

    @pytest.mark.asyncio
    async def test_voice_only_players_are_not_asked(self, bot):
        queue(1, "ranked", entry(5, VOICE))
        queue(2, "ranked", entry(10, VOICE))
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))
        set_voice_only(2, True)

        await offer_no_voice_game(bot, "ranked", NO_VOICE_ID)
        bot.users[1].send.assert_awaited_once()
        assert 2 not in bot.users
        # Still queued for voice like before
        assert lfg_queue[2]["queues"]["ranked"]["voice"] == VOICE

    @pytest.mark.asyncio
    async def test_offer_button_marks_voice_only(self, bot):
        queue(1, "ranked", entry(10, VOICE))
        queue(NO_VOICE_ID, "ranked", entry(0, NO_VOICE))
        view = NoVoiceOfferView(bot, "ranked", 1, NO_VOICE_ID)
        interaction, pending = click(view, "voice_only")
        await pending

        assert is_voice_only(1)
        assert lfg_queue[1]["queues"]["ranked"]["voice"] == VOICE
        kwargs = interaction.edit_original_response.await_args.kwargs
        assert "voice-only" in kwargs["content"]
        assert isinstance(kwargs["view"], VoiceOnlyToggleView)

    @pytest.mark.asyncio
    async def test_toggle_button_turns_it_off_and_on(self):
        set_voice_only(1, True)
        view = VoiceOnlyToggleView(1, True)
        assert view.toggle.label == "Turn off voice only"
        interaction, pending = click(view, "toggle")
        interaction.user.id = 1
        await pending
        assert not is_voice_only(1)
        assert view.toggle.label == "Mark me as voice only"

        interaction, pending = click(view, "toggle")
        interaction.user.id = 1
        await pending
        assert is_voice_only(1)

    @pytest.mark.asyncio
    async def test_toggle_button_is_only_for_its_owner(self):
        view = VoiceOnlyToggleView(1, False)
        interaction, pending = click(view, "toggle")
        interaction.user.id = 2
        interaction.response.send_message = AsyncMock()
        await pending
        assert not is_voice_only(1)
        interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_no_voice_join_without_a_match_sends_offers(mock_bot, mock_interaction):
    import asyncio

    from cogs.lfg import queue as queue_mod
    from cogs.lfg.queue import _process_queue_join

    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()
    with patch("cogs.lfg.queue.offer_no_voice_game", AsyncMock()) as offer, \
         patch("cogs.lfg.queue.ranked_block_message", return_value=None):
        # Offers go out after the join reply, in the background
        await _process_queue_join(mock_bot, mock_interaction, "testing", 30, None, voice=NO_VOICE)
        await asyncio.gather(*queue_mod._background_tasks)
        offer.assert_awaited_once_with(mock_bot, "testing", mock_interaction.user.id)

        offer.reset_mock()
        await _process_queue_join(mock_bot, mock_interaction, "rumble", 30, None, voice=VOICE)
        await asyncio.gather(*queue_mod._background_tasks)
        offer.assert_not_awaited()
