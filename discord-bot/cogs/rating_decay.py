"""Inactivity decay for Glicko-2 Avatar-mode seasons.

An avatar entry nobody has played for a week loses 10 points for each further
day until it plays again (rules in services/glicko2_season.py, DECAY_*). This
job takes what is owed off the live standings every few minutes, so the
leaderboard, !rank and the site always show the decayed number. Recording a
match and rebuilding a season apply the same rule, so nothing drifts if the
job is late.
"""

import logging
import sqlite3

from discord.ext import commands, tasks

from services import glicko2_season

logger = logging.getLogger(__name__)


def run_decay(db_path: str = "elo.db", now: str | None = None) -> list[dict]:
    """Apply decay owed for the active season. Returns the entries that moved."""
    conn = sqlite3.connect(db_path)
    try:
        event = glicko2_season.get_event(conn)
        moved = glicko2_season.apply_decay(conn, event, now)
        if moved:
            conn.commit()
        return moved
    finally:
        conn.close()


class RatingDecayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decay_job.start()

    def cog_unload(self):
        self.decay_job.cancel()

    @tasks.loop(minutes=10)
    async def decay_job(self):
        try:
            moved = run_decay()
        except sqlite3.Error as e:
            logger.warning("Inactivity decay skipped: %s", e)
            return
        except Exception:
            logger.error("Inactivity decay failed", exc_info=True)
            return
        for row in moved:
            logger.info(
                "Inactivity decay: user %s %s %s -> %s (-%d since last game)",
                row["user_id"], row["avatar"], row["before"], row["after"], row["decay"],
            )

    @decay_job.before_loop
    async def before_decay_job(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RatingDecayCog(bot))
