import discord
from discord.ext import commands

import config


class ReactionRolesCog(commands.Cog):
    """Assigns roles based on emoji reactions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.role_map = {
            "man_mage": config.MAGE_ROLE_ID,
        }

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        role_id = self.role_map.get(payload.emoji.name)
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            return

        member = payload.member or await guild.fetch_member(payload.user_id)
        if member.bot:
            return

        await member.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        role_id = self.role_map.get(payload.emoji.name)
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            return

        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if member.bot:
            return

        await member.remove_roles(role, reason="Reaction role removed")


def setup(bot: commands.Bot):
    bot.add_cog(ReactionRolesCog(bot))
