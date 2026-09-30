"""Avatar-mode events: per-(player, avatar) event ELO behind a per-event mode."""

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from repositories.avatar_elo_repo import (
    get_avatar_event_elo,
    get_avatar_standings,
    get_player_avatar_standings,
)
from repositories.elo_repo import get_active_event, get_top_16_user_ids, save_pairing
from services.avatar_mode import (
    DECK_REQUIRED_MESSAGE,
    DECK_UNREADABLE_MESSAGE,
    check_join_deck,
    get_event_ladder,
    lock_match_avatar,
    unique_players,
)
from services.elo_service import (
    correct_match_record,
    end_current_event,
    record_match,
    remove_match_record,
    start_new_event,
)
from utils.avatars import avatar_from_deck, canonical_avatar, validate_avatar_name

WINNER, LOSER, THIRD = 111, 222, 333


async def _record(winner_id=WINNER, loser_id=LOSER, **kwargs):
    defaults = dict(
        reporter_id=winner_id, winner_id=winner_id, winner_global=f"P{winner_id}",
        loser_id=loser_id, loser_global=f"P{loser_id}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
    )
    defaults.update(kwargs)
    return await record_match(**defaults)


def _match_row(match_id):
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute("SELECT * FROM match_records WHERE match_id = ?", (match_id,)).fetchone())
    finally:
        conn.close()


def _standing(user_id):
    conn = sqlite3.connect("elo.db")
    try:
        return conn.execute(
            "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()


# ── Avatar names ──


def test_avatar_names_ignore_case_spaces_and_punctuation():
    assert canonical_avatar("imposter") == "Imposter"
    assert canonical_avatar("realm eater") == "Realm-Eater"
    assert canonical_avatar("AVATAR OF AIR") == "Avatar of Air"
    assert canonical_avatar("Impostor") is None


def test_typo_is_rejected_with_a_suggestion_not_corrected():
    avatar, error = validate_avatar_name("Impostor")
    assert avatar is None
    assert "did you mean **Imposter**" in error

    avatar, error = validate_avatar_name("Zzzzzzzzzz")
    assert avatar is None and "did you mean" not in error


def test_avatar_is_read_from_curiosa_and_pso_shaped_decks():
    curiosa = {"avatar": [{"name": "Persecutor", "quantity": 1}], "spellbook": []}
    pso = '{"source": "sorcery_online", "avatar": [{"name": "imposter"}]}'
    assert avatar_from_deck(curiosa) == "Persecutor"
    assert avatar_from_deck(pso) == "Imposter"
    assert avatar_from_deck({}) is None
    assert avatar_from_deck("not json") is None


# ── Event mode ──


def test_start_event_records_mode_and_the_mode_is_locked():
    result = start_new_event("Avatar Season", elo_mode="avatar")
    assert result["elo_mode"] == "avatar"
    assert get_active_event()["elo_mode"] == "avatar"

    conn = sqlite3.connect("elo.db")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="cannot change"):
            conn.execute("UPDATE events SET elo_mode = 'player' WHERE event_id = ?", (result["event_id"],))
    finally:
        conn.close()


def test_start_event_defaults_to_player_mode_and_rejects_unknown_modes():
    assert start_new_event("Classic")["elo_mode"] == "player"
    with pytest.raises(ValueError):
        start_new_event("Oops", elo_mode="deck")


# ── Recording ──


@pytest.mark.asyncio
async def test_avatar_mode_match_moves_only_the_two_locked_avatar_entries():
    event = start_new_event("Avatar Season", elo_mode="avatar")
    pairing_id = save_pairing(1, WINNER, LOSER, "w-deck", "l-deck", "ranked",
                              player1_avatar="Imposter", player2_avatar="Persecutor")

    match_id, *_ = await _record(pairing_id=pairing_id)

    eid = event["event_id"]
    assert get_avatar_event_elo(eid, WINNER, "Imposter") > 1500
    assert get_avatar_event_elo(eid, LOSER, "Persecutor") < 1500
    assert get_avatar_event_elo(eid, WINNER, "Persecutor") == 1500  # other avatars untouched

    row = _match_row(match_id)
    assert (row["winner_avatar"], row["loser_avatar"]) == ("Imposter", "Persecutor")
    assert row["winner_avatar_elo_after"] == 1500 + row["winner_avatar_elo_change"]
    # Lifetime ELO still moves once per player
    assert _standing(WINNER)[0] > 1500 and _standing(LOSER)[0] < 1500


@pytest.mark.asyncio
async def test_a_second_avatar_is_a_fresh_1500_entry():
    event = start_new_event("Avatar Season", elo_mode="avatar")
    await _record(winner_avatar="Imposter", loser_avatar="Witch")
    await _record(winner_avatar="Imposter", loser_avatar="Witch")
    await _record(winner_id=LOSER, loser_id=WINNER, winner_avatar="Druid", loser_avatar="Persecutor")

    entries = {(e["user_id"], e["avatar"]): e for e in get_avatar_standings(event["event_id"])}
    assert entries[(WINNER, "Imposter")]["games_played"] == 2
    assert entries[(WINNER, "Persecutor")]["event_elo"] < 1500
    assert entries[(WINNER, "Persecutor")]["games_played"] == 1
    assert len(get_player_avatar_standings(event["event_id"], WINNER)) == 2


@pytest.mark.asyncio
async def test_player_mode_leaves_avatar_columns_empty():
    start_new_event("Classic")
    match_id, *_ = await _record(winner_avatar="Imposter", loser_avatar="Witch")
    row = _match_row(match_id)
    assert row["winner_avatar"] is None and row["winner_avatar_elo_change"] is None
    assert row["winner_elo_change"] > 0


@pytest.mark.asyncio
async def test_report_without_a_pairing_falls_back_to_reading_the_decks():
    event = start_new_event("Avatar Season", elo_mode="avatar")
    reads = {"w-deck": "Seer", "l-deck": "Witch"}
    with patch("services.elo_service.read_deck_avatar", AsyncMock(side_effect=lambda url: reads[url])):
        match_id, *_ = await _record(winner_deck_url="w-deck", loser_deck_url="l-deck")
    assert _match_row(match_id)["winner_avatar"] == "Seer"
    assert get_avatar_event_elo(event["event_id"], LOSER, "Witch") < 1500


# ── Ladder and top cut ──


@pytest.mark.asyncio
async def test_top_cut_counts_each_player_once():
    start_new_event("Avatar Season", elo_mode="avatar")
    # WINNER tops the ladder on two avatars; THIRD is the next unique player
    for avatar in ("Imposter", "Persecutor"):
        await _record(winner_avatar=avatar, loser_avatar="Witch")
    await _record(winner_id=THIRD, loser_id=LOSER, winner_avatar="Seer", loser_avatar="Druid")

    ladder = get_event_ladder()
    assert [e.user_id for e in ladder[:2]] == [WINNER, WINNER]
    assert [e.user_id for e in unique_players(ladder)][:2] == [WINNER, THIRD]
    top = get_top_16_user_ids()
    assert top.count(WINNER) == 1 and THIRD in top


@pytest.mark.asyncio
async def test_player_mode_ladder_is_one_row_per_player():
    start_new_event("Classic")
    await _record()
    ladder = get_event_ladder()
    assert {e.user_id for e in ladder} == {WINNER, LOSER}
    assert all(e.avatar is None for e in ladder)


# ── Admin corrections ──


@pytest.mark.asyncio
async def test_remove_match_reverts_every_ladder_by_its_own_change():
    event = start_new_event("Avatar Season", elo_mode="avatar")
    await _record(winner_avatar="Imposter", loser_avatar="Witch")
    match_id, *_ = await _record(winner_avatar="Imposter", loser_avatar="Witch")
    before = _match_row(match_id)

    remove_match_record(match_id)

    eid = event["event_id"]
    assert get_avatar_event_elo(eid, WINNER, "Imposter") == before["winner_avatar_elo_after"] - before["winner_avatar_elo_change"]
    lifetime, event_elo = _standing(WINNER)
    # Lifetime and event are undone separately (they differ: K=32 vs event K)
    assert lifetime == 1500 + _match_row_change_sum(WINNER, "lifetime")
    assert event_elo == 1500 + _match_row_change_sum(WINNER, "event")


def _match_row_change_sum(user_id, ladder):
    col = "winner_lifetime_elo_change" if ladder == "lifetime" else "winner_elo_change"
    conn = sqlite3.connect("match_records.db")
    try:
        return conn.execute(f"SELECT COALESCE(SUM({col}), 0) FROM match_records WHERE winner_id = ?",
                            (user_id,)).fetchone()[0]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_correct_match_swaps_avatars_and_keeps_lifetime_separate():
    event = start_new_event("Avatar Season", elo_mode="avatar")
    match_id, *_ = await _record(winner_avatar="Imposter", loser_avatar="Witch")

    correct_match_record(match_id)

    row = _match_row(match_id)
    assert (row["winner_id"], row["winner_avatar"]) == (LOSER, "Witch")
    assert (row["losser_id"], row["loser_avatar"]) == (WINNER, "Imposter")
    eid = event["event_id"]
    assert get_avatar_event_elo(eid, LOSER, "Witch") > 1500
    assert get_avatar_event_elo(eid, WINNER, "Imposter") < 1500
    # The flipped result is what's stored: lifetime moved by its own K=32 change
    assert _standing(LOSER)[0] == 1500 + row["winner_lifetime_elo_change"]
    assert _standing(LOSER)[1] == 1500 + row["winner_elo_change"]


@pytest.mark.asyncio
async def test_end_event_archives_avatar_columns_and_reports_avatar_top_players():
    start_new_event("Avatar Season", elo_mode="avatar")
    await _record(winner_avatar="Imposter", loser_avatar="Witch")
    summary = end_current_event()
    assert summary["elo_mode"] == "avatar"
    assert summary["top_players"][0][0] == f"P{WINNER} (Imposter)"

    conn = sqlite3.connect("match_records.db")
    try:
        archived = conn.execute("SELECT winner_avatar, loser_avatar FROM match_records_archive").fetchone()
    finally:
        conn.close()
    assert archived == ("Imposter", "Witch")


# ── Joining and locking ──


@pytest.mark.asyncio
async def test_join_check_requires_a_readable_deck():
    assert await check_join_deck(None) == (None, DECK_REQUIRED_MESSAGE)
    assert await check_join_deck("https://example.com/deck") == (None, DECK_UNREADABLE_MESSAGE)
    with patch("services.avatar_mode.read_deck_avatar", AsyncMock(return_value=None)):
        assert await check_join_deck("https://sorcerytcg.com/decks/abc") == (None, DECK_UNREADABLE_MESSAGE)
    with patch("services.avatar_mode.read_deck_avatar", AsyncMock(return_value="Seer")):
        assert await check_join_deck("https://playsorceryonline.com/?deck=pD-1gXa3cg8c") == ("Seer", None)


@pytest.mark.asyncio
async def test_lock_uses_the_match_time_read_and_falls_back_to_the_join_read():
    with patch("services.avatar_mode.read_deck_avatar", AsyncMock(return_value="Witch")):
        assert await lock_match_avatar("deck", "Seer") == "Witch"
    with patch("services.avatar_mode.read_deck_avatar", AsyncMock(return_value=None)):
        assert await lock_match_avatar("deck", "Seer") == "Seer"


# ── Queue join (Avatar mode) ──


@pytest.mark.asyncio
async def test_ranked_join_without_a_deck_is_refused_in_avatar_mode(mock_bot, mock_interaction):
    from cogs.lfg.queue import _process_queue_join
    from cogs.lfg.state import lfg_queue

    start_new_event("Avatar Season", elo_mode="avatar")
    lfg_cog = mock_bot.get_cog.return_value
    await _process_queue_join(mock_bot, mock_interaction, "ranked", 30, None)

    lfg_cog.add_to_lfg_queue.assert_not_called()
    assert mock_interaction.user.id not in lfg_queue
    assert mock_interaction.followup.send.await_args.args[0] == DECK_REQUIRED_MESSAGE


@pytest.mark.asyncio
async def test_ranked_join_stores_the_join_time_avatar(mock_bot, mock_interaction):
    from cogs.lfg.queue import _process_queue_join

    start_new_event("Avatar Season", elo_mode="avatar")
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()
    with patch("services.avatar_mode.read_deck_avatar", AsyncMock(return_value="Seer")):
        await _process_queue_join(mock_bot, mock_interaction, "ranked", 30, "https://sorcerytcg.com/decks/abc")

    assert lfg_cog.add_to_lfg_queue.call_args.kwargs["avatar"] == "Seer"


@pytest.mark.asyncio
async def test_casual_and_player_mode_joins_need_no_deck(mock_bot, mock_interaction):
    from cogs.lfg.queue import _process_queue_join

    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()

    start_new_event("Avatar Season", elo_mode="avatar")
    await _process_queue_join(mock_bot, mock_interaction, "testing", 30, None)
    assert lfg_cog.add_to_lfg_queue.call_count == 1

    start_new_event("Classic")
    await _process_queue_join(mock_bot, mock_interaction, "ranked", 30, None)
    assert lfg_cog.add_to_lfg_queue.call_count == 2
    assert lfg_cog.add_to_lfg_queue.call_args.kwargs["avatar"] is None
