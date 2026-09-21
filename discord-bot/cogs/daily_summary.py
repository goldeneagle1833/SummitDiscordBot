"""Daily Summary cog — posts an automated recap of the day's competitive activity."""

import asyncio
import datetime
import logging
import sqlite3
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

import config

logger = logging.getLogger("discord_bot")

EST = ZoneInfo("America/New_York")


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding '...' if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


class DailySummaryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_summary_task.start()

    def cog_unload(self):
        self.daily_summary_task.cancel()

    @tasks.loop(
        time=datetime.time(
            hour=config.DAILY_SUMMARY_HOUR,
            minute=config.DAILY_SUMMARY_MINUTE,
            tzinfo=EST,
        )
    )
    async def daily_summary_task(self):
        logger.info("Daily summary task firing...")
        try:
            await self._post_daily_summary()
        except Exception:
            logger.error("Daily summary task failed", exc_info=True)

    @daily_summary_task.before_loop
    async def before_daily_summary(self):
        await self.bot.wait_until_ready()
        next_run = self.daily_summary_task.next_iteration
        logger.info(f"Daily summary task is ready — next run: {next_run}")

    # ------------------------------------------------------------------
    # Admin command
    # ------------------------------------------------------------------

    @commands.command(name="daily_summary")
    @commands.has_permissions(administrator=True)
    async def trigger_summary(self, ctx):
        """Manually trigger the daily summary (admin only)."""
        await self._post_daily_summary(channel_override=ctx.channel)

    # ------------------------------------------------------------------
    # Core orchestrator
    # ------------------------------------------------------------------

    async def _post_daily_summary(self, channel_override=None):
        est_now = datetime.datetime.now(EST)
        date_prefix = f"{est_now.strftime('%Y-%m-%d')}%"
        date_display = est_now.strftime("%B %d, %Y")

        logger.info(f"Running daily summary for {date_display}...")

        channel = channel_override or self.bot.get_channel(config.DAILY_SUMMARY_CHANNEL_ID)
        if channel is None:
            logger.error("Daily summary channel not found — cannot post summary.")
            return

        # Gather stats
        stats = await asyncio.to_thread(self._query_stats, date_prefix)
        streak_data = await asyncio.to_thread(self._compute_streaks, date_prefix)
        stats.update(streak_data)

        # Build embed
        embed = discord.Embed(
            title=f"Daily Summary — {date_display}",
            color=0xFFD700,
        )
        embed.set_footer(text="Summit Bot • Matches tracked since midnight EST")

        all_zero = stats["total_matches"] == 0 and stats["casual_matches"] == 0 and stats["limited_matches"] == 0 and stats["rumble_matches"] == 0
        if all_zero:
            embed.description = "No matches were played today."
            logger.info("Zero-match day — posting quiet-day summary.")
            await channel.send(embed=embed)
            return

        # Core stats
        if stats["total_matches"]:
            embed.add_field(
                name="⚔️ Ranked Matches",
                value=_truncate(str(stats["total_matches"]), 200),
                inline=True,
            )

        if stats["casual_matches"]:
            embed.add_field(
                name="🎲 Casual Matches",
                value=_truncate(str(stats["casual_matches"]), 200),
                inline=True,
            )

        if stats["limited_matches"]:
            embed.add_field(
                name="📦 Limited Matches",
                value=_truncate(str(stats["limited_matches"]), 200),
                inline=True,
            )

        if stats["rumble_matches"]:
            embed.add_field(
                name="💥 Rumble Matches",
                value=_truncate(str(stats["rumble_matches"]), 200),
                inline=True,
            )

        if stats.get("unique_players"):
            embed.add_field(
                name="🎮 Unique Players",
                value=_truncate(str(stats["unique_players"]), 200),
                inline=True,
            )

        if stats.get("most_active"):
            user_id, name, count = stats["most_active"]
            embed.add_field(
                name="👑 Most Active Player",
                value=_truncate(f"<@{user_id}> ({count} matches)", 200),
                inline=False,
            )

        if stats.get("top_gainer"):
            user_id, name, change = stats["top_gainer"]
            embed.add_field(
                name="📈 Top ELO Gainer",
                value=_truncate(f"<@{user_id}> (+{change} ELO)", 200),
                inline=True,
            )

        if stats.get("biggest_loser"):
            user_id, name, change = stats["biggest_loser"]
            embed.add_field(
                name="📉 Biggest ELO Drop",
                value=_truncate(f"<@{user_id}> ({change} ELO)", 200),
                inline=True,
            )

        # Extended stats
        if stats.get("biggest_upset"):
            winner_id, winner_name, loser_id, loser_name, change = stats["biggest_upset"]
            embed.add_field(
                name="🎯 Biggest Upset",
                value=_truncate(f"<@{winner_id}> beat <@{loser_id}> (+{change} ELO)", 200),
                inline=False,
            )

        if stats.get("rivalry"):
            p1_id, p1, p2_id, p2, p1w, p2w, total = stats["rivalry"]
            embed.add_field(
                name="⚔️ Rivalry of the Day",
                value=_truncate(
                    f"<@{p1_id}> vs <@{p2_id}> — {p1w}-{p2w} ({total} games)", 200
                ),
                inline=False,
            )

        if stats.get("highest_rated"):
            w_id, w_name, l_id, l_name, w_elo, l_elo = stats["highest_rated"]
            embed.add_field(
                name="🏆 Highest Rated Match",
                value=_truncate(
                    f"<@{w_id}> ({w_elo}) vs <@{l_id}> ({l_elo})", 200
                ),
                inline=False,
            )

        if stats.get("ironman"):
            total_hours = stats["ironman"]
            embed.add_field(
                name="🦾 Total Sorcery",
                value=_truncate(
                    f"{total_hours} hours of Sorcery have been played today", 200
                ),
                inline=True,
            )

        if stats.get("deck_variety"):
            user_id, name, count = stats["deck_variety"]
            embed.add_field(
                name="🎴 Deck Variety",
                value=_truncate(
                    f"<@{user_id}> played {count} different decks", 200
                ),
                inline=True,
            )

        if stats.get("hot_streaks"):
            lines_out = []
            for user_id, name, streak in stats["hot_streaks"][:5]:
                lines_out.append(f"<@{user_id}> is on a {streak}-win streak")
            if len(stats["hot_streaks"]) > 5:
                lines_out.append(f"and {len(stats['hot_streaks']) - 5} more...")
            embed.add_field(
                name="🔥 Hot Streaks",
                value=_truncate("\n".join(lines_out), 200),
                inline=False,
            )

        if stats.get("broken_streaks"):
            lines_out = []
            for entry in stats["broken_streaks"][:5]:
                lines_out.append(f"<@{entry['player_id']}>'s {entry['streak']}-win streak was ended by <@{entry['broken_by_id']}>")
            embed.add_field(
                name="💔 Streak Broken",
                value=_truncate("\n".join(lines_out), 200),
                inline=False,
            )

        if stats.get("avg_duration") is not None:
            embed.add_field(
                name="⏱️ Avg Match Duration",
                value=_truncate(f"{round(stats['avg_duration'])} min", 200),
                inline=True,
            )

        await channel.send(embed=embed)
        logger.info(f"Daily summary posted to #{channel.name}")

    # ------------------------------------------------------------------
    # Database queries
    # ------------------------------------------------------------------

    def _query_stats(self, date_prefix: str) -> dict:
        """Query core and extended stats from match_records.db. Runs in a thread."""
        stats = {
            "total_matches": 0,
            "casual_matches": 0,
            "limited_matches": 0,
            "rumble_matches": 0,
            "most_active": None,
            "top_gainer": None,
            "biggest_loser": None,
            "unique_players": None,
            "avg_duration": None,
            "biggest_upset": None,
            "rivalry": None,
            "highest_rated": None,
            "ironman": None,
            "deck_variety": None,
        }

        conn = sqlite3.connect("match_records.db")
        try:
            cur = conn.cursor()

            # 1. Total matches (ranked)
            cur.execute(
                "SELECT COUNT(*) FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'",
                (date_prefix,),
            )
            stats["total_matches"] = cur.fetchone()[0]

            # 1b. Casual match count — count pairings (not just reported matches)
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM active_pairings WHERE created_at LIKE ? AND match_type = 'testing'",
                    (date_prefix,),
                )
                stats["casual_matches"] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                stats["casual_matches"] = 0

            # 1c. Limited match count — stored in limited_match_records table
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM limited_match_records WHERE timestamp LIKE ?",
                    (date_prefix,),
                )
                stats["limited_matches"] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                stats["limited_matches"] = 0

            # 1d. Rumble match count
            cur.execute(
                "SELECT COUNT(*) FROM match_records WHERE timestamp LIKE ? AND match_type = 'rumble'",
                (date_prefix,),
            )
            stats["rumble_matches"] = cur.fetchone()[0]

            if stats["total_matches"] == 0 and stats["casual_matches"] == 0 and stats["limited_matches"] == 0 and stats["rumble_matches"] == 0:
                return stats

            # 2. Most active player
            cur.execute(
                """
                SELECT player_id, player_name, COUNT(*) as match_count FROM (
                    SELECT winner_id as player_id, winner_display_name as player_name
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                ) GROUP BY player_id ORDER BY match_count DESC LIMIT 1
                """,
                (date_prefix, date_prefix),
            )
            row = cur.fetchone()
            if row:
                stats["most_active"] = (row[0], row[1], row[2])  # (user_id, name, count)

            # 3. Top ELO gainer (net across all matches)
            cur.execute(
                """
                SELECT player_id, player_name, SUM(elo_change) as net_change FROM (
                    SELECT winner_id as player_id, winner_display_name as player_name,
                           winner_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                                             AND winner_lifetime_elo_change IS NOT NULL
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name,
                           loser_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                                             AND loser_lifetime_elo_change IS NOT NULL
                ) GROUP BY player_id ORDER BY net_change DESC LIMIT 1
                """,
                (date_prefix, date_prefix),
            )
            row = cur.fetchone()
            if row:
                stats["top_gainer"] = (row[0], row[1], row[2])  # (user_id, name, change)

            # 5. Biggest ELO loser
            cur.execute(
                """
                SELECT player_id, player_name, SUM(elo_change) as net_change FROM (
                    SELECT winner_id as player_id, winner_display_name as player_name,
                           winner_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                                             AND winner_lifetime_elo_change IS NOT NULL
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name,
                           loser_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'
                                             AND loser_lifetime_elo_change IS NOT NULL
                ) GROUP BY player_id ORDER BY net_change ASC LIMIT 1
                """,
                (date_prefix, date_prefix),
            )
            row = cur.fetchone()
            if row and row[2] < 0:
                stats["biggest_loser"] = (row[0], row[1], row[2])  # (user_id, name, change)

            # 6. Unique players
            cur.execute(
                """
                SELECT COUNT(DISTINCT player_id) FROM (
                    SELECT winner_id as player_id FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                    UNION
                    SELECT losser_id as player_id FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                )
                """,
                (date_prefix, date_prefix),
            )
            stats["unique_players"] = cur.fetchone()[0]

            # 7. Average match duration
            cur.execute(
                "SELECT AVG(match_time) FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked' AND match_time > 0",
                (date_prefix,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                stats["avg_duration"] = row[0]

            # 8. Biggest upset (highest winner_lifetime_elo_change = lower-rated winner)
            cur.execute(
                """
                SELECT winner_id, winner_display_name, losser_id, losser_display_name, winner_lifetime_elo_change
                FROM match_records
                WHERE timestamp LIKE ? AND match_type = 'ranked'
                      AND winner_lifetime_elo_change IS NOT NULL
                      AND winner_lifetime_elo_change > 0
                ORDER BY winner_lifetime_elo_change DESC LIMIT 1
                """,
                (date_prefix,),
            )
            row = cur.fetchone()
            if row:
                stats["biggest_upset"] = (row[0], row[1], row[2], row[3], row[4])  # (winner_id, winner_name, loser_id, loser_name, change)

            # 9. Rivalry of the Day (pair who played each other most, min 2)
            cur.execute(
                """
                SELECT
                    MIN(winner_id, losser_id) as p1_id,
                    MAX(winner_id, losser_id) as p2_id,
                    COUNT(*) as match_count
                FROM match_records
                WHERE timestamp LIKE ? AND match_type = 'ranked'
                GROUP BY p1_id, p2_id
                HAVING match_count >= 2
                ORDER BY match_count DESC LIMIT 1
                """,
                (date_prefix,),
            )
            pair = cur.fetchone()
            if pair:
                p1_id, p2_id, total = pair
                cur.execute(
                    """
                    SELECT winner_id, winner_display_name, losser_display_name
                    FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                          AND ((winner_id = ? AND losser_id = ?)
                               OR (winner_id = ? AND losser_id = ?))
                    """,
                    (date_prefix, p1_id, p2_id, p2_id, p1_id),
                )
                rivalry_matches = cur.fetchall()
                p1_wins = sum(1 for m in rivalry_matches if m[0] == p1_id)
                p2_wins = total - p1_wins
                p1_name = next(
                    (m[1] if m[0] == p1_id else m[2] for m in rivalry_matches), None
                )
                p2_name = next(
                    (m[1] if m[0] == p2_id else m[2] for m in rivalry_matches), None
                )
                if p1_name and p2_name:
                    stats["rivalry"] = (p1_id, p1_name, p2_id, p2_name, p1_wins, p2_wins, total)

            # 10. Highest Rated Match (highest combined ELO)
            try:
                cur.execute("ATTACH DATABASE 'elo.db' AS elo_db")
                cur.execute(
                    """
                    SELECT m.winner_id, m.winner_display_name, m.losser_id, m.losser_display_name,
                           COALESCE(w.online_elo, w.elo, 1500) as winner_elo,
                           COALESCE(l.online_elo, l.elo, 1500) as loser_elo
                    FROM match_records m
                    LEFT JOIN elo_db.overall_standings w ON w.user_id = m.winner_id
                    LEFT JOIN elo_db.overall_standings l ON l.user_id = m.losser_id
                    WHERE m.timestamp LIKE ? AND m.match_type = 'ranked'
                    ORDER BY (COALESCE(w.online_elo, w.elo, 1500)
                              + COALESCE(l.online_elo, l.elo, 1500)) DESC
                    LIMIT 1
                    """,
                    (date_prefix,),
                )
                row = cur.fetchone()
                if row:
                    stats["highest_rated"] = (row[0], row[1], row[2], row[3], row[4], row[5])  # (w_id, w_name, l_id, l_name, w_elo, l_elo)
                cur.execute("DETACH DATABASE elo_db")
            except Exception:
                logger.debug("Could not query highest rated match", exc_info=True)

            # 11. Ironman (total hours of Sorcery played today)
            cur.execute(
                """
                SELECT ROUND(SUM(match_time) / 60.0, 1) as total_hours
                FROM match_records
                WHERE timestamp LIKE ? AND match_type = 'ranked' AND match_time > 0
                """,
                (date_prefix,),
            )
            row = cur.fetchone()
            if row and row[0]:
                stats["ironman"] = row[0]  # total hours

            # 12. Deck Variety (most different decks used, min 2)
            cur.execute(
                """
                SELECT player_id, player_name, COUNT(DISTINCT deck_url) as deck_count FROM (
                    SELECT winner_id as player_id,
                           winner_display_name as player_name,
                           curiosa_url_winner as deck_url
                    FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                          AND curiosa_url_winner IS NOT NULL
                          AND curiosa_url_winner != ''
                    UNION ALL
                    SELECT losser_id as player_id,
                           losser_display_name as player_name,
                           curiosa_url_loser as deck_url
                    FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                          AND curiosa_url_loser IS NOT NULL
                          AND curiosa_url_loser != ''
                )
                GROUP BY player_id
                HAVING deck_count >= 2
                ORDER BY deck_count DESC LIMIT 1
                """,
                (date_prefix, date_prefix),
            )
            row = cur.fetchone()
            if row:
                stats["deck_variety"] = (row[0], row[1], row[2])  # (user_id, name, count)

        finally:
            conn.close()

        return stats

    # ------------------------------------------------------------------
    # Streak detection
    # ------------------------------------------------------------------

    def _compute_streaks(self, date_prefix: str) -> dict:
        """Compute hot streaks and broken streaks. Runs in a thread."""
        result = {"hot_streaks": [], "broken_streaks": []}

        conn = sqlite3.connect("match_records.db")
        try:
            cur = conn.cursor()

            # Get distinct player IDs from today
            cur.execute(
                """
                SELECT DISTINCT player_id FROM (
                    SELECT winner_id as player_id FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                    UNION
                    SELECT losser_id as player_id FROM match_records
                    WHERE timestamp LIKE ? AND match_type = 'ranked'
                )
                """,
                (date_prefix, date_prefix),
            )
            player_ids = [row[0] for row in cur.fetchall()]

            for player_id in player_ids:
                # Fetch last 20 matches for this player
                cur.execute(
                    """
                    SELECT winner_id, losser_id, winner_display_name, losser_display_name, timestamp
                    FROM match_records
                    WHERE (winner_id = ? OR losser_id = ?) AND match_type = 'ranked'
                    ORDER BY timestamp DESC LIMIT 20
                    """,
                    (player_id, player_id),
                )
                matches = cur.fetchall()

                if not matches:
                    continue

                # Get player display name from most recent match
                if matches[0][0] == player_id:
                    player_name = matches[0][2]
                else:
                    player_name = matches[0][3]

                # Hot streak: count consecutive wins from most recent
                current_streak = 0
                for m in matches:
                    if m[0] == player_id:  # player is winner
                        current_streak += 1
                    else:
                        break

                if current_streak >= 3:
                    result["hot_streaks"].append((player_id, player_name, current_streak))

                # Broken streak: did this player lose today and have a 6+ streak before that loss?
                # Find the first loss today
                today_prefix = date_prefix.rstrip("%")
                first_loss_idx = None
                for i, m in enumerate(matches):
                    if m[1] == player_id and m[4].startswith(today_prefix):  # player is loser, today
                        first_loss_idx = i
                        # Don't break — we want the most recent loss today (lowest index)
                        break

                if first_loss_idx is not None:
                    # Count consecutive wins BEFORE this loss
                    pre_loss_streak = 0
                    for m in matches[first_loss_idx + 1 :]:
                        if m[0] == player_id:  # player won
                            pre_loss_streak += 1
                        else:
                            break

                    if pre_loss_streak >= 6:
                        # Who broke it? The winner of the loss match
                        loss_match = matches[first_loss_idx]
                        broken_by_id = loss_match[0]  # winner_id
                        broken_by = loss_match[2]  # winner_display_name
                        result["broken_streaks"].append(
                            {"player_id": player_id, "player": player_name, "streak": pre_loss_streak, "broken_by_id": broken_by_id, "broken_by": broken_by}
                        )

            # Sort hot streaks by length descending
            result["hot_streaks"].sort(key=lambda x: x[2], reverse=True)

        finally:
            conn.close()

        return result


async def setup(bot):
    await bot.add_cog(DailySummaryCog(bot))
