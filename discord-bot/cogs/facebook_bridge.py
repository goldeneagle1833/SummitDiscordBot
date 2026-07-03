"""
Facebook Bridge Cog

Bridges a Facebook Page with Discord channels.
- New Facebook posts create Discord threads in the meta-chat channel.
- Avatar-specific posts (starting with avatar name) go directly to avatar channels.
- Facebook comments appear in the corresponding Discord thread or avatar channel.
- Discord messages in threads/avatar channels get posted as comments on the Facebook post.
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

AVATAR_CHANNEL_MAP = {
    "Archimago": 1494118715414024253,
    "Waveshaper": 1511003284930953246,
    "Avatar of Air": 1511382800534605884,
    "Avatar of Earth": 1511386628034138162,
    "Avatar of Fire": 1519315038689562644,
    "Avatar of Water": 1519315255203987496,
    "Geomancer": 1513873409417674752,
    "Sparkmage": 1519314845185343498,
    "Flamecaller": 1519314932565545100,
    "Harbinger": 1513742725277810750,
    "Imposter": 1511387750845382717,
    "Druid": 1511415894885142768,
    "Enchantress": 1511400819071909919,
    "Pathfinder": 1514246289301176482,
    "Elementalist": 1515890274574930001,
    "Sorcerer": 1517149744416161893,
    "Bladedancer": 1517185249044332616,
    "Realm-Eater": 1519171306438922441,
    "Necromancer": 1519316017950752789,
    "Ironclad": 1519314777221103656,
    "Interrogator": 1519316126990078064,
    "Seer": 1519316391340019792,
    "Dragonlord": 1519334832180564048,
    "Templar": 1519334887260422184,
    "Savior": 1519337220090106088,
    "Magician": 1519340705279905922,
    "Animist": 1519341208302915645,
    "Witch": 1519342799437172786,
    "Deathspeaker": 1519346928058634361,
    "Corruptor": 1519353617419735081,
    "Battlemage": 1519450100638945402,
}

# Reverse lookup: channel_id -> avatar_name
AVATAR_CHANNEL_IDS = {v: k for k, v in AVATAR_CHANNEL_MAP.items()}


def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Map Facebook post IDs to Discord thread/channel IDs
    c.execute("""
        CREATE TABLE IF NOT EXISTS post_threads (
            fb_post_id TEXT PRIMARY KEY,
            discord_thread_id INTEGER NOT NULL,
            is_avatar_channel INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add is_avatar_channel column if it doesn't exist (migration)
    try:
        c.execute("ALTER TABLE post_threads ADD COLUMN is_avatar_channel INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
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
        self._tracked_threads = set()  # Thread IDs for meta-chat threads
        self._tracked_avatar_channels = set()  # Avatar channel IDs with active FB posts
        self._load_tracked()
        logger.info("FacebookBridgeCog initialized")

    def _load_tracked(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT discord_thread_id, is_avatar_channel FROM post_threads").fetchall()
        self._tracked_threads = {row[0] for row in rows if not row[1]}
        self._tracked_avatar_channels = {row[0] for row in rows if row[1]}
        conn.close()

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.poll_facebook.start()

    async def cog_unload(self):
        self.poll_facebook.cancel()
        if self.session:
            await self.session.close()

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

    def _get_latest_post_for_channel(self, channel_id):
        """Get the most recent FB post mapped to an avatar channel."""
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT fb_post_id FROM post_threads WHERE discord_thread_id = ? AND is_avatar_channel = 1 ORDER BY created_at DESC LIMIT 1",
            (channel_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def _save_post_thread(self, fb_post_id, discord_id, is_avatar_channel=False):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR IGNORE INTO post_threads (fb_post_id, discord_thread_id, is_avatar_channel) VALUES (?, ?, ?)",
            (fb_post_id, discord_id, 1 if is_avatar_channel else 0),
        )
        conn.commit()
        conn.close()
        if is_avatar_channel:
            self._tracked_avatar_channels.add(discord_id)
        else:
            self._tracked_threads.add(discord_id)

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

    def _match_avatar(self, message_text):
        """Check if message starts with an avatar name. Returns (avatar_name, channel_id) or None."""
        message_lower = message_text.lower()
        for avatar_name, channel_id in AVATAR_CHANNEL_MAP.items():
            if message_lower.startswith(avatar_name.lower()):
                return avatar_name, channel_id
        return None

    async def _fetch_posts(self, endpoint, sync_key):
        """Fetch posts from a Facebook endpoint, filtering by last seen time."""
        params = {
            "fields": "id,message,created_time,story,from",
            "limit": 10,
        }
        last_ts = self._get_sync_state(sync_key)
        if last_ts:
            params["since"] = self._iso_to_unix(last_ts)

        data = await self._fb_get(endpoint, params)
        if not data or "data" not in data:
            return []
        return data["data"]

    async def _check_new_posts(self):
        # Fetch from both the page feed and visitor posts
        feed_posts = await self._fetch_posts(f"{config.FACEBOOK_PAGE_ID}/feed", "last_post_time")
        visitor_posts = await self._fetch_posts(f"{config.FACEBOOK_PAGE_ID}/visitor_posts", "last_visitor_post_time")

        # Merge and deduplicate (visitor posts may also appear in feed)
        seen_ids = set()
        all_posts = []
        for post in feed_posts + visitor_posts:
            if post["id"] not in seen_ids:
                seen_ids.add(post["id"])
                all_posts.append(post)

        if not all_posts:
            return

        meta_channel = self.bot.get_channel(config.META_CHAT_CHANNEL_ID)
        if not meta_channel:
            logger.error(f"Meta chat channel {config.META_CHAT_CHANNEL_ID} not found")
            return

        logger.info(f"Facebook bridge: Found {len(all_posts)} posts to check")
        posts = all_posts

        # Process oldest first so threads appear in chronological order
        for post in reversed(posts):
            fb_post_id = post["id"]

            # Skip if we already have a mapping for this post
            if self._get_thread_for_post(fb_post_id):
                continue

            # Skip posts without text (e.g. profile picture updates)
            message = post.get("message") or post.get("story")
            if not message:
                continue

            poster_name = post.get("from", {}).get("name", "Unknown")
            embed = discord.Embed(
                description=message,
                color=discord.Color.blue(),
                timestamp=discord.utils.parse_time(post["created_time"]),
            )
            embed.set_author(name=f"{poster_name} (Facebook)")
            embed.set_footer(text="Facebook Post")

            # Check if this is an avatar post
            avatar_match = self._match_avatar(message)
            if avatar_match:
                avatar_name, avatar_channel_id = avatar_match
                avatar_channel = self.bot.get_channel(avatar_channel_id)
                if avatar_channel:
                    # Post directly in the avatar channel (no thread)
                    await avatar_channel.send(embed=embed)
                    self._save_post_thread(fb_post_id, avatar_channel_id, is_avatar_channel=True)
                    logger.info(f"Posted FB post {fb_post_id} to {avatar_name} channel {avatar_channel_id}")
                else:
                    logger.warning(f"Facebook bridge: Avatar channel {avatar_channel_id} for {avatar_name} not found")
            else:
                # Regular post -> create a thread in meta-chat
                thread_name = message[:95].split("\n")[0]
                if len(thread_name) < len(message.split("\n")[0]):
                    thread_name += "..."

                thread = await meta_channel.create_thread(
                    name=f"FB: {thread_name}"[:100],
                    type=discord.ChannelType.public_thread,
                )
                await thread.send(embed=embed)
                self._save_post_thread(fb_post_id, thread.id)
                logger.info(f"Created thread {thread.id} for FB post {fb_post_id}")

        # Update the last seen timestamps
        if feed_posts:
            self._set_sync_state("last_post_time", feed_posts[0]["created_time"])
        if visitor_posts:
            self._set_sync_state("last_visitor_post_time", visitor_posts[0]["created_time"])

    async def _get_channel_or_thread(self, discord_id):
        """Get a thread or channel from cache or fetch it."""
        ch = self.bot.get_channel(discord_id)
        if ch:
            return ch
        try:
            ch = await self.bot.fetch_channel(discord_id)
            return ch
        except discord.NotFound:
            logger.warning(f"Facebook bridge: Channel/thread {discord_id} not found")
            return None
        except discord.Forbidden:
            logger.warning(f"Facebook bridge: No access to channel/thread {discord_id}")
            return None

    async def _check_new_comments(self):
        conn = sqlite3.connect(DB_PATH)
        post_mappings = conn.execute(
            "SELECT fb_post_id, discord_thread_id, is_avatar_channel FROM post_threads"
        ).fetchall()
        conn.close()

        for fb_post_id, discord_id, is_avatar in post_mappings:
            data = await self._fb_get(
                f"{fb_post_id}/comments",
                {"fields": "id,message,from,created_time", "limit": 25},
            )
            if not data or "data" not in data:
                logger.debug(f"Facebook bridge: No comments data for post {fb_post_id}")
                continue

            target = await self._get_channel_or_thread(discord_id)
            if not target:
                continue

            new_comments = []
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

                new_comments.append((comment_id, commenter, message))

            if not new_comments:
                continue

            # Unarchive thread if needed (only applies to threads, not channels)
            if isinstance(target, discord.Thread) and target.archived:
                await target.edit(archived=False)

            for comment_id, commenter, message in new_comments:
                await target.send(f"**{commenter} (FB):** {message}")
                self._mark_comment_seen(comment_id)
                logger.info(f"Forwarded FB comment {comment_id} to {'channel' if is_avatar else 'thread'} {discord_id}")

    # -- Discord -> Facebook --

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if this is an avatar channel message
        if message.channel.id in self._tracked_avatar_channels:
            fb_post_id = self._get_latest_post_for_channel(message.channel.id)
            if fb_post_id:
                await self._post_to_facebook(message, fb_post_id)
            return

        # Check if this is a tracked thread message
        if not isinstance(message.channel, discord.Thread):
            return
        if message.channel.id not in self._tracked_threads:
            return

        fb_post_id = self._get_post_for_thread(message.channel.id)
        if not fb_post_id:
            return

        await self._post_to_facebook(message, fb_post_id)

    async def _post_to_facebook(self, message: discord.Message, fb_post_id: str):
        """Post a Discord message as a comment on a Facebook post."""
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
