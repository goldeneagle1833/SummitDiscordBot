"""A disputed match report puts the match back to unreported with fresh report buttons."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.lfg.persistent_confirm as pc
from cogs.lfg.state import pending_match_reports
from repositories.elo_repo import create_active_pairings_table, get_pairing_by_id, save_pairing

GUILD = 123456789
REPORTER = 111111
OPPONENT = 222222


@pytest.fixture
def tables():
    create_active_pairings_table()
    pc.ensure_pending_confirmations_table()
    pc.ensure_match_cards_table()
    yield
    conn = sqlite3.connect("match_records.db")
    for table in ("active_pairings", "pending_confirmations", "active_match_cards"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    pending_match_reports.clear()


def _report(pairing_id, **overrides):
    """A wrong report: the reporter says they won."""
    data = {
        "reporter_id": REPORTER,
        "reporter_global": "Reporter",
        "opponent_id": OPPONENT,
        "opponent_global": "Opponent",
        "winner_id": REPORTER,
        "winner_global": "Reporter",
        "loser_id": OPPONENT,
        "loser_global": "Opponent",
        "is_winner": False,
        "first_player": "y",
        "winner_deck_url": "https://curiosa.io/decks/reporter",
        "loser_deck_url": "https://curiosa.io/decks/opponent",
        "match_type": "ranked",
        "guild_id": GUILD,
        "pairing_id": pairing_id,
    }
    data.update(overrides)
    return data


def _bot():
    bot = MagicMock()
    users = {}

    async def fetch_user(uid):
        if uid not in users:
            user = MagicMock()
            user.id = uid
            user.mention = f"<@{uid}>"
            sent = MagicMock()
            sent.id = uid * 10
            sent.channel.id = uid * 100
            user.send = AsyncMock(return_value=sent)
            users[uid] = user
        return users[uid]

    bot.fetch_user = AsyncMock(side_effect=fetch_user)
    bot.get_channel = MagicMock(return_value=None)
    bot.users = users
    return bot


def _interaction(bot):
    interaction = MagicMock()
    interaction.client = bot
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.message.edit = AsyncMock()
    return interaction


def _cards(pairing_id):
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM active_match_cards WHERE pairing_id = ?", (pairing_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _has_report_button(view):
    return any(
        isinstance(item, pc.PersistentMatchCardReportButton) for item in view.children
    )


@pytest.mark.asyncio
async def test_dispute_reopens_match_and_sends_both_players_report_buttons(tables):
    pairing_id = save_pairing(GUILD, REPORTER, OPPONENT,
                              "https://curiosa.io/decks/reporter",
                              "https://curiosa.io/decks/opponent")
    data = _report(pairing_id)
    confirmation_id = pc.save_pending_confirmation(data)
    pending_match_reports[(REPORTER, OPPONENT)] = {"winner_id": REPORTER}
    bot = _bot()

    with patch("cogs.lfg.persistent_confirm.record_match") as record_match:
        await pc._execute_match_dispute(_interaction(bot), confirmation_id, pc.load_pending_confirmation(confirmation_id))

    record_match.assert_not_called()
    assert pc.load_pending_confirmation(confirmation_id) is None
    assert (REPORTER, OPPONENT) not in pending_match_reports
    assert get_pairing_by_id(GUILD, pairing_id)["status"] == "active"

    # Both players got a fresh, working match card (Report Result + Cancel + Report Player)
    for uid in (REPORTER, OPPONENT):
        user = bot.users[uid]
        user.send.assert_awaited_once()
        content = user.send.await_args.args[0]
        view = user.send.await_args.kwargs["view"]
        assert "Report Again" in content
        assert "no ELO changed" in content
        assert _has_report_button(view)

    cards = _cards(pairing_id)
    assert sorted(c["player1_id"] for c in cards) == [REPORTER, OPPONENT]
    # Each player's own deck stays theirs on the new card
    by_player = {c["player1_id"]: c for c in cards}
    assert by_player[REPORTER]["player1_deck_url"] == "https://curiosa.io/decks/reporter"
    assert by_player[OPPONENT]["player1_deck_url"] == "https://curiosa.io/decks/opponent"
    # Message refs saved so a later result edit can retire these cards too
    assert all(c["message_id"] for c in cards)


@pytest.mark.asyncio
async def test_old_match_card_is_retired(tables):
    pairing_id = save_pairing(GUILD, REPORTER, OPPONENT)
    old_view = pc.create_match_card_view(
        bot=None, pairing_id=pairing_id,
        player1_id=REPORTER, player1_global="Reporter",
        player2_id=OPPONENT, player2_global="Opponent",
        guild_id=GUILD,
    )
    data = _report(pairing_id)
    confirmation_id = pc.save_pending_confirmation(data)
    bot = _bot()

    with patch("cogs.lfg.persistent_confirm.edit_match_card_messages", new=AsyncMock()) as edit_cards:
        await pc._execute_match_dispute(_interaction(bot), confirmation_id, data)

    edit_cards.assert_awaited_once()
    assert pc.load_match_card(old_view.card_id) is None
    assert len(_cards(pairing_id)) == 2


@pytest.mark.asyncio
async def test_double_dispute_only_resets_once(tables):
    pairing_id = save_pairing(GUILD, REPORTER, OPPONENT)
    data = _report(pairing_id)
    confirmation_id = pc.save_pending_confirmation(data)
    bot = _bot()

    await pc._execute_match_dispute(_interaction(bot), confirmation_id, data)
    second = _interaction(bot)
    await pc._execute_match_dispute(second, confirmation_id, data)

    second.response.send_message.assert_awaited_once()
    assert "already processed" in second.response.send_message.await_args.args[0]
    assert len(_cards(pairing_id)) == 2


@pytest.mark.asyncio
async def test_dispute_without_open_pairing_keeps_old_guidance(tables):
    # Ladder challenges have no pairing to reopen
    data = _report(None)
    confirmation_id = pc.save_pending_confirmation(data)
    bot = _bot()
    interaction = _interaction(bot)

    await pc._execute_match_dispute(interaction, confirmation_id, data)

    assert "!challenge" in interaction.followup.send.await_args.args[0]
    reporter_msg = bot.users[REPORTER].send.await_args.args[0]
    assert "disputed your match report" in reporter_msg
    assert pc.load_pending_confirmation(confirmation_id) is None


@pytest.mark.asyncio
async def test_dispute_after_pairing_reported_does_not_reopen(tables):
    pairing_id = save_pairing(GUILD, REPORTER, OPPONENT)
    conn = sqlite3.connect("match_records.db")
    conn.execute("UPDATE active_pairings SET status = 'expired' WHERE pairing_id = ?", (pairing_id,))
    conn.commit()
    conn.close()
    data = _report(pairing_id)
    confirmation_id = pc.save_pending_confirmation(data)
    bot = _bot()

    await pc._execute_match_dispute(_interaction(bot), confirmation_id, data)

    assert _cards(pairing_id) == []


@pytest.mark.asyncio
async def test_dm_blocked_player_gets_card_in_fallback_channel_without_deck(tables):
    pairing_id = save_pairing(GUILD, REPORTER, OPPONENT, "https://curiosa.io/decks/reporter", None)
    data = _report(pairing_id)
    confirmation_id = pc.save_pending_confirmation(data)
    bot = _bot()
    reporter = await bot.fetch_user(REPORTER)
    reporter.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no dms"))
    channel = MagicMock()
    posted = MagicMock(id=5, channel=MagicMock(id=6))
    channel.send = AsyncMock(return_value=posted)
    bot.get_channel = MagicMock(return_value=channel)

    await pc._execute_match_dispute(_interaction(bot), confirmation_id, data)

    channel.send.assert_awaited_once()
    content = channel.send.await_args.args[0]
    assert content.startswith(f"<@{REPORTER}>")
    assert "curiosa.io" not in content
    assert _has_report_button(channel.send.await_args.kwargs["view"])
