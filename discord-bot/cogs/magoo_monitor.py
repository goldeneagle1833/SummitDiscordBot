"""
Magoo Monitor Cog
=================
Lets an admin redirect an Archimago complaint spiral to the main Sorcery
Discord's general channel with ``!magoo``.
"""

import discord
from discord.ext import commands
import logging

from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")

# Sorcery main Discord general channel link
SORCERY_GENERAL_LINK = "https://discord.com/channels/769359301466652693/769359301466652696"


class MagooMonitorCog(commands.Cog):
    """Post the Archimago complaint embed on demand."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_complaint_embed(self) -> discord.Embed:
        """Build the Archimago complaint threshold embed."""
        description = (
            "The Summit Vibe Monitor has detected excessive complaining "
            "about Archimago.\n\n"
            f"Please move to the [Sorcery Discord General]({SORCERY_GENERAL_LINK}) "
            f"to continue complaining, or move on :)\n\n"
            f"*This has been a public service announcement from the Summit Vibe Monitor.*"
        )
        embed = discord.Embed(
            title="Archimago Complaint Threshold Reached!",
            description=description,
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Archimago is fine. This is fine. Everything is fine.")
        return embed

    @commands.command(name="magoo")
    @is_bot_admin()
    async def magoo_trigger(self, ctx: commands.Context):
        """Manually trigger the Archimago complaint embed."""
        await ctx.channel.send(embed=self._build_complaint_embed())
        logger.info(f"Magoo complaint embed posted in #{ctx.channel.name}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MagooMonitorCog(bot))
