"""Late tickets: ratings above 1500 drop to 1500 after the grace week, unless the player has 2 or fewer games."""

import datetime
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.ticket_reset import TicketResetCog
from repositories.avatar_elo_repo import get_avatar_event_elo, set_avatar_event_elo
from repositories.elo_repo import get_active_event
from services.elo_service import record_match, start_new_event
from services.ticket_reset import apply_ticket_reset, plan_ticket_reset

PLAYER, OTHER = 111, 222
TICKET_ROLE = 999


def _age_event(days):
    """Move the running event's start back by `days`."""
    event = get_active_event()
    start = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    conn = sqlite3.connect("elo.db")
    conn.execute("UPDATE events SET start_date = ? WHERE event_id = ?", (start, event["event_id"]))
    conn.commit()
    conn.close()
    return get_active_event()


def _avatar_entry(event_id, user_id, avatar, elo, games):
    set_avatar_event_elo(event_id, user_id, f"P{user_id}", avatar, elo)
    conn = sqlite3.connect("elo.db")
    conn.execute(
        "UPDATE event_avatar_standings SET games_played = ? WHERE event_id = ? AND user_id = ? AND avatar = ?",
        (games, event_id, user_id, avatar),
    )
    conn.commit()
    conn.close()


def _avatar_event(days_in):
    start_new_event("Avatar Season", elo_mode="avatar")
    return _age_event(days_in)


def test_ticket_in_the_grace_week_changes_nothing():
    event = _avatar_event(days_in=3)
    _avatar_entry(event["event_id"], PLAYER, "Imposter", 1620, 10)
    assert plan_ticket_reset(event, PLAYER).reason == "grace"


def test_after_grace_entries_above_1500_drop_and_the_rest_stay():
    event = _avatar_event(days_in=10)
    eid = event["event_id"]
    _avatar_entry(eid, PLAYER, "Imposter", 1620, 4)
    _avatar_entry(eid, PLAYER, "Witch", 1480, 2)
    _avatar_entry(eid, OTHER, "Imposter", 1700, 9)

    plan = plan_ticket_reset(event, PLAYER)
    assert plan.will_reset and plan.games == 6
    assert plan.entries == [("Imposter", 1620)]

    apply_ticket_reset(event, PLAYER, "P111", plan)
    assert get_avatar_event_elo(eid, PLAYER, "Imposter") == 1500
    assert get_avatar_event_elo(eid, PLAYER, "Witch") == 1480
    assert get_avatar_event_elo(eid, OTHER, "Imposter") == 1700  # someone else untouched


def test_two_or_fewer_games_are_left_alone():
    event = _avatar_event(days_in=20)
    _avatar_entry(event["event_id"], PLAYER, "Imposter", 1530, 2)
    plan = plan_ticket_reset(event, PLAYER)
    assert plan.reason == "few_games" and not plan.will_reset


def test_games_count_across_all_avatars():
    event = _avatar_event(days_in=20)
    eid = event["event_id"]
    _avatar_entry(eid, PLAYER, "Imposter", 1530, 2)
    _avatar_entry(eid, PLAYER, "Witch", 1500, 1)
    assert plan_ticket_reset(event, PLAYER).entries == [("Imposter", 1530)]


def test_a_player_is_only_reset_once_per_season():
    event = _avatar_event(days_in=10)
    eid = event["event_id"]
    _avatar_entry(eid, PLAYER, "Imposter", 1620, 5)
    apply_ticket_reset(event, PLAYER, "P111", plan_ticket_reset(event, PLAYER))
    _avatar_entry(eid, PLAYER, "Imposter", 1590, 8)  # climbed back
    assert plan_ticket_reset(event, PLAYER).reason == "already_reset"


async def _win(winner, loser):
    await record_match(
        reporter_id=winner, winner_id=winner, winner_global=f"P{winner}",
        loser_id=loser, loser_global=f"P{loser}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
    )


@pytest.mark.asyncio
async def test_player_mode_season_elo_drops_to_1500():
    start_new_event("Classic", elo_mode="player")
    _age_event(days=-0.001)  # matches land after the start
    for _ in range(3):
        await _win(PLAYER, OTHER)
    event = _age_event(days=8)

    plan = plan_ticket_reset(event, PLAYER)
    assert plan.will_reset and plan.games == 3
    apply_ticket_reset(event, PLAYER, "P111", plan)
    conn = sqlite3.connect("elo.db")
    elo = conn.execute("SELECT online_event_elo FROM overall_standings WHERE user_id = ?", (PLAYER,)).fetchone()[0]
    conn.close()
    assert elo == 1500
    assert plan_ticket_reset(event, OTHER).reason == "nothing_above_cap"


def _member(roles, user_id=PLAYER):
    return SimpleNamespace(
        id=user_id, roles=[SimpleNamespace(id=r) for r in roles], guild=SimpleNamespace(id=1),
        global_name="P111", display_name="P111", send=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_gaining_the_ticket_role_resets_and_dms():
    event = _avatar_event(days_in=10)
    _avatar_entry(event["event_id"], PLAYER, "Imposter", 1620, 5)
    bot = MagicMock()
    bot.get_cog.return_value = SimpleNamespace(update_leaderboard=AsyncMock())
    cog = TicketResetCog(bot)
    after = _member([TICKET_ROLE])

    with patch("cogs.ticket_reset.config", SimpleNamespace(TICKET_HOLDER_ROLE_IDS={TICKET_ROLE}, GUILD_ID=1)):
        await cog.on_member_update(_member([]), after)

    assert get_avatar_event_elo(event["event_id"], PLAYER, "Imposter") == 1500
    after.send.assert_awaited_once()
    assert "1620 → 1500" in after.send.await_args.args[0]


@pytest.mark.asyncio
async def test_other_role_changes_do_nothing():
    event = _avatar_event(days_in=10)
    _avatar_entry(event["event_id"], PLAYER, "Imposter", 1620, 5)
    cog = TicketResetCog(MagicMock())
    with patch("cogs.ticket_reset.config", SimpleNamespace(TICKET_HOLDER_ROLE_IDS={TICKET_ROLE}, GUILD_ID=1)):
        await cog.on_member_update(_member([TICKET_ROLE]), _member([TICKET_ROLE, 5]))  # already had one
        await cog.on_member_update(_member([]), _member([5]))  # not a ticket role
    assert get_avatar_event_elo(event["event_id"], PLAYER, "Imposter") == 1620
