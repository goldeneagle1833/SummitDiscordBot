"""Dynamic voice channels - auto-create temporary voice rooms.

When a user joins the configured hub channel, the bot creates a new voice
channel in the same category and moves them into it. When everyone leaves
a temporary channel it is automatically deleted.
"""

import random

import discord
from discord.ext import commands
import logging

import config

ROOM_NAMES = [
    "Grassy Gnoll",
    "The Dungeon",
    "Back of the Bus",
    "Random Concrete Slab",
    "Two Tiny Tables Shoved Together",
    "Random Windy Park Bench",
    "Table of Fine Purpleheart",
    "Emergency Bathroom",
    "Sticky Mall Food Court",
    "Futon That Smells of Farts",
    "Bram Stroker's Daperyll Playboy Mansion",
    "Yourt's Bungalow",
    "Baba Yaga's Love Shack",
    "The Summit",
]

_ROOM_NAME_SET = set(ROOM_NAMES)

logger = logging.getLogger("discord_bot")


class DynamicVoiceCog(commands.Cog):
    """Creates and cleans up temporary voice channels on the fly."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_dynamic(self, channel: discord.VoiceChannel) -> bool:
        """A channel is dynamic if it's in the hub's category and has a known room name."""
        hub = self.bot.get_channel(config.DYNAMIC_VOICE_HUB_ID)
        if not hub:
            return False
        return (
            channel.category == hub.category
            and channel.id != hub.id
            and channel.name in _ROOM_NAME_SET
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Clean up any leftover empty dynamic channels from before a restart."""
        hub = self.bot.get_channel(config.DYNAMIC_VOICE_HUB_ID)
        if not hub or not hub.category:
            return
        for channel in hub.category.voice_channels:
            if channel.id == hub.id:
                continue
            if channel.name in _ROOM_NAME_SET and len(channel.members) == 0:
                await self._delete_channel(channel)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # --- Create: user joined the hub channel ---
        if (
            after.channel
            and after.channel.id == config.DYNAMIC_VOICE_HUB_ID
        ):
            await self._create_and_move(member, after.channel)

        # --- Cleanup: user left a dynamic channel that is now empty ---
        if (
            before.channel
            and len(before.channel.members) == 0
            and self._is_dynamic(before.channel)
        ):
            await self._delete_channel(before.channel)

    async def _create_and_move(
        self, member: discord.Member, hub: discord.VoiceChannel
    ):
        category = hub.category
        channel_name = random.choice(ROOM_NAMES)

        try:
            new_channel = await hub.guild.create_voice_channel(
                name=channel_name,
                category=category,
                reason="Dynamic voice room",
            )
            await member.move_to(new_channel)
            logger.info(
                f"Created dynamic voice channel '{channel_name}' "
                f"(id={new_channel.id}) for {member}"
            )
        except discord.Forbidden:
            logger.error("Missing permissions to create/move voice channels")
        except discord.HTTPException as e:
            logger.error(f"Failed to create dynamic voice channel: {e}")

    async def _delete_channel(self, channel: discord.VoiceChannel):
        try:
            await channel.delete(reason="Dynamic voice room empty")
            logger.info(
                f"Deleted empty dynamic voice channel '{channel.name}' "
                f"(id={channel.id})"
            )
        except discord.NotFound:
            pass  # already gone
        except discord.HTTPException as e:
            logger.error(f"Failed to delete dynamic voice channel: {e}")


def setup(bot: commands.Bot):
    bot.add_cog(DynamicVoiceCog(bot))
