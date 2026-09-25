"""Admin commands to block players from the pairing service.

``!ban @user`` opens a modal (time out dropdown + reasoning). Submitting it
stores a ban, pulls the player out of the LFG queue, DMs them the details and
logs the action. ``!unban @user`` lifts it. ``!bans`` lists active bans.

Enforcement lives at each pairing entry point (queue buttons, website queue,
``!challenge``, ladder challenges) via ``get_pairing_ban`` /
``pairing_ban_message`` from ``utils.database``.
"""

import datetime
import logging

import discord
from discord.ext import commands

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock, matching_web_users
from utils.checks import is_bot_admin
from utils.database import (
    BAN_DURATIONS,
    format_time_remaining,
    get_active_pairing_bans,
    get_pairing_ban,
    log_admin_action,
    remove_pairing_ban,
    set_pairing_ban,
)

logger = logging.getLogger("discord_bot")

BAN_MODAL_TITLE = "Block from Pairing Service"

DURATION_DESCRIPTIONS = {
    "24h": "Blocked for one day",
    "48h": "Blocked for two days",
    "72h": "Blocked for three days",
    "lifetime": "Blocked until an admin lifts it",
}


def member_is_admin(member) -> bool:
    """Admin, Bot Admin role or Judge role — mirrors utils.checks.is_bot_admin."""
    if member is None:
        return False
    perms = getattr(member, "guild_permissions", None)
    if perms is not None and getattr(perms, "administrator", False):
        return True
    role_ids = {role.id for role in getattr(member, "roles", []) or []}
    admin_role_ids = {
        getattr(config, "BOT_ADMIN_ROLE_ID", None),
        getattr(config, "JUDGE_ROLE_ID", None),
    } - {None}
    return bool(role_ids & admin_role_ids)


def _display(user) -> str:
    return getattr(user, "global_name", None) or getattr(user, "display_name", None) or str(user)


def _ban_dm_embed(ban: dict) -> discord.Embed:
    """The DM a player receives when they are banned."""
    embed = discord.Embed(
        title="You've been blocked from the Summit pairing service",
        description=(
            "An admin has blocked you from using the pairing service. While blocked "
            "you can't join the LFG queue, use the website queue, send or accept "
            "challenges, or issue ladder challenges."
        ),
        color=discord.Color.red(),
        timestamp=ban["banned_at"],
    )
    embed.add_field(name="Time out", value=ban["duration_label"], inline=True)
    if ban["expires_at"]:
        unix = int(ban["expires_at"].timestamp())
        embed.add_field(name="Lifts", value=f"<t:{unix}:f> (<t:{unix}:R>)", inline=True)
    else:
        embed.add_field(name="Lifts", value="Does not expire", inline=True)
    embed.add_field(name="Reasoning", value=ban["reason"][:1024], inline=False)
    embed.set_footer(text="If you think this is a mistake, please contact a server admin.")
    return embed


def _unban_dm_embed() -> discord.Embed:
    return discord.Embed(
        title="Your pairing service block has been lifted",
        description="You can use the LFG queue, challenges and the website queue again.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )


async def _try_dm(user, embed) -> bool:
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.warning(f"Could not DM pairing ban notice to {getattr(user, 'id', user)}: {e}")
        return False


def build_duration_select() -> discord.ui.Select:
    return discord.ui.Select(
        placeholder="How long should the block last?",
        min_values=1,
        max_values=1,
        required=True,
        options=[
            discord.SelectOption(
                label=label,
                value=key,
                description=DURATION_DESCRIPTIONS[key],
            )
            for key, (label, _hours) in BAN_DURATIONS.items()
        ],
    )


class PairingBanModal(discord.ui.Modal, title=BAN_MODAL_TITLE):
    """Time out dropdown + reasoning. Discord supplies the Cancel and Submit buttons."""

    reason = discord.ui.TextInput(
        label="Reasoning",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this player being blocked? This is sent to them.",
        required=True,
        min_length=3,
        max_length=1000,
    )

    def __init__(self, bot, target, admin):
        super().__init__(timeout=600)
        self.bot = bot
        self.target = target
        self.admin = admin
        self.duration_select = build_duration_select()
        # Dropdown first, reasoning underneath.
        self.remove_item(self.reason)
        self.add_item(discord.ui.Label(text="Time out", component=self.duration_select))
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("PairingBanCog")
        if not cog:
            await interaction.followup.send("Pairing bans are not available.", ephemeral=True)
            return
        duration_key = self.duration_select.values[0] if self.duration_select.values else None
        if duration_key not in BAN_DURATIONS:
            await interaction.followup.send("Please pick a time out length.", ephemeral=True)
            return
        embed = await cog.apply_ban(
            target=self.target,
            admin=self.admin,
            reason=self.reason.value.strip(),
            duration_key=duration_key,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"PairingBanModal error: {error}", exc_info=True)
        msg = f"Something went wrong applying the ban: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


class BanInitView(discord.ui.View):
    """A prefix command can't open a modal, so ``!ban`` posts this button pair first."""

    def __init__(self, modal: PairingBanModal):
        super().__init__(timeout=120)
        self.modal = modal
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.modal.admin.id:
            await interaction.response.send_message(
                "Only the admin who ran `!ban` can use these buttons.", ephemeral=True
            )
            return False
        return True

    async def _cleanup(self, interaction):
        try:
            await interaction.message.delete()
        except (discord.HTTPException, AttributeError):
            pass

    @discord.ui.button(label="🚫 Open Ban Form", style=discord.ButtonStyle.danger)
    async def open_form_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.modal)
        await self._cleanup(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ban cancelled.", ephemeral=True)
        await self._cleanup(interaction)


class PairingBanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Shared helpers (used by prefix + slash commands) ──────────────

    @staticmethod
    def validate_target(admin, target) -> str | None:
        """Return an error message if ``target`` can't be banned, else None."""
        if target is None:
            return "Please mention a user. Example: `!ban @username`"
        if getattr(target, "bot", False):
            return "You can't ban a bot from the pairing service."
        if target.id == admin.id:
            return "You can't ban yourself."
        if member_is_admin(target):
            return "You can't ban another admin or judge from the pairing service."
        return None

    def build_ban_modal(self, target, admin) -> PairingBanModal:
        return PairingBanModal(self.bot, target, admin)

    async def _remove_from_queue(self, user_id: int) -> bool:
        async with lfg_queue_lock:
            was_queued = lfg_queue.pop(user_id, None) is not None
            matching_web_users.pop(user_id, None)
        if was_queued:
            lfg_cog = self.bot.get_cog("LFGCog")
            if lfg_cog:
                try:
                    await lfg_cog.update_lfg_status()
                except Exception as e:
                    logger.warning(f"Could not refresh LFG status after ban: {e}")
        return was_queued

    async def apply_ban(self, target, admin, reason: str, duration_key: str) -> discord.Embed:
        """Store the ban, drop the player from the queue, DM them, log it. Returns the admin summary."""
        previous = get_pairing_ban(target.id)
        ban = set_pairing_ban(
            target.id,
            admin.id,
            reason,
            duration_key,
            user_name=_display(target),
            banned_by_name=_display(admin),
        )
        was_queued = await self._remove_from_queue(target.id)
        dm_sent = await _try_dm(target, _ban_dm_embed(ban))

        try:
            log_admin_action(
                admin.id,
                _display(admin),
                "pairing_ban",
                target_id=target.id,
                target_name=_display(target),
                previous_state=(
                    {
                        "duration_label": previous["duration_label"],
                        "expires_at": previous["expires_at"].isoformat() if previous["expires_at"] else None,
                        "reason": previous["reason"],
                    }
                    if previous
                    else None
                ),
                new_state={
                    "duration_label": ban["duration_label"],
                    "expires_at": ban["expires_at"].isoformat() if ban["expires_at"] else None,
                    "reason": reason,
                },
                details=f"Pairing ban ({ban['duration_label']}): {reason}",
            )
        except Exception as e:
            logger.error(f"Failed to audit-log pairing ban: {e}")

        logger.info(
            f"Pairing ban: {admin.id} banned {target.id} for {ban['duration_label']} — {reason}"
        )

        embed = discord.Embed(
            title="Pairing ban applied" if not previous else "Pairing ban updated",
            color=discord.Color.orange(),
            timestamp=ban["banned_at"],
        )
        embed.add_field(name="Player", value=f"{target.mention} ({_display(target)})", inline=False)
        embed.add_field(name="Time out", value=ban["duration_label"], inline=True)
        if ban["expires_at"]:
            unix = int(ban["expires_at"].timestamp())
            embed.add_field(name="Lifts", value=f"<t:{unix}:f> (<t:{unix}:R>)", inline=True)
        else:
            embed.add_field(name="Lifts", value="Never (lifetime)", inline=True)
        embed.add_field(name="Reasoning", value=reason[:1024], inline=False)
        notes = []
        notes.append("✅ Player was DMed." if dm_sent else "⚠️ Could not DM the player (DMs closed). They'll see the reason when they try to queue.")
        if was_queued:
            notes.append("Removed them from the LFG queue.")
        embed.add_field(name="Notes", value="\n".join(notes), inline=False)
        embed.set_footer(text=f"Banned by {_display(admin)} • use !unban to lift early")
        return embed

    async def apply_unban(self, target, admin) -> discord.Embed:
        removed = remove_pairing_ban(target.id)
        if not removed:
            return discord.Embed(
                title="No active pairing ban",
                description=f"{target.mention} isn't currently blocked from the pairing service.",
                color=discord.Color.greyple(),
            )
        dm_sent = await _try_dm(target, _unban_dm_embed())
        try:
            log_admin_action(
                admin.id,
                _display(admin),
                "pairing_unban",
                target_id=target.id,
                target_name=_display(target),
                previous_state={
                    "duration_label": removed["duration_label"],
                    "expires_at": removed["expires_at"].isoformat() if removed["expires_at"] else None,
                    "reason": removed["reason"],
                },
                new_state=None,
                details="Pairing ban lifted",
            )
        except Exception as e:
            logger.error(f"Failed to audit-log pairing unban: {e}")
        logger.info(f"Pairing unban: {admin.id} unbanned {target.id}")

        embed = discord.Embed(
            title="Pairing ban lifted",
            description=f"{target.mention} can use the pairing service again.",
            color=discord.Color.green(),
        )
        embed.add_field(name="Was", value=removed["duration_label"], inline=True)
        embed.add_field(name="Original reason", value=(removed["reason"] or "—")[:1024], inline=False)
        embed.set_footer(text="✅ Player was DMed." if dm_sent else "⚠️ Could not DM the player (DMs closed).")
        return embed

    def build_bans_embed(self) -> discord.Embed:
        bans = get_active_pairing_bans()
        embed = discord.Embed(title="Active pairing bans", color=discord.Color.orange())
        if not bans:
            embed.description = "Nobody is currently blocked from the pairing service."
            return embed
        lines = []
        for ban in bans[:25]:
            name = ban["user_name"] or str(ban["user_id"])
            remaining = format_time_remaining(ban)
            reason = (ban["reason"] or "").replace("\n", " ")
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append(
                f"<@{ban['user_id']}> ({name}) — **{ban['duration_label']}**, "
                f"{remaining} left — {reason}"
            )
        embed.description = "\n".join(lines)
        if len(bans) > 25:
            embed.set_footer(text=f"Showing 25 of {len(bans)} bans")
        return embed

    # ── Prefix commands ───────────────────────────────────────────────

    @commands.command()
    @is_bot_admin()
    async def ban(self, ctx, member: discord.Member = None):
        """Block a player from the pairing service. Usage: !ban @user (opens a form)."""
        error = self.validate_target(ctx.author, member)
        if error:
            await ctx.send(error)
            return
        existing = get_pairing_ban(member.id)
        note = ""
        if existing:
            note = (
                f"\n⚠️ {member.mention} already has a **{existing['duration_label']}** ban "
                f"({format_time_remaining(existing)} left). Submitting will replace it."
            )
        view = BanInitView(self.build_ban_modal(member, ctx.author))
        await ctx.send(
            f"Click below to choose a time out and reasoning for blocking {member.mention} "
            f"from the pairing service.{note}",
            view=view,
            delete_after=120,
        )

    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("I couldn't find that member. Please @mention them.")
        else:
            logger.error(f"ban error: {error}", exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def unban(self, ctx, member: discord.Member = None):
        """Lift a player's pairing service block. Usage: !unban @user"""
        if member is None:
            await ctx.send("Please mention a user. Example: `!unban @username`")
            return
        embed = await self.apply_unban(member, ctx.author)
        await ctx.send(embed=embed)

    @unban.error
    async def unban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("I couldn't find that member. Please @mention them.")
        else:
            logger.error(f"unban error: {error}", exc_info=True)
            await ctx.send(f"An error occurred: {error}")

    @commands.command(aliases=["pairing_bans"])
    @is_bot_admin()
    async def bans(self, ctx):
        """List active pairing service bans."""
        await ctx.send(embed=self.build_bans_embed())

    @bans.error
    async def bans_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"bans error: {error}", exc_info=True)
            await ctx.send(f"An error occurred: {error}")


async def setup(bot):
    await bot.add_cog(PairingBanCog(bot))
