"""Discord forum threads for player articles, kept in sync with the site.

When an article is published on sorcererssummit.com/articles the bot opens a
post for it in the articles forum channel (``ARTICLES_FORUM_CHANNEL_ID`` in
config.py, else a forum channel named ``player-articles``).  Comments then
flow both ways through web-app/articles.db:

- site -> Discord: the web app saves a comment with mirror_status 'pending';
  this cog posts "**Name** on the site: ..." in the thread and stores the
  Discord message ID.
- Discord -> site: a member's message in the thread is saved as a comment
  (source 'discord'); edits and deletes follow it.
- Deleting a comment on the site removes its Discord copy (moderators
  deleting a Discord member's comment also remove the original, when the bot
  has Manage Messages).
- Taking an article down locks and archives its thread; republishing reopens
  it.
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands, tasks

import config
from cogs.article_notifications import ARTICLES_DB_PATH, site_url

logger = logging.getLogger("discord_bot")

FORUM_NAME = "player-articles"
COMMENT_MAX = 1900
NO_PINGS = discord.AllowedMentions.none()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ArticleStore:
    """The few queries the bot runs against the web app's articles.db."""

    def __init__(self, db_path: Path = ARTICLES_DB_PATH):
        self.db_path = Path(db_path)

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _rows(self, sql: str, params=()) -> list[dict]:
        if not self.db_path.exists():
            return []
        conn = self._conn()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            return []  # web app hasn't created the tables yet
        finally:
            conn.close()

    def _write(self, sql: str, params=()) -> int:
        if not self.db_path.exists():
            return 0  # never create an empty articles.db from the bot
        conn = self._conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    # Threads
    def articles_needing_thread_work(self) -> list[dict]:
        return self._rows(
            # SELECT * so newer optional columns (external_url) are picked up
            # when present without breaking an older articles.db
            """SELECT * FROM articles
               WHERE (status = 'approved' AND forum_thread_id IS NULL)
                  OR (forum_thread_id IS NOT NULL AND status = 'approved' AND forum_locked = 1)
                  OR (forum_thread_id IS NOT NULL AND status != 'approved' AND forum_locked = 0)
               ORDER BY id LIMIT 10"""
        )

    def set_thread(self, article_id: int, thread_id: int):
        self._write("UPDATE articles SET forum_thread_id = ?, forum_locked = 0 WHERE id = ?",
                    (str(thread_id), article_id))

    def set_locked(self, article_id: int, locked: bool):
        self._write("UPDATE articles SET forum_locked = ? WHERE id = ?", (1 if locked else 0, article_id))

    def article_for_thread(self, thread_id: int) -> dict | None:
        rows = self._rows(
            "SELECT id, status FROM articles WHERE forum_thread_id = ?", (str(thread_id),)
        )
        return rows[0] if rows else None

    # Site -> Discord
    def pending_site_comments(self) -> list[dict]:
        return self._rows(
            """SELECT c.id, c.username, c.body, a.forum_thread_id
               FROM article_public_comments c JOIN articles a ON a.id = c.article_id
               WHERE c.source = 'site' AND c.mirror_status = 'pending' AND c.deleted = 0
                 AND a.status = 'approved' AND a.forum_thread_id IS NOT NULL
               ORDER BY c.id LIMIT 20"""
        )

    def mark_mirrored(self, comment_id: int, message_id: int | None, ok: bool = True):
        self._write(
            "UPDATE article_public_comments SET discord_message_id = ?, mirror_status = ? WHERE id = ?",
            (str(message_id) if message_id else None, "done" if ok else "failed", comment_id),
        )

    def pending_deletions(self) -> list[dict]:
        return self._rows(
            """SELECT c.id, c.source, c.discord_message_id, a.forum_thread_id
               FROM article_public_comments c JOIN articles a ON a.id = c.article_id
               WHERE c.deleted = 1 AND c.mirror_deleted = 0
                 AND c.discord_message_id IS NOT NULL AND a.forum_thread_id IS NOT NULL
               ORDER BY c.id LIMIT 20"""
        )

    def mark_mirror_deleted(self, comment_id: int):
        self._write("UPDATE article_public_comments SET mirror_deleted = 1 WHERE id = ?", (comment_id,))

    # Discord -> site
    def add_discord_comment(self, article_id: int, message_id: int, user_id: int,
                            username: str, avatar: str | None, body: str):
        self._write(
            """INSERT OR IGNORE INTO article_public_comments
               (article_id, source, user_id, username, avatar, body,
                discord_message_id, mirror_status, created_at)
               VALUES (?, 'discord', ?, ?, ?, ?, ?, 'done', ?)""",
            (article_id, str(user_id), username, avatar, body, str(message_id), _now()),
        )

    def edit_discord_comment(self, message_id: int, body: str) -> int:
        return self._write(
            """UPDATE article_public_comments SET body = ?, edited_at = ?
               WHERE discord_message_id = ? AND source = 'discord'""",
            (body, _now(), str(message_id)),
        )

    def discord_message_deleted(self, message_id: int) -> int:
        return self._write(
            """UPDATE article_public_comments SET deleted = 1, mirror_deleted = 1
               WHERE discord_message_id = ?""",
            (str(message_id),),
        )


def thread_starter_text(article: dict) -> str:
    url = site_url(f"/articles/{article['id']}-{article['slug']}")
    return (
        f"{article['summary']}\n\n"
        f"By **{article['author_name']}** · {article['category']}\n"
        + (f"Original article: {article['external_url']}\n" if article.get("external_url") else "")
        + f"Read it here: {url}\n\n"
        "Comment in this thread or under the article on the site. "
        "Comments show up in both places."
    )[:2000]


def comment_body(message: discord.Message) -> str:
    parts = [message.clean_content.strip()]
    parts += [a.url for a in message.attachments]
    return "\n".join(p for p in parts if p)[:2000]


def mirror_text(username: str, body: str) -> str:
    if len(body) > COMMENT_MAX:
        body = body[:COMMENT_MAX] + "..."
    return f"**{discord.utils.escape_markdown(username)}** on the site:\n{body}"


class ArticleDiscussionsCog(commands.Cog):
    def __init__(self, bot, store: ArticleStore | None = None):
        self.bot = bot
        self.store = store or ArticleStore()
        self._warned_no_forum = False
        self.sync.start()
        logger.info("ArticleDiscussionsCog initialized")

    def cog_unload(self):
        self.sync.cancel()

    # ------------------------------------------------------------------
    # Lookups

    def _forum(self) -> discord.ForumChannel | None:
        channel_id = int(getattr(config, "ARTICLES_FORUM_CHANNEL_ID", 0) or 0)
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if isinstance(channel, discord.ForumChannel):
                return channel
        guild_id = int(getattr(config, "SUMMIT_GUILD_ID", 0) or getattr(config, "GUILD_ID", 0) or 0)
        guilds = [self.bot.get_guild(guild_id)] if guild_id else list(self.bot.guilds)
        for guild in guilds:
            if guild is None:
                continue
            for forum in guild.forums:
                if forum.name.lower() == FORUM_NAME:
                    return forum
        return None

    def _guild(self) -> discord.Guild | None:
        guild_id = int(getattr(config, "SUMMIT_GUILD_ID", 0) or getattr(config, "GUILD_ID", 0) or 0)
        return self.bot.get_guild(guild_id) if guild_id else None

    async def _create_forum(self) -> discord.ForumChannel | None:
        """Make the player-articles forum the first time an article is published.

        Members can reply in article posts but can't start their own posts;
        only the bot opens one per published article.
        """
        guild = self._guild()
        if guild is None:
            return None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                send_messages=False,  # in a forum: no new posts
                send_messages_in_threads=True,  # but replying is fine
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, send_messages_in_threads=True,
                create_public_threads=True, manage_threads=True, manage_messages=True,
            ),
        }
        try:
            forum = await guild.create_forum(
                name=FORUM_NAME,
                topic="Player articles from sorcererssummit.com/articles. Comments here and "
                      "on the site stay in sync.",
                overwrites=overwrites,
                reason="Player articles discussion threads",
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Player articles: could not create the forum channel: {e}")
            return None
        logger.info(f"Player articles: created forum channel {forum.id}")
        return forum

    async def _thread(self, thread_id) -> discord.Thread | None:
        thread = self.bot.get_channel(int(thread_id))
        if thread is None:
            try:
                thread = await self.bot.fetch_channel(int(thread_id))
            except (discord.NotFound, discord.Forbidden):
                return None
        return thread if isinstance(thread, discord.Thread) else None

    # ------------------------------------------------------------------
    # Periodic sync (site -> Discord)

    @tasks.loop(seconds=20)
    async def sync(self):
        try:
            await self.sync_threads()
            await self.mirror_site_comments()
            await self.mirror_deletions()
        except Exception as e:
            logger.error(f"Article discussion sync failed: {e}")

    @sync.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    async def sync_threads(self):
        work = self.store.articles_needing_thread_work()
        if not work:
            return
        for article in work:
            if article["forum_thread_id"] is None:
                forum = self._forum() or await self._create_forum()
                if forum is None:
                    if not self._warned_no_forum:
                        logger.warning(
                            "Player articles: no forum channel and couldn't create one (the bot "
                            "needs Manage Channels, or set ARTICLES_FORUM_CHANNEL_ID); threads not created"
                        )
                        self._warned_no_forum = True
                    return
                created = await forum.create_thread(
                    name=article["title"][:100],
                    content=thread_starter_text(article),
                    allowed_mentions=NO_PINGS,
                )
                self.store.set_thread(article["id"], created.thread.id)
                logger.info(f"Article {article['id']}: forum thread {created.thread.id} created")
                continue

            thread = await self._thread(article["forum_thread_id"])
            want_locked = article["status"] != "approved"
            if thread is not None:
                try:
                    await thread.edit(locked=want_locked, archived=want_locked)
                except discord.Forbidden:
                    logger.warning(f"Article {article['id']}: no permission to lock/unlock thread")
            self.store.set_locked(article["id"], want_locked)

    async def mirror_site_comments(self):
        for c in self.store.pending_site_comments():
            thread = await self._thread(c["forum_thread_id"])
            if thread is None:
                self.store.mark_mirrored(c["id"], None, ok=False)
                continue
            try:
                if thread.archived and not thread.locked:
                    await thread.edit(archived=False)
                msg = await thread.send(mirror_text(c["username"], c["body"]), allowed_mentions=NO_PINGS)
                self.store.mark_mirrored(c["id"], msg.id)
            except (discord.Forbidden, discord.NotFound) as e:
                logger.warning(f"Article comment {c['id']}: could not post to Discord: {e}")
                self.store.mark_mirrored(c["id"], None, ok=False)

    async def mirror_deletions(self):
        for c in self.store.pending_deletions():
            thread = await self._thread(c["forum_thread_id"])
            if thread is not None:
                try:
                    await thread.get_partial_message(int(c["discord_message_id"])).delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    logger.warning(f"Article comment {c['id']}: no permission to delete the Discord message")
            self.store.mark_mirror_deleted(c["id"])

    # ------------------------------------------------------------------
    # Discord -> site

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id or not isinstance(message.channel, discord.Thread):
            return
        if message.id == message.channel.id:
            return  # a forum post's opening message
        article = self.store.article_for_thread(message.channel.id)
        if not article or article["status"] != "approved":
            return
        body = comment_body(message)
        if not body:
            return
        self.store.add_discord_comment(
            article["id"], message.id, message.author.id,
            message.author.display_name, message.author.display_avatar.url, body,
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        message = payload.cached_message
        content = payload.data.get("content")
        if content is None:
            return
        if message is not None and message.author.bot:
            return
        body = content.strip()
        if message is not None:
            message.content = content
            body = comment_body(message)
        if body:
            self.store.edit_discord_comment(payload.message_id, body[:2000])

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        self.store.discord_message_deleted(payload.message_id)


async def setup(bot):
    await bot.add_cog(ArticleDiscussionsCog(bot))
