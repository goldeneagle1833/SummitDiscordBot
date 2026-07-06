"""
Magoo Monitor Cog
=================
Monitors chat for excessive complaining about Archimago and redirects
people to the main Sorcery Discord's general channel when the threshold
is reached. Uses AI to judge complaint sentiment rather than keyword matching.
"""

import discord
from discord.ext import commands
import logging
import re
import time
from collections import deque

from openai import OpenAI

import config
from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")

# Aliases for Archimago (case-insensitive)
ARCHI_PATTERN = re.compile(
    r"\b(archimago|archi|magoo|arch[ie]mago)\b", re.IGNORECASE
)

# Sorcery main Discord general channel link
SORCERY_GENERAL_LINK = "https://discord.com/channels/769359301466652693/769359301466652696"

JUDGE_SYSTEM_PROMPT = """\
You are a vibe checker for a Sorcery: Contested Realm card game community Discord server.

Your job: given a batch of recent chat messages that mention "Archimago" (or "Archi" / "Magoo"), \
judge whether the conversation has devolved into a complaint spiral about Archimago being \
overpowered, broken, unfair, etc.

Normal discussion is fine — talking about Archi strategy, matchups, deck building, joking around, \
or even acknowledging Archi is strong without negativity does NOT count as complaining.

What DOES count: messages expressing frustration, calling Archi broken/busted/OP, demanding nerfs, \
saying it ruins the game, calling Archi players villains, etc. Sarcastic or humorous complaints \
still count as complaints.

Respond with ONLY a single integer from 0-10:
- 0-3: Normal discussion, no real complaining
- 4-6: Some grumbling but mostly discussion
- 7-10: Full complaint spiral, people are heated

Just the number, nothing else."""

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)


class MagooMonitorCog(commands.Cog):
    """Monitor chat vibes and detect Archimago complaint spirals."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Buffer of recent Archi-mentioning messages: (timestamp, author, content)
        self.message_buffer: deque[tuple[float, str, str]] = deque()

        # How many Archi-mentioning messages to collect before judging
        self.complaint_threshold = config.MAGOO_COMPLAINT_THRESHOLD
        # Time window in seconds
        self.window_seconds = config.MAGOO_WINDOW_SECONDS
        # Cooldown in seconds between triggers
        self.cooldown_seconds = config.MAGOO_COOLDOWN_SECONDS
        # AI complaint score that triggers the embed (0-10)
        self.score_threshold = config.MAGOO_SCORE_THRESHOLD

        # Last time we fired the embed (0 = never)
        self.last_triggered: float = 0
        # Buffer size at last AI check (avoid re-judging the same messages)
        self.last_judged_count: int = 0

        logger.info(
            f"MagooMonitorCog initialized "
            f"(threshold={self.complaint_threshold}, "
            f"window={self.window_seconds}s, "
            f"cooldown={self.cooldown_seconds}s, "
            f"score_threshold={self.score_threshold})"
        )

    def _mentions_archi(self, content: str) -> bool:
        """Check if a message mentions Archimago by any alias."""
        return bool(ARCHI_PATTERN.search(content))

    def _prune_old(self, now: float):
        """Remove messages outside the rolling window."""
        cutoff = now - self.window_seconds
        pruned = False
        while self.message_buffer and self.message_buffer[0][0] < cutoff:
            self.message_buffer.popleft()
            pruned = True
        if pruned:
            self.last_judged_count = 0

    def _judge_complaint_level(self) -> int:
        """Use AI to judge the complaint level of buffered messages. Returns 0-10."""
        if not self.message_buffer:
            return 0

        conversation = "\n".join(
            f"{author}: {content}"
            for _, author, content in self.message_buffer
        )

        score_text = ""
        try:
            response = openai_client.responses.create(
                model="gpt-4.1-nano",
                instructions=JUDGE_SYSTEM_PROMPT,
                input=conversation,
            )
            score_text = response.output_text.strip()
            score = int(score_text)
            return max(0, min(10, score))
        except (ValueError, TypeError):
            logger.warning(f"Magoo monitor: AI returned non-integer: {score_text!r}")
            return 0
        except Exception as e:
            logger.error(f"Magoo monitor AI error: {e}")
            return 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for Archimago complaint spirals."""
        if message.author.bot or not message.guild:
            return

        if not self._mentions_archi(message.content):
            return

        now = time.time()
        self.message_buffer.append(
            (now, message.author.display_name, message.content)
        )
        self._prune_old(now)

        logger.debug(
            f"Archi mention from {message.author.display_name}: "
            f"{len(self.message_buffer)}/{self.complaint_threshold} in window"
        )

        # Wait until we have enough Archi mentions to bother judging
        if len(self.message_buffer) < self.complaint_threshold:
            return

        # Don't re-judge the same set of messages
        if len(self.message_buffer) <= self.last_judged_count:
            return

        # Check cooldown
        if now - self.last_triggered < self.cooldown_seconds:
            return

        # Ask AI to judge the vibe
        self.last_judged_count = len(self.message_buffer)
        score = self._judge_complaint_level()
        logger.info(f"Magoo monitor AI complaint score: {score}/10")

        if score < self.score_threshold:
            return

        # Fire the embed!
        self.last_triggered = now
        self.message_buffer.clear()
        self.last_judged_count = 0

        await self._send_complaint_embed(message.channel, score)

    def _build_complaint_embed(self, score: int | None = None) -> discord.Embed:
        """Build the Archimago complaint threshold embed."""
        if score is not None:
            description = (
                f"The Summit Vibe Monitor has detected a complaint level of "
                f"**{score}/10** about Archimago.\n\n"
            )
        else:
            description = (
                "The Summit Vibe Monitor has detected excessive complaining "
                "about Archimago.\n\n"
            )
        description += (
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

    async def _send_complaint_embed(self, channel, score: int | None = None):
        """Send the complaint embed to a channel."""
        embed = self._build_complaint_embed(score)
        await channel.send(embed=embed)
        logger.info(
            f"Magoo complaint embed posted in #{channel.name} "
            f"(score={score})"
        )

    @commands.command(name="magoo")
    @is_bot_admin()
    async def magoo_trigger(self, ctx: commands.Context):
        """Manually trigger the Archimago complaint embed."""
        await self._send_complaint_embed(ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(MagooMonitorCog(bot))
