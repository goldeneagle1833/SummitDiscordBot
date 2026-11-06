"""Provisional Glicko-2 ratings in Discord messages.

Under 8 games a Glicko-2 rating shows as "Provisional (n/8)" instead of a
number, and the changes from those games are never shown. Elo seasons are
shown as before.
"""

import os
import sqlite3
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "config" not in sys.modules:
    fake_config = types.ModuleType("config")
    for key, value in {
        "MASTERS_ROLE_IDS": [], "OPENAI_API_KEY": "test-key", "DM_BACKUP_CHANNEL_ID": 0,
        "DM_DISABLED_ROLE_ID": 0, "DM_DISABLED_CHANNEL_ID": 0, "GUILD_ID": 0,
        "ACTIVE_PLAYER_ROLE_ID": 0, "MILESTONE_CHANNEL_ID": 0, "LFG_CHANNEL_ID": 0,
        "LEADERBOARD_CHANNEL_ID": 0, "TICKET_HOLDER_ROLE_IDS": [], "BOT_ADMIN_ROLE_ID": 0,
        "JUDGE_ROLE_ID": 0,
    }.items():
        setattr(fake_config, key, value)
    sys.modules["config"] = fake_config

from cogs.elo import EloCog
from services import provisional
from services.elo_service import (
    correct_match_record,
    get_current_event_match_elo_snapshot,
    remove_match_record,
    start_new_event,
)
from tests.test_glicko2_season import A, B, C, _record

FAR_PAST, FAR_FUTURE = "2000-01-01T00:00:00", "2999-01-01T00:00:00"


def _member(user_id, name):
    member = MagicMock()
    member.id = user_id
    member.display_name = name
    return member


async def _rank_text(user_id, admin=False):
    ctx = MagicMock()
    ctx.send = AsyncMock()
    cog = EloCog(MagicMock())
    with patch("utils.checks.check_is_admin", return_value=admin):
        await cog.rank.callback(cog, ctx, _member(user_id, f"P{user_id}"))
    return ctx.send.await_args.args[0]


async def _event_leaderboard_text():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    cog = EloCog(MagicMock())
    await cog.event_leaderboard.callback(cog, ctx)
    return ctx.send.await_args.args[0]


async def _play(n, winner=A, loser=B):
    return [await _record(winner, loser) for _ in range(n)]


def _event_elo(user_id):
    conn = sqlite3.connect("elo.db")
    try:
        return conn.execute(
            "SELECT online_event_elo FROM overall_standings WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# ── The helpers ──


def test_settled_first_ranks_settled_entries_only():
    entries = [("Zed", 1700, 3), ("Amy", 1650, 9), ("Bo", 1600, 5), ("Cy", 1550, 12)]
    ranked = provisional.settled_first(entries, True, lambda e: e[2], lambda e: e[0])
    assert ranked == [(1, entries[1]), (2, entries[3]), (None, entries[2]), (None, entries[0])]
    # Elo ladders keep every position
    assert provisional.settled_first(entries, False, lambda e: e[2], lambda e: e[0])[0] == (1, entries[0])


def test_change_text_hides_the_first_eight_games_only():
    assert provisional.change_text(40, 3) is None
    assert provisional.change_text(40, 8) is None
    assert provisional.change_text(12, 9, " ELO") == "+12 ELO"
    assert provisional.change_text(-7, None) == "-7"  # Elo rows have no games column


# ── !rank and the leaderboards ──


@pytest.mark.asyncio
async def test_rank_is_provisional_until_eight_games():
    start_new_event("Season 9", rating_system="glicko2")
    await _play(3)
    text = await _rank_text(A)
    assert "Provisional (3/8)" in text
    assert str(_event_elo(A)) not in text and "Rank #" not in text

    await _play(5)
    text = await _rank_text(A)
    assert f"{_event_elo(A)} (Rank #1)" in text
    assert "Provisional" not in text


@pytest.mark.asyncio
async def test_rank_admin_lifetime_is_provisional_and_shows_legacy_elo():
    conn = sqlite3.connect("elo.db")
    conn.execute("INSERT INTO overall_standings (user_id, user_display_name, online_elo) VALUES (?, 'PA', 1733)", (A,))
    conn.commit()
    conn.close()
    start_new_event("Season 9", rating_system="glicko2")
    await _play(2)
    text = await _rank_text(A, admin=True)
    assert "**Lifetime ELO:** Provisional (2/8)" in text
    assert "**Legacy ELO (Seasons 1-8):** 1733" in text


@pytest.mark.asyncio
async def test_event_leaderboard_lists_provisional_entries_after_settled_ones_unranked():
    start_new_event("Season 9", rating_system="glicko2")
    await _play(8, A, B)  # A and B settled at 8 games
    await _play(2, C, B)  # C provisional at 2, B now 10
    text = await _event_leaderboard_text()
    lines = text.splitlines()[1:]
    assert lines[0] == f"#1: P{A} - {_event_elo(A)} Elo"
    assert lines[1] == f"#2: P{B} - {_event_elo(B)} Elo"
    assert lines[2] == f"- P{C} - Provisional (2/8)"


@pytest.mark.asyncio
async def test_elo_seasons_show_numbers_from_the_first_game():
    start_new_event("Season 8")
    await _play(1)
    text = await _rank_text(A)
    assert f"{_event_elo(A)} (Rank #1)" in text and "Provisional" not in text
    board = await _event_leaderboard_text()
    assert f"#1: P{A} - " in board and "Provisional" not in board
    removed = remove_match_record((await _play(1))[0])
    assert any("Event -" in line for line in removed["reverted_info"])


# ── Fixes and snapshots ──


@pytest.mark.asyncio
async def test_remove_match_text_leaves_out_hidden_changes():
    start_new_event("Season 9", rating_system="glicko2")
    first = (await _play(1))[0]
    result = remove_match_record(first)
    assert result["reverted_info"] == [
        f"**P{A}**: provisional, change not shown", f"**P{B}**: provisional, change not shown",
    ]

    ids = await _play(9)
    result = remove_match_record(ids[-1])  # game 9: shown
    assert result["reverted_info"][0].startswith(f"**P{A}**: Lifetime -") and "Event -" in result["reverted_info"][0]


@pytest.mark.asyncio
async def test_correct_match_text_leaves_out_hidden_changes():
    start_new_event("Season 9", rating_system="glicko2")
    ids = await _play(2)
    result = correct_match_record(ids[0])
    assert result["new_winner_elo_change_hidden"] and result["new_loser_elo_change_hidden"]
    assert provisional.corrected_side_text(result, "winner") == f"**P{B}**"
    assert "ELO" not in provisional.corrected_side_text(result, "loser")


@pytest.mark.asyncio
async def test_match_elo_hides_a_provisional_sides_before_and_after():
    start_new_event("Season 9", rating_system="glicko2")
    match_id = (await _play(1))[0]
    snapshot = get_current_event_match_elo_snapshot(match_id)
    ctx = MagicMock()
    ctx.send = AsyncMock()
    cog = EloCog(MagicMock())
    with patch("cogs.elo.get_current_event_match_elo_snapshot", return_value=snapshot), \
            patch("utils.checks.check_is_admin", return_value=True):
        await cog.match_elo.callback(cog, ctx, str(match_id))
    text = ctx.send.await_args.args[0]
    assert "->" not in text
    assert text.count("Event: Provisional (1/8) at this match") == 2


# ── Daily summary ──


def _daily_stats():
    import config

    for name, value in (("DAILY_SUMMARY_HOUR", 23), ("DAILY_SUMMARY_MINUTE", 0), ("DAILY_SUMMARY_CHANNEL_ID", 0)):
        if not hasattr(config, name):
            setattr(config, name, value)
    from cogs.daily_summary import DailySummaryCog

    cog = DailySummaryCog.__new__(DailySummaryCog)
    return cog._query_stats(FAR_PAST, FAR_FUTURE)


@pytest.mark.asyncio
async def test_daily_summary_ignores_hidden_lifetime_changes():
    start_new_event("Season 9", rating_system="glicko2")
    await _play(3)
    stats = _daily_stats()
    assert stats["total_matches"] == 3
    assert stats["top_gainer"] is None and stats["biggest_loser"] is None
    assert stats["biggest_upset"] is None and stats["highest_rated"] is None

    await _play(7)  # games 9 and 10 are shown
    stats = _daily_stats()
    conn = sqlite3.connect("match_records.db")
    shown = conn.execute(
        "SELECT SUM(winner_lifetime_elo_change) FROM season_match_records WHERE winner_lifetime_games > 8"
    ).fetchone()[0]
    conn.close()
    assert stats["top_gainer"][0] == A and stats["top_gainer"][2] == shown
    assert stats["highest_rated"] is not None


@pytest.mark.asyncio
async def test_daily_summary_elo_lifetime_unchanged():
    start_new_event("Season 8")
    await _play(1)
    stats = _daily_stats()
    assert stats["top_gainer"][0] == A and stats["top_gainer"][2] > 0
    assert stats["highest_rated"] is not None


# ── Ladder stakes ──


@pytest.mark.asyncio
async def test_ladder_stakes_note_leaves_out_the_gap_for_provisional_players():
    from cogs.lfg.pairing_messages import ladder_stakes_note

    start_new_event("Season 9", rating_system="glicko2")
    await _play(1)
    assert "diff" not in ladder_stakes_note(A, B)
    start_new_event("Season 8")
    assert "ELO diff < 100" in ladder_stakes_note(A, B)
