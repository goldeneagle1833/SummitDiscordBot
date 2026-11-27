"""Inactivity decay for Glicko-2 Avatar-mode seasons.

An avatar entry nobody has played for 10 days loses 10 points for each further
day until it plays again (rules in services/glicko2_season.py, DECAY_*). This
job takes what is owed off the live standings every few minutes, so the
leaderboard, !rank and the site always show the decayed number. Recording a
match and rebuilding a season apply the same rule, so nothing drifts if the
job is late.

A day before an avatar starts decaying, the player gets one DM about it
(once per idle stretch; playing that avatar resets it).
"""

import datetime
import logging
import sqlite3

import discord

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


def take_warnings(db_path: str = "elo.db", now: str | None = None) -> tuple[dict | None, list[dict]]:
    """Entries due a 24-hour warning, marked as sent (so each goes out once)."""
    conn = sqlite3.connect(db_path)
    try:
        event = glicko2_season.get_event(conn)
        warnings = glicko2_season.decay_warnings(conn, event, now)
        if warnings:
            glicko2_season.mark_decay_warned(conn, event, warnings)
            conn.commit()
        return event, warnings
    finally:
        conn.close()


def warning_text(event: dict, warnings: list[dict]) -> str:
    """One DM for all of a player's avatars that start decaying in the next day."""
    per_day = int(glicko2_season.DECAY_PER_DAY)
    lines = []
    for w in sorted(warnings, key=lambda w: w["starts_at"]):
        unix = int(datetime.datetime.fromisoformat(w["starts_at"]).timestamp())
        lines.append(f"- **{w['avatar']}** ({w['rating']}): starts <t:{unix}:R>")
    many = len(warnings) > 1
    return (
        f"⏳ **Rating decay heads-up ({event['event_name']})**\n"
        f"You haven't played {'these avatars' if many else 'this avatar'} in a ranked game for "
        f"{glicko2_season.DECAY_GRACE_DAYS} days. Starting tomorrow, "
        f"{'each one' if many else 'it'} loses {per_day} points a day until you play "
        f"{'it' if not many else 'that avatar'} again "
        f"(never below {int(glicko2_season.DECAY_FLOOR)}):\n" + "\n".join(lines)
    )


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
        await self._send_warnings()

    async def _send_warnings(self):
        try:
            event, warnings = take_warnings()
        except sqlite3.Error as e:
            logger.warning("Decay warnings skipped: %s", e)
            return
        by_user: dict[int, list[dict]] = {}
        for w in warnings:
            by_user.setdefault(w["user_id"], []).append(w)
        for user_id, items in by_user.items():
            try:
                user = await self.bot.fetch_user(int(user_id))
                await user.send(warning_text(event, items))
                logger.info("Decay warning sent to %s for %s", user_id, [w["avatar"] for w in items])
            except (discord.Forbidden, discord.NotFound):
                logger.info("Decay warning not delivered to %s (DMs closed or no user)", user_id)
            except Exception:
                logger.error("Decay warning to %s failed", user_id, exc_info=True)

    @decay_job.before_loop
    async def before_decay_job(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RatingDecayCog(bot))
