"""LFG join modal extras: the Recent decks dropdown and the avatar channel alert."""

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import config
from cogs.lfg import avatar_alert
from cogs.lfg import queue as queue_mod
from cogs.lfg.queue import DeckURLModal, PointsQueueModal, chosen_deck
from cogs.lfg.state import lfg_queue
from repositories.recent_decks_repo import get_recent_decks, recent_deck_summary

ME = 123456789
OPP = 4242
CURIOSA = "https://sorcerytcg.com/decks/"


def _deck_json(avatar, name):
    return json.dumps({"name": name, "avatar": [{"name": avatar}]})


def _add_match(winner, loser, ts, winner_url, loser_url, winner_json="{}", loser_json="{}"):
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        "INSERT INTO match_records (winner_id, losser_id, timestamp, curiosa_url_winner, "
        "curiosa_url_loser, json_deck_data_winner, json_deck_data_loser) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (winner, loser, ts, winner_url, loser_url, winner_json, loser_json),
    )
    conn.commit()
    conn.close()


def _set_replays_public(*user_ids):
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_profiles (user_id TEXT PRIMARY KEY, profile_public_sections TEXT)"
    )
    for user_id in user_ids:
        conn.execute(
            "INSERT OR REPLACE INTO user_profiles VALUES (?, ?)",
            (user_id, json.dumps({"replays": True})),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def avatar_channels():
    with patch.object(config, "AVATAR_CHANNEL_MAP", {"Sorcerer": 9001, "Seer": 9002}, create=True):
        yield


@pytest.fixture
def no_avatar_channels():
    with patch.object(config, "AVATAR_CHANNEL_MAP", {}, create=True):
        yield


RECENT = [
    {"url": f"{CURIOSA}aaa", "avatar": "Sorcerer", "deck_name": "Blue Skies", "wins": 3, "losses": 1,
     "last_played": "2026-10-29T20:00:00"},
    {"url": f"{CURIOSA}bbb", "avatar": "Seer", "deck_name": None, "wins": 0, "losses": 2,
     "last_played": "2026-10-20T20:00:00"},
]


# ── Recent decks from match history ──


def test_recent_decks_are_grouped_newest_first_from_both_sides_of_the_match():
    _add_match(ME, OPP, "2026-10-01T10:00:00", f"{CURIOSA}old", f"{CURIOSA}x",
               _deck_json("Seer", "Old Seer"))
    _add_match(OPP, ME, "2026-10-28T10:00:00", f"{CURIOSA}x", f"{CURIOSA}new?tab=view",
               loser_json=_deck_json("Sorcerer", "Blue Skies"))
    _add_match(ME, OPP, "2026-10-29T10:00:00", f"{CURIOSA}new/edit", f"{CURIOSA}x",
               _deck_json("Sorcerer", "Blue Skies"))
    _add_match(ME, OPP, "2026-10-30T10:00:00", "No URL provided", f"{CURIOSA}x")

    decks = get_recent_decks(ME)

    assert [d["url"] for d in decks] == [f"{CURIOSA}new", f"{CURIOSA}old"]
    assert decks[0] == {
        "url": f"{CURIOSA}new", "avatar": "Sorcerer", "deck_name": "Blue Skies",
        "wins": 1, "losses": 1, "last_played": "2026-10-29T10:00:00",
    }
    assert decks[1]["deck_name"] == "Old Seer"


def test_recent_decks_never_include_the_opponents_deck():
    _add_match(OPP, ME, "2026-10-28T10:00:00", f"{CURIOSA}theirs", None)
    assert get_recent_decks(ME) == []


def test_recent_deck_summary():
    assert recent_deck_summary(RECENT[0]) == "Sorcerer · 3-1 · last played Oct 29"


# ── Modal layout ──


def _labels(modal):
    return [item for item in modal.children if isinstance(item, discord.ui.Label)]


def test_ranked_modal_fits_recent_decks_and_alert_by_moving_the_season_rules(avatar_channels):
    modal = DeckURLModal(MagicMock(), queue_type="ranked", recent_decks=RECENT)

    assert len(modal.children) == 5
    assert not [i for i in modal.children if isinstance(i, discord.ui.TextDisplay)]
    recent, voice, alert = _labels(modal)
    assert recent.text == "Recent decks"
    assert recent.description.startswith("For Gothic Season 8 (NO SEER/SCRY).")
    assert [o.label for o in modal.recent_decks_select.options] == ["Blue Skies", "Seer"]
    assert modal.children[:2] == [recent, modal.deck_url]
    # Alert checkbox sits at the bottom, under the duration
    assert modal.children[-2] is modal.timeframe
    assert modal.children[-1] is alert
    assert isinstance(alert.component, discord.ui.Checkbox)
    assert not alert.component.default


def test_ranked_modal_without_recent_decks_keeps_the_season_rules_on_top(avatar_channels):
    modal = DeckURLModal(MagicMock(), queue_type="ranked", recent_decks=[])
    assert isinstance(modal.children[0], discord.ui.TextDisplay)
    assert modal.recent_decks_select is None
    assert modal.alert_checkbox is not None


def test_no_avatar_channels_means_no_alert_option(no_avatar_channels):
    modal = DeckURLModal(MagicMock(), queue_type="ranked", recent_decks=RECENT)
    assert modal.alert_checkbox is None
    # With room to spare, the season rules stay on top
    assert isinstance(modal.children[0], discord.ui.TextDisplay)
    assert modal.recent_decks_select is not None


def test_points_modal_gets_both_extras(avatar_channels):
    modal = PointsQueueModal(MagicMock(), recent_decks=RECENT)
    assert len(modal.children) == 5
    assert modal.children[1] is modal.deck_url
    assert not modal.deck_url.required


def test_typed_link_wins_over_the_dropdown_pick():
    select = MagicMock(values=["0"])
    assert chosen_deck(f"{CURIOSA}typed/edit ", select, RECENT) == (f"{CURIOSA}typed", None)
    assert chosen_deck("", select, RECENT) == (f"{CURIOSA}aaa", "Sorcerer")
    assert chosen_deck("", MagicMock(values=[]), RECENT) == (None, None)


# ── The alert itself ──


def _channel_bot():
    channel = MagicMock()
    channel.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    return bot, channel


async def _alert(bot, **overrides):
    kwargs = dict(
        player_id=ME, player_name="Bruce", opponent_id=OPP, opponent_name="Geoffrey",
        pairing_id=77, match_type="ranked", avatar="Sorcerer", deck_url=f"{CURIOSA}aaa",
    )
    kwargs.update(overrides)
    return await avatar_alert.send_avatar_alert(bot, **kwargs)


@pytest.mark.asyncio
async def test_alert_links_the_replay_only_when_both_players_share_replays(avatar_channels):
    bot, channel = _channel_bot()
    with patch.object(avatar_alert, "get_pairing_replay", return_value="https://playsorceryonline.com/replay/abc"):
        assert await _alert(bot)
        text = channel.send.await_args.args[0]
        assert "**Bruce** is playing **Sorcerer** in a Ranked game against **Geoffrey**" in text
        assert "replay" not in text.lower()
        assert CURIOSA not in text  # never the deck link

        _set_replays_public(str(ME), f"google_{OPP}")
        await _alert(bot)
        assert "[Watch the replay](https://playsorceryonline.com/replay/abc)" in channel.send.await_args.args[0]
    bot.get_channel.assert_called_with(9001)


@pytest.mark.asyncio
async def test_alert_reads_the_avatar_from_the_deck_when_unknown(avatar_channels):
    bot, _ = _channel_bot()
    with patch.object(avatar_alert, "read_deck_avatar", AsyncMock(return_value="seer")):
        assert await _alert(bot, avatar=None)
    bot.get_channel.assert_called_with(9002)


@pytest.mark.asyncio
async def test_alert_skips_avatars_without_a_channel(avatar_channels):
    bot, channel = _channel_bot()
    assert not await _alert(bot, avatar="Witch")
    channel.send.assert_not_called()


# ── Queue flow ──


@pytest.fixture
def established_players():
    with patch("cogs.lfg.queue.ranked_block_message", return_value=None):
        yield


@pytest.mark.asyncio
async def test_queued_player_with_alert_is_announced_when_matched(
    mock_bot, mock_interaction, established_players, avatar_channels,
):
    lfg_queue[OPP] = {"queues": {"testing": {
        "deck_url": f"{CURIOSA}opp", "voice": "voice",
        "alert_avatar": True, "deck_avatar": "Seer",
    }}}
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = OPP
    lfg_cog.resolve_match_type.return_value = "testing"
    lfg_cog.update_lfg_status = AsyncMock()
    send_alert = AsyncMock()

    try:
        with patch.object(queue_mod, "save_pairing", return_value=77), \
                patch.object(queue_mod, "provision_match_and_publish_results", AsyncMock(return_value={})), \
                patch.object(queue_mod, "send_pairing_messages", AsyncMock()), \
                patch.object(queue_mod, "announce_pairing", AsyncMock()), \
                patch.object(queue_mod, "create_match_card_view", return_value=None), \
                patch.object(queue_mod, "send_avatar_alert", send_alert):
            await queue_mod._process_queue_join(
                mock_bot, mock_interaction, "testing", 30, f"{CURIOSA}me"
            )
            for _ in range(3):
                await asyncio.gather(*list(queue_mod._background_tasks))
    finally:
        lfg_queue.clear()

    # Only the waiting player ticked the box
    send_alert.assert_called_once()
    kwargs = send_alert.call_args.kwargs
    assert kwargs["player_id"] == OPP
    assert kwargs["avatar"] == "Seer"
    assert kwargs["pairing_id"] == 77
    assert kwargs["match_type"] == "testing"


@pytest.mark.asyncio
async def test_alert_choice_is_stored_with_the_queue_entry(
    mock_bot, mock_interaction, established_players,
):
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()
    await queue_mod._process_queue_join(
        mock_bot, mock_interaction, "testing", 30, f"{CURIOSA}me",
        alert_avatar=True, deck_avatar="Sorcerer",
    )
    kwargs = lfg_cog.add_to_lfg_queue.call_args.kwargs
    assert kwargs["alert_avatar"] is True
    assert kwargs["deck_avatar"] == "Sorcerer"
    assert "Avatar channel alert:** on" in mock_interaction.followup.send.await_args.args[0]
