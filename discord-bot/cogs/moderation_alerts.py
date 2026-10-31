"""DM the owner when a player blocks or reports someone, with Timeout / Ban.

Blocks come from the Summit profile page or Play Sorcery Online; reports come
from the Report Player button on match messages or Play Sorcery Online. Both
land in match_records.db, so this cog polls for new rows and DMs each one
once (``moderation_alerts`` remembers what was sent).

Each DM has **Timeout** and **Ban** buttons for the blocked / reported
player. Pressing one never acts straight away: it posts a confirm prompt
(with a duration picker for timeouts) and only **Confirm** does it. The
buttons are DynamicItems so they still work after a bot restart.

Timeout and Ban are Discord's own: timeout mutes them in the Summit server,
ban removes them from it. **Pairing Block** is the ``!ban`` pairing-service
block (24/48/72 hours or lifetime); its form is the confirm step, and its
reasoning is DMed to the player. Every action is logged to
``moderation_actions`` (shown on the website's admin panel) and the admin
audit log. Pairing blocks set from the website are followed up here too:
the player is pulled out of the LFG queue and DMed.
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
    get_history_counts,
    get_pending_web_pairing_blocks,
    get_profile_name,
    get_report,
    get_unsent_blocks,
    get_unsent_reports,
    log_moderation_action,
    mark_alerted,
    mark_bot_done,
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


def alert_recipient_ids() -> list[int]:
    """Who gets the DMs: MODERATION_ALERT_USER_IDS, else the owner."""
    ids = getattr(config, "MODERATION_ALERT_USER_IDS", None) or [getattr(config, "OWNER_ID", 0)]
    return [int(i) for i in ids if i]


def _guild_id() -> int:
    return int(getattr(config, "SUMMIT_GUILD_ID", 0) or getattr(config, "GUILD_ID", 0) or 0)


def is_discord_id(value) -> bool:
    text = str(value or "")
    return text.isdigit() and 15 <= len(text) <= 25


def can_moderate(client, user) -> bool:
    """The alert recipients, plus server admins / Bot Admin / Judge."""
    if user.id in alert_recipient_ids():
        return True
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
) -> tuple[bool, str]:
    """Time out or ban ``target_id`` in the Summit server. Returns (ok, message)."""
    guild = client.get_guild(_guild_id())
    if guild is None:
        return False, "I can't find the Summit server right now. Try again in a minute."

    audit_reason = (reason or "Summit block/report alert")[:500]
    by = _display(moderator)
    try:
        if action == "timeout":
            minutes = int(minutes or DEFAULT_TIMEOUT_MINUTES)
            member = guild.get_member(int(target_id))
            if member is None:
                member = await guild.fetch_member(int(target_id))
            await member.timeout(datetime.timedelta(minutes=minutes), reason=f"{audit_reason} (by {by})")
            target_name = target_name or _display(member)
            done = f"Timed out **{target_name}** for {format_duration(minutes)}."
        elif action == "ban":
            await guild.ban(
                discord.Object(id=int(target_id)),
                reason=f"{audit_reason} (by {by})",
                delete_message_seconds=0,
            )
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


# ── confirm prompt ───────────────────────────────────────────────────


class ModerationConfirmView(discord.ui.View):
    """Second step: pick a duration (timeouts) and press Confirm."""

    def __init__(self, *, action, target_id, target_name, source_kind, source_ref, reason):
        super().__init__(timeout=600)
        self.action = action
        self.target_id = int(target_id)
        self.target_name = target_name
        self.source_kind = source_kind
        self.source_ref = source_ref
        self.reason = reason
        self.minutes = DEFAULT_TIMEOUT_MINUTES

        if action == "timeout":
            self.duration = discord.ui.Select(
                placeholder="How long?",
                options=[
                    discord.SelectOption(label=label, value=str(m), default=m == DEFAULT_TIMEOUT_MINUTES)
                    for m, label in TIMEOUT_CHOICES
                ],
                row=0,
            )
            self.duration.callback = self._pick_duration
            self.add_item(self.duration)

        confirm = discord.ui.Button(
            label="Confirm timeout" if action == "timeout" else "Confirm ban",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        confirm.callback = self._confirm
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
        cancel.callback = self._cancel
        self.add_item(confirm)
        self.add_item(cancel)

    def prompt(self) -> str:
        who = f"**{self.target_name}** (<@{self.target_id}>)"
        if self.action == "timeout":
            return (
                f"Time out {who} in the Summit Discord? Pick how long, then press Confirm.\n"
                "They can't chat, react or join voice until it ends."
            )
        return f"Ban {who} from the Summit Discord? This removes them from the server."

    async def _pick_duration(self, interaction: discord.Interaction):
        self.minutes = int(self.duration.values[0])
        for option in self.duration.options:
            option.default = option.value == self.duration.values[0]
        await interaction.response.edit_message(view=self)

    async def _confirm(self, interaction: discord.Interaction):
        if not can_moderate(interaction.client, interaction.user):
            await interaction.response.send_message("Only admins can do this.", ephemeral=True)
            return
        await interaction.response.defer()
        ok, message = await perform_moderation(
            interaction.client,
            action=self.action,
            target_id=self.target_id,
            moderator=interaction.user,
            minutes=self.minutes,
            reason=self.reason,
            source_kind=self.source_kind,
            source_ref=self.source_ref,
            target_name=self.target_name,
        )
        self.stop()
        await interaction.edit_original_response(
            content=message if ok else f"Not done: {message}", view=None
        )

    async def _cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(content="Cancelled. Nothing was changed.", view=None)


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
            await interaction.response.send_message("Only admins can use these buttons.", ephemeral=True)
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
        view = ModerationConfirmView(
            action=self.action,
            target_id=self.target_id,
            target_name=target_name,
            source_kind=self.kind,
            source_ref=self.ref,
            reason=self._reason(),
        )
        await interaction.response.send_message(view.prompt(), view=view)

    def _reason(self) -> str:
        if self.kind == KIND_REPORT and self.ref.isdigit():
            report = get_report(int(self.ref))
            if report:
                labels = [REASON_LABELS.get(r, r) for r in report["reasons"]]
                text = "; ".join(labels) or (report.get("details") or "")
                return f"Player report #{self.ref}: {text}"[:500]
            return f"Player report #{self.ref}"
        return "Blocked by another player"

    def _player_reason(self) -> str:
        """Starting text for the pairing block reasoning, which the player sees.

        Never names who reported or blocked them.
        """
        if self.kind == KIND_REPORT and self.ref.isdigit():
            report = get_report(int(self.ref))
            if report and report["reasons"]:
                labels = [REASON_LABELS.get(r, r).replace("Opponent ", "") for r in report["reasons"]]
                return "Reported after a match: " + "; ".join(labels)
            return "Reported after a match"
        return "Blocked by other players"


def moderation_view(target_id, kind: str, ref) -> discord.ui.View:
    """Buttons for one alert. A non-Discord account gets only the admin link."""
    view = discord.ui.View(timeout=None)
    if is_discord_id(target_id):
        view.add_item(PersistentModerationButton("timeout", int(target_id), kind, str(ref or "")))
        view.add_item(PersistentModerationButton("ban", int(target_id), kind, str(ref or "")))
        view.add_item(PersistentModerationButton("pblock", int(target_id), kind, str(ref or "")))
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

    async def _deliver(self, recipients, embed, view) -> bool:
        sent = False
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
        if not recipients:
            return 0

        count = 0
        for report in reports:
            embed = await build_report_embed(self.bot, report)
            view = moderation_view(report["reported_id"], KIND_REPORT, report["id"])
            # Mark as sent even if every DM failed, so one closed DM box
            # doesn't make the bot retry the same alert forever.
            await self._deliver(recipients, embed, view)
            mark_alerted(KIND_REPORT, str(report["id"]))
            count += 1
        for block in blocks:
            embed = await build_block_embed(self.bot, block)
            view = moderation_view(block["blocked_user_id"], KIND_BLOCK, block["user_id"])
            await self._deliver(recipients, embed, view)
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
