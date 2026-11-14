"""Caps a player's season ratings at 1500 when they get a ticket after the grace week.

Watches for a ticket holder role being added (config.TICKET_HOLDER_ROLE_IDS);
the rules live in services/ticket_reset.py.
"""

import logging

import discord
from discord.ext import commands

import config
from repositories.elo_repo import get_active_event
from services.ticket_reset import RESET_CAP, apply_ticket_reset, plan_ticket_reset

logger = logging.getLogger("discord_bot")


def _has_ticket(member) -> bool:
    ticket_roles = set(getattr(config, "TICKET_HOLDER_ROLE_IDS", ()) or ())
    return any(role.id in ticket_roles for role in member.roles)


def _dm_text(event_name: str, entries) -> str:
    lines = "\n".join(
        f"- {avatar}: {old} → {RESET_CAP}" if avatar else f"- {old} → {RESET_CAP}"
        for avatar, old in entries
    )
    return (
        f"Thanks for picking up a ticket for **{event_name}**! "
        f"Because it came after the first week of the season, your season ratings above {RESET_CAP} "
        f"were set to {RESET_CAP}:\n{lines}\n"
        f"Anything at or below {RESET_CAP} stays where it was. Good luck on the climb!"
    )


class TicketResetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild_id = getattr(config, "GUILD_ID", None)
        if guild_id and getattr(after.guild, "id", None) != guild_id:
            return
        if _has_ticket(before) or not _has_ticket(after):
            return
        await self.handle_new_ticket(after)

    async def handle_new_ticket(self, member) -> None:
        event = get_active_event()
        try:
            plan = plan_ticket_reset(event, member.id)
        except Exception:
            logger.exception("Could not check the late-ticket reset for %s", member.id)
            return
        if not plan.will_reset:
            logger.info("New ticket for %s: no reset (%s, %s games)", member.id, plan.reason, plan.games)
            return

        name = getattr(member, "global_name", None) or member.display_name
        try:
            apply_ticket_reset(event, member.id, name, plan)
        except Exception:
            logger.exception("Late-ticket reset failed for %s", member.id)
            return

        lfg = self.bot.get_cog("LFGCog")
        if lfg is not None:
            try:
                await lfg.update_leaderboard()
            except Exception:
                logger.exception("Leaderboard refresh after late-ticket reset failed")

        try:
            await member.send(_dm_text(event["event_name"], plan.entries))
        except (discord.Forbidden, discord.HTTPException):
            logger.info("Could not DM %s about their late-ticket reset", member.id)


async def setup(bot):
    await bot.add_cog(TicketResetCog(bot))
