"""Dust Code reward system cog.

Players can donate dust codes via DM. Codes are randomly awarded
after match confirmations based on a ramping probability.
"""

import discord
from discord.ext import commands
import logging

import config
from repositories.dust_repo import (
    create_dust_tables,
    get_available_code_count,
    get_drop_status,
)
from services.dust_service import donate_code

logger = logging.getLogger("discord_bot")


class DustCog(commands.Cog):
    """Manages dust code donations and admin queries."""

    def __init__(self, bot):
        self.bot = bot
        create_dust_tables()

    @commands.command(name="donatedust")
    @commands.dm_only()
    async def donate_dust(self, ctx, *, code: str):
        """Donate a dust code via DM. Usage: !donatedust 11111 22222 33333 44444 or !donatedust 1111 2222 3333 4444 5555"""
        success, message = donate_code(
            code.strip(),
            ctx.author.id,
            ctx.author.display_name,
        )
        await ctx.send(message)

        # If codes are running low, notify
        if success:
            remaining = get_available_code_count()
            if remaining == 0:
                await self._notify_owner_no_codes()

    @donate_dust.error
    async def donate_dust_error(self, ctx, error):
        if isinstance(error, commands.PrivateMessageOnly):
            await ctx.send("This command can only be used in DMs with the bot.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please provide a code. Usage: `!donatedust 11111 22222 33333 44444` or `!donatedust 1111 2222 3333 4444 5555`")
        else:
            logger.error(f"Error in donatedust: {error}", exc_info=True)

    @commands.command(name="dustcodes")
    async def dust_codes_status(self, ctx):
        """Check dust code status (admin only)."""
        is_admin = False
        if ctx.guild:
            member = ctx.guild.get_member(ctx.author.id)
            if member:
                if member.guild_permissions.administrator:
                    is_admin = True
                elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in member.roles):
                    is_admin = True
        if ctx.author.id == config.OWNER_ID:
            is_admin = True

        if not is_admin:
            await ctx.send("You don't have permission to use this command.")
            return

        available = get_available_code_count()
        status = get_drop_status()

        embed = discord.Embed(title="Dust Code Status", color=discord.Color.gold())
        embed.add_field(name="Available Codes", value=str(available), inline=True)
        if status:
            embed.add_field(
                name="Games Since Reset",
                value=f"{status['games_since_reset']} / 100",
                inline=True,
            )
            embed.add_field(
                name="Next Drop Chance",
                value=status["current_chance"],
                inline=True,
            )
            if status["dropped_this_cycle"]:
                embed.add_field(
                    name="Cycle Status",
                    value="Locked (already dropped this cycle)",
                    inline=False,
                )
            if status["last_drop_game"] is not None:
                embed.add_field(
                    name="Last Drop At Game #",
                    value=str(status["last_drop_game"]),
                    inline=True,
                )
        await ctx.send(embed=embed)

    async def _notify_owner_no_codes(self):
        """DM the server owner that codes have run out."""
        try:
            owner = await self.bot.fetch_user(config.OWNER_ID)
            await owner.send(
                "**Dust Code Alert:** All dust codes have been claimed or given out. "
                "No more codes are available for drops."
            )
        except Exception as e:
            logger.error(f"Could not DM owner about dust codes: {e}")


def setup(bot):
    bot.add_cog(DustCog(bot))
