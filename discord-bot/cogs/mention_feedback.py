"""@mention the bot to send feedback to the website Feedback board.

  @Summit Bot feedback: the LFG button doesn't work on mobile

Also accepts "bug:", "bug report:", "feature:", "feature request:", "idea:"
and "suggestion:". Any other mention is ignored. There is no AI here: the
earlier AI question answering was removed on 2026-11-28 at Bruce's request.
"""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from services import feedback_intake

logger = logging.getLogger("discord_bot")

FEEDBACK_PREFIX = re.compile(
    r"^\s*(feedback|bug(?: report)?|feature(?: request)?|idea|suggestion)\s*[:\-–]\s*",
    re.IGNORECASE,
)


class MentionFeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _own_role(message: discord.Message):
        guild = getattr(message, "guild", None)
        role = getattr(guild, "self_role", None) if guild is not None else None
        return role if isinstance(getattr(role, "id", None), int) else None

    def _mention_text(self, message: discord.Message) -> str | None:
        """The message without the bot tag, or None if the bot wasn't tagged."""
        me = self.bot.user
        if me is None:
            return None
        content = message.content or ""
        tags = [f"<@{me.id}>", f"<@!{me.id}>"]
        role = self._own_role(message)
        if role is not None:
            tags.append(f"<@&{role.id}>")
        if not any(tag in content for tag in tags):
            return None
        for tag in tags:
            content = content.replace(tag, "")
        return content.strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if (message.content or "").startswith("!"):
            return
        text = self._mention_text(message)
        if text is None:
            return
        intake = self.bot.get_cog("FeedbackIntakeCog")
        if intake and intake.is_feedback_location(message.channel):
            return  # posts there already go to the feedback board
        match = FEEDBACK_PREFIX.match(text)
        if not match:
            return
        body = text[match.end():].strip()
        none = discord.AllowedMentions.none()
        if len(body) < 10:
            await message.reply(
                "Tell me a bit more, like `@Summit Bot feedback: the LFG button does nothing on my phone`.",
                mention_author=False, allowed_mentions=none,
            )
            return
        item_id = await feedback_intake.submit(
            title=feedback_intake.make_title(body),
            description=body,
            feedback_type=feedback_intake.guess_type(match.group(1), body),
            source_ref=message.id,
            username=message.author.display_name,
            user_id=message.author.id,
        )
        reply = (
            "Thanks! That's on the feedback board now. 📝"
            if item_id else
            "I couldn't save that just now. Please use the Feedback link on sorcererssummit.com."
        )
        await message.reply(reply, mention_author=False, allowed_mentions=none)


async def setup(bot):
    await bot.add_cog(MentionFeedbackCog(bot))
