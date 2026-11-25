"""Who goes first: balanced from each player's going-first history."""

import random
import sys
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))
import cogs.lfg.queue  # noqa: F401  (loads the LFG package before the PSO service, avoiding a circular import)
from repositories.turn_order_repo import (
    choose_first_player,
    going_first_counts,
    pick_first_player,
)
from services.sorcery_online_matchmaking import provision_sorcery_online_match


def _add(table, winner, loser, winner_first, loser_first, match_type="ranked"):
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        f"INSERT INTO {table} (winner_id, losser_id, timestamp, winner_went_first, loser_went_first, match_type) "
        "VALUES (?, ?, '2026-10-01 12:00:00', ?, ?, ?)",
        (winner, loser, winner_first, loser_first, match_type),
    )
    conn.commit()
    conn.close()


def test_match_records_has_the_columns_we_read():
    # Real table layout from create_db, not a hand-made fixture
    conn = sqlite3.connect("match_records.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    conn.close()
    assert {"winner_id", "losser_id", "winner_went_first", "loser_went_first", "match_type"} <= cols


def test_counts_both_players_and_skips_unknown_rows():
    _add("match_records", 1, 2, "y", "n")    # 1 first
    _add("match_records", 2, 1, "Yes", "No")  # 2 first (web-style flags)
    _add("match_records", 1, 2, "n", None)   # 2 first, loser flag missing
    _add("match_records", 1, 2, "n", "n")    # admin Limited: unknown, skipped
    _add("match_records", 1, 2, None, None)  # not recorded, skipped
    _add("match_records", 3, 1, "y", "n")    # 3 first
    assert going_first_counts([1, 2]) == {1: (1, 4), 2: (2, 3)}


def test_counts_archive_and_season_tables_when_present():
    conn = sqlite3.connect("match_records.db")
    for table in ("match_records_archive", "season_match_records"):
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table} (winner_id INTEGER, losser_id INTEGER, "
            "timestamp TEXT, winner_went_first TEXT, loser_went_first TEXT, match_type TEXT)"
        )
    conn.commit()
    conn.close()
    _add("match_records_archive", 1, 2, "y", "n")
    _add("season_match_records", 2, 1, "n", "y")
    assert going_first_counts([1]) == {1: (2, 2)}


def test_chance_is_half_plus_half_the_gap():
    from repositories.turn_order_repo import first_player_chance
    assert first_player_chance(0.4, 0.6) == pytest.approx(0.6)
    assert first_player_chance(0.6, 0.4) == pytest.approx(0.4)
    assert first_player_chance(0.5, 0.5) == pytest.approx(0.5)
    assert first_player_chance(0.3, 0.7) == pytest.approx(0.7)
    assert first_player_chance(0.0, 1.0) == pytest.approx(1.0)


class _Roll:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def test_lower_share_is_more_likely_not_certain():
    counts = {1: (6, 10), 2: (4, 10)}  # player 2 gets a 60% chance
    assert choose_first_player(1, 2, counts, rng=_Roll(0.59)) == 2  # 1 has 40%
    assert choose_first_player(1, 2, counts, rng=_Roll(0.39)) == 1
    assert choose_first_player(2, 1, counts, rng=_Roll(0.59)) == 2
    assert choose_first_player(2, 1, counts, rng=_Roll(0.61)) == 1


def test_weighted_draw_matches_the_chance():
    rng = random.Random(7)
    counts = {1: (6, 10), 2: (4, 10)}
    picks = [choose_first_player(1, 2, counts, rng=rng) for _ in range(20000)]
    assert picks.count(2) / len(picks) == pytest.approx(0.6, abs=0.02)


def test_no_history_counts_as_half():
    # newcomer (50%) vs 30% -> newcomer has 40%
    assert choose_first_player(1, 2, {1: (0, 0), 2: (3, 10)}, rng=_Roll(0.41)) == 2
    assert choose_first_player(1, 2, {1: (0, 0), 2: (3, 10)}, rng=_Roll(0.39)) == 1


def test_even_history_is_a_coin_flip():
    seen = {choose_first_player(1, 2, {1: (5, 10), 2: (1, 2)}, rng=random.Random(s)) for s in range(30)}
    assert seen == {1, 2}


def test_pick_first_player_reads_history_from_db():
    _add("match_records", 10, 20, "y", "n")
    assert pick_first_player([{"discord_user_id": 10}, {"discord_user_id": 20}]) == 20


def test_pick_first_player_never_raises():
    assert pick_first_player([{"discord_user_id": 10}]) is None
    assert pick_first_player([{"discord_user_id": 10}, {"discord_user_id": 10}]) is None
    with patch("repositories.turn_order_repo._recent_history", side_effect=RuntimeError("db down")):
        assert pick_first_player([{"discord_user_id": 10}, {"discord_user_id": 20}]) is None


def _session():
    success = MagicMock(status=200)
    success.json = AsyncMock(return_value={"players": [
        {"discordUserId": "10", "gameUrl": "https://playsorceryonline.com/?m=one"},
        {"discordUserId": "20", "gameUrl": "https://playsorceryonline.com/?m=two"},
    ]})
    success.__aenter__ = AsyncMock(return_value=success)
    success.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.post.return_value = success
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_pairing_json_names_the_first_player(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    _add("match_records", 10, 20, "y", "n")
    session = _session()
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session):
        links = await provision_sorcery_online_match(1, 2, "ranked", [
            {"discord_user_id": 10, "display_name": "Alice"},
            {"discord_user_id": 20, "display_name": "Bob"},
        ])
    assert len(links) == 2
    assert session.post.call_args.kwargs["json"]["firstPlayerDiscordUserId"] == "20"


@pytest.mark.asyncio
async def test_pairing_still_opens_when_pick_fails(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    session = _session()
    with (
        patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session),
        patch("repositories.turn_order_repo._recent_history", side_effect=RuntimeError("db down")),
    ):
        links = await provision_sorcery_online_match(1, 2, "ranked", [
            {"discord_user_id": 10, "display_name": "Alice"},
            {"discord_user_id": 20, "display_name": "Bob"},
        ])
    assert len(links) == 2
    assert "firstPlayerDiscordUserId" not in session.post.call_args.kwargs["json"]


def test_each_queue_only_counts_its_own_games():
    _add("match_records", 1, 2, "y", "n", "ranked")
    _add("match_records", 1, 2, "y", "n", "testing")
    _add("match_records", 2, 1, "y", "n", "testing")
    _add("match_records", 1, 2, "y", "n", None)  # old row with no type = ranked
    assert going_first_counts([1], "ranked") == {1: (2, 2)}
    assert going_first_counts([1], "testing") == {1: (1, 2)}
    assert going_first_counts([1], "rumble") == {1: (0, 0)}


def test_limited_reads_the_limited_tables():
    from repositories.limited_repo import create_limited_tables
    create_limited_tables()
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        "INSERT INTO limited_match_records (winner_id, loser_id, timestamp, winner_went_first, loser_went_first) "
        "VALUES (1, 2, '2026-10-01', 'y', 'n')"
    )
    conn.execute(  # admin-entered: both 'n', skipped
        "INSERT INTO limited_match_records (winner_id, loser_id, timestamp, winner_went_first, loser_went_first) "
        "VALUES (2, 1, '2026-10-02', 'n', 'n')"
    )
    conn.commit()
    conn.close()
    _add("match_records", 2, 1, "y", "n", "ranked")
    assert going_first_counts([1, 2], "limited") == {1: (1, 1), 2: (0, 1)}


def test_precon_reads_the_precon_ladder_table():
    from services.precon_ladder import ensure_schema
    conn = sqlite3.connect("match_records.db")
    ensure_schema(conn)
    for removed in (0, 1):
        conn.execute(
            "INSERT INTO precon_match_records (winner_id, loser_id, timestamp, winner_went_first, "
            "loser_went_first, removed) VALUES (1, 2, '2026-10-01', 'y', 'n', ?)", (removed,)
        )
    conn.commit()
    conn.close()
    _add("match_records", 2, 1, "y", "n", "precon")  # older precon game in the main table
    assert going_first_counts([1], "precon") == {1: (1, 2)}


@pytest.mark.asyncio
async def test_pairing_json_uses_the_queue_history(monkeypatch):
    monkeypatch.setenv("DRAFT_SORCERY_API_KEY", "configured-key")
    _add("match_records", 10, 20, "y", "n", "ranked")   # in ranked, 10 went first
    _add("match_records", 20, 10, "y", "n", "testing")  # in casual, 20 went first
    session = _session()
    with patch("services.sorcery_online_matchmaking.aiohttp.ClientSession", return_value=session):
        await provision_sorcery_online_match(1, 2, "testing", [
            {"discord_user_id": 10, "display_name": "Alice"},
            {"discord_user_id": 20, "display_name": "Bob"},
        ])
    assert session.post.call_args.kwargs["json"]["firstPlayerDiscordUserId"] == "10"


def test_only_the_last_10_games_count():
    conn = sqlite3.connect("match_records.db")
    # 30 old games going first, then 10 newer games going second
    for day in range(1, 31):
        conn.execute(
            "INSERT INTO match_records (winner_id, losser_id, timestamp, winner_went_first, loser_went_first, match_type) "
            "VALUES (1, 2, ?, 'y', 'n', 'ranked')", (f"2026-09-{day:02d} 12:00:00",)
        )
    for day in range(1, 11):
        conn.execute(
            "INSERT INTO match_records (winner_id, losser_id, timestamp, winner_went_first, loser_went_first, match_type) "
            "VALUES (1, 2, ?, 'n', 'y', 'ranked')", (f"2026-10-{day:02d} 12:00:00",)
        )
    conn.commit()
    conn.close()
    assert going_first_counts([1, 2]) == {1: (0, 10), 2: (10, 10)}
    assert going_first_counts([1], recent=None) == {1: (30, 40)}


def test_three_firsts_in_a_row_means_going_second():
    # Player 1 went first in their last 3; shares would favour them anyway
    counts = {1: (3, 10), 2: (7, 10)}
    streaks = {1: (True, 3), 2: (False, 1)}
    assert choose_first_player(1, 2, counts, rng=_Roll(0.0), streaks=streaks) == 2


def test_three_seconds_in_a_row_means_going_first():
    counts = {1: (8, 10), 2: (2, 10)}
    streaks = {1: (False, 3), 2: (True, 1)}
    assert choose_first_player(1, 2, counts, rng=_Roll(0.99), streaks=streaks) == 1


def test_caps_that_agree_and_caps_that_clash():
    counts = {1: (5, 10), 2: (5, 10)}
    # 1 on 3 firsts, 2 on 3 seconds: both say player 2 goes first
    assert choose_first_player(1, 2, counts, rng=_Roll(0.0), streaks={1: (True, 3), 2: (False, 4)}) == 2
    # both on 3 firsts: one of them has to extend, so the weighted chance decides
    assert choose_first_player(1, 2, counts, rng=_Roll(0.0), streaks={1: (True, 3), 2: (True, 3)}) == 1
    assert choose_first_player(1, 2, counts, rng=_Roll(0.99), streaks={1: (True, 3), 2: (True, 3)}) == 2


def test_short_runs_use_the_weighted_chance():
    counts = {1: (5, 10), 2: (5, 10)}
    streaks = {1: (True, 2), 2: (False, 2)}
    assert choose_first_player(1, 2, counts, rng=_Roll(0.0), streaks=streaks) == 1
    assert choose_first_player(1, 2, counts, rng=_Roll(0.99), streaks=streaks) == 2


def test_streak_read_from_the_database():
    conn = sqlite3.connect("match_records.db")
    # Player 1: older second, then 3 newest games going first
    rows = [("2026-10-01", 2, 1, "y", "n"), ("2026-10-02", 1, 3, "y", "n"),
            ("2026-10-03", 4, 1, "n", "y"), ("2026-10-04", 1, 5, "y", "n")]
    for when, w, l, wf, lf in rows:
        conn.execute(
            "INSERT INTO match_records (winner_id, losser_id, timestamp, winner_went_first, loser_went_first, match_type) "
            "VALUES (?, ?, ?, ?, ?, 'ranked')", (w, l, when, wf, lf)
        )
    conn.commit()
    conn.close()
    # Player 6 has no history; 1's shares (3 of 4) already lean to 6, but even
    # a roll that would hand 1 the first turn can't: the cap decides
    assert pick_first_player([{"discord_user_id": 1}, {"discord_user_id": 6}]) == 6
    with patch("repositories.turn_order_repo.random.random", return_value=0.0):
        assert pick_first_player([{"discord_user_id": 1}, {"discord_user_id": 6}]) == 6
