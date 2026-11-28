"""Standalone Play Sorcery Online ranked games, and website-only (Google login) players.

The website holds a PSO Ranked report with no Summit pairing for 24 hours,
then posts it to /standalone-results. The bot records it like a queued
ranked game. Players may be Discord ids or Summit player numbers.
"""

import json
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from services.elo_service import record_match, start_new_event
from services.summit_result_reporting import (
    CALLBACK_TABLE,
    _notify_sorcery_online_match_recorded,
    record_standalone_result,
)
from utils.player_ids import is_summit_player_number, player_mention

NUMBER = 1_000_000_000_000_001
DISCORD = 123456789012345678


def test_player_numbers_never_look_like_discord_ids():
    assert is_summit_player_number(NUMBER)
    assert is_summit_player_number(str(NUMBER))
    assert not is_summit_player_number(DISCORD)
    assert not is_summit_player_number(81384788765712384)  # one of Discord's first accounts
    assert not is_summit_player_number("google_1")
    assert player_mention(DISCORD, "Dee") == f"<@{DISCORD}>"
    assert player_mention(NUMBER, "Gee") == "**Gee**"


def _callbacks():
    conn = sqlite3.connect("match_records.db")
    try:
        return conn.execute(
            f"SELECT guild_id, pairing_id, winner_id, loser_id, match_id, played_cards FROM {CALLBACK_TABLE}"
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_standalone_result_is_recorded_once_per_report(mock_bot):
    execute = AsyncMock(return_value=901)
    with patch("services.summit_result_reporting._execute_match_confirmation", new=execute), \
         patch("services.summit_result_reporting._notify_sorcery_online_match_recorded", new=AsyncMock()) as notify:
        first = await record_standalone_result(
            mock_bot, report_key=44, winner_id=str(NUMBER), loser_id=str(DISCORD),
            winner_name="Gee", loser_name="Dee", winner_deck_url="https://curiosa.io/decks/a",
            winner_went_first=False, played_cards={str(NUMBER): ["Spire"]},
        )
        retry = await record_standalone_result(
            mock_bot, report_key=44, winner_id=str(NUMBER), loser_id=str(DISCORD),
            winner_name="Gee", loser_name="Dee",
        )

    assert first == {"recorded": True, "duplicate": False, "match_id": 901}
    assert retry == {"recorded": False, "duplicate": True, "match_id": 901}
    execute.assert_awaited_once()
    data = execute.await_args.args[2]
    assert data["winner_id"] == NUMBER and data["loser_id"] == DISCORD
    assert data["match_type"] == "ranked"
    assert data["pairing_id"] is None and data["guild_id"] is None
    assert data["notify_reporter"] is False
    assert data["first_player"] == "n"  # the winner reported, and went second
    assert data["dedupe_key"] == "standalone:44"
    notify.assert_awaited_once()
    [row] = _callbacks()
    assert row[:5] == (0, 44, NUMBER, DISCORD, 901)
    assert json.loads(row[5]) == {str(NUMBER): ["Spire"]}


@pytest.mark.asyncio
async def test_unknown_turn_order_stays_unknown(mock_bot):
    execute = AsyncMock(return_value=902)
    with patch("services.summit_result_reporting._execute_match_confirmation", new=execute), \
         patch("services.summit_result_reporting._notify_sorcery_online_match_recorded", new=AsyncMock()):
        await record_standalone_result(
            mock_bot, report_key=45, winner_id=DISCORD, loser_id=NUMBER,
            winner_name="Dee", loser_name="Gee",
        )
    assert execute.await_args.args[2]["first_player"] is None


@pytest.mark.asyncio
async def test_failed_recording_raises_so_the_website_retries(mock_bot):
    with patch("services.summit_result_reporting._execute_match_confirmation", new=AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError):
            await record_standalone_result(
                mock_bot, report_key=46, winner_id=DISCORD, loser_id=NUMBER,
                winner_name="Dee", loser_name="Gee",
            )
    assert _callbacks() == []


@pytest.mark.asyncio
async def test_same_player_twice_is_refused(mock_bot):
    with pytest.raises(ValueError):
        await record_standalone_result(
            mock_bot, report_key=47, winner_id=NUMBER, loser_id=NUMBER,
            winner_name="Gee", loser_name="Gee",
        )


@pytest.mark.asyncio
async def test_website_only_player_gets_no_discord_message_or_mention():
    loser = MagicMock()
    loser.send = AsyncMock()
    fallback = MagicMock()
    fallback.send = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=loser)
    bot.get_channel.return_value = fallback

    await _notify_sorcery_online_match_recorded(
        bot, match_id=903, match_type="ranked",
        winner_id=NUMBER, winner_name="Gee", loser_id=DISCORD, loser_name="Dee",
    )

    bot.fetch_user.assert_awaited_once_with(DISCORD)
    loser.send.assert_awaited_once()
    fallback.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_player_number_is_stored_exactly_in_the_real_tables():
    """INTEGER player columns keep a 16-digit number intact (a raw Google id would not fit)."""
    start_new_event("Season 9")
    match_id, *_ = await record_match(
        reporter_id=NUMBER, winner_id=NUMBER, winner_global="Gee",
        loser_id=DISCORD, loser_global="Dee", first_player="y", match_time=20,
        match_comment="Reported by Play Sorcery Online", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
    )

    conn = sqlite3.connect("match_records.db")
    try:
        winner, loser, winner_type = conn.execute(
            "SELECT winner_id, losser_id, typeof(winner_id) FROM match_records WHERE match_id = ?",
            (match_id,),
        ).fetchone()
    finally:
        conn.close()
    assert (winner, loser, winner_type) == (NUMBER, DISCORD, "integer")

    conn = sqlite3.connect("elo.db")
    try:
        row = conn.execute(
            "SELECT user_display_name, online_event_elo FROM overall_standings WHERE user_id = ?",
            (NUMBER,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] == "Gee" and row[1] > 1500


def test_expiry_job_retries_pso_reports_and_skips_website_only_dms():
    import time
    from cogs.match_confirmation_jobs import MatchConfirmationJobs, PSO_RETRY_SECONDS

    now = int(time.time())
    retry = MatchConfirmationJobs._retry_pso_report
    assert retry({"source": "PSO Ranked", "expires_at": now - 3600})
    assert not retry({"source": "PSO Ranked", "expires_at": now - PSO_RETRY_SECONDS - 60})
    assert not retry({"source": "Web", "expires_at": now - 3600})

    jobs = MatchConfirmationJobs.__new__(MatchConfirmationJobs)
    assert jobs._is_valid_discord_id(str(DISCORD))
    assert not jobs._is_valid_discord_id(str(NUMBER))
    assert not jobs._is_valid_discord_id("google_123")
