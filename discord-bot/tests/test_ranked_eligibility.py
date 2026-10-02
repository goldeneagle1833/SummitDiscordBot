"""Ranked is closed to brand-new players until they have two games on record."""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from cogs.lfg.queue import JoinQueueButtons, _process_queue_join
from cogs.lfg.state import lfg_queue
from services.elo_service import record_match
from services.ranked_eligibility import (
    MIN_GAMES_FOR_RANKED,
    count_recorded_games,
    ranked_block_message,
)

NEWBIE = 123456789  # conftest's mock_user
VETERAN = 555


async def _play(winner, loser, match_type="testing"):
    await record_match(
        reporter_id=winner, winner_id=winner, winner_global=f"P{winner}",
        loser_id=loser, loser_global=f"P{loser}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n", match_type=match_type,
    )


def test_a_brand_new_player_is_told_how_to_unlock_ranked():
    message = ranked_block_message(NEWBIE)
    assert "You've played 0 so far" in message and "play 2 more games" in message
    assert "Casual" in message


@pytest.mark.asyncio
async def test_two_games_of_any_kind_open_ranked():
    await _play(NEWBIE, VETERAN, match_type="testing")  # a casual win
    assert "play 1 more game " in ranked_block_message(NEWBIE)

    await _play(VETERAN, NEWBIE, match_type="rumble")  # a rumble loss counts too
    assert ranked_block_message(NEWBIE) is None
    assert count_recorded_games(NEWBIE) == MIN_GAMES_FOR_RANKED


@pytest.mark.asyncio
async def test_past_season_and_website_games_count():
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        """CREATE TABLE match_records_archive (
               archive_id INTEGER PRIMARY KEY, event_id INTEGER, winner_id INTEGER, losser_id INTEGER)"""
    )
    conn.execute("INSERT INTO match_records_archive (event_id, winner_id, losser_id) VALUES (1, ?, 9)", (NEWBIE,))
    conn.execute("CREATE TABLE match_reports_web (winner_id TEXT, losser_id TEXT)")
    conn.execute("INSERT INTO match_reports_web VALUES ('9', ?)", (str(NEWBIE),))  # ids are text there
    conn.commit()
    conn.close()

    assert ranked_block_message(NEWBIE) is None


def test_a_database_error_never_locks_players_out():
    with patch("services.ranked_eligibility.count_recorded_games", side_effect=sqlite3.OperationalError("locked")):
        assert ranked_block_message(NEWBIE) is None


@pytest.mark.asyncio
async def test_new_player_is_refused_at_the_ranked_button_and_never_queued(mock_bot, mock_interaction):
    with patch("cogs.lfg.queue.queue_is_enabled", return_value=True):
        await JoinQueueButtons(mock_bot)._handle_join(mock_interaction, "ranked")
    mock_interaction.response.send_modal.assert_not_awaited()
    assert "Ranked opens after your first 2 games" in mock_interaction.response.send_message.await_args.args[0]

    lfg_cog = mock_bot.get_cog.return_value
    await _process_queue_join(mock_bot, mock_interaction, "ranked", 30, None)
    lfg_cog.add_to_lfg_queue.assert_not_called()
    assert mock_interaction.user.id not in lfg_queue


@pytest.mark.asyncio
async def test_new_player_can_still_join_casual(mock_bot, mock_interaction):
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()

    with patch("cogs.lfg.queue.queue_is_enabled", return_value=True):
        await JoinQueueButtons(mock_bot)._handle_join(mock_interaction, "testing")
    mock_interaction.response.send_modal.assert_awaited_once()

    await _process_queue_join(mock_bot, mock_interaction, "testing", 30, None)
    lfg_cog.add_to_lfg_queue.assert_called_once()


@pytest.mark.asyncio
async def test_established_player_joins_ranked_as_before(mock_bot, mock_interaction):
    player = mock_interaction.user.id  # the mock_bot fixture renumbers the shared mock user
    await _play(player, VETERAN)
    await _play(VETERAN, player)
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()

    await _process_queue_join(mock_bot, mock_interaction, "ranked", 30, None)

    lfg_cog.add_to_lfg_queue.assert_called_once()
