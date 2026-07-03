"""
Reddit Bridge Cog

Bridges a subreddit with a Discord channel (read-only).
- New Reddit posts create Discord threads in the configured channel.
- New Reddit comments on tracked posts appear as messages in the Discord thread.
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

DB_PATH = Path(__file__).parent.parent / "reddit_bridge.db"
REDDIT_BASE = "https://www.reddit.com"
USER_AGENT = "SummitDiscordBot/1.0 (Discord bot; https://sorcererssummit.com)"


def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS post_threads (
            reddit_post_id TEXT PRIMARY KEY,
            discord_thread_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen_comments (
            reddit_comment_id TEXT PRIMARY KEY
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


class RedditBridgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_database()
        self.session = None
        logger.info("RedditBridgeCog initialized")

    async def cog_load(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT}
        )
        self.poll_reddit.start()

    async def cog_unload(self):
        self.poll_reddit.cancel()
        if self.session:
            await self.session.close()

    # -- Reddit API helpers --

    async def _reddit_get(self, url):
        """Fetch JSON from Reddit's public API."""
        async with self.session.get(url) as resp:
            if resp.status == 429:
                logger.warning("Reddit bridge: Rate limited, will retry next cycle")
                return None
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Reddit API error ({resp.status}): {text[:200]}")
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

    def _get_thread_for_post(self, reddit_post_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT discord_thread_id FROM post_threads WHERE reddit_post_id = ?",
            (reddit_post_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _save_post_thread(self, reddit_post_id, thread_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO post_threads (reddit_post_id, discord_thread_id) VALUES (?, ?)",
            (reddit_post_id, thread_id),
        )
        conn.commit()
        conn.close()

    def _is_comment_seen(self, comment_id):
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT 1 FROM seen_comments WHERE reddit_comment_id = ?", (comment_id,)
        ).fetchone()
        conn.close()
        return row is not None

    def _mark_comment_seen(self, comment_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO seen_comments (reddit_comment_id) VALUES (?)",
            (comment_id,),
        )
        conn.commit()
        conn.close()

    async def _get_thread(self, thread_id):
        """Get a thread from cache or fetch it."""
        thread = self.bot.get_channel(thread_id)
        if thread:
            return thread
        try:
            thread = await self.bot.fetch_channel(thread_id)
            return thread
        except (discord.NotFound, discord.Forbidden):
            logger.warning(f"Reddit bridge: Thread {thread_id} not found or inaccessible")
            return None

    # -- Polling loop --

    @tasks.loop(seconds=120)
    async def poll_reddit(self):
        if not config.REDDIT_SUBREDDIT:
            return
        try:
            await self._check_new_posts()
            await self._check_new_comments()
        except Exception as e:
            logger.error(f"Reddit bridge poll error: {e}", exc_info=True)

    @poll_reddit.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    async def _check_new_posts(self):
        url = f"{REDDIT_BASE}/r/{config.REDDIT_SUBREDDIT}/new.json?limit=10"
        data = await self._reddit_get(url)
        if not data or "data" not in data:
            return

        posts = data["data"].get("children", [])
        if not posts:
            return

        channel = self.bot.get_channel(config.REDDIT_CHANNEL_ID)
        if not channel:
            logger.error(f"Reddit bridge: Channel {config.REDDIT_CHANNEL_ID} not found")
            return

        # Filter to only new posts (after our last seen time)
        last_ts = self._get_sync_state("last_reddit_post_time")
        last_ts_float = float(last_ts) if last_ts else 0

        new_posts = []
        for item in posts:
            post = item["data"]
            if post["created_utc"] > last_ts_float:
                new_posts.append(post)

        if not new_posts:
            return

        logger.info(f"Reddit bridge: Found {len(new_posts)} new posts")

        # Process oldest first
        for post in reversed(new_posts):
            post_id = post["id"]

            if self._get_thread_for_post(post_id):
                continue

            title = post.get("title", "")
            selftext = post.get("selftext", "")
            author = post.get("author", "[deleted]")
            permalink = post.get("permalink", "")
            post_url = f"{REDDIT_BASE}{permalink}"
            created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)

            # Build embed
            description = selftext[:4000] if selftext else ""
            if post.get("url") and not post["url"].startswith(f"{REDDIT_BASE}/r/"):
                # External link post
                description = f"[Link]({post['url']})\n\n{description}" if description else f"[Link]({post['url']})"

            embed = discord.Embed(
                title=title[:256],
                url=post_url,
                description=description,
                color=discord.Color.orange(),
                timestamp=created,
            )
            embed.set_author(name=f"u/{author} (Reddit)")
            embed.set_footer(text=f"r/{config.REDDIT_SUBREDDIT}")

            # Create thread
            thread_name = title[:95]
            if len(thread_name) < len(title):
                thread_name += "..."

            thread = await channel.create_thread(
                name=f"Reddit: {thread_name}"[:100],
                type=discord.ChannelType.public_thread,
            )
            await thread.send(embed=embed)
            self._save_post_thread(post_id, thread.id)
            logger.info(f"Created thread {thread.id} for Reddit post {post_id}")

        # Update last seen time to newest post
        newest_ts = posts[0]["data"]["created_utc"]
        self._set_sync_state("last_reddit_post_time", str(newest_ts))

    async def _check_new_comments(self):
        conn = sqlite3.connect(DB_PATH)
        post_threads = conn.execute("SELECT reddit_post_id, discord_thread_id FROM post_threads").fetchall()
        conn.close()

        for reddit_post_id, thread_id in post_threads:
            url = f"{REDDIT_BASE}/comments/{reddit_post_id}.json?limit=25&sort=new"
            data = await self._reddit_get(url)
            if not data or len(data) < 2:
                continue

            comments_data = data[1].get("data", {}).get("children", [])
            if not comments_data:
                continue

            thread = await self._get_thread(thread_id)
            if not thread:
                continue

            new_comments = []
            for item in comments_data:
                if item["kind"] != "t1":
                    continue
                comment = item["data"]
                comment_id = comment["id"]

                if self._is_comment_seen(comment_id):
                    continue

                author = comment.get("author", "[deleted]")
                body = comment.get("body", "")

                if not body or body == "[deleted]":
                    self._mark_comment_seen(comment_id)
                    continue

                new_comments.append((comment_id, author, body))

            if not new_comments:
                continue

            # Unarchive thread if needed
            if isinstance(thread, discord.Thread) and thread.archived:
                await thread.edit(archived=False)

            for comment_id, author, body in new_comments:
                # Truncate long comments
                if len(body) > 1900:
                    body = body[:1900] + "..."
                await thread.send(f"**u/{author} (Reddit):** {body}")
                self._mark_comment_seen(comment_id)
                logger.info(f"Forwarded Reddit comment {comment_id} to thread {thread_id}")


def setup(bot):
    bot.add_cog(RedditBridgeCog(bot))
