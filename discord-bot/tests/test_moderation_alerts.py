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
    ModerationReasonModal,
    PersistentModerationButton,
    moderation_view,
    perform_moderation,
)
from repositories.blocked_users_repo import create_blocked_users_table
from repositories.moderation_repo import (
    create_moderation_tables,
    get_actions_for_target,
    get_open_group_chat as get_open_chat,
    get_unsent_blocks,
    get_unsent_reports,
)
from repositories.player_reports_repo import create_player_reports_table, save_player_report

OWNER = 111111111111111111
REPORTED = 222222222222222222
REPORTER = 333333333333333333
GUILD = 444444444444444444
MODCH = 555555555555555555
MOD2 = 666666666666666666


@pytest.fixture(autouse=True)
def _tables():
    create_player_reports_table()
    create_blocked_users_table()
    with patch.object(mod.config, "OWNER_ID", OWNER, create=True), \
         patch.object(mod.config, "SUMMIT_GUILD_ID", GUILD, create=True), \
         patch.object(mod.config, "MODERATION_ALERT_USER_IDS", None, create=True), \
         patch.object(mod.config, "MODERATION_ALERT_CHANNEL_ID", MODCH, create=True), \
         patch.object(mod.config, "MODERATION_CHAT_CATEGORY_ID", 0, create=True):
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
    channel = MagicMock(id=MODCH)
    channel.send = AsyncMock()
    bot.get_channel.side_effect = lambda cid: channel if cid == MODCH else None
    bot.mod_channel = channel
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
    assert labels == ["Timeout", "Ban", "Pairing Block", "Group chat", "Note", "Mod Tools"]
    assert block_call.kwargs["embed"].title == "Player blocked"
    assert "no show twice" in str(block_call.kwargs["embed"].fields)

    # Second pass: nothing new
    assert await cog.run_once() == 0
    assert owner.send.await_count == 2
    # The mod channel got the same two alerts
    assert bot.mod_channel.send.await_count == 2
    assert bot.mod_channel.send.await_args_list[0].kwargs["embed"] is report_embed


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
    assert [getattr(c, "item", c).label for c in view.children] == ["Note", "Mod Tools"]


def test_button_custom_id_round_trips_through_the_template():
    button = PersistentModerationButton("ban", REPORTED, "block", "google_999")
    match = PersistentModerationButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
    assert match and match["action"] == "ban" and match["ref"] == "google_999"
    assert len(button.item.custom_id) <= 100


# ── confirm step ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pressing_ban_opens_a_reason_form_and_does_nothing_yet():
    create_moderation_tables()
    _report(reasons=["toxic"])
    button = PersistentModerationButton("ban", REPORTED, "report", "1")
    interaction = MagicMock()
    interaction.user.id = OWNER
    interaction.client.get_user.return_value = MagicMock(global_name="Opponent")
    interaction.response.send_modal = AsyncMock()
    guild = MagicMock()
    guild.ban = AsyncMock()
    interaction.client.get_guild.return_value = guild

    await button.callback(interaction)

    guild.ban.assert_not_awaited()
    modal = interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, ModerationReasonModal)
    assert modal.title == "Ban Opponent"
    assert modal.duration is None
    assert modal.reason.label == "Reason (sent to the player)"
    assert modal.reason.required and modal.reason.min_length == 3
    assert modal.reason.default.startswith("Reported after a match: was rude")
    assert "Reporter" not in modal.reason.default


@pytest.mark.asyncio
async def test_block_reason_never_names_the_blocker():
    create_moderation_tables()
    button = PersistentModerationButton("timeout", REPORTED, "block", str(REPORTER))
    interaction = MagicMock()
    interaction.user.id = OWNER
    interaction.client.get_user.return_value = MagicMock(global_name="Opponent")
    interaction.response.send_modal = AsyncMock()
    await button.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    assert modal.reason.default == "Blocked by other players"
    assert str(REPORTER) not in modal.reason.default


@pytest.mark.asyncio
async def test_strangers_cant_press_the_buttons():
    button = PersistentModerationButton("timeout", REPORTED, "report", "1")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.client.get_guild.return_value.get_member.return_value = None
    interaction.response.send_message = AsyncMock()
    await button.callback(interaction)
    assert "Only admins" in interaction.response.send_message.await_args.args[0]


def test_timeout_form_has_a_duration_picker_defaulting_to_one_day():
    modal = ModerationReasonModal(action="timeout", target_id=REPORTED, target_name="Opponent",
                                  source_kind="report", source_ref="1", default_reason="x")
    assert modal.title == "Time out Opponent"
    assert [o.label for o in modal.duration.options] == ["1 hour", "1 day", "1 week", "28 days"]
    assert [o.default for o in modal.duration.options] == [False, True, False, False]
    assert modal.minutes == 1440


@pytest.mark.asyncio
async def test_submitting_the_timeout_form_times_them_out_with_the_typed_reason():
    create_moderation_tables()
    member = MagicMock(global_name="Opponent")
    member.timeout = AsyncMock()
    guild = MagicMock()
    guild.name = "Sorcerers Summit"
    guild.get_member.return_value = member
    player = MagicMock()
    player.send = AsyncMock()
    modal = ModerationReasonModal(action="timeout", target_id=REPORTED, target_name="Opponent",
                                  source_kind="report", source_ref="1", default_reason="x")
    interaction = MagicMock()
    interaction.user = MagicMock(id=OWNER, global_name="Bruce")
    interaction.client.get_guild.return_value = guild
    interaction.client.get_user.return_value = player
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    with patch.object(type(modal.duration), "values", property(lambda self: ["60"])), \
         patch.object(type(modal.reason), "value", property(lambda self: "  Spamming the LFG channel  ")):
        await modal.on_submit(interaction)

    assert member.timeout.await_args.args[0].total_seconds() == 3600
    assert member.timeout.await_args.kwargs["reason"] == "Spamming the LFG channel (report #1, by Bruce)"
    embed = player.send.await_args.kwargs["embed"]
    assert embed.title == "You've been timed out in Sorcerers Summit"
    assert {f.name: f.value for f in embed.fields}["Reason"] == "Spamming the LFG channel"
    text = interaction.followup.send.await_args.args[0]
    assert "1 hour" in text and "DMed" in text
    [row] = get_actions_for_target(REPORTED)
    assert row["reason"] == "Spamming the LFG channel"


@pytest.mark.asyncio
async def test_strangers_cant_submit_the_form():
    modal = ModerationReasonModal(action="ban", target_id=REPORTED, target_name="Opponent",
                                  source_kind="report", source_ref="1")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.client.get_guild.return_value.get_member.return_value = None
    interaction.response.send_message = AsyncMock()
    await modal.on_submit(interaction)
    assert "Only admins" in interaction.response.send_message.await_args.args[0]


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
    client.get_user.return_value.send = AsyncMock()
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
    client.get_user.return_value.send = AsyncMock()
    ok, _ = await perform_moderation(client, action="ban", target_id=REPORTED,
                                     moderator=MagicMock(id=OWNER, global_name="Bruce"))
    assert ok
    assert guild.ban.await_args.args[0].id == REPORTED
    assert get_actions_for_target(REPORTED)[0]["action"] == "ban"


@pytest.mark.asyncio
async def test_ban_dms_the_reason_before_banning():
    create_moderation_tables()
    order = []
    player = MagicMock()
    player.send = AsyncMock(side_effect=lambda **kw: order.append("dm") or MagicMock())
    guild = MagicMock()
    guild.name = "Sorcerers Summit"
    guild.ban = AsyncMock(side_effect=lambda *a, **kw: order.append("ban"))
    client = MagicMock()
    client.get_guild.return_value = guild
    client.get_user.return_value = player
    ok, msg = await perform_moderation(client, action="ban", target_id=REPORTED,
                                       moderator=MagicMock(id=OWNER, global_name="Bruce"),
                                       reason="Cheating", source_kind="block", source_ref=str(REPORTER))
    assert ok and order == ["dm", "ban"] and "DMed" in msg
    embed = player.send.await_args.kwargs["embed"]
    assert embed.title == "You've been banned from Sorcerers Summit"
    assert guild.ban.await_args.kwargs["reason"] == "Cheating (by Bruce)"


@pytest.mark.asyncio
async def test_refused_ban_deletes_the_dm_again():
    create_moderation_tables()
    sent = MagicMock()
    sent.delete = AsyncMock()
    player = MagicMock()
    player.send = AsyncMock(return_value=sent)
    guild = MagicMock()
    guild.ban = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    client = MagicMock()
    client.get_guild.return_value = guild
    client.get_user.return_value = player
    ok, _ = await perform_moderation(client, action="ban", target_id=REPORTED,
                                     moderator=MagicMock(id=OWNER, global_name="Bruce"), reason="Cheating")
    assert not ok
    sent.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_closed_dms_still_time_them_out():
    create_moderation_tables()
    member = MagicMock(global_name="Opponent")
    member.timeout = AsyncMock()
    guild = MagicMock()
    guild.get_member.return_value = member
    player = MagicMock()
    player.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "closed"))
    client = MagicMock()
    client.get_guild.return_value = guild
    client.get_user.return_value = player
    ok, msg = await perform_moderation(client, action="timeout", target_id=REPORTED, minutes=60,
                                       moderator=MagicMock(id=OWNER, global_name="Bruce"), reason="Rude")
    assert ok and "couldn't DM" in msg
    member.timeout.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_refusing_is_reported_and_not_logged():
    create_moderation_tables()
    guild = MagicMock()
    guild.ban = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "no"))
    client = MagicMock()
    client.get_guild.return_value = guild
    client.get_user.return_value.send = AsyncMock()
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


# ── mod channel copy ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mod_channel_failing_still_dms_the_owner():
    create_moderation_tables()
    _report()
    bot, owner = _bot()
    bot.mod_channel.send.side_effect = discord.Forbidden(MagicMock(status=403), "no access")
    cog = _cog(bot)
    assert await cog.run_once() == 1
    assert owner.send.await_count == 1


@pytest.mark.asyncio
async def test_channel_id_zero_turns_the_channel_copy_off():
    create_moderation_tables()
    _report()
    bot, owner = _bot()
    with patch.object(mod.config, "MODERATION_ALERT_CHANNEL_ID", 0):
        assert await _cog(bot).run_once() == 1
    assert owner.send.await_count == 1
    bot.mod_channel.send.assert_not_awaited()


def test_default_channel_is_the_summit_mod_channel():
    with patch.object(mod, "config", MagicMock(spec=[])):
        assert mod.alert_channel_id() == 1574423902254530713


def test_website_moderators_can_use_the_buttons():
    create_moderation_tables()
    conn = sqlite3.connect("match_records.db")
    conn.execute("CREATE TABLE IF NOT EXISTS moderators (discord_user_id TEXT PRIMARY KEY, display_name TEXT)")
    conn.execute("INSERT OR IGNORE INTO moderators VALUES (?, 'Mod')", (str(MOD2),))
    conn.commit()
    conn.close()
    client = MagicMock()
    client.get_guild.return_value.get_member.return_value = None
    assert mod.can_moderate(client, MagicMock(id=MOD2))
    assert not mod.can_moderate(client, MagicMock(id=999))


# ── group chat ───────────────────────────────────────────────────────


def test_group_chat_custom_id_round_trips():
    button = mod.PersistentGroupChatButton(REPORTED, "block", "google_999")
    match = mod.PersistentGroupChatButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
    assert match and match["target"] == str(REPORTED) and match["ref"] == "google_999"
    assert len(button.item.custom_id) <= 100


def _chat_world():
    """A fake Summit server with the player, two moderators and no chats yet."""
    guild = MagicMock()
    guild.categories = []
    player = MagicMock(id=REPORTED, global_name="Opponent", mention=f"<@{REPORTED}>")
    mod1 = MagicMock(id=OWNER, global_name="Bruce", mention=f"<@{OWNER}>")
    mod2 = MagicMock(id=MOD2, global_name="Helper", mention=f"<@{MOD2}>")
    members = {REPORTED: player, OWNER: mod1, MOD2: mod2}
    guild.get_member.side_effect = members.get
    guild.create_category = AsyncMock(return_value=MagicMock(name="Mod Chats"))

    channel = MagicMock(id=777, mention="<#777>")
    channel.name = "mod-chat-opponent"
    channel.guild = guild
    channel.send = AsyncMock()
    channel.set_permissions = AsyncMock()
    channel.edit = AsyncMock()
    granted = {}

    async def create_text_channel(name, *, category, overwrites, reason):
        channel.name = name
        granted.update({m: o for m, o in overwrites.items()})
        return channel

    async def set_permissions(member, *, overwrite, reason=None):
        granted[member] = overwrite

    channel.set_permissions.side_effect = set_permissions
    channel.overwrites_for.side_effect = lambda m: granted.get(m) or discord.PermissionOverwrite()
    guild.create_text_channel = AsyncMock(side_effect=create_text_channel)
    guild.get_channel.side_effect = lambda cid: channel if cid == 777 else None

    client = MagicMock()
    client.get_guild.return_value = guild
    modch = MagicMock(id=MODCH)
    modch.send = AsyncMock()
    client.get_channel.side_effect = lambda cid: modch if cid == MODCH else None
    client.get_user.side_effect = lambda uid: members.get(uid)
    return client, guild, channel, granted, player, mod1, mod2, modch


@pytest.mark.asyncio
async def test_first_press_makes_a_private_chat_with_only_the_player_and_presser():
    create_moderation_tables()
    _report()
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()

    ok, msg = await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod1)

    assert ok and "<#777>" in msg
    guild.create_category.assert_awaited_once()
    assert channel.name == "mod-chat-opponent"
    assert granted[guild.default_role].view_channel is False
    assert granted[player].view_channel and granted[mod1].view_channel
    assert mod2 not in granted
    intro = channel.send.await_args.kwargs
    assert f"<@{REPORTED}>" in intro["content"]
    text = intro["embed"].title + intro["embed"].description
    assert "Reporter" not in text and str(REPORTER) not in text
    assert "player report" in text
    assert [c.item.label for c in intro["view"].children] == ["Close chat"]
    assert "opened a group chat" in modch.send.await_args.args[0]


@pytest.mark.asyncio
async def test_later_presses_join_the_same_chat():
    create_moderation_tables()
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="block", ref=str(REPORTER), moderator=mod1)

    ok, msg = await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="5", moderator=mod2)
    assert ok and "Added you" in msg
    assert guild.create_text_channel.await_count == 1
    assert granted[mod2].view_channel
    assert "joined the chat" in channel.send.await_args.args[0]

    ok, msg = await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="5", moderator=mod2)
    assert ok and "already in" in msg


@pytest.mark.asyncio
async def test_block_intro_doesnt_mention_a_report_or_the_blocker():
    create_moderation_tables()
    client, guild, channel, *_rest = _chat_world()
    mod1 = _rest[2]
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="block", ref=str(REPORTER), moderator=mod1)
    embed = channel.send.await_args.kwargs["embed"]
    assert "report" not in embed.description.lower()
    assert str(REPORTER) not in embed.description


@pytest.mark.asyncio
async def test_deleted_chat_channel_gets_replaced():
    create_moderation_tables()
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod1)
    guild.get_channel.side_effect = lambda cid: None
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod2)
    assert guild.create_text_channel.await_count == 2


@pytest.mark.asyncio
async def test_player_who_left_cant_be_added():
    create_moderation_tables()
    client, guild, *_ = _chat_world()
    guild.get_member.side_effect = lambda uid: None
    guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "gone"))
    ok, msg = await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1",
                                                moderator=MagicMock(id=OWNER))
    assert not ok and "not in the Summit server" in msg
    guild.create_text_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_anyone_in_the_mod_channel_can_press_group_chat_but_not_elsewhere():
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.client.get_guild.return_value.get_member.return_value = None
    interaction.channel_id = MODCH
    assert mod.can_use_mod_buttons(interaction.client, interaction)
    interaction.channel_id = 123
    assert not mod.can_use_mod_buttons(interaction.client, interaction)

    button = mod.PersistentGroupChatButton(REPORTED, "report", "1")
    interaction.response.send_message = AsyncMock()
    await button.callback(interaction)
    assert "Only moderators" in interaction.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_close_chat_removes_the_player_and_keeps_history():
    create_moderation_tables()
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod1)

    close = mod.PersistentCloseChatButton()
    interaction = MagicMock()
    interaction.channel = channel
    interaction.client = client
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    interaction.user = player  # the player can't close it
    await close.callback(interaction)
    assert "Only a moderator" in interaction.response.send_message.await_args.args[0]

    interaction.user = mod1
    await close.callback(interaction)
    assert granted[player] is None
    assert channel.edit.await_args.kwargs["name"] == "closed-mod-chat-opponent"
    assert get_open_chat(REPORTED) is None
    assert "Chat closed" in interaction.followup.send.await_args.args[0]

    # A new press after closing starts a fresh chat
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="2", moderator=mod2)
    assert guild.create_text_channel.await_count == 2


@pytest.mark.asyncio
async def test_opening_a_chat_posts_the_players_record_in_the_mod_channel_only():
    create_moderation_tables()
    _report(reasons=["toxic"], details="called me names")
    _report(reasons=["toxic", "slow"], details="")
    _block(REPORTER, REPORTED, reason="no show twice")
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()

    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="2", moderator=mod1)

    summary = modch.send.await_args.kwargs["embed"]
    text = summary.title + summary.description + str([(f.name, f.value) for f in summary.fields])
    assert summary.title == "Player summary: Opponent"
    assert "2 report(s) and 1 block(s)" in summary.description
    assert "Reporter" in text and "called me names" in text and "no show twice" in text
    assert "<#777>" in summary.description
    # The chat itself never gets the summary or the reporter's name
    for call in channel.send.await_args_list:
        embed = call.kwargs.get("embed")
        assert embed is None or "Reporter" not in (embed.description or "")

    # Joining later doesn't post the summary again
    modch.send.reset_mock()
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="2", moderator=mod2)
    assert modch.send.await_args.kwargs.get("embed") is None


@pytest.mark.asyncio
async def test_chats_go_in_the_summit_category_by_default():
    create_moderation_tables()
    client, guild, channel, *_rest = _chat_world()
    mod1 = _rest[2]
    category = MagicMock()
    guild.get_channel.side_effect = lambda cid: category if cid == mod.DEFAULT_CHAT_CATEGORY_ID else None
    with patch.object(mod, "config", MagicMock(spec=["SUMMIT_GUILD_ID", "OWNER_ID"], SUMMIT_GUILD_ID=GUILD, OWNER_ID=OWNER)):
        await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod1)
    assert guild.create_text_channel.await_args.kwargs["category"] is category
    guild.create_category.assert_not_awaited()


def test_summary_field_stays_under_discords_limit():
    lines = [f"line {i} " + "x" * 90 for i in range(30)]
    joined = mod._join_lines(lines)
    assert len(joined) <= 1024 and joined.endswith("…")


# ── notes, transcripts, repeat flags, weekly summary ─────────────────

import datetime as _dt


class _History:
    def __init__(self, messages):
        self.messages = messages

    def __call__(self, **kw):
        async def gen():
            for m in self.messages:
                yield m
        return gen()


def _msg(author, content, minute):
    m = MagicMock(content=content, embeds=[], attachments=[])
    m.author = author
    m.created_at = _dt.datetime(2026, 11, 23, 14, minute, tzinfo=_dt.timezone.utc)
    return m


@pytest.mark.asyncio
async def test_closing_saves_the_transcript_on_the_record_and_posts_it():
    create_moderation_tables()
    client, guild, channel, granted, player, mod1, mod2, modch = _chat_world()
    await mod.open_or_join_group_chat(client, target_id=REPORTED, kind="report", ref="1", moderator=mod1)
    channel.history = _History([_msg(mod1, "Hi, can we talk about Saturday?", 1), _msg(player, "sorry about that", 2)])

    close = mod.PersistentCloseChatButton()
    interaction = MagicMock(channel=channel, client=client, user=mod1)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await close.callback(interaction)

    conn = sqlite3.connect("match_records.db")
    transcript, count = conn.execute(
        "SELECT transcript, message_count FROM moderation_group_chats WHERE channel_id = '777'"
    ).fetchone()
    conn.close()
    assert count == 2
    assert "[2026-11-23 09:01 AM] Bruce: Hi, can we talk about Saturday?" in transcript
    assert "Opponent: sorry about that" in transcript
    posted = modch.send.await_args
    assert "2 messages saved" in posted.args[0]
    assert posted.kwargs["file"].filename.endswith(".txt")
    # The summary shows the past chat
    record = mod.get_player_record(REPORTED)
    assert record["chats"][0]["message_count"] == 2


@pytest.mark.asyncio
async def test_note_button_saves_a_private_note_shown_in_the_summary():
    create_moderation_tables()
    button = mod.PersistentNoteButton(REPORTED)
    match = mod.PersistentNoteButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
    assert match and match["target"] == str(REPORTED)

    interaction = MagicMock()
    interaction.user = MagicMock(id=OWNER, global_name="Bruce")
    interaction.channel_id = MODCH
    interaction.client.get_user.return_value = MagicMock(global_name="Opponent")
    interaction.response.send_modal = AsyncMock()
    await button.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, mod.ModNoteModal)

    interaction.response.send_message = AsyncMock()
    interaction.client.get_channel.return_value.send = AsyncMock()
    with patch.object(type(modal.note), "value", property(lambda self: "Talked to them, they apologised")):
        await modal.on_submit(interaction)
    assert "Note saved" in interaction.response.send_message.await_args.args[0]
    record = mod.get_player_record(REPORTED)
    assert record["notes"][0]["note"] == "Talked to them, they apologised"
    embed = await mod.build_player_summary_embed(MagicMock(), REPORTED, "Opponent")
    assert any(f.name == "Mod notes" and "apologised" in f.value for f in embed.fields)


@pytest.mark.asyncio
async def test_three_complaints_in_a_week_flag_the_player_once():
    create_moderation_tables()
    bot, owner = _bot()
    cog = _cog(bot)
    _report()
    await cog.run_once()
    _report(reporter_id=444, reporter_name="Two")
    await cog.run_once()
    heads_ups = [c for c in bot.mod_channel.send.await_args_list
                 if c.kwargs["embed"].title.startswith("Heads-up")]
    assert heads_ups == []

    _block(REPORTER, REPORTED, reason="rude again")
    await cog.run_once()
    heads_ups = [c for c in bot.mod_channel.send.await_args_list
                 if c.kwargs["embed"].title.startswith("Heads-up")]
    assert len(heads_ups) == 1
    assert "3 reports/blocks in the last 7 days" in heads_ups[0].kwargs["embed"].title
    labels = [getattr(c, "item", c).label for c in heads_ups[0].kwargs["view"].children]
    assert "Group chat" in labels and "Note" in labels

    # A 4th one in the same week doesn't flag again
    _report(reporter_id=555, reporter_name="Three")
    await cog.run_once()
    heads_ups = [c for c in bot.mod_channel.send.await_args_list
                 if c.kwargs["embed"].title.startswith("Heads-up")]
    assert len(heads_ups) == 1


@pytest.mark.asyncio
async def test_weekly_summary_posts_on_monday_once():
    create_moderation_tables()
    _report()
    _block(REPORTER, REPORTED)
    bot, owner = _bot()
    cog = _cog(bot)
    assert not await cog.post_weekly_summary(today=_dt.date(2026, 11, 24))  # Tuesday
    assert await cog.post_weekly_summary(today=_dt.date(2026, 11, 23))  # Monday
    assert not await cog.post_weekly_summary(today=_dt.date(2026, 11, 23))
    embed = bot.mod_channel.send.await_args.kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert embed.title.startswith("Weekly mod summary")
    assert fields["Reports"] == "1" and fields["Blocks"] == "1"
    assert "2 report(s)/block(s)" in fields["Most reported this week"]


# ── website requests ─────────────────────────────────────────────────


def test_player_kind_buttons_round_trip_and_start_with_an_empty_reason():
    for item in (mod.PersistentModerationButton("ban", REPORTED, "player", "web"),
                 mod.PersistentGroupChatButton(REPORTED, "player", "web")):
        assert type(item).__discord_ui_compiled_template__.fullmatch(item.item.custom_id)
    assert mod.PersistentModerationButton("timeout", REPORTED, "player", "web")._player_reason() == ""


@pytest.mark.asyncio
async def test_website_summary_request_posts_summary_with_buttons_once():
    create_moderation_tables()
    _report()
    conn = sqlite3.connect("match_records.db")
    conn.execute("INSERT INTO moderation_summary_requests (target_id, requested_by_name) VALUES (?, 'Bruce')",
                 (str(REPORTED),))
    conn.commit()
    conn.close()
    bot, owner = _bot()
    cog = _cog(bot)
    await cog.run_once()
    calls = [c for c in bot.mod_channel.send.await_args_list if c.args and "Mod Tools page" in c.args[0]]
    assert len(calls) == 1
    assert calls[0].kwargs["embed"].title.startswith("Player summary")
    labels = [getattr(c, "item", c).label for c in calls[0].kwargs["view"].children]
    assert labels[:5] == ["Timeout", "Ban", "Pairing Block", "Group chat", "Note"]
    await cog.run_once()
    calls = [c for c in bot.mod_channel.send.await_args_list if c.args and "Mod Tools page" in c.args[0]]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_website_match_flips_use_correct_match_and_record_the_outcome():
    create_moderation_tables()
    conn = sqlite3.connect("match_records.db")
    conn.execute("INSERT INTO moderation_match_flips (match_id, target_id, requested_by_name) VALUES (9, ?, 'Bruce')",
                 (str(REPORTED),))
    conn.execute("INSERT INTO moderation_match_flips (match_id, target_id, requested_by_name) VALUES (4, ?, 'Bruce')",
                 (str(REPORTED),))
    conn.commit()
    conn.close()
    bot, owner = _bot()
    bot.get_cog.return_value.update_leaderboard = AsyncMock()
    cog = _cog(bot)
    calls = []

    def fake_correct(match_id):
        calls.append(match_id)
        if match_id == 9:
            raise ValueError("Match ID #9 is from an ended season and can't be changed.")
        return {"new_winner_name": "Reporter", "original_winner_name": "Opponent",
                "new_loser_name": "Opponent", "original_loser_name": "Reporter", "recalculated_count": 3}

    with patch("utils.database.correct_match_record", side_effect=fake_correct):
        assert await cog.run_match_flips() == 2
    assert calls == [4, 9]  # oldest match first
    conn = sqlite3.connect("match_records.db")
    rows = dict(conn.execute("SELECT match_id, status FROM moderation_match_flips").fetchall())
    conn.close()
    assert rows == {4: "done", 9: "error"}
    text = bot.mod_channel.send.await_args.args[0]
    assert "Winner is now Reporter" in text and "ended season" in text
    bot.get_cog.return_value.update_leaderboard.assert_awaited()
    assert await cog.run_match_flips() == 0


def test_mod_tools_button_opens_the_players_mod_page():
    view = moderation_view(REPORTED, "report", "1")
    link = view.children[-1]
    assert link.label == "Mod Tools"
    assert link.url == f"https://sorcererssummit.com/mod-tools/player/{REPORTED}"


@pytest.mark.asyncio
async def test_anyone_in_the_mod_channel_can_use_timeout_ban_and_pairing_block():
    create_moderation_tables()
    for action in ("timeout", "ban"):
        button = PersistentModerationButton(action, REPORTED, "report", "1")
        interaction = MagicMock()
        interaction.user.id = 999  # not an admin, not on the website list
        interaction.channel_id = MODCH
        interaction.client.get_guild.return_value.get_member.return_value = None
        interaction.client.get_user.return_value = MagicMock(global_name="Opponent")
        interaction.response.send_modal = AsyncMock()
        await button.callback(interaction)
        assert isinstance(interaction.response.send_modal.await_args.args[0], ModerationReasonModal)

    # Submitting the form from the mod channel works too
    modal = ModerationReasonModal(action="ban", target_id=REPORTED, target_name="Opponent",
                                  source_kind="report", source_ref="1")
    interaction = MagicMock()
    interaction.user = MagicMock(id=999, global_name="Helper")
    interaction.channel_id = MODCH
    interaction.client.get_guild.return_value.get_member.return_value = None
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    with patch.object(mod, "perform_moderation", AsyncMock(return_value=(True, "Banned."))) as do, \
         patch.object(type(modal.reason), "value", property(lambda self: "Harassment")):
        await modal.on_submit(interaction)
    do.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()


# ── thanking reporters after a ban ───────────────────────────────────


def _action(action, target=REPORTED):
    from repositories.moderation_repo import log_moderation_action
    log_moderation_action(target_id=target, target_name="Opponent", action=action, reason="x",
                          source_kind="report", source_ref="1", by_id=OWNER, by_name="Bruce", via="discord")


def _thanks_dms(bot):
    return [c for c in bot._dm.send.await_args_list if c.kwargs["embed"].title == "Thank you for your report"]


def _thanks_bot():
    bot, owner = _bot()
    reporter_dm = MagicMock()
    reporter_dm.send = AsyncMock(return_value=MagicMock())
    player = MagicMock(global_name="Opponent")
    bot.get_user.side_effect = lambda uid: owner if uid == OWNER else player if uid == REPORTED else reporter_dm
    bot._dm = reporter_dm
    return bot


@pytest.mark.asyncio
async def test_old_bans_dont_thank_anyone():
    create_moderation_tables()
    _report()
    _action("ban")
    bot = _thanks_bot()
    assert await _cog(bot).thank_reporters_for_new_bans() == 0
    assert _thanks_dms(bot) == []


@pytest.mark.asyncio
async def test_ban_thanks_each_reporter_once_and_never_says_what_happened():
    create_moderation_tables()
    _report()
    _report(reasons=["stalling"])  # same reporter twice
    _report(reporter_id=777777777777777777, reporter_name="Two")
    _block(888888888888888888, REPORTED)  # blockers aren't DMed
    bot = _thanks_bot()
    cog = _cog(bot)
    await cog.thank_reporters_for_new_bans()  # seeds; nothing banned yet
    _action("timeout")
    assert await cog.thank_reporters_for_new_bans() == 0  # timeouts don't count

    _action("ban")
    assert await cog.thank_reporters_for_new_bans() == 2
    dms = _thanks_dms(bot)
    assert len(dms) == 2
    text = dms[0].kwargs["embed"].description
    assert "Thank you for your recent player report" in text and "action has been taken" in text
    assert "Opponent" not in text and str(REPORTED) not in text
    assert "ban" not in text.lower() and "timeout" not in text.lower()
    assert "Thanked 2 of 2" in bot.mod_channel.send.await_args.args[0]

    # A pairing block later doesn't thank the same reports again
    _action("pairing_block")
    assert await cog.thank_reporters_for_new_bans() == 0
    # ...but a new report after that is thanked on the next ban
    _report(reporter_id=999999999999999999, reporter_name="Three")
    _action("ban")
    assert await cog.thank_reporters_for_new_bans() == 1


@pytest.mark.asyncio
async def test_bang_command_and_discord_bans_thank_reporters():
    create_moderation_tables()
    _report()
    bot = _thanks_bot()
    cog = _cog(bot)
    await cog.thank_reporters_for_new_bans()
    from repositories.pairing_bans_repo import create_pairing_bans_table
    create_pairing_bans_table()
    conn = sqlite3.connect("match_records.db")
    conn.execute("INSERT INTO pairing_bans (user_id, banned_by_id, reason, duration_label, banned_at) "
                 "VALUES (?, '1', 'x', '24 hours', '2026-11-23 19:00:00')", (str(REPORTED),))
    conn.commit()
    conn.close()
    assert await cog.thank_reporters_for_new_bans() == 1

    _report(reporter_id=777777777777777777, reporter_name="Two")
    await cog.on_member_ban(MagicMock(id=GUILD), MagicMock(id=REPORTED))
    assert len(_thanks_dms(bot)) == 2
