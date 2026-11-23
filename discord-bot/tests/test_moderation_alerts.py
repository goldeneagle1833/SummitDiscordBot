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
    assert labels == ["Timeout", "Ban", "Pairing Block", "Group chat", "Admin panel"]
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
    assert [getattr(c, "item", c).label for c in view.children] == ["Admin panel"]


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
    assert mod.can_open_group_chat(interaction.client, interaction)
    interaction.channel_id = 123
    assert not mod.can_open_group_chat(interaction.client, interaction)

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
