"""Scheduled season end: top cut selection, seeding and the drafted bracket."""

import datetime
import random
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.lfg.cog import LFGCog
from repositories.elo_repo import get_active_event, set_event_scheduled_end
from services.avatar_mode import LadderEntry
from services.elo_service import record_match, start_new_event
from services.postseason import (
    PostseasonError,
    bracket_name,
    create_draft_bracket,
    extract_end_time,
    limited_bracket_name,
    limited_top_cut,
    round_one_byes,
    seed_top_cut,
    select_top_cut,
)


def _entry(user_id, elo, avatar=None):
    return LadderEntry(user_id, f"P{user_id}", elo, 5, avatar)


def _bracket_tables():
    """The website's bracket tables the bot writes a draft into."""
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        """CREATE TABLE brackets (
               bracket_id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL UNIQUE,
               name TEXT NOT NULL, description TEXT, entrant_count INTEGER NOT NULL,
               bracket_size INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
               seeded_from TEXT, elo_event_name TEXT, confirm_hours INTEGER NOT NULL DEFAULT 48,
               created_by TEXT, created_at TEXT NOT NULL, published_at TEXT,
               completed_at TEXT, updated_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE bracket_entrants (
               bracket_id INTEGER NOT NULL, seed INTEGER NOT NULL, user_id TEXT,
               display_name TEXT NOT NULL, elo INTEGER, games INTEGER,
               is_ticket_holder INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (bracket_id, seed))"""
    )
    conn.commit()
    conn.close()


# ── Parsing the end time ──


@pytest.mark.parametrize("text, expected", [
    ("avatar Season 9 <t:1794805140:F>", (1794805140, "avatar Season 9")),
    ("<t:1794805140> Season 9", (1794805140, "Season 9")),
    ("Season 9 <t:1794805140:R> Finals", (1794805140, "Season 9 Finals")),
    ("Season 9 1794805140", (1794805140, "Season 9")),
    ("Season 9", (None, "Season 9")),
    ("Season 2026", (None, "Season 2026")),
])
def test_end_time_is_pulled_out_of_the_command(text, expected):
    assert extract_end_time(text) == expected


# ── Top cut ──


def test_top_cut_is_the_first_32_unique_ticket_holders():
    # Player 1 tops the ladder on two avatars; player 2 has no ticket
    ladder = [_entry(1, 1700, "Imposter"), _entry(1, 1690, "Witch"), _entry(2, 1680, "Seer")]
    ladder += [_entry(uid, 1700 - uid, "Druid") for uid in range(3, 40)]
    holders = {1, *range(3, 40)}

    cut = select_top_cut(ladder, holders)

    assert len(cut) == 32
    assert [e.user_id for e in cut[:3]] == [1, 3, 4]
    assert cut[0].avatar == "Imposter"  # their best entry
    assert 2 not in {e.user_id for e in cut}
    assert len({e.user_id for e in cut}) == 32


def test_top_8_keep_their_order_and_the_rest_are_drawn_at_random():
    qualifiers = [_entry(uid, 2000 - uid) for uid in range(1, 33)]
    seeded = seed_top_cut(qualifiers, rng=random.Random(4))

    assert [e.user_id for e in seeded[:8]] == list(range(1, 9))
    rest = [e.user_id for e in seeded[8:]]
    assert sorted(rest) == list(range(9, 33))
    assert rest != list(range(9, 33))


@pytest.mark.parametrize("count, byes", [(32, 0), (30, 2), (24, 8), (17, 15), (16, 0), (1, 0)])
def test_byes_only_fill_empty_bracket_spots(count, byes):
    assert round_one_byes(count) == byes


def test_small_fields_are_all_byes_in_ladder_order():
    qualifiers = [_entry(uid, 2000 - uid) for uid in range(1, 6)]
    assert [e.user_id for e in seed_top_cut(qualifiers)] == [1, 2, 3, 4, 5]


# ── Drafting the bracket ──


def test_draft_bracket_is_written_for_the_website():
    _bracket_tables()
    seeded = [_entry(uid, 2000 - uid, "Imposter") for uid in range(1, 33)]

    bracket = create_draft_bracket("Summit Gothic Season 7", seeded, created_by=99)

    assert bracket["name"] == "Summit Gothic Season 7 Post Season Bracket"
    assert bracket["slug"] == "summit-gothic-season-7-post-season-bracket"
    conn = sqlite3.connect("match_records.db")
    row = conn.execute(
        "SELECT status, entrant_count, bracket_size, seeded_from, elo_event_name FROM brackets"
    ).fetchone()
    entrants = conn.execute(
        "SELECT seed, user_id, elo, is_ticket_holder FROM bracket_entrants ORDER BY seed"
    ).fetchall()
    conn.close()
    assert row == ("draft", 32, 32, "ticket_holders", "Summit Gothic Season 7")
    assert entrants[0] == (1, "1", 1999, 1) and len(entrants) == 32


def test_a_second_bracket_with_the_same_name_gets_its_own_slug():
    _bracket_tables()
    seeded = [_entry(1, 1600), _entry(2, 1500)]
    first = create_draft_bracket("Season 7", seeded)
    second = create_draft_bracket("Season 7", seeded)
    assert second["slug"] == f"{first['slug']}-2"


def test_drafting_fails_clearly_without_the_site_tables_or_players():
    with pytest.raises(PostseasonError, match="bracket tables"):
        create_draft_bracket("Season 7", [_entry(1, 1600), _entry(2, 1500)])
    with pytest.raises(PostseasonError, match="at least 2"):
        create_draft_bracket("Season 7", [_entry(1, 1600)])
    assert bracket_name("Season 7") == "Season 7 Post Season Bracket"


# ── Scheduled end ──


def test_end_time_is_stored_on_the_event_and_can_change():
    ends = int(time.time()) + 3600
    result = start_new_event("Season 7", elo_mode="avatar", scheduled_end_at=ends)
    assert result["scheduled_end_at"] == ends
    assert get_active_event()["scheduled_end_at"] == ends

    set_event_scheduled_end(result["event_id"], None)
    assert get_active_event()["scheduled_end_at"] is None
    assert start_new_event("Season 8")["scheduled_end_at"] is None


def _cog_stub(ticket_holders):
    cog = MagicMock()
    cog._ticket_holder_ids = AsyncMock(return_value=set(ticket_holders))
    cog._assign_top_cut_role = AsyncMock(return_value={
        "added": len(ticket_holders), "removed": 0, "kept": 0, "failed": [], "role_id": 77, "error": None,
    })
    cog._season_end_retry_after = None
    cog._announce_season_end = AsyncMock()
    cog.update_leaderboard = AsyncMock()
    cog.bot.user.id = 1
    return cog


async def _play(winner, loser, winner_avatar="Imposter", loser_avatar="Witch"):
    await record_match(
        reporter_id=winner, winner_id=winner, winner_global=f"P{winner}",
        loser_id=loser, loser_global=f"P{loser}", first_player="y", match_time=20,
        match_comment="", winner_deck_url=None, loser_deck_url=None,
        winner_went_first="y", loser_went_first="n",
        winner_avatar=winner_avatar, loser_avatar=loser_avatar,
    )


@pytest.mark.asyncio
async def test_ending_the_season_takes_top_cut_and_drafts_the_bracket():
    _bracket_tables()
    event = start_new_event("Season 7", elo_mode="avatar")
    await _play(11, 22)
    await _play(11, 33, winner_avatar="Seer")
    await _play(33, 22)
    cog = _cog_stub(ticket_holders={11, 22})  # 33 has no ticket

    summary, seeded, bracket, error = await LFGCog._end_season_with_top_cut(cog, get_active_event())

    assert summary["event_name"] == "Season 7" and error is None
    assert [e.user_id for e in seeded] == [11, 22]  # 11 counted once, at their best avatar
    assert bracket["entrant_count"] == 2
    assert get_active_event() is None
    assert event["event_id"] == summary["event_id"]


@pytest.mark.asyncio
async def test_scheduled_end_waits_for_its_time_then_ends_and_announces():
    start_new_event("Season 7", scheduled_end_at=int(time.time()) + 3600)
    cog = _cog_stub(ticket_holders=set())
    cog._end_season_with_top_cut = AsyncMock(return_value=(
        {"event_name": "Season 7", "total_matches": 0, "total_players": 0}, [], None, None,
    ))
    tick = LFGCog.check_scheduled_event_end.coro

    await tick(cog)
    cog._end_season_with_top_cut.assert_not_awaited()

    set_event_scheduled_end(get_active_event()["event_id"], int(time.time()) - 5)
    with patch("cogs.lfg.cog.log_admin_action"):
        await tick(cog)
    cog._end_season_with_top_cut.assert_awaited_once()
    cog._announce_season_end.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_scheduled_end_backs_off_instead_of_retrying_every_minute():
    start_new_event("Season 7", scheduled_end_at=int(time.time()) - 5)
    cog = _cog_stub(ticket_holders=set())
    cog._end_season_with_top_cut = AsyncMock(side_effect=RuntimeError("db locked"))
    tick = LFGCog.check_scheduled_event_end.coro

    await tick(cog)
    await tick(cog)

    assert cog._end_season_with_top_cut.await_count == 1
    assert cog._season_end_retry_after > datetime.datetime.now()


def test_season_end_message_lists_ladder_seeds_and_the_random_draw():
    seeded = [_entry(uid, 2000 - uid, "Imposter") for uid in range(1, 33)]
    summary = {"event_name": "Season 7", "total_matches": 412, "total_players": 60}
    bracket = {"name": "Season 7 Post Season Bracket", "entrant_count": 32}

    embed = LFGCog._season_end_embed(MagicMock(), summary, seeded, bracket, None)

    assert "Season 7 has ended" in embed.title and "Leaderboard" not in embed.title
    text = embed.description
    assert "Top cut: the top 32 ticket holders" in text
    assert "Seeds 1–8 (by ladder rank)" in text and "Seeds 9–32 (random draw)" in text
    assert "bye" not in text  # a full 32 fills the bracket
    assert "<@1> (Imposter) — 1999" in text and "<@32>" in text
    assert "Season 7 Post Season Bracket" in text
    assert len(text) < 4096

    short = LFGCog._season_end_embed(MagicMock(), summary, seeded[:28], bracket, None)
    assert "Seeds 1–4 get a round one bye." in short.description

    empty = LFGCog._season_end_embed(MagicMock(), summary, [], None, "Fewer than 2 ticket holders qualified.")
    assert "no top cut" in empty.description


# ── Top Cut role ──


def _member(user_id):
    member = MagicMock()
    member.id = user_id
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


def _role_cog(role_members, guild_members):
    role = MagicMock()
    role.id = 77
    role.members = role_members
    guild = MagicMock()
    guild.get_role.return_value = role
    by_id = {m.id: m for m in guild_members}
    guild.get_member.side_effect = by_id.get
    guild.fetch_member = AsyncMock(side_effect=lambda uid: by_id[uid])
    cog = MagicMock()
    cog.bot.get_guild.return_value = guild
    return cog, role


@pytest.mark.asyncio
async def test_top_cut_role_moves_from_last_seasons_players_to_the_new_qualifiers():
    old_only, both, new_only = _member(1), _member(2), _member(3)
    cog, role = _role_cog(role_members=[old_only, both], guild_members=[old_only, both, new_only])

    result = await LFGCog._assign_top_cut_role(cog, [2, 3])

    old_only.remove_roles.assert_awaited_once()
    both.remove_roles.assert_not_awaited()
    both.add_roles.assert_not_awaited()
    new_only.add_roles.assert_awaited_once()
    assert (result["removed"], result["kept"], result["added"], result["failed"]) == (1, 1, 1, [])
    assert result["role_id"] == 77


@pytest.mark.asyncio
async def test_top_cut_role_is_left_alone_when_nobody_qualified():
    holder = _member(1)
    cog, _ = _role_cog(role_members=[holder], guild_members=[holder])

    result = await LFGCog._assign_top_cut_role(cog, [])

    holder.remove_roles.assert_not_awaited()
    assert result["removed"] == 0 and result["role_id"] is None


@pytest.mark.asyncio
async def test_a_member_the_bot_cannot_update_is_reported_not_fatal():
    import discord

    stuck, fine = _member(1), _member(2)
    stuck.add_roles.side_effect = discord.HTTPException(MagicMock(status=403), "Missing Permissions")
    cog, _ = _role_cog(role_members=[], guild_members=[stuck, fine])

    result = await LFGCog._assign_top_cut_role(cog, [1, 2])

    assert result["added"] == 1 and result["failed"] == [1]


@pytest.mark.asyncio
async def test_ending_the_season_hands_out_the_top_cut_role():
    _bracket_tables()
    start_new_event("Season 7", elo_mode="avatar")
    await _play(11, 22)
    cog = _cog_stub(ticket_holders={11, 22})

    summary, seeded, _, _ = await LFGCog._end_season_with_top_cut(cog, get_active_event())

    assert set(cog._assign_top_cut_role.await_args.args[0]) == {11, 22}
    assert summary["top_cut_role"]["role_id"] == 77
    embed = LFGCog._season_end_embed(MagicMock(), summary, seeded, None, None)
    assert "<@&77>" in embed.description and "Top Cut channel" in embed.description


# ── Limited season bracket ──


def _limited_season(players):
    """A Limited season in progress: [(user_id, name, season_elo, games)]."""
    from repositories.limited_repo import create_limited_tables

    create_limited_tables()
    elo = sqlite3.connect("elo.db")
    matches = sqlite3.connect("match_records.db")
    for user_id, name, season_elo, games in players:
        elo.execute(
            "INSERT INTO limited_elo (user_id, user_display_name, elo, lifetime_elo) VALUES (?, ?, ?, 1500)",
            (user_id, name, season_elo),
        )
        for _ in range(games):
            matches.execute(
                "INSERT INTO limited_match_records (winner_id, loser_id) VALUES (?, 5555)", (user_id,)
            )
    elo.commit()
    matches.commit()
    elo.close()
    matches.close()


def test_limited_top_cut_is_the_top_8_on_the_limited_ladder():
    _limited_season(
        [(i, f"L{i}", 1600 - i, 3) for i in range(1, 11)]
        + [(99, "Idle", 1900, 0)]  # no games this season: not on the ladder
    )

    top = limited_top_cut()

    assert [e.user_id for e in top] == list(range(1, 9))
    assert top[0].event_elo == 1599 and top[0].games_played == 3


def test_limited_bracket_names():
    assert limited_bracket_name("Limited Season 3") == "Limited Season 3 Top 8"
    assert limited_bracket_name("Fall Draft") == "Fall Draft Limited Top 8"


def test_limited_draft_bracket_is_written_for_the_website():
    _bracket_tables()  # the site hasn't added its format column yet
    seeded = [_entry(uid, 1700 - uid) for uid in range(1, 9)]

    bracket = create_draft_bracket("Limited Season 3", seeded, created_by=99, format="limited")

    assert bracket["name"] == "Limited Season 3 Top 8"
    conn = sqlite3.connect("match_records.db")
    row = conn.execute(
        "SELECT entrant_count, bracket_size, seeded_from, elo_event_name, format FROM brackets"
    ).fetchone()
    entrants = conn.execute(
        "SELECT seed, user_id, is_ticket_holder FROM bracket_entrants ORDER BY seed"
    ).fetchall()
    conn.close()
    assert row == (8, 8, "limited", "Limited Season 3", "limited")
    assert [e[1] for e in entrants] == [str(i) for i in range(1, 9)]
    assert all(e[2] == 0 for e in entrants)


@pytest.mark.asyncio
async def test_ending_a_limited_season_drafts_its_bracket():
    _bracket_tables()
    seeded = [_entry(uid, 1700 - uid) for uid in range(1, 9)]
    cog = MagicMock()
    cog._assign_top_cut_role = AsyncMock()

    drafted = await LFGCog._draft_limited_bracket(cog, "Limited Season 3", seeded, created_by=1)

    assert drafted["bracket"]["name"] == "Limited Season 3 Top 8"
    assert drafted["error"] is None
    # No Limited role configured, so nobody's roles change.
    cog._assign_top_cut_role.assert_not_awaited()
    text = LFGCog._limited_top_cut_text(drafted)
    assert "<@1>" in text and "Limited Season 3 Top 8" in text


@pytest.mark.asyncio
async def test_a_limited_season_with_too_few_players_says_so():
    drafted = await LFGCog._draft_limited_bracket(MagicMock(), "Limited Season 3", [_entry(1, 1600)])
    assert drafted["bracket"] is None
    assert "could not be drafted" in LFGCog._limited_top_cut_text(drafted)
