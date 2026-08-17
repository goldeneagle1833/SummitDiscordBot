"""Content Monitor Cog — watches the sorcery-content channel for shared links.

When a user posts a URL in the content channel, this cog automatically creates
a promo banner on the website that lasts 24 hours or until a new link is posted.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord.ext import commands

import config

logger = logging.getLogger("discord_bot")

# analytics.db lives in the web-app directory (sibling to discord-bot)
ANALYTICS_DB_PATH = Path(__file__).parent.parent.parent / "web-app" / "analytics.db"

# Regex to extract URLs from message text
URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+')

# Identify auto-created content banners
CONTENT_BANNER_CREATOR = "content-bot"


class ContentMonitorCog(commands.Cog):
    """Monitors the sorcery-content channel and creates promo banners from shared links."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("ContentMonitorCog initialized")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots
        if message.author.bot:
            return

        # Only watch the sorcery-content channel
        if message.channel.id != config.CONTENT_CHANNEL_ID:
            return

        # Extract the first URL from the message
        url = self._extract_url(message)
        if not url:
            return

        # Build banner details from the message
        author_name = message.author.display_name
        title = f"{author_name}'s Latest Content"
        subtitle = self._build_subtitle(message, url)

        # Deactivate previous content banners, then create a new one
        try:
            self._deactivate_old_content_banners()
            self._create_content_banner(title=title, subtitle=subtitle, link=url)
            logger.info(f"Created content banner for {author_name}: {url}")
        except Exception:
            logger.error("Failed to create content banner", exc_info=True)

    def _extract_url(self, message: discord.Message) -> str | None:
        """Extract the first URL from message content or embeds."""
        # Check message text
        if message.content:
            match = URL_PATTERN.search(message.content)
            if match:
                return match.group(0)

        # Check embeds (Discord auto-embeds links)
        for embed in message.embeds:
            if embed.url:
                return embed.url

        return None

    def _build_subtitle(self, message: discord.Message, url: str) -> str:
        """Build a subtitle from the message content, stripping the URL."""
        text = message.content or ""
        # Remove the URL from the text to get a description
        text = URL_PATTERN.sub("", text).strip()

        if text:
            # Truncate if too long
            if len(text) > 120:
                text = text[:117] + "..."
            return text

        # Fallback: use embed title if available
        for embed in message.embeds:
            if embed.title:
                return embed.title

        return "Check out this Sorcery community content!"

    def _deactivate_old_content_banners(self):
        """Deactivate all previously auto-created content banners."""
        conn = sqlite3.connect(str(ANALYTICS_DB_PATH))
        conn.execute(
            "UPDATE promo_banners SET active = 0 WHERE created_by = ?",
            (CONTENT_BANNER_CREATOR,),
        )
        conn.commit()
        conn.close()

    def _create_content_banner(self, title: str, link: str, subtitle: str | None = None):
        """Create a new promo banner expiring in 24 hours."""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn = sqlite3.connect(str(ANALYTICS_DB_PATH))
        conn.execute(
            """INSERT INTO promo_banners
               (title, subtitle, link, badge_text, color, expires_at, active, created_by, images)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                title,
                subtitle,
                link,
                "COMMUNITY",
                "purple",
                expires_at,
                CONTENT_BANNER_CREATOR,
                json.dumps([]),
            ),
        )
        conn.commit()
        conn.close()
