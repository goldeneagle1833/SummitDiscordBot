"""Tests for the Give Kudos button on match messages."""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.lfg.pairing_messages import PairingPlayer, send_pairing_messages
from cogs.lfg.player_kudos import (
    KUDOS_REASONS,
    PersistentKudosButton,
    PlayerKudosModal,
    is_kudos_item,
)
from cogs.lfg.player_report import report_player_only_view
from repositories.player_kudos_repo import (
    KudosError,
    create_player_kudos_table,
    find_kudos_match,
    save_player_kudos,
)


@pytest.fixture(autouse=True)
def _kudos_table():
    create_player_kudos_table()


def _add_match(winner, loser, pairing_id=None, days_ago=0):
    conn = sqlite3.connect("match_records.db")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match_records)")}
    if "pairing_id" not in cols:
        conn.execute("ALTER TABLE match_records ADD COLUMN pairing_id INTEGER")
    if "match_type" not in cols:
        conn.execute("ALTER TABLE match_records ADD COLUMN match_type TEXT DEFAULT 'ranked'")
    ts = (datetime.now() - timedelta(days=days_ago)).isoformat()
    cur = conn.execute(
        "INSERT INTO match_records (winner_id, losser_id, timestamp, pairing_id, match_type) "
        "VALUES (?, ?, ?, ?, 'ranked')",
        (winner, loser, ts, pairing_id),
    )
    conn.commit()
    match_id = cur.lastrowid
    conn.close()
    return match_id


def _rows():
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM player_kudos ORDER BY id")]
    conn.close()
    return rows


def _interaction(user_id=10, name="Giver"):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.global_name = name
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    receiver = MagicMock(global_name="Opponent")
    receiver.send = AsyncMock()
    interaction.client.get_user.return_value = receiver
    return interaction


# ── storage ──────────────────────────────────────────────────────────


def test_kudos_need_a_recorded_match_between_the_two():
    with pytest.raises(KudosError) as e:
        save_player_kudos(giver_id=10, receiver_id=20, reasons=["good_sport"])
    assert e.value.code == "no_match"

    _add_match(30, 10)  # a match against someone else doesn't count
    with pytest.raises(KudosError):
        save_player_kudos(giver_id=10, receiver_id=20, reasons=["good_sport"])

    _add_match(20, 10, days_ago=30)  # too old
    with pytest.raises(KudosError):
        save_player_kudos(giver_id=10, receiver_id=20, reasons=["good_sport"])


def test_one_kudos_per_match_and_its_tied_to_that_match():
    match_id = _add_match(20, 10, pairing_id=5)
    save_player_kudos(
        giver_id=10, giver_name="Giver", receiver_id=20, receiver_name="Opp",
        reasons=["good_sport", "great_voice"], message="  gg!  ", pairing_id=5,
    )
    [row] = _rows()
    assert row["match_id"] == match_id
    assert row["pairing_id"] == 5
    assert json.loads(row["reasons"]) == ["good_sport", "great_voice"]
    assert row["message"] == "gg!"
    assert row["anonymous"] == 0

    with pytest.raises(KudosError) as e:
        save_player_kudos(giver_id=10, receiver_id=20, reasons=["friendly"], pairing_id=5)
    assert e.value.code == "already_given"

    # The opponent can still thank the giver back.
    save_player_kudos(giver_id=20, receiver_id=10, reasons=["friendly"], pairing_id=5)
    # And a second game means a second chance.
    _add_match(10, 20)
    save_player_kudos(giver_id=10, receiver_id=20, reasons=["great_game"])
    assert len(_rows()) == 3


def test_a_pairing_without_a_stored_result_falls_back_to_their_latest_match():
    match_id = _add_match(20, 10, pairing_id=None)
    assert find_kudos_match(10, 20, pairing_id=99)["match_id"] == match_id


# ── button ───────────────────────────────────────────────────────────


def test_reason_labels_fit_discord_limits():
    assert len(KUDOS_REASONS) <= 10
    assert all(len(label) <= 100 for _, label in KUDOS_REASONS)


@pytest.mark.asyncio
async def test_the_button_survives_a_restart_from_its_custom_id():
    button = PersistentKudosButton(123456789012345678, 876543210987654321, 55)
    custom_id = button.item.custom_id
    assert len(custom_id) <= 100
    match = PersistentKudosButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    rebuilt = await PersistentKudosButton.from_custom_id(None, None, match)
    assert (rebuilt.giver_id, rebuilt.receiver_id, rebuilt.pairing_id) == (
        123456789012345678, 876543210987654321, 55,
    )


@pytest.mark.asyncio
async def test_only_the_owner_can_press_it_and_only_after_the_result():
    button = PersistentKudosButton(10, 20, 1)

    stranger = _interaction(user_id=99)
    await button.callback(stranger)
    stranger.response.send_modal.assert_not_awaited()

    early = _interaction(user_id=10)
    await button.callback(early)
    early.response.send_modal.assert_not_awaited()
    assert "once this match's result" in early.response.send_message.await_args.args[0]

    _add_match(10, 20, pairing_id=1)
    owner = _interaction(user_id=10)
    await button.callback(owner)
    modal = owner.response.send_modal.await_args.args[0]
    assert isinstance(modal, PlayerKudosModal)
    assert modal.receiver_id == 20


# ── modal ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submitting_saves_the_kudos_and_tells_the_opponent():
    _add_match(10, 20, pairing_id=3)
    modal = PlayerKudosModal(receiver_id=20, pairing_id=3)
    modal.reasons._values = ["helpful"]
    modal.message._value = "Explained Rubble for me, thanks!"
    modal.privacy._values = []

    interaction = _interaction()
    await modal.on_submit(interaction)

    [row] = _rows()
    assert row["giver_name"] == "Giver" and row["receiver_name"] == "Opponent"
    assert row["message"] == "Explained Rubble for me, thanks!"
    assert "You applauded" in interaction.response.send_message.await_args.args[0]
    dm = interaction.client.get_user.return_value.send.await_args.args[0]
    assert "**Giver** applauded you" in dm
    assert "Helped me learn" in dm


@pytest.mark.asyncio
async def test_anonymous_kudos_hide_the_givers_name_from_the_opponent_too():
    _add_match(10, 20, pairing_id=3)
    modal = PlayerKudosModal(receiver_id=20, pairing_id=3)
    modal.reasons._values = ["good_sport"]
    modal.message._value = ""
    modal.privacy._values = ["anonymous"]

    interaction = _interaction()
    await modal.on_submit(interaction)

    assert _rows()[0]["anonymous"] == 1
    dm = interaction.client.get_user.return_value.send.await_args.args[0]
    assert "Someone you played" in dm and "Giver" not in dm


@pytest.mark.asyncio
async def test_empty_kudos_are_not_saved():
    _add_match(10, 20, pairing_id=3)
    modal = PlayerKudosModal(receiver_id=20, pairing_id=3)
    modal.reasons._values = []
    modal.message._value = "  "
    modal.privacy._values = []
    interaction = _interaction()
    await modal.on_submit(interaction)
    assert _rows() == []


# ── on the match messages ────────────────────────────────────────────


def _player(user_id, name):
    user = MagicMock()
    user.id = user_id
    user.mention = f"<@{user_id}>"
    user.global_name = name
    user.display_name = name
    sent = MagicMock(id=999)
    sent.channel.id = 888
    user.send = AsyncMock(return_value=sent)
    return PairingPlayer(user_id, name, user)


@pytest.mark.asyncio
async def test_both_players_get_a_kudos_button_pointing_at_the_other():
    reporter = _player(10, "Reporter")
    other = _player(20, "Other")
    card_view = discord.ui.View(timeout=None)
    card_view.card_id = 42
    card_view.pairing_id = 77

    await send_pairing_messages(
        MagicMock(), reporter=reporter, other=other, match_card_view=card_view, match_type="ranked",
    )

    def kudos(view):
        return [i.custom_id for i in view.children if is_kudos_item(i)]

    assert kudos(reporter.user.send.await_args.kwargs["view"]) == ["pkd:10:20:77"]
    assert kudos(other.user.send.await_args.kwargs["view"]) == ["pkd:20:10:77"]


def test_the_result_edit_keeps_report_player_and_give_kudos():
    message = MagicMock()
    message.components = [
        discord.ActionRow(
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": "Report Result", "custom_id": "pmcr:1"},
                    {"type": 2, "style": 2, "label": "Report Player", "custom_id": "prp:10:20:77:ranked"},
                    {"type": 2, "style": 3, "label": "Give Kudos", "custom_id": "pkd:10:20:77",
                     "disabled": True},
                ],
            },
        )
    ]
    view = report_player_only_view(message)
    assert [item.custom_id for item in view.children] == ["prp:10:20:77:ranked", "pkd:10:20:77"]
    assert all(not item.disabled for item in view.children)
