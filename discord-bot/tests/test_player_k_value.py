"""Season K-factor is per player: 16 for the first game, +2 per game, max 32;
a match is played at the lower of the two players' K."""

import sqlite3

import pytest

from repositories.elo_repo import get_user_event_games
from services.elo_service import (
    calculate_player_event_k,
    correct_match_record,
    get_current_event_match_elo_snapshot,
    match_event_k,
    record_match,
    recalculate_event_elo,
    remove_match_record,
    start_new_event,
    update_elo,
)

A, B, C = 101, 202, 303


async def _play(winner, loser, **kwargs):
    result = await record_match(
        reporter_id=winner, winner_id=winner, winner_global=f"P{winner}",
        loser_id=loser, loser_global=f"P{loser}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n", **kwargs,
    )
    return result[0]


def _match(match_id):
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM match_records WHERE match_id = ?", (match_id,)).fetchone())
    finally:
        conn.close()


def _event_elo(user_id):
    conn = sqlite3.connect("elo.db")
    try:
        return conn.execute(
            "SELECT online_event_elo FROM overall_standings WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_k_starts_at_16_rises_by_2_per_game_and_caps_at_32():
    assert [calculate_player_event_k(games) for games in range(10)] == [
        16, 18, 20, 22, 24, 26, 28, 30, 32, 32,
    ]
    assert calculate_player_event_k(500) == 32


def test_a_match_uses_the_lower_of_the_two_k_values():
    assert match_event_k(0, 0) == 16
    assert match_event_k(8, 0) == 16   # veteran vs first game
    assert match_event_k(3, 5) == 22
    assert match_event_k(20, 30) == 32


@pytest.mark.asyncio
async def test_each_players_k_follows_their_own_games():
    start_new_event("Season 7")

    first = _match(await _play(A, B))
    assert first["event_k"] == 16
    assert first["winner_elo_change"] == update_elo(1500, 1500, True, k=16) - 1500  # +8
    assert (get_user_event_games(A), get_user_event_games(B)) == (1, 1)

    await _play(A, B)                    # both on their 2nd game: K 18
    third = _match(await _play(A, C))    # A's 3rd game (K 20) vs C's 1st (K 16)
    assert third["event_k"] == 16
    assert (get_user_event_games(A), get_user_event_games(C)) == (3, 1)

    fourth = _match(await _play(A, B))   # A's 4th (K 22) vs B's 3rd (K 20)
    assert fourth["event_k"] == 20


@pytest.mark.asyncio
async def test_lifetime_elo_still_uses_k_32():
    start_new_event("Season 7")
    row = _match(await _play(A, B))
    assert row["winner_lifetime_elo_change"] == 16  # K 32 at even ratings
    assert row["winner_elo_change"] == 8            # K 16 for the season ladder


@pytest.mark.asyncio
async def test_avatar_entries_use_the_players_k_not_the_avatars():
    start_new_event("Season 7", elo_mode="avatar")
    for _ in range(8):
        await _play(A, B, winner_avatar="Imposter", loser_avatar="Witch")

    # Both players are past the ramp, so a brand-new avatar entry still plays at K 32
    row = _match(await _play(A, B, winner_avatar="Seer", loser_avatar="Druid"))
    assert row["event_k"] == 32
    assert row["winner_avatar_elo_change"] == 16


@pytest.mark.asyncio
async def test_casual_games_do_not_advance_k():
    start_new_event("Season 7")
    await _play(A, B, match_type="testing")
    assert get_user_event_games(A) == 0
    assert _match(await _play(A, B))["event_k"] == 16


@pytest.mark.asyncio
async def test_a_new_season_restarts_everyones_ramp():
    start_new_event("Season 7")
    await _play(A, B)
    await _play(A, B)
    start_new_event("Season 8")
    assert get_user_event_games(A) == 0
    assert _match(await _play(A, B))["event_k"] == 16


@pytest.mark.asyncio
async def test_removing_a_match_takes_a_game_off_both_players():
    start_new_event("Season 7")
    await _play(A, B)
    match_id = await _play(A, B)

    remove_match_record(match_id)

    assert (get_user_event_games(A), get_user_event_games(B)) == (1, 1)
    assert _match(await _play(A, B))["event_k"] == 18


@pytest.mark.asyncio
async def test_correcting_a_match_replays_it_at_the_same_k():
    start_new_event("Season 7")
    await _play(A, B)
    match_id = await _play(A, C)   # A's 2nd game vs C's 1st: K 16

    correct_match_record(match_id)

    row = _match(match_id)
    assert row["winner_id"] == C and row["event_k"] == 16
    assert row["winner_elo_change"] == update_elo(1500, 1508, True, k=16) - 1500
    assert (get_user_event_games(A), get_user_event_games(C)) == (2, 1)


@pytest.mark.asyncio
async def test_recalculate_rebuilds_elo_k_and_game_counts():
    start_new_event("Season 7")
    ids = [await _play(A, B), await _play(A, C), await _play(B, C)]
    expected = {uid: _event_elo(uid) for uid in (A, B, C)}

    # Scramble what the replay has to restore
    conn = sqlite3.connect("elo.db")
    conn.execute("UPDATE overall_standings SET online_event_elo = 1234, online_event_games = 9")
    conn.commit()
    conn.close()
    conn = sqlite3.connect("match_records.db")
    conn.execute("UPDATE match_records SET event_k = NULL")
    conn.commit()
    conn.close()

    recalculate_event_elo()

    assert {uid: _event_elo(uid) for uid in (A, B, C)} == expected
    assert [get_user_event_games(uid) for uid in (A, B, C)] == [2, 2, 2]
    assert [_match(mid)["event_k"] for mid in ids] == [16, 16, 18]


@pytest.mark.asyncio
async def test_match_elo_snapshot_reports_the_k_the_match_used():
    start_new_event("Season 7")
    await _play(A, B)
    match_id = await _play(A, B)

    snapshot = get_current_event_match_elo_snapshot(match_id)

    assert snapshot["event_k"] == 18
    assert snapshot["winner"]["event_after"] == _event_elo(A)
