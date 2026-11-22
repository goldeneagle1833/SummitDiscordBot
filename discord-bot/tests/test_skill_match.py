"""Opt-in Skill matching for the Ranked queue: rating gap that widens with wait time."""

import datetime
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1))

from cogs.lfg.cog import LFGCog
from cogs.lfg.skill_match import (
    MAX_GAP,
    START_GAP,
    allowed_gap,
    queue_rating as real_queue_rating,
    release_skill_waits,
    skill_players_ready,
)
from cogs.lfg.state import lfg_queue, matching_web_users
from cogs.lfg.voice import VOICE
from repositories.skill_match_repo import set_skill_match, skill_match_ids, wants_skill_match

RATINGS = {111: 1500, 222: 1800, 333: 1550, 999: 1500}


def entry(seconds_ago, queue_type="ranked", avatar=None, **extra):
    e = {
        "timestamp": datetime.datetime.now() - datetime.timedelta(seconds=seconds_ago),
        "timeframe": 30,
        "deck_url": "https://deck.test/1",
        "origin": "discord",
        "voice": VOICE,
    }
    if avatar:
        e["avatar"] = avatar
    e.update(extra)
    return {"queues": {queue_type: e}}


@pytest.fixture
def lfg_cog():
    cog = object.__new__(LFGCog)
    cog.bot = Mock()
    cog.lfg_channel_id = 1
    cog.check_last_match_opponent = MagicMock(return_value=False)
    cog.clean_expired_lfg = MagicMock()
    return cog


@pytest.fixture
def ctx():
    c = Mock()
    c.author = Mock()
    c.author.id = 999
    return c


@pytest.fixture(autouse=True)
def fake_ratings():
    lfg_queue.clear()
    matching_web_users.clear()
    with patch("cogs.lfg.skill_match.queue_rating", side_effect=lambda uid, avatar=None: RATINGS.get(uid)):
        yield
    lfg_queue.clear()
    matching_web_users.clear()


def test_setting_is_off_by_default_and_round_trips():
    assert wants_skill_match(10) is False
    set_skill_match(10, True, "test")
    set_skill_match(10, True, "test")
    assert wants_skill_match(10) is True
    assert skill_match_ids([10, 20]) == {10}
    set_skill_match(10, False)
    assert wants_skill_match(10) is False


def test_gap_starts_at_150_widens_50_a_minute_and_caps_at_400():
    assert allowed_gap(0) == START_GAP == 150
    assert allowed_gap(60) == 200
    assert allowed_gap(150) == 275
    assert allowed_gap(3600) == MAX_GAP == 400


def test_players_without_the_setting_pair_as_before(lfg_cog, ctx):
    lfg_queue[222] = entry(0)  # 300 points away, nobody opted in
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 222


def test_waiting_player_with_setting_on_skips_a_far_joiner(lfg_cog, ctx):
    set_skill_match(222, True)
    lfg_queue[222] = entry(10)  # 300 apart, gap allowed ~158
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") is None


def test_joiner_with_setting_on_is_held_to_it_too(lfg_cog, ctx):
    set_skill_match(999, True)
    lfg_queue[222] = entry(10)
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") is None


def test_close_player_is_picked_over_an_older_far_one(lfg_cog, ctx):
    set_skill_match(999, True)
    lfg_queue[222] = entry(60)   # older but 300 apart
    lfg_queue[333] = entry(5)    # 50 apart
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 333


def test_gap_widens_with_the_longer_wait(lfg_cog, ctx):
    set_skill_match(222, True)
    lfg_queue[222] = entry(4 * 60)  # waited 4 min: gap allowed 350 >= 300
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 222


def test_queued_since_keeps_the_original_join_time(lfg_cog, ctx):
    set_skill_match(222, True)
    first_join = datetime.datetime.now() - datetime.timedelta(minutes=5)
    lfg_queue[222] = entry(1, queued_since=first_join)
    assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 222


def test_other_queues_ignore_the_setting(lfg_cog, ctx):
    set_skill_match(222, True)
    lfg_queue[222] = entry(0, queue_type="testing")
    assert lfg_cog.check_if_someone_is_lfg(ctx, "testing") == 222


def test_unreadable_rating_never_blocks_a_game(lfg_cog, ctx):
    set_skill_match(222, True)
    lfg_queue[222] = entry(0)
    with patch("cogs.lfg.skill_match.queue_rating", return_value=None):
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked") == 222


def test_queue_avatar_is_used_for_the_rating(lfg_cog, ctx):
    set_skill_match(222, True)
    lfg_queue[222] = entry(0, avatar="Sparkmage")
    seen = []

    def rating(uid, avatar=None):
        seen.append((uid, avatar))
        return 1500

    with patch("cogs.lfg.skill_match.queue_rating", side_effect=rating):
        assert lfg_cog.check_if_someone_is_lfg(ctx, "ranked", joiner_avatar="Flamecaller") == 222
    assert set(seen) == {(999, "Flamecaller"), (222, "Sparkmage")}


class TestSweep:
    def test_pairs_waiting_players_once_the_gap_has_widened(self, lfg_cog):
        set_skill_match(111, True)
        lfg_queue[111] = entry(5 * 60)  # 300 apart from 222, allowed 400 now
        lfg_queue[222] = entry(30)
        ready = skill_players_ready(lfg_cog)
        assert [uid for uid, _ in ready] == [111]
        assert 111 not in lfg_queue and 222 in lfg_queue

    def test_leaves_players_alone_while_still_too_far_apart(self, lfg_cog):
        set_skill_match(111, True)
        lfg_queue[111] = entry(30)
        lfg_queue[222] = entry(20)
        assert skill_players_ready(lfg_cog) == []
        assert 111 in lfg_queue

    @pytest.mark.asyncio
    async def test_rejoin_keeps_first_join_time(self, lfg_cog):
        set_skill_match(111, True)
        lfg_queue[111] = entry(5 * 60)
        first = lfg_queue[111]["queues"]["ranked"]["timestamp"]
        lfg_queue[222] = entry(30)
        bot = MagicMock()
        bot.get_cog.return_value = lfg_cog
        guild = MagicMock()
        guild.get_member.return_value = Mock(id=111)
        bot.get_guild.return_value = guild
        with patch("cogs.lfg.queue._process_queue_join", AsyncMock()) as join:
            await release_skill_waits(bot)
        assert join.await_args.args[2] == "ranked"
        assert join.await_args.kwargs["queued_since"] == first


@pytest.mark.asyncio
async def test_queue_rating_reads_the_glicko2_avatar_rating():
    from services.elo_service import record_match, start_new_event

    start_new_event("Season 9", elo_mode="avatar", rating_system="glicko2")
    await record_match(
        reporter_id=111, winner_id=111, winner_global="A", loser_id=222, loser_global="B",
        first_player="y", match_time=20, match_comment="", winner_deck_url=None,
        loser_deck_url=None, winner_went_first="y", loser_went_first="n",
        winner_avatar="Seer", loser_avatar="Witch",
    )
    assert real_queue_rating(111, "Seer") > 1500
    assert real_queue_rating(222, "Witch") < 1500
    assert real_queue_rating(111, "Druid") == 1500  # no games on that avatar yet
