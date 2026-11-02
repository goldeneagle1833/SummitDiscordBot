"""Tests for block/report DMs to the owner with Timeout / Ban buttons."""

import os
import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cogs.moderation_alerts as mod
from cogs.moderation_alerts import (
    ModerationAlertsCog,
    ModerationConfirmView,
    PersistentModerationButton,
    moderation_view,
    perform_moderation,
)
from repositories.blocked_users_repo import create_blocked_users_table
from repositories.moderation_repo import (
    create_moderation_tables,
    get_actions_for_target,
    get_unsent_blocks,
    get_unsent_reports,
)
from repositories.player_reports_repo import create_player_reports_table, save_player_report

OWNER = 111111111111111111
REPORTED = 222222222222222222
REPORTER = 333333333333333333
GUILD = 444444444444444444


@pytest.fixture(autouse=True)
def _tables():
    create_player_reports_table()
    create_blocked_users_table()
    with patch.object(mod.config, "OWNER_ID", OWNER, create=True), \
         patch.object(mod.config, "SUMMIT_GUILD_ID", GUILD, create=True), \
         patch.object(mod.config, "MODERATION_ALERT_USER_IDS", None, create=True):
        yield


def _block(user_id, blocked, reason="rude"):
    conn = sqlite3.connect("match_records.db")
    conn.execute(
        "INSERT INTO blocked_users (user_id, blocked_user_id, reason) VALUES (?, ?, ?)",
        (str(user_id), str(blocked), reason),
    )
    conn.commit()
    conn.close()


def _report(**kw):
    args = dict(reporter_id=REPORTER, reporter_name="Reporter", reported_id=REPORTED,
                reported_name="Opponent", pairing_id=7, match_type="ranked",
                reasons=["toxic"], details="called me names")
    args.update(kw)
    save_player_report(**args)


def _bot():
    bot = MagicMock()
    owner = MagicMock(id=OWNER)
    owner.send = AsyncMock()
    bot.get_user.side_effect = lambda uid: owner if uid == OWNER else MagicMock(global_name=f"user{uid}")
    return bot, owner


def _cog(bot):
    with patch("discord.ext.tasks.Loop.start"):
        return ModerationAlertsCog(bot)


# ── which rows get sent ──────────────────────────────────────────────


def test_turning_it_on_does_not_dm_old_blocks_and_reports():
    _report()
    _block(REPORTER, REPORTED)
    create_moderation_tables()
    assert get_unsent_reports() == [] and get_unsent_blocks() == []


@pytest.mark.asyncio
async def test_each_new_report_and_block_is_dmed_once_with_buttons():
    create_moderation_tables()
    _report()
    _block(REPORTER, REPORTED, reason="no show twice")
    bot, owner = _bot()
    cog = _cog(bot)

    assert await cog.run_once() == 2
    assert owner.send.await_count == 2
    report_call, block_call = owner.send.await_args_list
    report_embed = report_call.kwargs["embed"]
    assert report_embed.title.startswith("Player report #")
    assert "rude, toxic" in str(report_embed.fields).lower()
    labels = [getattr(c, "item", c).label for c in report_call.kwargs["view"].children]
    assert labels == ["Timeout", "Ban", "Pairing Block", "Admin panel"]
    assert block_call.kwargs["embed"].title == "Player blocked"
    assert "no show twice" in str(block_call.kwargs["embed"].fields)

    # Second pass: nothing new
    assert await cog.run_once() == 0
    assert owner.send.await_count == 2


@pytest.mark.asyncio
async def test_closed_dms_dont_resend_forever():
    create_moderation_tables()
    _report()
    bot, owner = _bot()
    owner.send.side_effect = discord.Forbidden(MagicMock(status=403), "closed")
    cog = _cog(bot)
    assert await cog.run_once() == 1
    assert await cog.run_once() == 0


def test_google_only_accounts_get_no_timeout_or_ban_buttons():
    view = moderation_view("google_12345", "block", REPORTER)
    assert [getattr(c, "item", c).label for c in view.children] == ["Admin panel"]


def test_button_custom_id_round_trips_through_the_template():
    button = PersistentModerationButton("ban", REPORTED, "block", "google_999")
    match = PersistentModerationButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
    assert match and match["action"] == "ban" and match["ref"] == "google_999"
    assert len(button.item.custom_id) <= 100


# ── confirm step ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pressing_ban_only_asks_for_confirmation():
    create_moderation_tables()
    button = PersistentModerationButton("ban", REPORTED, "report", "1")
    interaction = MagicMock()
    interaction.user.id = OWNER
    interaction.client.get_user.return_value = MagicMock(global_name="Opponent")
    interaction.response.send_message = AsyncMock()
    guild = MagicMock()
    guild.ban = AsyncMock()
    interaction.client.get_guild.return_value = guild

    await button.callback(interaction)

    guild.ban.assert_not_awaited()
    text = interaction.response.send_message.await_args.args[0]
    view = interaction.response.send_message.await_args.kwargs["view"]
    assert "Ban" in text and isinstance(view, ModerationConfirmView)
    assert [c.label for c in view.children] == ["Confirm ban", "Cancel"]


@pytest.mark.asyncio
async def test_strangers_cant_press_the_buttons():
    button = PersistentModerationButton("timeout", REPORTED, "report", "1")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.client.get_guild.return_value.get_member.return_value = None
    interaction.response.send_message = AsyncMock()
    await button.callback(interaction)
    assert "Only admins" in interaction.response.send_message.await_args.args[0]


def test_timeout_prompt_has_a_duration_picker_defaulting_to_one_day():
    view = ModerationConfirmView(action="timeout", target_id=REPORTED, target_name="Opponent",
                                 source_kind="report", source_ref="1", reason="x")
    select = view.children[0]
    assert [o.label for o in select.options] == ["1 hour", "1 day", "1 week", "28 days"]
    assert [o.default for o in select.options] == [False, True, False, False]
    assert view.minutes == 1440


# ── doing it ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_times_them_out_and_logs_it():
    create_moderation_tables()
    member = MagicMock(global_name="Opponent")
    member.timeout = AsyncMock()
    guild = MagicMock()
    guild.get_member.return_value = member
    client = MagicMock()
    client.get_guild.return_value = guild
    moderator = MagicMock(id=OWNER, global_name="Bruce")

    ok, msg = await perform_moderation(client, action="timeout", target_id=REPORTED,
                                       moderator=moderator, minutes=60, reason="toxic",
                                       source_kind="report", source_ref="1")
    assert ok and "1 hour" in msg
    assert member.timeout.await_args.args[0].total_seconds() == 3600
    [row] = get_actions_for_target(REPORTED)
    assert row["action"] == "timeout" and row["duration_minutes"] == 60 and row["via"] == "discord"


@pytest.mark.asyncio
async def test_ban_bans_by_id_even_if_they_left():
    create_moderation_tables()
    guild = MagicMock()
    guild.ban = AsyncMock()
    client = MagicMock()
    client.get_guild.return_value = guild
    ok, _ = await perform_moderation(client, action="ban", target_id=REPORTED,
                                     moderator=MagicMock(id=OWNER, global_name="Bruce"))
    assert ok
    assert guild.ban.await_args.args[0].id == REPORTED
    assert get_actions_for_target(REPORTED)[0]["action"] == "ban"


@pytest.mark.asyncio
async def test_discord_refusing_is_reported_and_not_logged():
    create_moderation_tables()
    guild = MagicMock()
    guild.ban = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    client = MagicMock()
    client.get_guild.return_value = guild
    ok, msg = await perform_moderation(client, action="ban", target_id=REPORTED,
                                       moderator=MagicMock(id=OWNER, global_name="Bruce"))
    assert not ok and "Ban Members" in msg
    assert get_actions_for_target(REPORTED) == []


# ── pairing block ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pairing_block_opens_the_ban_form_prefilled_without_naming_the_reporter():
    create_moderation_tables()
    _report(reasons=["toxic", "no_show"])
    button = PersistentModerationButton("pblock", REPORTED, "report", "1")
    interaction = MagicMock()
    interaction.user.id = OWNER
    interaction.client.get_cog.return_value = MagicMock()
    interaction.client.get_user.return_value = MagicMock(id=REPORTED, global_name="Opponent")
    interaction.response.send_modal = AsyncMock()

    await button.callback(interaction)

    modal = interaction.response.send_modal.await_args.args[0]
    assert modal.title == "Block from Pairing Service"
    assert modal.reason.default.startswith("Reported after a match: was rude")
    assert "Reporter" not in modal.reason.default


@pytest.mark.asyncio
async def test_submitting_the_form_blocks_and_logs_it():
    from cogs.moderation_alerts import AlertPairingBlockModal

    create_moderation_tables()
    cog = MagicMock()
    cog.apply_ban = AsyncMock(return_value=discord.Embed(title="Pairing ban applied"))
    bot = MagicMock()
    bot.get_cog.return_value = cog
    target = MagicMock(id=REPORTED, global_name="Opponent")
    admin = MagicMock(id=OWNER, global_name="Bruce")
    modal = AlertPairingBlockModal.build(bot, target, admin, default_reason="Reported after a match",
                                         source_kind="report", source_ref="1")
    modal.duration_select._values = ["48h"]
    with patch.object(type(modal.duration_select), "values", property(lambda self: ["48h"])):
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        await modal.on_submit(interaction)

    assert cog.apply_ban.await_args.kwargs["duration_key"] == "48h"
    [row] = get_actions_for_target(REPORTED)
    assert row["action"] == "pairing_block" and row["duration_label"] == "48 hours"


@pytest.mark.asyncio
async def test_website_pairing_blocks_are_followed_up_once():
    from repositories.moderation_repo import log_moderation_action
    from repositories.pairing_bans_repo import set_pairing_ban

    create_moderation_tables()
    set_pairing_ban(REPORTED, OWNER, "Reported after a match", "24h")
    action_id = log_moderation_action(target_id=REPORTED, action="pairing_block", via="web",
                                      duration_label="24 hours")
    conn = sqlite3.connect("match_records.db")
    conn.execute("UPDATE moderation_actions SET bot_done = 0 WHERE id = ?", (action_id,))
    conn.commit()
    conn.close()

    bot, _ = _bot()
    pairing_cog = MagicMock()
    pairing_cog._remove_from_queue = AsyncMock(return_value=True)
    bot.get_cog.return_value = pairing_cog
    player = MagicMock(id=REPORTED)
    player.send = AsyncMock()
    bot.get_user.side_effect = lambda uid: player
    cog = _cog(bot)

    assert await cog.follow_up_web_pairing_blocks() == 1
    pairing_cog._remove_from_queue.assert_awaited_once_with(REPORTED)
    assert "pairing service" in player.send.await_args.kwargs["embed"].title
    assert await cog.follow_up_web_pairing_blocks() == 0
