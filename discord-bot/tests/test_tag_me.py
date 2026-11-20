"""Tag me queue setting: players with it off are named in pairing messages but not pinged."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.lfg.pairing_messages import PairingPlayer, announce_pairing, send_pairing_messages
from repositories.tag_me_repo import pairing_mentions, set_tag_me, untagged_ids, wants_tag


def _pinged(allowed):
    return {u.id for u in allowed.users}


def test_on_by_default_and_round_trip():
    assert wants_tag(10) is True
    set_tag_me(10, False)
    set_tag_me(10, False)
    assert wants_tag(10) is False
    assert untagged_ids([10, 20]) == {10}
    set_tag_me(10, True)
    assert wants_tag(10) is True
    assert untagged_ids([10, 20]) == set()


def test_pairing_mentions_only_ping_players_with_tag_me_on():
    set_tag_me(20, False, "test")
    allowed = pairing_mentions(10, 20)
    assert _pinged(allowed) == {10}
    assert allowed.everyone is False and allowed.roles is False


def test_pairing_mentions_ping_everyone_if_the_setting_cant_be_read():
    with patch("repositories.tag_me_repo.untagged_ids", side_effect=RuntimeError("db")):
        assert _pinged(pairing_mentions(10, 20)) == {10, 20}


@pytest.mark.asyncio
async def test_announcement_names_both_players_but_pings_only_tag_me_on():
    set_tag_me(20, False)
    channel = MagicMock()
    channel.send = AsyncMock()

    await announce_pairing(
        channel,
        player_a=MagicMock(id=10, mention="<@10>"),
        player_b=MagicMock(id=20, mention="<@20>"),
        match_type="ranked",
    )

    assert "<@10> matched with <@20>!" in channel.send.await_args.args[0]
    assert _pinged(channel.send.await_args.kwargs["allowed_mentions"]) == {10}


@pytest.mark.asyncio
async def test_announcement_pings_both_by_default():
    channel = MagicMock()
    channel.send = AsyncMock()
    await announce_pairing(
        channel,
        player_a=MagicMock(id=10, mention="<@10>"),
        player_b=MagicMock(id=20, mention="<@20>"),
    )
    assert _pinged(channel.send.await_args.kwargs["allowed_mentions"]) == {10, 20}


def _no_dm_player(user_id):
    user = MagicMock(id=user_id, mention=f"<@{user_id}>")
    user.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "no DMs"))
    return PairingPlayer(user_id, f"P{user_id}", user)


@pytest.mark.asyncio
async def test_dm_disabled_fallback_respects_tag_me():
    set_tag_me(20, False)
    fallback = MagicMock()
    fallback.send = AsyncMock(return_value=MagicMock(id=1, channel=MagicMock(id=2)))
    view = discord.ui.View()
    view.card_id = 5
    with patch("cogs.lfg.pairing_messages._open_dm_disabled_channel", AsyncMock(return_value=fallback)), \
            patch("cogs.lfg.pairing_messages.update_match_card_message_ref"):
        await send_pairing_messages(
            MagicMock(), reporter=_no_dm_player(10), other=_no_dm_player(20), match_card_view=view,
        )

    reporter_call, other_call = fallback.send.await_args_list
    assert reporter_call.args[0].startswith("<@10>")
    assert other_call.args[0].startswith("<@20>")
    assert _pinged(reporter_call.kwargs["allowed_mentions"]) == {10}
    assert _pinged(other_call.kwargs["allowed_mentions"]) == {10}
