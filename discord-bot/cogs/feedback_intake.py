"""Copy posts from the Discord bug/feature channel onto the website Feedback board.

Each new forum post (or top-level message, if the channel is a plain text
channel) becomes one board item. From there the "Feedback auto PR" GitHub
Action triages it like site feedback. The bot reacts 📝 once it is saved.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

import config
from services import feedback_intake

logger = logging.getLogger("discord_bot")

DEFAULT_CHANNEL_NAME = "summit-website-or-bot-bug-feature-reports"
SAVED_EMOJI = "📝"
MIN_LENGTH = 15  # skip "+1", "same", etc.


class FeedbackIntakeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = int(getattr(config, "FEEDBACK_CHANNEL_ID", 0) or 0)
        self.channel_name = getattr(config, "FEEDBACK_CHANNEL_NAME", DEFAULT_CHANNEL_NAME)

    def _is_feedback_channel(self, channel) -> bool:
        if channel is None:
            return False
        if self.channel_id:
            return channel.id == self.channel_id
        return getattr(channel, "name", None) == self.channel_name

    def is_feedback_location(self, channel) -> bool:
        """True for the feedback channel itself or a post inside it (used by ask_bot)."""
        if isinstance(channel, discord.Thread):
            return self._is_feedback_channel(channel.parent)
        return self._is_feedback_channel(channel)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """A new forum post in the feedback forum."""
        if not isinstance(thread.parent, discord.ForumChannel):
            return
        if not self._is_feedback_channel(thread.parent):
            return
        starter = None
        for _ in range(3):  # the starter message can lag the thread event
            try:
                starter = thread.starter_message or await thread.fetch_message(thread.id)
                break
            except (discord.NotFound, discord.HTTPException):
                await asyncio.sleep(2)
        if starter is None or starter.author.bot:
            return
        tags = " ".join(tag.name for tag in getattr(thread, "applied_tags", []) or [])
        body = (starter.content or "").strip()
        if starter.attachments:
            body += "\n\nAttachments: " + ", ".join(a.url for a in starter.attachments[:5])
        await self._save(
            message=starter,
            title=thread.name,
            description=body or thread.name,
            feedback_type=feedback_intake.guess_type(tags, thread.name, body),
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Top-level messages when the feedback channel is a plain text channel."""
        if message.author.bot or not message.guild:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not self._is_feedback_channel(message.channel):
            return
        if message.reference or (message.content or "").startswith("!"):
            return
        text = (message.content or "").strip()
        if len(text) < MIN_LENGTH:
            return
        await self._save(
            message=message,
            title=feedback_intake.make_title(text),
            description=text,
            feedback_type=feedback_intake.guess_type(text),
        )

    async def _save(self, *, message: discord.Message, title: str,
                    description: str, feedback_type: str):
        item_id = await feedback_intake.submit(
            title=title,
            description=description,
            feedback_type=feedback_type,
            source_ref=message.id,
            username=message.author.display_name,
            user_id=message.author.id,
        )
        if item_id is None:
            return
        logger.info(f"Feedback from Discord saved as board item #{item_id}")
        try:
            await message.add_reaction(SAVED_EMOJI)
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(FeedbackIntakeCog(bot))
