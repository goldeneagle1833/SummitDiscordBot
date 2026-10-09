"""Tests for the shared pairing messages both players receive on a match."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.lfg.helpers import (
    MATCH_CORRECTION_CHANNEL_ID,
    correction_tip,
    deck_text_if_private,
)
from cogs.lfg.pairing_messages import (
    PairingPlayer,
    announce_match_id,
    announce_pairing,
    match_delivery_extras,
    match_type_presentation,
    send_pairing_messages,
)
from cogs.lfg.voice import SUMMIT_VOICE_URL
from services.summit_result_reporting import _notify_sorcery_online_match_recorded


def _player(user_id, name, deck_url=None, dm_ok=True, interaction=None):
    user = MagicMock()
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.global_name = name
    user.display_name = name
    if dm_ok:
        user.send = AsyncMock(return_value=_sent_message())
    else:
        user.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "no DMs"))
    return PairingPlayer(user_id, name, user, deck_url, interaction=interaction)


def _sent_message():
    message = MagicMock()
    message.id = 999
    message.channel.id = 888
    return message


def _bot(dm_channel=None):
    bot = MagicMock()
    bot.get_channel.return_value = dm_channel
    bot.get_guild.return_value = None
    return bot


def _card_view():
    view = MagicMock()
    view.card_id = 42
    return view


# ── wording ──────────────────────────────────────────────────────────


def test_correction_tip_names_the_command_and_channel():
    tip = correction_tip()
    assert "!correct_match <match id>" in tip
    assert f"<#{MATCH_CORRECTION_CHANNEL_ID}>" in tip


def test_correction_tip_fills_in_a_known_match_id():
    tip = correction_tip(2241)
    assert "!correct_match 2241" in tip
    assert "<match id>" not in tip


@pytest.mark.asyncio
async def test_a_result_recorded_outside_discord_carries_both_tips():
    bot = MagicMock()
    user = MagicMock()
    user.send = AsyncMock()
    bot.fetch_user = AsyncMock(return_value=user)

    await _notify_sorcery_online_match_recorded(
        bot,
        match_id=2241,
        match_type="ranked",
        winner_id=10,
        winner_name="t1ny",
        loser_id=20,
        loser_name="Bruce",
    )

    assert user.send.await_count == 2
    for call in user.send.await_args_list:
        text = call.args[0]
        assert "**Match ID: #2241**" in text
        assert "📋 Report Last Match" in text
        assert "!correct_match 2241" in text


@pytest.mark.asyncio
async def test_both_players_get_the_same_match_type_and_the_correction_tip():
    reporter = _player(10, "Reporter", deck_url="https://curiosa.io/decks/a")
    other = _player(20, "Other", deck_url="https://curiosa.io/decks/b")

    await send_pairing_messages(
        _bot(),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
        match_type="limited",
    )

    reporter_text = reporter.user.send.await_args.args[0]
    other_text = other.user.send.await_args.args[0]

    emoji, label = match_type_presentation("limited")
    for text in (reporter_text, other_text):
        assert f"{emoji} **{label} Match Found!**" in text
        assert "!correct_match <match id>" in text
        assert f"<#{MATCH_CORRECTION_CHANNEL_ID}>" in text

    # Each player sees their own deck, never their opponent's.
    assert "decks/a" in reporter_text and "decks/b" not in reporter_text
    assert "decks/b" in other_text and "decks/a" not in other_text

    # Only the reporter is told they hold the buttons.
    assert "You have the match report buttons" in reporter_text
    assert "**Reporter** has the match report buttons" in other_text


@pytest.mark.asyncio
async def test_headline_override_is_used_for_accepted_challenges():
    reporter = _player(10, "Reporter")
    other = _player(20, "Other")

    await send_pairing_messages(
        _bot(),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
        headline="Challenge Accepted!",
    )

    for player in (reporter, other):
        text = player.user.send.await_args.args[0]
        assert "**Challenge Accepted!**" in text
        assert "Match Found!" not in text


# ── delivery ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_dms_report_no_fallback():
    reporter = _player(10, "Reporter")
    other = _player(20, "Other")

    delivery = await send_pairing_messages(
        _bot(),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
    )

    assert delivery.fell_back_for(10) is False
    assert delivery.fell_back_for(20) is False


@pytest.mark.asyncio
async def test_dm_failure_falls_back_to_channel_without_leaking_the_deck():
    dm_channel = MagicMock()
    dm_channel.send = AsyncMock(return_value=_sent_message())
    dm_channel.set_permissions = AsyncMock()

    reporter = _player(10, "Reporter", deck_url="https://curiosa.io/decks/a", dm_ok=False)
    other = _player(20, "Other")

    delivery = await send_pairing_messages(
        _bot(dm_channel),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
    )

    assert delivery.fell_back_for(10) is True
    assert delivery.fell_back_for(20) is False

    fallback_text = dm_channel.send.await_args.args[0]
    assert "<@10>" in fallback_text  # pings the player it is meant for
    assert "curiosa.io" not in fallback_text
    assert "!correct_match <match id>" in fallback_text


@pytest.mark.asyncio
async def test_an_interacting_player_is_answered_ephemerally():
    interaction = MagicMock()
    interaction.followup.send = AsyncMock()

    reporter = _player(10, "Reporter", interaction=interaction)
    other = _player(20, "Other")

    delivery = await send_pairing_messages(
        _bot(),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
        headline="Challenge Accepted!",
    )

    reporter.user.send.assert_not_awaited()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert delivery.fell_back_for(10) is False


# ── announcement ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_announcement_uses_the_match_type_and_optional_note():
    channel = MagicMock()
    channel.send = AsyncMock()
    player_a = MagicMock(mention="<@10>")
    player_b = MagicMock(mention="<@20>")

    await announce_pairing(
        channel,
        player_a=player_a,
        player_b=player_b,
        match_type="points",
        note=" 🏆 note",
    )

    text = channel.send.await_args.args[0]
    assert "📊 **Rumble (Omens) Match Found!**" in text
    assert "<@10> matched with <@20>!" in text
    assert text.endswith(" 🏆 note")
    assert "Match ID" not in text


@pytest.mark.asyncio
async def test_announcement_remembers_its_message_when_a_pairing_id_is_given():
    # The record id does not exist yet, so the message is stored to be edited later.
    channel = MagicMock()
    channel.send = AsyncMock(return_value=_sent_message())

    with patch("cogs.lfg.pairing_messages.save_pairing_announcement") as save:
        await announce_pairing(
            channel,
            player_a=MagicMock(mention="<@10>"),
            player_b=MagicMock(mention="<@20>"),
            match_type="ranked",
            pairing_id=417,
        )

    assert "Match ID" not in channel.send.await_args.args[0]
    save.assert_called_once_with(417, "ranked", 888, 999)


@pytest.mark.asyncio
async def test_announcement_is_not_remembered_without_a_pairing_id():
    # Direct challenges without a guild fall back to pairing id 0.
    channel = MagicMock()
    channel.send = AsyncMock(return_value=_sent_message())

    with patch("cogs.lfg.pairing_messages.save_pairing_announcement") as save:
        await announce_pairing(
            channel,
            player_a=MagicMock(mention="<@10>"),
            player_b=MagicMock(mention="<@20>"),
            pairing_id=0,
        )

    save.assert_not_called()


@pytest.mark.asyncio
async def test_recorded_match_id_is_appended_to_the_announcement():
    message = MagicMock()
    message.content = "⚔️ **Ranked Match Found!** <@10> matched with <@20>!"
    message.edit = AsyncMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=message)
    bot = _bot(channel)

    with (
        patch(
            "cogs.lfg.pairing_messages.get_pairing_announcement",
            return_value={"channel_id": 888, "message_id": 999},
        ),
        patch("cogs.lfg.pairing_messages.delete_pairing_announcement") as delete,
    ):
        await announce_match_id(bot, 417, "ranked", 1234)

    channel.fetch_message.assert_awaited_once_with(999)
    message.edit.assert_awaited_once_with(
        content="⚔️ **Ranked Match Found!** <@10> matched with <@20>! **Match ID:** #1234"
    )
    delete.assert_called_once_with(417, "ranked")


@pytest.mark.asyncio
async def test_match_id_is_skipped_when_the_announcement_is_unknown():
    bot = _bot()
    with patch("cogs.lfg.pairing_messages.get_pairing_announcement", return_value=None):
        await announce_match_id(bot, 417, "ranked", 1234)
    bot.get_channel.assert_not_called()


@pytest.mark.asyncio
async def test_announcement_ref_round_trips_through_the_database():
    from utils.database import (
        delete_pairing_announcement,
        get_pairing_announcement,
        save_pairing_announcement,
    )

    save_pairing_announcement(5, "ranked", 888, 999)
    save_pairing_announcement(5, "limited", 777, 666)  # limited ids are a separate space
    assert get_pairing_announcement(5, "ranked") == {"channel_id": 888, "message_id": 999}
    assert get_pairing_announcement(5, "limited") == {"channel_id": 777, "message_id": 666}

    delete_pairing_announcement(5, "ranked")
    assert get_pairing_announcement(5, "ranked") is None
    assert get_pairing_announcement(5, "limited") is not None


# ── no deck lists in public channels ─────────────────────────────────


def test_deck_line_is_kept_in_a_dm_and_dropped_in_a_guild_channel():
    dm = MagicMock(guild=None)
    public = MagicMock(guild=MagicMock())
    assert deck_text_if_private(dm, "\n**Your Deck:** https://curiosa.io/decks/a")
    assert deck_text_if_private(public, "\n**Your Deck:** https://curiosa.io/decks/a") == ""


@pytest.mark.asyncio
async def test_neither_players_fallback_message_carries_a_deck_url():
    dm_channel = MagicMock()
    dm_channel.send = AsyncMock(return_value=_sent_message())
    dm_channel.set_permissions = AsyncMock()

    reporter = _player(10, "Reporter", deck_url="https://curiosa.io/decks/a", dm_ok=False)
    other = _player(20, "Other", deck_url="https://curiosa.io/decks/b", dm_ok=False)

    await send_pairing_messages(
        _bot(dm_channel),
        reporter=reporter,
        other=other,
        match_card_view=_card_view(),
    )

    assert dm_channel.send.await_count == 2
    for call in dm_channel.send.await_args_list:
        text = call.args[0]
        assert "curiosa.io" not in text
        assert "http" not in text.replace(SUMMIT_VOICE_URL, "")


@pytest.mark.asyncio
async def test_announcement_is_skipped_when_there_is_no_channel():
    # Nothing to assert beyond "does not raise" - the LFG channel can be
    # missing when the bot has not cached it yet.
    await announce_pairing(None, player_a=MagicMock(), player_b=MagicMock())


def test_links_in_pairing_messages_are_wrapped_to_skip_embeds():
    from cogs.lfg.helpers import scrub_urls
    from cogs.lfg.voice import voice_match_text

    assert f"(<{SUMMIT_VOICE_URL}>)" in voice_match_text(True)
    *_, reporter_text, other_text, _ = match_delivery_extras(
        {1: "https://pso/a", 2: "https://pso/b"}, 1, 2
    )
    assert "<https://pso/a>" in reporter_text
    assert "<https://pso/b>" in other_text
    assert scrub_urls("Deck: <https://curiosa.io/decks/a>") == "Deck: [link removed]"
