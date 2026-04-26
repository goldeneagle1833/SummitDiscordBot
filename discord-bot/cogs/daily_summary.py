"""Daily Summary cog — posts an automated recap of the day's competitive activity."""

import asyncio
import datetime
import logging
import sqlite3
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from openai import OpenAI

import config

logger = logging.getLogger("discord_bot")

EST = ZoneInfo("America/New_York")

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

DAILY_SUMMARY_PROMPT = (
    "You are a Discord bot writing a daily recap for Sorcery: Contested Realm, a competitive card game. "
    "You will receive raw stats as labeled lines. Your job is to rewrite EACH stat with personality and flair, "
    "plus write a short commentary intro (2-3 sentences, under 80 words).\n\n"
    "IMPORTANT: Vary your style every day. Rotate between these voices at random: "
    "Epic fantasy narrator, hype sports broadcaster, dry comedic observer, poetic bard, trash-talking arena announcer. "
    "Pick ONE style per day. Do not mix styles.\n\n"
    "OUTPUT FORMAT — follow this EXACTLY:\n"
    "COMMENTARY: [Your 2-3 sentence intro paragraph here]\n"
    "MATCHES_PLAYED: [Flavored version, must include the actual number]\n"
    "UNIQUE_PLAYERS: [Flavored version, must include the actual number]\n"
    "MOST_ACTIVE: [Flavored version, must include the player name and match count]\n"
    "TOP_GAINER: [Flavored version, must include the player name and ELO change]\n"
    "BIGGEST_LOSER: [Flavored version, must include the player name and ELO change]\n"
    "BIGGEST_UPSET: [Flavored version, must include both player names and ELO change]\n"
    "RIVALRY: [Flavored version, must include both player names and the record]\n"
    "HIGHEST_RATED: [Flavored version, must include both player names and combined ELO]\n"
    "IRONMAN: [Flavored version, must include the total hours — this is the combined gameplay time across ALL players today, not a single player]\n"
    "DECK_VARIETY: [Flavored version, must include player name and deck count]\n"
    "HOT_STREAKS: [Flavored version, must include player names and streak counts]\n"
    "STREAK_BROKEN: [Flavored version, must include player names and streak count]\n"
    "AVG_DURATION: [Flavored version, must include the duration in minutes]\n\n"
    "RULES:\n"
    "- Only include labels that appear in the input. Skip labels for stats not provided.\n"
    "- Each line must start with the label followed by a colon.\n"
    "- Keep each field SHORT (under 100 characters). The commentary can be longer.\n"
    "- NO emojis anywhere.\n"
    "- You MUST include the actual numbers/names from the input — add flair around them, don't replace them.\n"
    "- If no matches were played, only output COMMENTARY with a short 'quiet day' message."
)


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

        # GPT-flavored stats
        stats_text = self._format_stats_for_gpt(stats)
        gpt = await asyncio.to_thread(self._generate_commentary, stats_text)
        if gpt is None:
            gpt = {}

        if stats["total_matches"] == 0:
            embed.description = gpt.get("COMMENTARY", "No ranked matches were played today.")
            logger.info("Zero-match day — posting quiet-day summary.")
            await channel.send(embed=embed)
            return

        # Commentary intro
        if gpt.get("COMMENTARY"):
            embed.description = _truncate(gpt["COMMENTARY"], 200)

        # Core stats — GPT-flavored values with raw fallbacks
        embed.add_field(
            name="⚔️ Matches Played",
            value=_truncate(gpt.get("MATCHES_PLAYED", str(stats["total_matches"])), 200),
            inline=True,
        )

        if stats.get("unique_players"):
            embed.add_field(
                name="🎮 Unique Players",
                value=_truncate(gpt.get("UNIQUE_PLAYERS", str(stats["unique_players"])), 200),
                inline=True,
            )

        if stats.get("most_active"):
            user_id, name, count = stats["most_active"]
            embed.add_field(
                name="👑 Most Active Player",
                value=_truncate(gpt.get("MOST_ACTIVE", f"<@{user_id}> ({count} matches)"), 200),
                inline=False,
            )

        if stats.get("top_gainer"):
            user_id, name, change = stats["top_gainer"]
            embed.add_field(
                name="📈 Top ELO Gainer",
                value=_truncate(gpt.get("TOP_GAINER", f"<@{user_id}> (+{change} ELO)"), 200),
                inline=True,
            )

        if stats.get("biggest_loser"):
            user_id, name, change = stats["biggest_loser"]
            embed.add_field(
                name="📉 Biggest ELO Drop",
                value=_truncate(gpt.get("BIGGEST_LOSER", f"<@{user_id}> ({change} ELO)"), 200),
                inline=True,
            )

        # Extended stats
        if stats.get("biggest_upset"):
            winner_id, winner_name, loser_id, loser_name, change = stats["biggest_upset"]
            embed.add_field(
                name="🎯 Biggest Upset",
                value=_truncate(gpt.get("BIGGEST_UPSET", f"<@{winner_id}> beat <@{loser_id}> (+{change} ELO)"), 200),
                inline=False,
            )

        if stats.get("rivalry"):
            p1_id, p1, p2_id, p2, p1w, p2w, total = stats["rivalry"]
            embed.add_field(
                name="⚔️ Rivalry of the Day",
                value=_truncate(
                    gpt.get("RIVALRY", f"<@{p1_id}> vs <@{p2_id}> — {p1w}-{p2w} ({total} games)"), 200
                ),
                inline=False,
            )

        if stats.get("highest_rated"):
            w_id, w_name, l_id, l_name, w_elo, l_elo = stats["highest_rated"]
            embed.add_field(
                name="🏆 Highest Rated Match",
                value=_truncate(
                    gpt.get("HIGHEST_RATED", f"<@{w_id}> ({w_elo}) vs <@{l_id}> ({l_elo})"), 200
                ),
                inline=False,
            )

        if stats.get("ironman"):
            total_hours = stats["ironman"]
            embed.add_field(
                name="🦾 Total Sorcery",
                value=_truncate(
                    gpt.get("IRONMAN", f"{total_hours} hours of Sorcery have been played today"), 200
                ),
                inline=True,
            )

        if stats.get("deck_variety"):
            user_id, name, count = stats["deck_variety"]
            embed.add_field(
                name="🎴 Deck Variety",
                value=_truncate(
                    gpt.get("DECK_VARIETY", f"<@{user_id}> played {count} different decks"), 200
                ),
                inline=True,
            )

        if stats.get("hot_streaks"):
            fallback_lines = []
            for user_id, name, streak in stats["hot_streaks"][:5]:
                fallback_lines.append(f"<@{user_id}> is on a {streak}-win streak")
            if len(stats["hot_streaks"]) > 5:
                fallback_lines.append(f"and {len(stats['hot_streaks']) - 5} more...")
            embed.add_field(
                name="🔥 Hot Streaks",
                value=_truncate(gpt.get("HOT_STREAKS", "\n".join(fallback_lines)), 200),
                inline=False,
            )

        if stats.get("broken_streaks"):
            fallback_lines = []
            for entry in stats["broken_streaks"][:5]:
                fallback_lines.append(f"<@{entry['player_id']}>'s {entry['streak']}-win streak was ended by <@{entry['broken_by_id']}>")
            embed.add_field(
                name="💔 Streak Broken",
                value=_truncate(gpt.get("STREAK_BROKEN", "\n".join(fallback_lines)), 200),
                inline=False,
            )

        if stats.get("avg_duration") is not None:
            embed.add_field(
                name="⏱️ Avg Match Duration",
                value=_truncate(gpt.get("AVG_DURATION", f"{round(stats['avg_duration'])} min"), 200),
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

            # 1. Total matches
            cur.execute(
                "SELECT COUNT(*) FROM match_records WHERE timestamp LIKE ? AND match_type = 'ranked'",
                (date_prefix,),
            )
            stats["total_matches"] = cur.fetchone()[0]

            if stats["total_matches"] == 0:
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

    # ------------------------------------------------------------------
    # GPT commentary
    # ------------------------------------------------------------------

    def _format_stats_for_gpt(self, stats: dict) -> str:
        """Convert stats dict into human-readable text for GPT input."""
        if stats["total_matches"] == 0:
            return "No matches were played today."

        lines = [
            "Today's stats:",
            f"- {stats['total_matches']} ranked matches played",
        ]

        if stats.get("unique_players"):
            lines.append(f"- {stats['unique_players']} unique players")

        if stats.get("most_active"):
            user_id, name, count = stats["most_active"]
            lines.append(f"- Most active: {name} ({count} matches)")

        if stats.get("top_gainer"):
            user_id, name, change = stats["top_gainer"]
            lines.append(f"- Top ELO gainer: {name} (+{change})")

        if stats.get("biggest_loser"):
            user_id, name, change = stats["biggest_loser"]
            lines.append(f"- Biggest ELO drop: {name} ({change})")

        if stats.get("biggest_upset"):
            winner_id, winner_name, loser_id, loser_name, change = stats["biggest_upset"]
            lines.append(f"- Biggest upset: {winner_name} beat {loser_name} (+{change} ELO gain)")

        if stats.get("rivalry"):
            p1_id, p1, p2_id, p2, p1w, p2w, total = stats["rivalry"]
            lines.append(f"- Rivalry of the day: {p1} vs {p2}, {p1w}-{p2w} record ({total} games)")

        if stats.get("highest_rated"):
            w_id, w_name, l_id, l_name, w_elo, l_elo = stats["highest_rated"]
            lines.append(f"- Highest rated match: {w_name} ({w_elo} ELO) vs {l_name} ({l_elo} ELO)")

        if stats.get("ironman"):
            total_hours = stats["ironman"]
            lines.append(f"- Total Sorcery: {total_hours} hours of gameplay today")

        if stats.get("deck_variety"):
            user_id, name, count = stats["deck_variety"]
            lines.append(f"- Deck variety: {name} played {count} different decks today")

        if stats.get("hot_streaks"):
            streaks = ", ".join(f"{name} ({n}-win streak)" for user_id, name, n in stats["hot_streaks"][:5])
            lines.append(f"- Hot streaks: {streaks}")

        if stats.get("broken_streaks"):
            for entry in stats["broken_streaks"][:3]:
                lines.append(f"- Streak broken: {entry['player']}'s {entry['streak']}-win streak ended by {entry['broken_by']}")

        if stats.get("avg_duration") is not None:
            lines.append(f"- Avg match duration: {round(stats['avg_duration'])} min")

        return "\n".join(lines)

    def _generate_commentary(self, stats_text: str):
        """Generate GPT-flavored stats from raw stats text. Returns parsed dict or None."""
        try:
            response = openai_client.responses.create(
                model="gpt-4.1-nano",
                instructions=DAILY_SUMMARY_PROMPT,
                input=stats_text,
            )
            logger.info("GPT commentary generated successfully")
            return self._parse_gpt_response(response.output_text)
        except Exception as e:
            logger.error(f"OpenAI API error for daily summary: {e}")
            return None

    @staticmethod
    def _parse_gpt_response(text: str) -> dict:
        """Parse labeled GPT output into a dict keyed by label."""
        result = {}
        for line in text.strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().upper()
                value = value.strip()
                if key and value:
                    result[key] = value
        return result


async def setup(bot):
    await bot.add_cog(DailySummaryCog(bot))
