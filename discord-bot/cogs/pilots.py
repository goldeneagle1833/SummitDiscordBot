"""Cog for managing pilots (feature flags) via admin commands."""

import discord
from discord.ext import commands

from utils.checks import is_bot_admin
from services.pilots_service import enable_pilot, disable_pilot, list_pilots


class PilotsCog(commands.Cog):
    """Admin commands for toggling feature pilots on/off."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @is_bot_admin()
    async def pilot_on(self, ctx, name: str):
        """Enable a pilot. Usage: !pilot_on <name>"""
        enable_pilot(name)
        await ctx.send(f"Pilot **{name}** is now **ON**.")

    @commands.command()
    @is_bot_admin()
    async def pilot_off(self, ctx, name: str):
        """Disable a pilot. Usage: !pilot_off <name>"""
        disable_pilot(name)
        await ctx.send(f"Pilot **{name}** is now **OFF**.")

    @commands.command()
    @is_bot_admin()
    async def pilots(self, ctx):
        """List all pilots and their status. Usage: !pilots"""
        all_pilots = list_pilots()
        if not all_pilots:
            await ctx.send("No pilots configured.")
            return

        lines = []
        for p in all_pilots:
            status = "ON" if p["enabled"] else "OFF"
            emoji = "\u2705" if p["enabled"] else "\u274c"
            lines.append(f"{emoji} **{p['name']}** - {status}")

        await ctx.send("**Pilots:**\n" + "\n".join(lines))


async def setup(bot):
    await bot.add_cog(PilotsCog(bot))
