"""DM the owner when a player blocks or reports someone, with Timeout / Ban.

Blocks come from the Summit profile page or Play Sorcery Online; reports come
from the Report Player button on match messages or Play Sorcery Online. Both
land in match_records.db, so this cog polls for new rows and DMs each one
once (``moderation_alerts`` remembers what was sent).

Each DM has **Timeout** and **Ban** buttons for the blocked / reported
player. Pressing one never acts straight away: it opens a form (a duration
picker for timeouts, plus a reason) and only **Submit** does it. The reason
is DMed to the player and goes in the Discord audit log; it never names who
reported or blocked them. The buttons are DynamicItems so they still work
after a bot restart.

Timeout and Ban are Discord's own: timeout mutes them in the Summit server,
ban removes them from it. **Pairing Block** is the ``!ban`` pairing-service
block (24/48/72 hours or lifetime); its form is the confirm step, and its
reasoning is DMed to the player. Every action is logged to
``moderation_actions`` (shown on the website's admin panel) and the admin
audit log. Pairing blocks set from the website are followed up here too:
the player is pulled out of the LFG queue and DMed.

The same alert is also posted in the moderator channel
(``MODERATION_ALERT_CHANNEL_ID``). Every alert has a **Group chat** button:
the first press makes a private channel in a private "Mod Chats" category
with the blocked / reported player and whoever pressed it; anyone who presses
it later (on that alert or any other alert about the same player) is added to
the same chat. The player only ever sees a neutral intro, never who reported
or blocked them. A **Close chat** button in the chat removes the player and
renames the channel ``closed-...`` so moderators keep the history. When a
chat opens, the mod channel (never the chat) gets a summary of every report,
block and past action against the player.
"""

import datetime
import logging

import discord
from discord.ext import commands, tasks

import config
from cogs.lfg.player_report import REASON_LABELS
from repositories.audit_repo import log_admin_action
from repositories.moderation_repo import (
    KIND_BLOCK,
    KIND_REPORT,
    block_key,
    close_group_chat,
    get_group_chat_by_channel,
    get_history_counts,
    get_open_group_chat,
    get_pending_web_pairing_blocks,
    get_player_record,
    get_profile_name,
    get_report,
    get_unsent_blocks,
    get_unsent_reports,
    is_site_moderator,
    log_moderation_action,
    mark_alerted,
    mark_bot_done,
    save_group_chat,
)
from repositories.pairing_bans_repo import BAN_DURATIONS, get_pairing_ban

logger = logging.getLogger("discord_bot")

ADMIN_PAGE_URL = "https://sorcererssummit.com/admin/audit-log"
MOD_PREFIX = "mod:"

# (minutes, label). Discord caps a timeout at 28 days.
TIMEOUT_CHOICES = [
    (60, "1 hour"),
    (1440, "1 day"),
    (10080, "1 week"),
    (40320, "28 days"),
]
DEFAULT_TIMEOUT_MINUTES = 1440
TIMEOUT_LABELS = dict(TIMEOUT_CHOICES)

SOURCE_LABELS = {"sorcery-online": "Play Sorcery Online"}

# Bruce's moderator channel; config.MODERATION_ALERT_CHANNEL_ID overrides it
# (set it to 0 to turn the channel copy off).
DEFAULT_ALERT_CHANNEL_ID = 1574423902254530713
# Bruce's private category for group chats; config.MODERATION_CHAT_CATEGORY_ID overrides it.
DEFAULT_CHAT_CATEGORY_ID = 1574425023563825192
CHAT_CATEGORY_NAME = "Mod Chats"
CHAT_PREFIX = "modchat:"
CHAT_CLOSE_ID = "modchat-close"


def alert_recipient_ids() -> list[int]:
    """Who gets the DMs: MODERATION_ALERT_USER_IDS, else the owner."""
    ids = getattr(config, "MODERATION_ALERT_USER_IDS", None) or [getattr(config, "OWNER_ID", 0)]
    return [int(i) for i in ids if i]


def alert_channel_id() -> int:
    """The moderator channel that gets a copy of every alert (0 = none)."""
    value = getattr(config, "MODERATION_ALERT_CHANNEL_ID", DEFAULT_ALERT_CHANNEL_ID)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _guild_id() -> int:
    return int(getattr(config, "SUMMIT_GUILD_ID", 0) or getattr(config, "GUILD_ID", 0) or 0)


def is_discord_id(value) -> bool:
    text = str(value or "")
    return text.isdigit() and 15 <= len(text) <= 25


def can_moderate(client, user) -> bool:
    """The alert recipients, website moderators, and server admins / Bot Admin / Judge."""
    if user.id in alert_recipient_ids():
        return True
    try:
        if is_site_moderator(user.id):
            return True
    except Exception as e:
        logger.warning(f"Moderator list check failed: {e}")
    guild = client.get_guild(_guild_id()) if client else None
    member = guild.get_member(user.id) if guild else None
    if member is None:
        return False
    from cogs.pairing_bans import member_is_admin
    return member_is_admin(member)


def _display(user) -> str:
    return getattr(user, "global_name", None) or getattr(user, "display_name", None) or str(user.id)


def format_duration(minutes) -> str:
    return TIMEOUT_LABELS.get(int(minutes or 0), f"{minutes} minutes")


# ── doing the action ─────────────────────────────────────────────────


def player_dm_embed(action: str, *, reason: str, minutes: int | None = None, server: str | None = None):
    """The DM a player gets when they are timed out or banned.

    Only the reason the admin typed; never who reported or blocked them.
    """
    server = server or "the Sorcerers Summit Discord"
    if action == "timeout":
        until = discord.utils.utcnow() + datetime.timedelta(minutes=int(minutes or DEFAULT_TIMEOUT_MINUTES))
        embed = discord.Embed(
            title=f"You've been timed out in {server}",
            description="You can't chat, react or join voice in the server until it ends.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Length", value=format_duration(minutes), inline=True)
        unix = int(until.timestamp())
        embed.add_field(name="Ends", value=f"<t:{unix}:f> (<t:{unix}:R>)", inline=True)
    else:
        embed = discord.Embed(
            title=f"You've been banned from {server}",
            color=discord.Color.red(),
        )
    embed.add_field(name="Reason", value=(reason or "-")[:1024], inline=False)
    embed.set_footer(text="If you think this is a mistake, please contact a server admin.")
    return embed


def audit_log_reason(reason: str | None, source_kind: str | None, source_ref: str | None, by: str) -> str:
    """Reason shown in Discord's audit log: the admin's reason, the report number, who did it."""
    text = (reason or "Summit block/report alert").strip()
    tag = f"report #{source_ref}" if source_kind == KIND_REPORT and str(source_ref or "").isdigit() else None
    suffix = f" ({tag}, by {by})" if tag else f" (by {by})"
    return text[: 500 - len(suffix)] + suffix


async def _dm_player(client, target_id: int, embed):
    """DM the player. Returns the message, or None if their DMs are closed."""
    try:
        user = client.get_user(int(target_id)) or await client.fetch_user(int(target_id))
        return await user.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException, discord.NotFound) as e:
        logger.warning(f"Could not DM moderation notice to {target_id}: {e}")
        return None


async def perform_moderation(
    client,
    *,
    action: str,
    target_id: int,
    moderator,
    minutes: int | None = None,
    reason: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    target_name: str | None = None,
    notify_player: bool = True,
) -> tuple[bool, str]:
    """Time out or ban ``target_id`` in the Summit server. Returns (ok, message).

    With ``notify_player`` the player is DMed the action and ``reason``. A ban
    DM goes first (once banned they share no server with the bot, so a DM
    would fail) and is deleted again if Discord refuses the ban.
    """
    guild = client.get_guild(_guild_id())
    if guild is None:
        return False, "I can't find the Summit server right now. Try again in a minute."

    by = _display(moderator)
    audit_reason = audit_log_reason(reason, source_kind, source_ref, by)
    server = getattr(guild, "name", None)
    server = server if isinstance(server, str) and server else None
    dm = None
    try:
        if action == "timeout":
            minutes = int(minutes or DEFAULT_TIMEOUT_MINUTES)
            member = guild.get_member(int(target_id))
            if member is None:
                member = await guild.fetch_member(int(target_id))
            await member.timeout(datetime.timedelta(minutes=minutes), reason=audit_reason)
            target_name = target_name or _display(member)
            done = f"Timed out **{target_name}** for {format_duration(minutes)}."
            if notify_player:
                dm = await _dm_player(
                    client, target_id,
                    player_dm_embed("timeout", reason=reason, minutes=minutes, server=server),
                )
        elif action == "ban":
            if notify_player:
                dm = await _dm_player(client, target_id, player_dm_embed("ban", reason=reason, server=server))
            try:
                await guild.ban(
                    discord.Object(id=int(target_id)),
                    reason=audit_reason,
                    delete_message_seconds=0,
                )
            except discord.HTTPException:
                if dm is not None:
                    try:
                        await dm.delete()
                    except discord.HTTPException:
                        pass
                raise
            done = f"Banned **{target_name or target_id}** from the server."
        else:
            return False, "Unknown action."
    except discord.NotFound:
        return False, "They are not in the Summit server any more, so there is nobody to time out."
    except discord.Forbidden:
        return False, (
            "Discord refused. The bot needs Moderate Members (timeout) or Ban Members, "
            "and its role must be above theirs. Server admins can't be timed out."
        )
    except discord.HTTPException as e:
        return False, f"Discord returned an error: {e}"

    if notify_player:
        done += " They were DMed the reason." if dm is not None else " I couldn't DM them (their DMs are closed)."

    try:
        log_moderation_action(
            target_id=target_id,
            target_name=target_name,
            action=action,
            duration_minutes=minutes if action == "timeout" else None,
            reason=reason,
            source_kind=source_kind,
            source_ref=source_ref,
            by_id=moderator.id,
            by_name=by,
            via="discord",
        )
        log_admin_action(
            moderator.id, by, f"discord_{action}",
            target_id=target_id, target_name=target_name,
            new_state={"minutes": minutes} if action == "timeout" else None,
            details=reason,
        )
    except Exception as e:
        logger.error(f"Moderation action done but not logged: {e}", exc_info=True)

    logger.info("Moderation: %s %s %s (%s)", by, action, target_id, minutes)
    return True, done


# ── reason form (the confirm step) ───────────────────────────────────


class ModerationReasonModal(discord.ui.Modal):
    """Timeout / Ban form: duration (timeouts) and a reason, then Submit.

    Discord supplies Cancel and Submit, so Submit is the confirm step. The
    reason is DMed to the player and goes in the audit log.
    """

    def __init__(self, *, action, target_id, target_name, source_kind, source_ref, default_reason=""):
        verb = "Time out" if action == "timeout" else "Ban"
        super().__init__(title=f"{verb} {target_name}"[:45], timeout=600)
        self.action = action
        self.target_id = int(target_id)
        self.target_name = target_name
        self.source_kind = source_kind
        self.source_ref = source_ref

        self.duration = None
        if action == "timeout":
            self.duration = discord.ui.Select(
                placeholder="How long?",
                min_values=1,
                max_values=1,
                required=True,
                options=[
                    discord.SelectOption(label=label, value=str(m), default=m == DEFAULT_TIMEOUT_MINUTES)
                    for m, label in TIMEOUT_CHOICES
                ],
            )
            self.add_item(discord.ui.Label(
                text="How long",
                description="They can't chat, react or join voice until it ends.",
                component=self.duration,
            ))

        self.reason = discord.ui.TextInput(
            label="Reason (sent to the player)",
            style=discord.TextStyle.paragraph,
            placeholder=(
                "Why are they being timed out? They get this in a DM."
                if action == "timeout"
                else "Why are they being banned? They get this in a DM before the ban."
            ),
            default=(default_reason or "")[:1000] or None,
            required=True,
            min_length=3,
            max_length=1000,
        )
        self.add_item(self.reason)

    @property
    def minutes(self) -> int:
        if self.duration is not None and self.duration.values:
            return int(self.duration.values[0])
        return DEFAULT_TIMEOUT_MINUTES

    async def on_submit(self, interaction: discord.Interaction):
        if not can_moderate(interaction.client, interaction.user):
            await interaction.response.send_message("Only admins and moderators can do this.", ephemeral=True)
            return
        await interaction.response.defer()
        ok, message = await perform_moderation(
            interaction.client,
            action=self.action,
            target_id=self.target_id,
            moderator=interaction.user,
            minutes=self.minutes,
            reason=self.reason.value.strip(),
            source_kind=self.source_kind,
            source_ref=self.source_ref,
            target_name=self.target_name,
        )
        text = message if ok else f"Not done: {message}"
        if ok:
            text += f"\nReason: {self.reason.value.strip()[:1500]}"
        await interaction.followup.send(text)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"ModerationReasonModal error: {error}", exc_info=True)
        msg = f"Something went wrong: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


# ── pairing block form ───────────────────────────────────────────────


def _pairing_modal_class():
    from cogs.pairing_bans import PairingBanModal
    return PairingBanModal


class AlertPairingBlockModal:
    """Builds the ``!ban`` form for an alert, prefilled, and logs the result.

    The form (duration + reasoning, then Submit) is the confirm step.
    """

    @staticmethod
    def build(bot, target, admin, *, default_reason, source_kind, source_ref):
        base = _pairing_modal_class()

        class _Modal(base):
            async def on_submit(self, interaction: discord.Interaction):
                await super().on_submit(interaction)
                duration_key = self.duration_select.values[0] if self.duration_select.values else None
                if duration_key not in BAN_DURATIONS:
                    return
                try:
                    log_moderation_action(
                        target_id=target.id,
                        target_name=_display(target),
                        action="pairing_block",
                        duration_label=BAN_DURATIONS[duration_key][0],
                        reason=self.reason.value.strip(),
                        source_kind=source_kind,
                        source_ref=source_ref,
                        by_id=admin.id,
                        by_name=_display(admin),
                        via="discord",
                    )
                except Exception as e:
                    logger.error(f"Pairing block done but not logged: {e}", exc_info=True)

        modal = _Modal(bot, target, admin)
        modal.reason.default = (default_reason or "")[:1000]
        return modal


# ── buttons on the alert ─────────────────────────────────────────────


BUTTON_LABELS = {"timeout": "Timeout", "ban": "Ban", "pblock": "Pairing Block"}


class PersistentModerationButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"mod:(?P<action>timeout|ban|pblock):(?P<target>\d+):(?P<kind>block|report):(?P<ref>[\w-]*)",
):
    """Timeout / Ban button on a block or report DM.

    ``ref`` is the report id, or the blocker's id for a block.
    """

    def __init__(self, action: str, target_id: int, kind: str, ref: str = ""):
        self.action = action
        self.target_id = int(target_id)
        self.kind = kind
        self.ref = str(ref or "")
        super().__init__(
            discord.ui.Button(
                label=BUTTON_LABELS[action],
                style=discord.ButtonStyle.danger if action == "ban" else discord.ButtonStyle.secondary,
                custom_id=f"{MOD_PREFIX}{action}:{self.target_id}:{kind}:{self.ref}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], int(match["target"]), match["kind"], match["ref"])

    async def callback(self, interaction: discord.Interaction):
        if not can_moderate(interaction.client, interaction.user):
            await interaction.response.send_message(
                "Only admins and moderators can use these buttons.", ephemeral=True
            )
            return
        if self.action == "pblock":
            if interaction.client.get_cog("PairingBanCog") is None:
                await interaction.response.send_message("Pairing bans are not available.", ephemeral=True)
                return
            try:
                target = interaction.client.get_user(self.target_id) or await interaction.client.fetch_user(
                    self.target_id
                )
            except discord.HTTPException:
                await interaction.response.send_message("I can't find that Discord account.", ephemeral=True)
                return
            modal = AlertPairingBlockModal.build(
                interaction.client, target, interaction.user,
                default_reason=self._player_reason(),
                source_kind=self.kind, source_ref=self.ref,
            )
            await interaction.response.send_modal(modal)
            return
        target_name = await resolve_name(interaction.client, self.target_id)
        modal = ModerationReasonModal(
            action=self.action,
            target_id=self.target_id,
            target_name=target_name,
            source_kind=self.kind,
            source_ref=self.ref,
            default_reason=self._player_reason(),
        )
        await interaction.response.send_modal(modal)

    def _player_reason(self) -> str:
        """Starting text for the reason box, which the player sees.

        Never names who reported or blocked them.
        """
        if self.kind == KIND_REPORT and self.ref.isdigit():
            report = get_report(int(self.ref))
            if report and report["reasons"]:
                labels = [REASON_LABELS.get(r, r).replace("Opponent ", "") for r in report["reasons"]]
                return "Reported after a match: " + "; ".join(labels)
            return "Reported after a match"
        return "Blocked by other players"


# ── group chat ───────────────────────────────────────────────────────


CHAT_MEMBER_PERMS = dict(
    view_channel=True, send_messages=True, read_message_history=True,
    attach_files=True, embed_links=True, add_reactions=True,
)


def can_open_group_chat(client, interaction) -> bool:
    """Anyone pressing it in the moderator channel (only mods can see it),
    plus everyone who can use the other alert buttons."""
    channel_id = alert_channel_id()
    if channel_id and getattr(interaction, "channel_id", None) == channel_id:
        return True
    return can_moderate(client, interaction.user)


def chat_channel_name(player_name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in str(player_name).lower())
    slug = "-".join(part for part in slug.split("-") if part)[:80] or "player"
    return f"mod-chat-{slug}"


def chat_intro_embed(player_name: str, kind: str) -> discord.Embed:
    """What the player sees when the chat opens. Never names who reported or blocked them."""
    about = (
        "a player report from one of your recent matches"
        if kind == KIND_REPORT
        else "some of your recent games"
    )
    embed = discord.Embed(
        title="A Summit moderator would like to talk with you",
        description=(
            f"Hi {player_name}, a moderator from the Sorcerers Summit would like to chat about {about}.\n\n"
            "This channel is private: only you and the Summit moderators in it can see it. "
            "Please reply here when you get a chance."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Moderators: press Close chat when you're done.")
    return embed


async def _chat_category(guild):
    """The private category for group chats: config id, else "Mod Chats", made if missing."""
    cat_id = int(getattr(config, "MODERATION_CHAT_CATEGORY_ID", DEFAULT_CHAT_CATEGORY_ID) or 0)
    if cat_id:
        category = guild.get_channel(cat_id)
        if category is not None:
            return category
    for category in getattr(guild, "categories", []) or []:
        if str(category.name).lower() == CHAT_CATEGORY_NAME.lower():
            return category
    return await guild.create_category(
        CHAT_CATEGORY_NAME,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
        },
        reason="Private category for moderator group chats",
    )


async def _member(guild, user_id):
    member = guild.get_member(int(user_id))
    if member is None:
        member = await guild.fetch_member(int(user_id))
    return member


def _short_date(value) -> str:
    return str(value or "")[:10] or "?"


def _clip(text, n=120) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


async def build_player_summary_embed(client, target_id, player_name: str, chat_channel) -> discord.Embed:
    """Everything on record about the player, for the mod channel only.

    It names reporters and blockers, so it is never posted in the chat itself.
    """
    record = get_player_record(target_id)
    embed = discord.Embed(
        title=f"Player summary: {player_name}",
        description=(
            f"Group chat: {chat_channel.mention}\n"
            f"{record['report_total']} report(s) and {record['block_total']} block(s) against them in total."
        ),
        color=discord.Color.orange(),
    )
    reasons = {}
    for report in record["reports"]:
        for r in report["reasons"]:
            label = REASON_LABELS.get(r, r)
            reasons[label] = reasons.get(label, 0) + 1
    if reasons:
        common = sorted(reasons.items(), key=lambda kv: -kv[1])
        embed.add_field(
            name="Most reported for",
            value="\n".join(f"- {label} ({n})" for label, n in common[:6])[:1024],
            inline=False,
        )
    if record["reports"]:
        lines = []
        for report in record["reports"]:
            who = report.get("reporter_name") or report["reporter_id"]
            what = ", ".join(REASON_LABELS.get(r, r) for r in report["reasons"]) or "-"
            line = f"**#{report['id']}** {_short_date(report['created_at'])} by {who}: {what}"
            if report.get("details"):
                line += f" · \"{_clip(report['details'], 80)}\""
            lines.append(line)
        more = record["report_total"] - len(record["reports"])
        if more > 0:
            lines.append(f"…and {more} older")
        embed.add_field(name="Reports (newest first)", value=_join_lines(lines), inline=False)
    if record["blocks"]:
        lines = []
        for block in record["blocks"]:
            who = await resolve_name(client, block["user_id"])
            lines.append(f"{_short_date(block['created_at'])} by {who}: {_clip(block.get('reason') or '-', 80)}")
        more = record["block_total"] - len(record["blocks"])
        if more > 0:
            lines.append(f"…and {more} older")
        embed.add_field(name="Blocks (newest first)", value=_join_lines(lines), inline=False)
    if record["actions"]:
        lines = []
        for action in record["actions"]:
            name = {"timeout": "Timeout", "ban": "Ban", "pairing_block": "Pairing block"}.get(
                action["action"], str(action["action"]).replace("_", " ").capitalize()
            )
            length = action.get("duration_label") or (
                format_duration(action["duration_minutes"]) if action.get("duration_minutes") else ""
            )
            bits = f"{_short_date(action['created_at'])} {name}"
            if length:
                bits += f" ({length})"
            if action.get("by_name"):
                bits += f" by {action['by_name']}"
            if action.get("reason"):
                bits += f": {_clip(action['reason'], 60)}"
            lines.append(bits)
        embed.add_field(name="Past actions", value=_join_lines(lines), inline=False)
    if not (record["reports"] or record["blocks"] or record["actions"]):
        embed.add_field(name="Record", value="Nothing on record yet.", inline=False)
    embed.set_footer(text="Mod channel only. The player can't see this.")
    return embed


def _join_lines(lines) -> str:
    """Join lines into one embed field (1024 max), dropping the tail if needed."""
    out = []
    for line in lines:
        if len("\n".join(out + [line])) > 1000:
            out.append("…")
            break
        out.append(line)
    return "\n".join(out) or "-"


async def _post_to_mod_channel(client, text: str, embed=None):
    channel_id = alert_channel_id()
    if not channel_id:
        return
    try:
        channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
        await channel.send(text, embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as e:
        logger.warning(f"Moderation: could not post to mod channel: {e}")


async def open_or_join_group_chat(client, *, target_id, kind, ref, moderator) -> tuple[bool, str]:
    """Make the player's private chat (or reuse the open one) and add ``moderator``.

    Returns (ok, message for the moderator).
    """
    guild = client.get_guild(_guild_id())
    if guild is None:
        return False, "I can't find the Summit server right now. Try again in a minute."
    if int(target_id) == int(moderator.id):
        return False, "You can't open a group chat with yourself."
    try:
        player = await _member(guild, target_id)
    except discord.NotFound:
        return False, "They're not in the Summit server any more, so I can't add them to a chat."
    except discord.HTTPException as e:
        return False, f"Discord returned an error: {e}"
    try:
        mod_member = await _member(guild, moderator.id)
    except discord.HTTPException:
        return False, "You need to be in the Summit server to join the chat."

    player_name = await resolve_name(client, target_id, _display(player))
    by = _display(moderator)
    tag = f"report #{ref}" if kind == KIND_REPORT else "block"

    try:
        existing = get_open_group_chat(target_id)
        channel = guild.get_channel(int(existing["channel_id"])) if existing else None
        if existing and channel is None:
            # Someone deleted the channel by hand; start a fresh one.
            close_group_chat(existing["channel_id"], "channel deleted")
            existing = None

        if channel is not None:
            overwrite = channel.overwrites_for(mod_member)
            if overwrite.view_channel:
                return True, f"You're already in the chat with {player_name}: {channel.mention}"
            await channel.set_permissions(
                mod_member, overwrite=discord.PermissionOverwrite(**CHAT_MEMBER_PERMS),
                reason=f"Moderator joined group chat ({tag})",
            )
            await channel.send(f"{mod_member.mention} joined the chat.")
            await _post_to_mod_channel(
                client, f"**{by}** joined the group chat with **{player_name}** ({tag}): {channel.mention}"
            )
            return True, f"Added you to the chat with {player_name}: {channel.mention}"

        category = await _chat_category(guild)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(manage_channels=True, **CHAT_MEMBER_PERMS),
            player: discord.PermissionOverwrite(**CHAT_MEMBER_PERMS),
            mod_member: discord.PermissionOverwrite(**CHAT_MEMBER_PERMS),
        }
        channel = await guild.create_text_channel(
            chat_channel_name(player_name),
            category=category,
            overwrites=overwrites,
            reason=f"Moderator group chat with {player_name} ({tag}, opened by {by})",
        )
        save_group_chat(
            target_id=target_id, channel_id=channel.id, source_kind=kind, source_ref=ref,
            opened_by_id=moderator.id, opened_by_name=by,
        )
        view = discord.ui.View(timeout=None)
        view.add_item(PersistentCloseChatButton())
        await channel.send(
            content=f"{player.mention} {mod_member.mention}",
            embed=chat_intro_embed(player_name, kind),
            view=view,
        )
    except discord.Forbidden:
        return False, (
            "Discord refused. The bot needs the Manage Channels and Manage Roles permissions "
            "to make the private chat."
        )
    except discord.HTTPException as e:
        return False, f"Discord returned an error: {e}"

    try:
        log_admin_action(
            moderator.id, by, "moderation_group_chat",
            target_id=target_id, target_name=player_name, details=f"{tag}, channel {channel.id}",
        )
    except Exception as e:
        logger.error(f"Group chat opened but not logged: {e}", exc_info=True)
    try:
        summary = await build_player_summary_embed(client, target_id, player_name, channel)
    except Exception as e:
        logger.error(f"Group chat summary failed: {e}", exc_info=True)
        summary = None
    await _post_to_mod_channel(
        client, f"**{by}** opened a group chat with **{player_name}** ({tag}): {channel.mention}", embed=summary
    )
    return True, f"Opened a private chat with {player_name}: {channel.mention}"


class PersistentGroupChatButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"modchat:(?P<target>\d+):(?P<kind>block|report):(?P<ref>[\w-]*)",
):
    """Group chat button on a block / report alert."""

    def __init__(self, target_id: int, kind: str, ref: str = ""):
        self.target_id = int(target_id)
        self.kind = kind
        self.ref = str(ref or "")
        super().__init__(
            discord.ui.Button(
                label="Group chat",
                style=discord.ButtonStyle.primary,
                custom_id=f"{CHAT_PREFIX}{self.target_id}:{kind}:{self.ref}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["target"]), match["kind"], match["ref"])

    async def callback(self, interaction: discord.Interaction):
        if not can_open_group_chat(interaction.client, interaction):
            await interaction.response.send_message("Only moderators can use this button.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, message = await open_or_join_group_chat(
            interaction.client, target_id=self.target_id, kind=self.kind, ref=self.ref,
            moderator=interaction.user,
        )
        await interaction.followup.send(message if ok else f"Not done: {message}", ephemeral=True)


class PersistentCloseChatButton(discord.ui.DynamicItem[discord.ui.Button], template=r"modchat-close"):
    """Close chat button inside a group chat. Any moderator in the chat can press it."""

    def __init__(self):
        super().__init__(
            discord.ui.Button(label="Close chat", style=discord.ButtonStyle.secondary, custom_id=CHAT_CLOSE_ID)
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        chat = get_group_chat_by_channel(getattr(channel, "id", 0))
        if chat is None or chat.get("closed_at"):
            await interaction.response.send_message("This chat is already closed.", ephemeral=True)
            return
        if str(interaction.user.id) == str(chat["target_id"]):
            await interaction.response.send_message("Only a moderator can close this chat.", ephemeral=True)
            return
        await interaction.response.defer()
        by = _display(interaction.user)
        try:
            guild = channel.guild
            player = guild.get_member(int(chat["target_id"])) or discord.Object(id=int(chat["target_id"]))
            await channel.set_permissions(player, overwrite=None, reason=f"Group chat closed by {by}")
            name = str(channel.name)
            if not name.startswith("closed-"):
                await channel.edit(name=f"closed-{name}"[:100], reason=f"Group chat closed by {by}")
        except discord.HTTPException as e:
            await interaction.followup.send(f"Not done: Discord returned an error: {e}", ephemeral=True)
            return
        close_group_chat(channel.id, by)
        await interaction.followup.send(
            f"Chat closed by **{by}**. The player can't see this channel any more; "
            "moderators keep the history here. Delete the channel when you no longer need it."
        )
        await _post_to_mod_channel(interaction.client, f"**{by}** closed {channel.mention}.")


def moderation_view(target_id, kind: str, ref) -> discord.ui.View:
    """Buttons for one alert. A non-Discord account gets only the admin link."""
    view = discord.ui.View(timeout=None)
    if is_discord_id(target_id):
        view.add_item(PersistentModerationButton("timeout", int(target_id), kind, str(ref or "")))
        view.add_item(PersistentModerationButton("ban", int(target_id), kind, str(ref or "")))
        view.add_item(PersistentModerationButton("pblock", int(target_id), kind, str(ref or "")))
        view.add_item(PersistentGroupChatButton(int(target_id), kind, str(ref or "")))
    view.add_item(discord.ui.Button(label="Admin panel", style=discord.ButtonStyle.link, url=ADMIN_PAGE_URL))
    return view


# ── building the DM ──────────────────────────────────────────────────


async def resolve_name(client, user_id, fallback=None) -> str:
    name = get_profile_name(user_id)
    if name:
        return name
    if is_discord_id(user_id) and client is not None:
        try:
            user = client.get_user(int(user_id)) or await client.fetch_user(int(user_id))
            return _display(user)
        except Exception:
            pass
    return fallback or str(user_id)


def _who(name, user_id) -> str:
    if is_discord_id(user_id):
        return f"{name} (<@{user_id}>)\n`{user_id}`"
    return f"{name}\n`{user_id}` (no Discord account)"


def _history_line(target_id) -> str:
    counts = get_history_counts(target_id)
    return f"{counts['reports']} report(s) and {counts['blocks']} block(s) against them in total"


async def build_report_embed(client, report: dict) -> discord.Embed:
    reported = await resolve_name(client, report["reported_id"], report.get("reported_name"))
    reporter = await resolve_name(client, report["reporter_id"], report.get("reporter_name"))
    embed = discord.Embed(
        title=f"Player report #{report['id']}",
        color=discord.Color.orange(),
    )
    embed.add_field(name="Reported player", value=_who(reported, report["reported_id"]), inline=True)
    embed.add_field(name="Reported by", value=_who(reporter, report["reporter_id"]), inline=True)
    reasons = [f"- {REASON_LABELS.get(r, r)}" for r in report.get("reasons") or []]
    embed.add_field(name="What happened", value="\n".join(reasons) or "-", inline=False)
    if report.get("details"):
        embed.add_field(name="Feedback", value=report["details"][:1024], inline=False)
    match_bits = []
    if report.get("match_type"):
        match_bits.append(f"{str(report['match_type']).capitalize()} match")
    if report.get("pairing_id"):
        match_bits.append(f"pairing {report['pairing_id']}")
    match_bits.append(f"via {SOURCE_LABELS.get(report.get('source'), 'Discord')}")
    embed.add_field(name="Match", value=", ".join(match_bits), inline=False)
    embed.add_field(name="History", value=_history_line(report["reported_id"]), inline=False)
    embed.set_footer(text=f"Filed {report.get('created_at') or ''} UTC")
    return embed


async def build_block_embed(client, block: dict) -> discord.Embed:
    blocked = await resolve_name(client, block["blocked_user_id"])
    blocker = await resolve_name(client, block["user_id"])
    embed = discord.Embed(title="Player blocked", color=discord.Color.dark_red())
    embed.add_field(name="Blocked player", value=_who(blocked, block["blocked_user_id"]), inline=True)
    embed.add_field(name="Blocked by", value=_who(blocker, block["user_id"]), inline=True)
    embed.add_field(name="Reason", value=(block.get("reason") or "-")[:1024], inline=False)
    embed.add_field(name="History", value=_history_line(block["blocked_user_id"]), inline=False)
    embed.set_footer(text=f"Blocked {block.get('created_at') or ''} UTC")
    return embed


class ModerationAlertsCog(commands.Cog):
    """Polls for new blocks and reports and DMs them to the owner."""

    def __init__(self, bot):
        self.bot = bot
        self.send_alerts.start()
        logger.info("ModerationAlertsCog initialized")

    def cog_unload(self):
        self.send_alerts.cancel()

    async def _recipients(self):
        users = []
        for user_id in alert_recipient_ids():
            try:
                users.append(self.bot.get_user(user_id) or await self.bot.fetch_user(user_id))
            except Exception as e:
                logger.warning(f"Moderation alerts: can't find recipient {user_id}: {e}")
        return users

    async def _mod_channel(self):
        channel_id = alert_channel_id()
        if not channel_id:
            return None
        try:
            return self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        except Exception as e:
            logger.warning(f"Moderation alerts: can't find mod channel {channel_id}: {e}")
            return None

    async def _deliver(self, recipients, embed, view, channel=None) -> bool:
        sent = False
        if channel is not None:
            try:
                await channel.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
                sent = True
            except Exception as e:
                logger.warning(f"Moderation alerts: post to mod channel failed: {e}")
        for user in recipients:
            try:
                await user.send(embed=embed, view=view)
                sent = True
            except discord.Forbidden:
                logger.warning(f"Moderation alerts: DMs closed for {user.id}")
            except Exception as e:
                logger.warning(f"Moderation alerts: DM to {user.id} failed: {e}")
        return sent

    async def follow_up_web_pairing_blocks(self) -> int:
        """Pull website-blocked players out of the queue and DM them."""
        pending = get_pending_web_pairing_blocks()
        if not pending:
            return 0
        cog = self.bot.get_cog("PairingBanCog")
        if cog is None:
            return 0
        from cogs.pairing_bans import _ban_dm_embed, _try_dm

        for row in pending:
            try:
                user_id = int(row["target_id"])
                await cog._remove_from_queue(user_id)
                ban = get_pairing_ban(user_id)
                if ban:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    await _try_dm(user, _ban_dm_embed(ban))
            except Exception as e:
                logger.warning(f"Web pairing block follow-up {row['id']} failed: {e}")
            mark_bot_done(row["id"])
        return len(pending)

    async def run_once(self) -> int:
        """Send every unsent block and report. Returns how many were sent."""
        await self.follow_up_web_pairing_blocks()
        reports = get_unsent_reports()
        blocks = get_unsent_blocks()
        if not reports and not blocks:
            return 0
        recipients = await self._recipients()
        channel = await self._mod_channel()
        if not recipients and channel is None:
            return 0

        count = 0
        for report in reports:
            embed = await build_report_embed(self.bot, report)
            view = moderation_view(report["reported_id"], KIND_REPORT, report["id"])
            # Mark as sent even if every DM failed, so one closed DM box
            # doesn't make the bot retry the same alert forever.
            await self._deliver(recipients, embed, view, channel)
            mark_alerted(KIND_REPORT, str(report["id"]))
            count += 1
        for block in blocks:
            embed = await build_block_embed(self.bot, block)
            view = moderation_view(block["blocked_user_id"], KIND_BLOCK, block["user_id"])
            await self._deliver(recipients, embed, view, channel)
            mark_alerted(KIND_BLOCK, block_key(block))
            count += 1
        return count

    @tasks.loop(seconds=30)
    async def send_alerts(self):
        try:
            await self.run_once()
        except Exception as e:
            logger.error(f"Moderation alerts loop failed: {e}", exc_info=True)

    @send_alerts.before_loop
    async def before_send_alerts(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ModerationAlertsCog(bot))
