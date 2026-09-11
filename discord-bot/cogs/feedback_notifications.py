import logging
import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("discord_bot")

FEEDBACK_DB_PATH = Path(
    os.environ.get(
        "FEEDBACK_DB_PATH",
        Path(__file__).resolve().parent.parent.parent / "web-app" / "feedback.db",
    )
)


class FeedbackNotificationsCog(commands.Cog):
    """DMs users when their feedback submission is resolved.

    The web app sets notified=0 when a feedback item moves to 'resolved'.
    This cog polls for those rows and sends a Discord DM to the submitter,
    then marks them notified.
    """

    def __init__(self, bot):
        self.bot = bot
        self.check_resolved.start()
        logger.info("FeedbackNotificationsCog initialized")

    def cog_unload(self):
        self.check_resolved.cancel()

    def _fetch_pending(self):
        if not FEEDBACK_DB_PATH.exists():
            return []
        conn = sqlite3.connect(FEEDBACK_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            return [
                dict(r) for r in conn.execute(
                    """SELECT * FROM feedback
                       WHERE status = 'resolved'
                         AND notified = 0
                         AND user_id IS NOT NULL"""
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()

    def _mark_notified(self, feedback_id: int):
        conn = sqlite3.connect(FEEDBACK_DB_PATH)
        try:
            conn.execute(
                "UPDATE feedback SET notified = 1 WHERE id = ?",
                (feedback_id,),
            )
            conn.commit()
        finally:
            conn.close()

    @tasks.loop(seconds=60)
    async def check_resolved(self):
        try:
            pending = self._fetch_pending()
        except Exception as e:
            logger.error(f"Feedback notifications: fetch failed: {e}")
            return

        for item in pending:
            try:
                user = self.bot.get_user(int(item["user_id"]))
                if user is None:
                    user = await self.bot.fetch_user(int(item["user_id"]))

                embed = discord.Embed(
                    title="Your Feedback Has Been Resolved!",
                    description=(
                        f"**{item['title']}**\n\n"
                        f"Your {item['type'].replace('_', ' ')} has been reviewed "
                        f"and marked as resolved by the Summit team."
                    ),
                    color=discord.Color.green(),
                )
                if item.get("admin_notes"):
                    embed.add_field(
                        name="Admin Notes",
                        value=item["admin_notes"][:1024],
                        inline=False,
                    )
                embed.set_footer(text="Sorcerers Summit Feedback")

                await user.send(embed=embed)
                self._mark_notified(item["id"])
                logger.info(
                    f"Feedback DM sent to {item['user_id']} for item {item['id']}"
                )
            except discord.Forbidden:
                self._mark_notified(item["id"])
                logger.info(
                    f"Feedback DM blocked for user {item['user_id']} "
                    f"(item {item['id']})"
                )
            except discord.NotFound:
                self._mark_notified(item["id"])
                logger.info(
                    f"Feedback user {item['user_id']} not found (item {item['id']})"
                )
            except Exception as e:
                logger.warning(
                    f"Feedback notification {item['id']} error: {e}"
                )

    @check_resolved.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(FeedbackNotificationsCog(bot))
