"""Precon (Lavamancer vs Frostmage) queue and Glicko-2 ladder."""

import asyncio
import datetime
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from services import precon_ladder, precon_service
from services.precon_ladder import (
    FROSTMAGE,
    LAVAMANCER,
    MIN_RANKED_GAMES,
    Rating,
    normalize_precon,
    play,
)

T0 = datetime.datetime(2026, 11, 12, 18, 0, 0)


@pytest.fixture(autouse=True)
def fresh_cache():
    precon_service.clear_cache()
    yield
    precon_service.clear_cache()


@pytest.fixture
def conn():
    c = sqlite3.connect("match_records.db")
    yield c
    c.close()


def _game(conn, w, l, at, wp=LAVAMANCER, lp=FROSTMAGE):
    return precon_ladder.record_match(
        conn, winner_id=w, loser_id=l, winner_name=f"P{w}", loser_name=f"P{l}",
        winner_precon=wp, loser_precon=lp, now=at,
    )


# --- engine ---


def test_precon_names_accept_short_and_long_forms():
    assert normalize_precon("LM") == LAVAMANCER
    assert normalize_precon("Lavamancer") == LAVAMANCER
    assert normalize_precon(" fm ") == FROSTMAGE
    assert normalize_precon("Frostmage") == FROSTMAGE
    assert normalize_precon("Sparkmage") is None
    assert normalize_precon(None) is None


def test_a_win_moves_both_new_players_the_same_amount():
    winner, loser = play(Rating(), Rating(), T0.isoformat())
    assert winner.display > 1500 > loser.display
    assert winner.display - 1500 == 1500 - loser.display
    assert winner.rd < 200 and loser.rd < 200


def test_rd_never_drops_below_the_floor():
    a, b = Rating(), Rating()
    for i in range(200):
        a, b = play(a, b, (T0 + datetime.timedelta(minutes=i)).isoformat())
    assert a.rd >= precon_ladder.RD_FLOOR - 1e-9


def test_season_runs_four_weeks_and_only_one_at_a_time(conn):
    season = precon_ladder.start_season(conn, "LM vs FM 1", created_by=5, now=T0)
    assert season["ends_at"] == (T0 + datetime.timedelta(days=28)).isoformat()
    assert precon_ladder.open_season(conn, now=T0 + datetime.timedelta(days=27))["season_id"] == season["season_id"]
    assert precon_ladder.open_season(conn, now=T0 + datetime.timedelta(days=28)) is None
    with pytest.raises(ValueError):
        precon_ladder.start_season(conn, "Another", now=T0 + datetime.timedelta(days=1))


def test_games_outside_a_season_are_kept_but_not_rated(conn):
    result = _game(conn, 1, 2, T0)
    assert result["rated"] is False and result["season_id"] is None
    assert precon_ladder.get_match(conn, result["match_id"])["winner_precon"] == LAVAMANCER


def test_standings_rank_players_with_enough_games_and_split_records_by_precon(conn):
    season = precon_ladder.start_season(conn, "S", now=T0)
    for i in range(MIN_RANKED_GAMES):
        _game(conn, 1, 2, T0 + datetime.timedelta(hours=i), LAVAMANCER, FROSTMAGE)
    _game(conn, 3, 1, T0 + datetime.timedelta(hours=10), FROSTMAGE, FROSTMAGE)
    rows = precon_ladder.standings(conn, season["season_id"])
    by_id = {r["user_id"]: r for r in rows}
    assert by_id["1"]["rank"] == 1 and by_id["1"]["ranked"]
    assert by_id["1"]["lm_wins"] == MIN_RANKED_GAMES and by_id["1"]["fm_losses"] == 1
    assert by_id["2"]["ranked"] and by_id["2"]["fm_losses"] == MIN_RANKED_GAMES
    # One game: listed, but after the ranked players and with no rank
    assert by_id["3"]["rank"] is None
    assert rows[-1]["user_id"] == "3"
    stats = precon_ladder.season_stats(conn, season["season_id"])
    assert stats["games"] == MIN_RANKED_GAMES + 1
    assert stats["lm_vs_fm"] == {"lm_wins": MIN_RANKED_GAMES, "fm_wins": 0, "lm_mirrors": 0, "fm_mirrors": 1, "no_precon": 0}


def test_rebuild_gives_the_same_ratings_as_playing_live(conn):
    season = precon_ladder.start_season(conn, "S", now=T0)
    pattern = [(1, 2), (2, 3), (3, 1), (1, 2), (1, 3), (2, 1)]
    for i, (w, l) in enumerate(pattern):
        _game(conn, w, l, T0 + datetime.timedelta(hours=i * 7))
    live = precon_ladder.standings(conn, season["season_id"])
    precon_ladder.rebuild_season(conn, season["season_id"])
    assert precon_ladder.standings(conn, season["season_id"]) == live


def test_removing_a_game_re_rates_the_season(conn):
    season = precon_ladder.start_season(conn, "S", now=T0)
    first = _game(conn, 1, 2, T0 + datetime.timedelta(hours=1))
    _game(conn, 2, 1, T0 + datetime.timedelta(hours=2))
    precon_ladder.remove_match(conn, first["match_id"])
    rows = {r["user_id"]: r for r in precon_ladder.standings(conn, season["season_id"])}
    assert rows["2"]["wins"] == 1 and rows["2"]["games"] == 1
    assert rows["2"]["rating"] > 1500
    assert precon_ladder.remove_match(conn, first["match_id"]) is None


def test_rematch_check_looks_at_each_players_last_precon_game(conn):
    precon_ladder.start_season(conn, "S", now=T0)
    _game(conn, 1, 2, T0)
    assert precon_ladder.played_last_game_together(conn, 2, 1)
    _game(conn, 1, 3, T0 + datetime.timedelta(minutes=5))
    # Player 2's last game was still against 1
    assert precon_ladder.played_last_game_together(conn, 1, 2)
    _game(conn, 2, 3, T0 + datetime.timedelta(minutes=10))
    assert not precon_ladder.played_last_game_together(conn, 1, 2)


def test_finished_seasons_get_one_final_post(conn):
    season = precon_ladder.start_season(conn, "S", now=T0)
    assert precon_ladder.seasons_needing_final_post(conn, now=T0 + datetime.timedelta(days=1)) == []
    later = T0 + datetime.timedelta(days=29)
    assert [s["season_id"] for s in precon_ladder.seasons_needing_final_post(conn, now=later)] == [season["season_id"]]
    precon_ladder.mark_final_posted(conn, season["season_id"], now=later)
    assert precon_ladder.seasons_needing_final_post(conn, now=later) == []


def test_web_app_copy_is_identical():
    bot_copy = Path(precon_ladder.__file__)
    web_copy = bot_copy.parents[2] / "web-app" / "services" / "precon_ladder.py"
    assert web_copy.read_text(encoding="utf-8") == bot_copy.read_text(encoding="utf-8")


# --- queue ---


def test_precon_queue_needs_its_switch_and_an_open_season():
    from cogs.lfg.queue_definitions import enabled_queue_definitions, queue_is_enabled

    # Off by default: merging never opens the queue
    assert precon_service.settings(use_cache=False)["queue_enabled"] is False
    precon_service.start_season("LM vs FM")
    assert not queue_is_enabled("precon")
    precon_service.update_settings({"queue_enabled": "on"})
    assert queue_is_enabled("precon")
    assert "precon" in [d["type"] for d in enabled_queue_definitions()]
    # Pilots don't touch it
    with patch("cogs.lfg.queue_definitions.is_pilot_active", return_value=False):
        assert queue_is_enabled("precon")
    precon_service.end_season()
    assert not queue_is_enabled("precon")


def test_rematch_block_follows_the_setting(conn):
    _game(conn, 1, 2, T0 + datetime.timedelta(hours=1))
    assert precon_service.played_last_game_together(1, 2)
    precon_service.update_settings({"block_rematch": False})
    assert not precon_service.played_last_game_together(1, 2)


def test_season_length_setting_is_used_when_starting():
    precon_service.update_settings({"season_days": 7})
    season = precon_service.start_season("Short one")
    start = datetime.datetime.fromisoformat(season["starts_at"])
    assert datetime.datetime.fromisoformat(season["ends_at"]) - start == datetime.timedelta(days=7)


def test_precon_matches_only_pair_with_precon():
    from cogs.lfg.cog import LFGCog

    assert LFGCog.resolve_match_type("precon", "precon") == "precon"


def test_random_precons_always_split_lm_and_fm():
    import random as _random

    seen = set()
    for seed in range(20):
        pair = precon_service.random_precons(_random.Random(seed))
        assert sorted(pair) == sorted([LAVAMANCER, FROSTMAGE])
        seen.add(pair)
    assert len(seen) == 2  # both ways round happen


@pytest.mark.asyncio
async def test_precon_pairing_assigns_one_lm_and_one_fm_at_random(mock_bot, mock_interaction):
    from cogs.lfg import queue as queue_mod
    from cogs.lfg.state import lfg_queue

    opponent_id = 4242
    lfg_queue[opponent_id] = {"queues": {"precon": {
        "deck_url": None, "voice": "voice", "precon": None,
    }}}
    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = opponent_id
    lfg_cog.resolve_match_type.return_value = "precon"
    lfg_cog.update_lfg_status = AsyncMock()
    provision = AsyncMock(return_value={})
    try:
        with patch.object(queue_mod, "save_pairing", return_value=91) as save, \
                patch.object(queue_mod, "provision_match_and_publish_results", provision), \
                patch.object(queue_mod, "send_pairing_messages", AsyncMock()) as send, \
                patch.object(queue_mod, "announce_pairing", AsyncMock()), \
                patch.object(queue_mod, "create_match_card_view", return_value=None), \
                patch("services.precon_service.random_precons", return_value=(FROSTMAGE, LAVAMANCER)):
            await queue_mod._process_queue_join(
                mock_bot, mock_interaction, "precon", 30, None, precon="LM",  # a pick is ignored
            )
            for _ in range(3):
                await asyncio.gather(*list(queue_mod._background_tasks))
    finally:
        lfg_queue.clear()

    assert save.call_args.kwargs["match_type"] == "precon"
    assert save.call_args.kwargs["player1_avatar"] == "Frostmage"
    assert save.call_args.kwargs["player2_avatar"] == "Lavamancer"
    players = provision.await_args.args[3]
    assert [p["precon"] for p in players] == [FROSTMAGE, LAVAMANCER]
    shown = {send.await_args.kwargs[k].avatar for k in ("reporter", "other")}
    assert shown == {"Lavamancer", "Frostmage"}


@pytest.mark.asyncio
async def test_queued_precon_player_is_told_the_precon_is_random(mock_bot, mock_interaction):
    from cogs.lfg import queue as queue_mod

    lfg_cog = mock_bot.get_cog.return_value
    lfg_cog.check_if_someone_is_lfg.return_value = None
    lfg_cog.update_lfg_status = AsyncMock()
    await queue_mod._process_queue_join(
        mock_bot, mock_interaction, "precon", 30, None, precon=FROSTMAGE,
    )
    assert lfg_cog.add_to_lfg_queue.call_args.kwargs["precon"] is None
    message = mock_interaction.followup.send.await_args.args[0]
    assert "Precon (LM/FM)" in message and "at random" in message


def test_pso_provisioning_names_the_precon():
    from services.sorcery_online_matchmaking import _provision_player

    entry = _provision_player({"discord_user_id": 10, "display_name": "A", "deck_url": None, "precon": FROSTMAGE})
    assert entry == {"discordUserId": "10", "displayName": "A", "deckUrl": None, "precon": FROSTMAGE}
    assert "precon" not in _provision_player({"discord_user_id": 10, "display_name": "A"})


# --- reporting ---


@pytest.mark.asyncio
async def test_pso_precon_result_lands_on_the_ladder_not_match_records(mock_bot):
    from cogs.lfg.persistent_confirm import (
        create_match_card_view,
        ensure_match_cards_table,
        ensure_pending_confirmations_table,
    )
    from repositories.elo_repo import get_pairing_by_id, save_pairing
    from services.summit_result_reporting import record_sorcery_online_result

    precon_service.start_season("LM vs FM")
    user = MagicMock()
    user.send = AsyncMock()
    mock_bot.fetch_user = AsyncMock(return_value=user)
    mock_bot.get_cog.return_value.update_leaderboard = AsyncMock()
    ensure_match_cards_table()
    ensure_pending_confirmations_table()
    pairing_id = save_pairing(1, 10, 20, "", "", "precon",
                              player1_avatar="Lavamancer", player2_avatar="Frostmage")
    create_match_card_view(
        bot=mock_bot, pairing_id=pairing_id, player1_id=10, player1_global="Alice",
        player2_id=20, player2_global="Bob", guild_id=1, match_type="precon",
    )
    from repositories.elo_repo import set_pairing_replay

    set_pairing_replay(pairing_id, "https://playsorceryonline.com/replay/abc123")
    with patch("cogs.lfg.pairing_messages.announce_match_id", AsyncMock()), \
            patch("cogs.lfg.persistent_confirm.edit_match_card_messages", AsyncMock()):
        result = await record_sorcery_online_result(
            mock_bot, guild_id=1, pairing_id=pairing_id, queue_type="precon",
            reporter_id=20, winner_id=20, loser_id=10,
        )
    assert result["recorded"] is True
    game = precon_service.match_for_pairing(pairing_id)
    assert game["match_id"] == result["match_id"]
    assert (game["winner_id"], game["winner_precon"]) == (20, FROSTMAGE)
    assert (game["loser_id"], game["loser_precon"]) == (10, LAVAMANCER)
    assert game["winner_rating_after"] > 1500 > game["loser_rating_after"]
    assert game["source"] == "pso"
    assert game["replay_url"] == "https://playsorceryonline.com/replay/abc123"
    assert get_pairing_by_id(1, pairing_id)["status"] == "reported"
    with sqlite3.connect("match_records.db") as c:
        assert c.execute("SELECT COUNT(*) FROM match_records").fetchone()[0] == 0
    # The DM names the precon fix command, not the ranked one
    assert "remove_precon_match" in user.send.await_args_list[0].args[0]


def test_precon_games_count_toward_ranked_eligibility(conn):
    from services.ranked_eligibility import count_recorded_games

    _game(conn, 1, 2, T0)
    _game(conn, 2, 1, T0 + datetime.timedelta(minutes=1))
    assert count_recorded_games(1) == 2
