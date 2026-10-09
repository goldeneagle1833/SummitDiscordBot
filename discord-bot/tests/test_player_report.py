"""Tests for the Report Player button on match messages."""

import json
import os
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.lfg.pairing_messages import PairingPlayer, send_pairing_messages
from cogs.lfg.player_report import (
    REPORT_REASONS,
    PersistentReportPlayerButton,
    PlayerReportModal,
    is_report_player_item,
    report_player_only_view,
)
from repositories.player_reports_repo import create_player_reports_table, save_player_report


@pytest.fixture(autouse=True)
def _player_reports_table():
    create_player_reports_table()


def _rows():
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM player_reports ORDER BY id")]
    conn.close()
    return rows


def _interaction(user_id=10, name="Reporter"):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.global_name = name
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    reported = MagicMock(global_name="Opponent")
    interaction.client.get_user.return_value = reported
    return interaction


def _report_buttons(view):
    return [item for item in view.children if is_report_player_item(item)]


# ── storage ──────────────────────────────────────────────────────────


def test_a_report_is_saved_with_its_reasons_and_feedback():
    save_player_report(
        reporter_id=10, reporter_name="Reporter",
        reported_id=20, reported_name="Opponent",
        pairing_id=7, match_type="ranked",
        reasons=["voice_refused", "left_early"], details="  left at 2 life  ",
    )
    [row] = _rows()
    assert row["reporter_id"] == "10" and row["reported_id"] == "20"
    assert json.loads(row["reasons"]) == ["voice_refused", "left_early"]
    assert row["details"] == "left at 2 life"
    assert row["pairing_id"] == 7


# ── button ───────────────────────────────────────────────────────────


def test_the_suggested_reasons_include_bruces_two_and_fit_discord_limits():
    labels = [label for _, label in REPORT_REASONS]
    assert "Opponent joined voice but didn't want to use voice" in labels
    assert "Opponent left the match early without conceding" in labels
    assert len(REPORT_REASONS) <= 10
    assert all(len(label) <= 100 for label in labels)


@pytest.mark.asyncio
async def test_the_button_survives_a_restart_from_its_custom_id():
    button = PersistentReportPlayerButton(123456789012345678, 876543210987654321, 55, "ranked")
    custom_id = button.item.custom_id
    assert len(custom_id) <= 100

    match = PersistentReportPlayerButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    rebuilt = await PersistentReportPlayerButton.from_custom_id(None, None, match)
    assert rebuilt.reporter_id == 123456789012345678
    assert rebuilt.reported_id == 876543210987654321
    assert rebuilt.pairing_id == 55
    assert rebuilt.match_type == "ranked"


@pytest.mark.asyncio
async def test_only_the_messages_owner_can_open_the_report():
    button = PersistentReportPlayerButton(10, 20, 1, "ranked")

    stranger = _interaction(user_id=99)
    await button.callback(stranger)
    stranger.response.send_modal.assert_not_awaited()

    owner = _interaction(user_id=10)
    await button.callback(owner)
    modal = owner.response.send_modal.await_args.args[0]
    assert isinstance(modal, PlayerReportModal)
    assert modal.reported_id == 20


# ── modal ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submitting_the_modal_files_a_report():
    modal = PlayerReportModal(reported_id=20, pairing_id=3, match_type="casual")
    modal.reasons._values = ["toxic"]
    modal.details._value = "Called me names"

    interaction = _interaction()
    await modal.on_submit(interaction)

    [row] = _rows()
    assert row["reporter_name"] == "Reporter"
    assert row["reported_name"] == "Opponent"
    assert json.loads(row["reasons"]) == ["toxic"]
    assert row["details"] == "Called me names"
    assert "sent to the admins" in interaction.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_an_empty_report_is_not_saved():
    modal = PlayerReportModal(reported_id=20, pairing_id=3, match_type="ranked")
    modal.details._value = "   "

    interaction = _interaction()
    await modal.on_submit(interaction)

    assert _rows() == []
    assert "Nothing was reported" in interaction.response.send_message.await_args.args[0]


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
async def test_both_players_get_a_report_player_button_pointing_at_the_other():
    reporter = _player(10, "Reporter")
    other = _player(20, "Other")
    card_view = discord.ui.View(timeout=None)
    card_view.card_id = 42
    card_view.pairing_id = 77

    bot = MagicMock()
    await send_pairing_messages(
        bot, reporter=reporter, other=other, match_card_view=card_view, match_type="ranked",
    )

    [reporter_button] = _report_buttons(reporter.user.send.await_args.kwargs["view"])
    [other_button] = _report_buttons(other.user.send.await_args.kwargs["view"])
    assert reporter_button.custom_id == "prp:10:20:77:ranked"
    assert other_button.custom_id == "prp:20:10:77:ranked"


def test_editing_a_card_to_the_result_keeps_only_report_player():
    message = MagicMock()
    message.components = [
        discord.ActionRow(
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": "Report Result", "custom_id": "pmcr:1"},
                    {"type": 2, "style": 4, "label": "Cancel Match", "custom_id": "pmcc:1"},
                    {"type": 2, "style": 2, "label": "Report Player", "custom_id": "prp:10:20:77:ranked",
                     "disabled": True},
                ],
            },
        )
    ]
    view = report_player_only_view(message)
    assert [item.custom_id for item in view.children] == ["prp:10:20:77:ranked"]
    assert view.children[0].disabled is False


def test_a_card_without_report_player_gets_no_view():
    message = MagicMock()
    message.components = []
    assert report_player_only_view(message) is None
