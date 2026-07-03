"""
Facebook Bridge Cog

Bridges a Facebook Page with a Discord channel.
- New Facebook posts create Discord threads in the meta-chat channel.
- Facebook comments on those posts appear as messages in the Discord thread.
- Discord messages in those threads get posted as comments on the Facebook post.
"""

import discord
from discord.ext import commands, tasks
import aiohttp
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger("discord_bot")

DB_PATH = Path(__file__).parent.parent / "facebook_bridge.db"
GRAPH_API = "https://graph.facebook.com/v25.0"


def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Map Facebook post IDs to Discord thread IDs
    c.execute("""
        CREATE TABLE IF NOT EXISTS post_threads (
            fb_post_id TEXT PRIMARY KEY,
            discord_thread_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Track which Facebook comments we've already forwarded
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen_comments (
            fb_comment_id TEXT PRIMARY KEY
        )
    """)
    # Track which Discord messages we've already forwarded (to avoid echo)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sent_from_discord (
            fb_comment_id TEXT PRIMARY KEY
        )
    """)
    # Track the latest post time so we only fetch new posts
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


class FacebookBridgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_database()
        self.session = None
        self._tracked_threads = set()
        self._load_tracked_threads()
        logger.info("FacebookBridgeCog initialized")

    def _load_tracked_threads(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT discord_thread_id FROM post_threads").fetchall()
        self._tracked_threads = {row[0] for row in rows}
        conn.close()

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.poll_facebook.start()

    async def cog_unload(self):
        self.poll_facebook.cancel()
        if self.session:
            await self.session.close()

    def _get_headers(self):
        return {"Authorization": f"Bearer {config.FACEBOOK_PAGE_ACCESS_TOKEN}"}

    # -- Facebook API helpers --

    async def _fb_get(self, endpoint, params=None):
        if params is None:
            params = {}
        params["access_token"] = config.FACEBOOK_PAGE_ACCESS_TOKEN
        url = f"{GRAPH_API}/{endpoint}"
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Facebook API error ({resp.status}): {text}")
                return None
            return await resp.json()

    async def _fb_post(self, endpoint, data=None):
        if data is None:
            data = {}
        data["access_token"] = config.FACEBOOK_PAGE_ACCESS_TOKEN
        url = f"{GRAPH_API}/{endpoint}"
        async with self.session.post(url, data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Facebook API post error ({resp.status}): {text}")
                return None
            return await resp.json()

    # -- Database helpers --

    def _get_sync_state(self, key):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None

    def _set_sync_state(self, key, value):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
        conn.close()

    def _get_thread_for_post(self, fb_post_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT discord_thread_id FROM post_threads WHERE fb_post_id = ?",
            (fb_post_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _get_post_for_thread(self, thread_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT fb_post_id FROM post_threads WHERE discord_thread_id = ?",
            (thread_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _save_post_thread(self, fb_post_id, thread_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO post_threads (fb_post_id, discord_thread_id) VALUES (?, ?)",
            (fb_post_id, thread_id),
        )
        conn.commit()
        conn.close()
        self._tracked_threads.add(thread_id)

    def _is_comment_seen(self, fb_comment_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT 1 FROM seen_comments WHERE fb_comment_id = ?", (fb_comment_id,)
        ).fetchone()
        conn.close()
        return row is not None

    def _mark_comment_seen(self, fb_comment_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO seen_comments (fb_comment_id) VALUES (?)",
            (fb_comment_id,),
        )
        conn.commit()
        conn.close()

    def _is_sent_from_discord(self, fb_comment_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT 1 FROM sent_from_discord WHERE fb_comment_id = ?", (fb_comment_id,)
        ).fetchone()
        conn.close()
        return row is not None

    def _mark_sent_from_discord(self, fb_comment_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO sent_from_discord (fb_comment_id) VALUES (?)",
            (fb_comment_id,),
        )
        conn.commit()
        conn.close()

    # -- Polling loop --

    @tasks.loop(seconds=60)
    async def poll_facebook(self):
        if not config.FACEBOOK_PAGE_ACCESS_TOKEN:
            return
        try:
            await self._check_new_posts()
            await self._check_new_comments()
        except Exception as e:
            logger.error(f"Facebook bridge poll error: {e}", exc_info=True)

    @poll_facebook.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    def _iso_to_unix(self, iso_time):
        """Convert Facebook ISO timestamp to Unix timestamp for the since parameter."""
        dt = datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%S%z")
        return str(int(dt.timestamp()))

    async def _check_new_posts(self):
        params = {
            "fields": "id,message,created_time,story",
            "limit": 10,
        }

        # Only fetch posts newer than what we've seen
        last_ts = self._get_sync_state("last_post_time")
        if last_ts:
            params["since"] = self._iso_to_unix(last_ts)

        data = await self._fb_get(f"{config.FACEBOOK_PAGE_ID}/feed", params)
        if not data or "data" not in data:
            logger.warning("Facebook bridge: No data returned from feed endpoint")
            return

        posts = data["data"]
        if not posts:
            return

        channel = self.bot.get_channel(config.META_CHAT_CHANNEL_ID)
        if not channel:
            logger.error(f"Meta chat channel {config.META_CHAT_CHANNEL_ID} not found")
            return

        logger.info(f"Facebook bridge: Found {len(posts)} posts to check")

        # Process oldest first so threads appear in chronological order
        for post in reversed(posts):
            fb_post_id = post["id"]

            # Skip if we already have a thread for this post
            if self._get_thread_for_post(fb_post_id):
                continue

            # Skip posts without text (e.g. profile picture updates)
            message = post.get("message") or post.get("story")
            if not message:
                continue

            # Create a Discord thread
            # Thread name: first 95 chars of the post (Discord limit is 100)
            thread_name = message[:95].split("\n")[0]
            if len(thread_name) < len(message.split("\n")[0]):
                thread_name += "..."

            thread = await channel.create_thread(
                name=f"FB: {thread_name}"[:100],
                type=discord.ChannelType.public_thread,
            )

            # Post the full Facebook message as the first message in the thread
            embed = discord.Embed(
                description=message,
                color=discord.Color.blue(),
                timestamp=discord.utils.parse_time(post["created_time"]),
            )
            embed.set_author(name="Golden Eagle Cards (Facebook)")
            embed.set_footer(text="Facebook Post")
            await thread.send(embed=embed)

            self._save_post_thread(fb_post_id, thread.id)
            logger.info(f"Created thread {thread.id} for FB post {fb_post_id}")

        # Update the last seen timestamp to the newest post
        newest_time = posts[0]["created_time"]
        self._set_sync_state("last_post_time", newest_time)

    async def _get_thread(self, thread_id):
        """Get a thread from cache or fetch it."""
        thread = self.bot.get_channel(thread_id)
        if thread:
            return thread
        try:
            thread = await self.bot.fetch_channel(thread_id)
            return thread
        except discord.NotFound:
            logger.warning(f"Facebook bridge: Thread {thread_id} not found")
            return None
        except discord.Forbidden:
            logger.warning(f"Facebook bridge: No access to thread {thread_id}")
            return None

    async def _check_new_comments(self):
        conn = sqlite3.connect(DB_PATH)
        post_threads = conn.execute("SELECT fb_post_id, discord_thread_id FROM post_threads").fetchall()
        conn.close()

        for fb_post_id, thread_id in post_threads:
            data = await self._fb_get(
                f"{fb_post_id}/comments",
                {"fields": "id,message,from,created_time", "limit": 25},
            )
            if not data or "data" not in data:
                logger.debug(f"Facebook bridge: No comments data for post {fb_post_id}")
                continue

            thread = await self._get_thread(thread_id)
            if not thread:
                continue

            for comment in data["data"]:
                comment_id = comment["id"]

                # Skip if already seen or if we posted it from Discord
                if self._is_comment_seen(comment_id):
                    continue
                if self._is_sent_from_discord(comment_id):
                    self._mark_comment_seen(comment_id)
                    continue

                commenter = comment.get("from", {}).get("name", "Unknown")
                message = comment.get("message", "")

                if not message:
                    self._mark_comment_seen(comment_id)
                    continue

                await thread.send(f"**{commenter} (FB):** {message}")
                self._mark_comment_seen(comment_id)
                logger.info(f"Forwarded FB comment {comment_id} to thread {thread_id}")

    # -- Discord -> Facebook --

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Only handle messages in tracked threads
        if not isinstance(message.channel, discord.Thread):
            return
        if message.channel.id not in self._tracked_threads:
            return

        fb_post_id = self._get_post_for_thread(message.channel.id)
        if not fb_post_id:
            return

        # Post as a comment on the Facebook post
        comment_text = f"[{message.author.display_name}]: {message.content}"
        logger.info(f"Facebook bridge: Posting Discord msg to FB post {fb_post_id}")
        result = await self._fb_post(
            f"{fb_post_id}/comments",
            {"message": comment_text},
        )

        if result and "id" in result:
            self._mark_sent_from_discord(result["id"])
            self._mark_comment_seen(result["id"])
            logger.info(
                f"Posted Discord message from {message.author} to FB post {fb_post_id}"
            )
        else:
            logger.error(
                f"Failed to post Discord message to FB post {fb_post_id}: {result}"
            )


def setup(bot):
    bot.add_cog(FacebookBridgeCog(bot))
