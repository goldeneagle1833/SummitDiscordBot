"""Player blocks are honored on every way two players can be paired.

A block in either direction (A blocked B, or B blocked A) must keep the pair
apart in every queue (ranked, casual, rumble, Limited, Omens/points, precon,
voice and no-voice), in direct challenges and in ladder challenges. Uses the
real blocked_users table, not a mocked check.
"""

import datetime
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

sys.modules.setdefault("config", MagicMock(GUILD_ID=1, BOT_ADMIN_ROLE_ID=1001, JUDGE_ROLE_ID=1002))

import cogs.lfg.ladder as ladder_module
from cogs.lfg.challenge import BLOCKED_CHALLENGE_MESSAGE, ChallengeAcceptModal, ChallengeButtons
from cogs.lfg.cog import LFGCog
from cogs.lfg.ladder import LadderChallengeJoinButton, _resolve_ladder_challenge
from cogs.lfg.state import active_ladder_challenges, lfg_queue
from repositories.blocked_users_repo import create_blocked_users_table

JOINER = 999
BLOCKED = 111
OTHER = 222

ALL_QUEUES = ["ranked", "testing", "rumble", "limited", "points", "precon"]


@pytest.fixture(autouse=True)
def clean_state():
    lfg_queue.clear()
    active_ladder_challenges.clear()
    create_blocked_users_table()
    with sqlite3.connect("match_records.db") as conn:
        conn.execute("DELETE FROM blocked_users")
    yield
    lfg_queue.clear()
    active_ladder_challenges.clear()
    with sqlite3.connect("match_records.db") as conn:
        conn.execute("DELETE FROM blocked_users")


def block(blocker, blocked):
    with sqlite3.connect("match_records.db") as conn:
        conn.execute(
            "INSERT INTO blocked_users (user_id, blocked_user_id, reason) VALUES (?, ?, 'test')",
            (str(blocker), str(blocked)),
        )


def make_member(user_id, name="Player"):
    member = MagicMock()
    member.id = user_id
    member.global_name = name
    member.display_name = name
    member.mention = f"<@{user_id}>"
    member.bot = False
    member.send = AsyncMock()
    return member


def queued(queue_type, minutes_ago, **extra):
    entry = {
        "timestamp": datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago),
        "timeframe": 30,
        "deck_url": None,
        "voice": "no_voice",
    }
    entry.update(extra)
    return {"queues": {queue_type: entry}}


@pytest.fixture
def lfg_cog():
    cog = object.__new__(LFGCog)
    cog.bot = Mock()
    cog.lfg_channel_id = 1
    cog.check_last_match_opponent = MagicMock(return_value=False)
    return cog


def ctx_for(user_id):
    ctx = Mock()
    ctx.author.id = user_id
    return ctx


# ── Every queue ─────────────────────────────────────────────────────


@pytest.mark.parametrize("queue_type", ALL_QUEUES)
@pytest.mark.parametrize("direction", ["joiner_blocked_them", "they_blocked_joiner"])
def test_block_skips_player_in_every_queue(lfg_cog, queue_type, direction):
    if direction == "joiner_blocked_them":
        block(JOINER, BLOCKED)
    else:
        block(BLOCKED, JOINER)
    # The blocked player has waited longest, so FIFO would pick them first
    lfg_queue[BLOCKED] = queued(queue_type, 10)
    lfg_queue[OTHER] = queued(queue_type, 2)

    with patch("services.precon_service.played_last_game_together", return_value=False):
        matched = lfg_cog.check_if_someone_is_lfg(ctx_for(JOINER), queue_type, voice="no_voice")

    assert matched == OTHER


@pytest.mark.parametrize("queue_type", ALL_QUEUES)
def test_only_blocked_player_waiting_means_no_match(lfg_cog, queue_type):
    block(BLOCKED, JOINER)
    lfg_queue[BLOCKED] = queued(queue_type, 5)

    with patch("services.precon_service.played_last_game_together", return_value=False):
        assert lfg_cog.check_if_someone_is_lfg(ctx_for(JOINER), queue_type, voice="no_voice") is None


@pytest.mark.parametrize("voice", ["voice", "no_voice"])
def test_block_skips_player_with_either_voice_choice(lfg_cog, voice):
    block(JOINER, BLOCKED)
    lfg_queue[BLOCKED] = queued("testing", 10, voice=voice)
    lfg_queue[OTHER] = queued("testing", 2, voice=voice)

    assert lfg_cog.check_if_someone_is_lfg(ctx_for(JOINER), "testing", voice=voice) == OTHER


def test_voice_hold_sweep_skips_blocked_partner(lfg_cog):
    """The voice-hold sweep re-matches a waiting player; blocks still apply."""
    from cogs.lfg.voice_hold import _HoldContext

    block(JOINER, BLOCKED)
    lfg_queue[BLOCKED] = queued("testing", 10, voice="no_voice")

    assert lfg_cog.check_if_someone_is_lfg(
        _HoldContext(JOINER), "testing", voice="voice", voice_flexible=True, voice_hold=False
    ) is None


def test_no_block_still_pairs(lfg_cog):
    lfg_queue[BLOCKED] = queued("testing", 10)
    assert lfg_cog.check_if_someone_is_lfg(ctx_for(JOINER), "testing", voice="no_voice") == BLOCKED


# ── Direct challenges ───────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker,blocked", [(JOINER, BLOCKED), (BLOCKED, JOINER)])
async def test_challenge_command_refused_when_blocked(blocker, blocked):
    block(blocker, blocked)
    cog = object.__new__(LFGCog)
    cog.bot = Mock()
    ctx = MagicMock()
    ctx.author = make_member(JOINER)
    ctx.send = AsyncMock()
    opponent = make_member(BLOCKED)

    await cog.challenge.callback(cog, ctx, opponent)

    ctx.send.assert_awaited_once()
    text = ctx.send.await_args.args[0]
    assert "can't challenge that player" in text
    assert "block" not in text.lower()  # blocks stay private
    opponent.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_challenge_refused_when_blocked():
    block(BLOCKED, JOINER)
    view = ChallengeButtons(challenger_id=JOINER, challenger_global="Challenger")
    interaction = MagicMock()
    interaction.user = make_member(BLOCKED)
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()

    await view.accept_button.callback(interaction)

    interaction.response.send_modal.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(BLOCKED_CHALLENGE_MESSAGE, ephemeral=True)


@pytest.mark.asyncio
async def test_accept_modal_refused_when_block_added_while_open():
    modal = ChallengeAcceptModal(challenger_id=JOINER, challenger_global="Challenger")
    block(JOINER, BLOCKED)
    interaction = MagicMock()
    interaction.user = make_member(BLOCKED)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.client.fetch_user = AsyncMock(return_value=make_member(JOINER))
    lfg_queue[JOINER] = queued("ranked", 1)

    with patch("cogs.lfg.challenge.save_pairing") as save_pairing:
        await modal.on_submit(interaction)
        save_pairing.assert_not_called()

    interaction.followup.send.assert_awaited_once_with(BLOCKED_CHALLENGE_MESSAGE, ephemeral=True)
    assert JOINER in lfg_queue  # nothing was changed


# ── Ladder challenges ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ladder_join_refused_when_blocked():
    block(JOINER, BLOCKED)
    active_ladder_challenges[JOINER] = {"joiners": []}
    view = LadderChallengeJoinButton(bot=Mock(), challenger_id=JOINER)
    interaction = MagicMock()
    interaction.user = make_member(BLOCKED)
    interaction.response.send_message = AsyncMock()

    await view.join_button.callback(interaction)

    assert active_ladder_challenges[JOINER]["joiners"] == []
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_ladder_resolve_never_picks_blocked_joiner():
    block(BLOCKED, JOINER)  # landed after they joined
    active_ladder_challenges[JOINER] = {
        "joiners": [
            {"user_id": BLOCKED, "global_name": "Blocked"},
            {"user_id": OTHER, "global_name": "Other"},
        ],
        "challenger_global": "Challenger",
        "challenge_id": None,
        "channel": None,
        "message": None,
    }
    picked = []

    def fake_choice(joiners):
        picked.extend(j["user_id"] for j in joiners)
        raise RuntimeError("stop after the pick")

    with patch.object(ladder_module.random, "choice", side_effect=fake_choice):
        with pytest.raises(RuntimeError):
            await _resolve_ladder_challenge(Mock(), JOINER)

    assert picked == [OTHER]
