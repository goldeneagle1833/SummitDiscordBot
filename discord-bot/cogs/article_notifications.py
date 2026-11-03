"""Delivers player-article DMs queued by the web app.

The web app writes one row per DM into ``article_notifications`` in
web-app/articles.db:

- reviewers (ARTICLE_REVIEWER_IDS in the web app's env, else the admins) when
  an article is submitted, edited, or the author replies;
- the author (Discord logins only) when a reviewer comments, requests
  changes, approves or rejects.

This cog polls for pending rows every 30 seconds, sends each as an embed with
a link button back to the site, and marks it sent (or failed after a few
tries, or straight away when the user has DMs closed).
"""

import logging
import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands, tasks

import config

logger = logging.getLogger("discord_bot")

ARTICLES_DB_PATH = Path(
    os.environ.get(
        "ARTICLES_DB_PATH",
        Path(__file__).resolve().parent.parent.parent / "web-app" / "articles.db",
    )
)

MAX_ATTEMPTS = 5
ARTICLE_COLOR = discord.Color.from_rgb(212, 175, 55)


def site_url(link_path: str | None) -> str | None:
    if not link_path:
        return None
    base = str(getattr(config, "WEB_APP_URL", "") or "https://sorcererssummit.com").rstrip("/")
    return base + link_path


def fetch_pending(db_path: Path = ARTICLES_DB_PATH) -> list[dict]:
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(r) for r in conn.execute(
                """SELECT * FROM article_notifications
                   WHERE status = 'pending' AND attempts < ?
                   ORDER BY id ASC LIMIT 10""",
                (MAX_ATTEMPTS,),
            ).fetchall()
        ]
    except sqlite3.OperationalError:
        return []  # table not created yet: no article ever submitted
    finally:
        conn.close()


def mark(notification_id: int, success: bool, error: str | None = None,
         permanent: bool = False, db_path: Path = ARTICLES_DB_PATH):
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        if success:
            conn.execute(
                """UPDATE article_notifications
                   SET status = 'sent', sent_at = datetime('now'), attempts = attempts + 1
                   WHERE id = ?""",
                (notification_id,),
            )
        else:
            conn.execute(
                """UPDATE article_notifications
                   SET attempts = attempts + 1, last_error = ?,
                       status = CASE WHEN ? OR attempts + 1 >= ?
                                THEN 'failed' ELSE 'pending' END
                   WHERE id = ?""",
                (error, 1 if permanent else 0, MAX_ATTEMPTS, notification_id),
            )
        conn.commit()
    finally:
        conn.close()


def build_message(n: dict) -> tuple[discord.Embed, discord.ui.View | None]:
    url = site_url(n.get("link_path"))
    embed = discord.Embed(
        title=f"📝 {n['subject']}",
        description=(n.get("body") or "")[:4000],
        color=ARTICLE_COLOR,
        url=url,
    )
    embed.set_footer(text="Sorcerers Summit · Player Articles")
    view = None
    if url:
        view = discord.ui.View()
        label = "Review on the site" if n.get("audience") == "reviewer" else "Open on the site"
        view.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))
    return embed, view


async def deliver(bot, n: dict, db_path: Path = ARTICLES_DB_PATH):
    try:
        user = bot.get_user(int(n["recipient"]))
        if user is None:
            user = await bot.fetch_user(int(n["recipient"]))
        embed, view = build_message(n)
        if view is not None:
            await user.send(embed=embed, view=view)
        else:
            await user.send(embed=embed)
        mark(n["id"], True, db_path=db_path)
    except discord.Forbidden:
        mark(n["id"], False, "DMs closed (Forbidden)", permanent=True, db_path=db_path)
        logger.info(f"Article DM blocked for {n['recipient']} (notification {n['id']})")
    except discord.NotFound:
        mark(n["id"], False, "Recipient not found", permanent=True, db_path=db_path)
    except Exception as e:  # network blips: retried next loop
        mark(n["id"], False, str(e)[:500], db_path=db_path)
        logger.warning(f"Article notification {n['id']} delivery error: {e}")


class ArticleNotificationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.deliver_notifications.start()
        logger.info("ArticleNotificationsCog initialized")

    def cog_unload(self):
        self.deliver_notifications.cancel()

    @tasks.loop(seconds=30)
    async def deliver_notifications(self):
        try:
            pending = fetch_pending()
        except Exception as e:
            logger.error(f"Article notifications: fetch failed: {e}")
            return
        for n in pending:
            await deliver(self.bot, n)

    @deliver_notifications.before_loop
    async def before_deliver(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ArticleNotificationsCog(bot))
