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


def _add(table, winner, loser, winner_first, loser_first):
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        f"INSERT INTO {table} (winner_id, losser_id, timestamp, winner_went_first, loser_went_first) "
        "VALUES (?, ?, '2026-10-01 12:00:00', ?, ?)",
        (winner, loser, winner_first, loser_first),
    )
    conn.commit()
    conn.close()


def test_match_records_has_the_columns_we_read():
    # Real table layout from create_db, not a hand-made fixture
    conn = sqlite3.connect("match_records.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    conn.close()
    assert {"winner_id", "losser_id", "winner_went_first", "loser_went_first"} <= cols


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
            "timestamp TEXT, winner_went_first TEXT, loser_went_first TEXT)"
        )
    conn.commit()
    conn.close()
    _add("match_records_archive", 1, 2, "y", "n")
    _add("season_match_records", 2, 1, "n", "y")
    assert going_first_counts([1]) == {1: (2, 2)}


def test_lower_share_goes_first():
    counts = {1: (6, 10), 2: (4, 10)}
    assert choose_first_player(1, 2, counts) == 2
    assert choose_first_player(2, 1, counts) == 2


def test_no_history_counts_as_half():
    assert choose_first_player(1, 2, {1: (0, 0), 2: (3, 10)}) == 2
    assert choose_first_player(1, 2, {1: (0, 0), 2: (7, 10)}) == 1


def test_tie_is_a_coin_flip():
    seen = {choose_first_player(1, 2, {1: (5, 10), 2: (1, 2)}, rng=random.Random(s)) for s in range(30)}
    assert seen == {1, 2}


def test_pick_first_player_reads_history_from_db():
    _add("match_records", 10, 20, "y", "n")
    assert pick_first_player([{"discord_user_id": 10}, {"discord_user_id": 20}]) == 20


def test_pick_first_player_never_raises():
    assert pick_first_player([{"discord_user_id": 10}]) is None
    assert pick_first_player([{"discord_user_id": 10}, {"discord_user_id": 10}]) is None
    with patch("repositories.turn_order_repo.going_first_counts", side_effect=RuntimeError("db down")):
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
        patch("repositories.turn_order_repo.going_first_counts", side_effect=RuntimeError("db down")),
    ):
        links = await provision_sorcery_online_match(1, 2, "ranked", [
            {"discord_user_id": 10, "display_name": "Alice"},
            {"discord_user_id": 20, "display_name": "Bob"},
        ])
    assert len(links) == 2
    assert "firstPlayerDiscordUserId" not in session.post.call_args.kwargs["json"]
