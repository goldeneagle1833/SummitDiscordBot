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
WEB_APP_URL = getattr(config, "WEB_APP_URL", "https://sorcererssummit.com").rstrip("/")
SUNDAY = 6  # datetime.weekday()

MATCH_TYPES = (
    ("total_matches", "Ranked"),
    ("casual_matches", "Casual"),
    ("limited_matches", "Limited"),
    ("rumble_matches", "Rumble"),
)


def _player(guild, user_id, name) -> str:
    """Format a player as a bold link to their site profile plus a mention.

    Mentions in embeds render as raw ``<@id>`` when the viewer's client hasn't
    cached that user, so the name is always shown as plain text too. The live
    server display name is preferred over the name stored with the match.
    """
    member = guild.get_member(int(user_id)) if guild and str(user_id).isdigit() else None
    display = member.display_name if member else (name or "Unknown")
    # Square brackets would break the masked link
    display = discord.utils.escape_markdown(display).replace("[", "(").replace("]", ")")
    return f"[**{display}**]({WEB_APP_URL}/player/{user_id}) (<@{user_id}>)"


def _join_lines(lines, max_len: int = 1024) -> str:
    """Join lines for an embed field, dropping whole lines instead of cutting
    one in half (a cut mention shows up as broken text)."""
    out = []
    used = 0
    for i, line in enumerate(lines):
        extra = len(line) + (1 if out else 0)
        if used + extra > max_len - 20:
            out.append(f"…and {len(lines) - i} more")
            break
        out.append(line)
        used += extra
    return "\n".join(out)


def _total(counts: dict) -> int:
    return sum(counts.get(key) or 0 for key, _ in MATCH_TYPES)


def _delta(current: int, previous: int) -> str:
    """Return '▲ 3', '▼ 2' or '±0' for the change from previous to current."""
    diff = (current or 0) - (previous or 0)
    if diff > 0:
        return f"▲ {diff}"
    if diff < 0:
        return f"▼ {-diff}"
    return "±0"


def _period(kind: str, today: datetime.date) -> dict:
    """Date range [start, end) for the recap plus the matching previous period."""
    days = 7 if kind == "weekly" else 1
    end = today + datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=days)
    prev_start = start - datetime.timedelta(days=days)
    if kind == "weekly":
        title = f"📆 Weekly Recap — {start.strftime('%b %d')} to {today.strftime('%b %d, %Y')}"
        compare_label = "last week"
        footer = "Summit Bot • Matches tracked over the last 7 days (EST)"
    else:
        title = f"📊 Daily Recap — {today.strftime('%A, %B %d, %Y')}"
        compare_label = "yesterday"
        footer = "Summit Bot • Matches tracked since midnight EST"
    return {
        "kind": kind,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "prev_start": prev_start.isoformat(),
        "prev_end": start.isoformat(),
        "title": title,
        "compare_label": compare_label,
        "footer": footer,
    }


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
            await self._post_summary("daily")
        except Exception:
            logger.error("Daily summary task failed", exc_info=True)

        # Sunday night also gets the weekly recap, right after the daily one
        if datetime.datetime.now(EST).weekday() == SUNDAY:
            logger.info("Sunday — posting weekly recap...")
            try:
                await self._post_summary("weekly")
            except Exception:
                logger.error("Weekly summary failed", exc_info=True)

    @daily_summary_task.before_loop
    async def before_daily_summary(self):
        await self.bot.wait_until_ready()
        next_run = self.daily_summary_task.next_iteration
        logger.info(f"Daily summary task is ready — next run: {next_run}")

    # ------------------------------------------------------------------
    # Admin commands
    # ------------------------------------------------------------------

    @commands.command(name="daily_summary")
    @commands.has_permissions(administrator=True)
    async def trigger_summary(self, ctx):
        """Manually trigger the daily summary (admin only)."""
        await self._post_summary("daily", channel_override=ctx.channel)

    @commands.command(name="weekly_summary")
    @commands.has_permissions(administrator=True)
    async def trigger_weekly_summary(self, ctx):
        """Manually trigger the weekly recap for the last 7 days (admin only)."""
        await self._post_summary("weekly", channel_override=ctx.channel)

    # ------------------------------------------------------------------
    # Core orchestrator
    # ------------------------------------------------------------------

    async def _post_summary(self, kind: str, channel_override=None):
        period = _period(kind, datetime.datetime.now(EST).date())
        logger.info(f"Running {kind} summary for {period['start']} to {period['end']}...")

        channel = channel_override or self.bot.get_channel(config.DAILY_SUMMARY_CHANNEL_ID)
        if channel is None:
            logger.error("Daily summary channel not found — cannot post summary.")
            return

        # Gather stats
        stats = await asyncio.to_thread(self._query_stats, period["start"], period["end"])
        streak_data = await asyncio.to_thread(self._compute_streaks, period["start"], period["end"])
        stats.update(streak_data)
        previous = await asyncio.to_thread(self._query_counts, period["prev_start"], period["prev_end"])

        embed = _build_embed(period, stats, previous, getattr(channel, "guild", None))
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        logger.info(f"{kind.capitalize()} summary posted to #{channel.name}")

    # ------------------------------------------------------------------
    # Database queries
    # ------------------------------------------------------------------

    def _query_counts(self, start: str, end: str) -> dict:
        """Query only match/player counts for a period (used for comparisons). Runs in a thread."""
        conn = sqlite3.connect("match_records.db")
        try:
            return self._count_activity(conn.cursor(), start, end)
        finally:
            conn.close()

    @staticmethod
    def _count_activity(cur, start: str, end: str) -> dict:
        """Match counts per type plus unique ranked players for [start, end)."""
        counts = {}

        # Ranked matches
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'",
            (start, end),
        )
        counts["total_matches"] = cur.fetchone()[0]

        # Casual match count — count pairings (not just reported matches)
        try:
            cur.execute(
                "SELECT COUNT(*) FROM active_pairings WHERE created_at >= ? AND created_at < ? AND match_type = 'testing'",
                (start, end),
            )
            counts["casual_matches"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            counts["casual_matches"] = 0

        # Limited match count — stored in limited_match_records table
        try:
            cur.execute(
                "SELECT COUNT(*) FROM limited_match_records WHERE timestamp >= ? AND timestamp < ?",
                (start, end),
            )
            counts["limited_matches"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            counts["limited_matches"] = 0

        # Rumble match count
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'rumble'",
            (start, end),
        )
        counts["rumble_matches"] = cur.fetchone()[0]

        # Unique ranked players
        cur.execute(
            """
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT winner_id as player_id FROM match_records
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                UNION
                SELECT losser_id as player_id FROM match_records
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
            )
            """,
            (start, end, start, end),
        )
        counts["unique_players"] = cur.fetchone()[0]

        return counts

    def _query_stats(self, start: str, end: str) -> dict:
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
            "busiest_day": None,
        }

        conn = sqlite3.connect("match_records.db")
        try:
            cur = conn.cursor()

            stats.update(self._count_activity(cur, start, end))

            if stats["total_matches"] == 0 and stats["casual_matches"] == 0 and stats["limited_matches"] == 0 and stats["rumble_matches"] == 0:
                return stats

            # 2. Most active player
            cur.execute(
                """
                SELECT player_id, player_name, COUNT(*) as match_count FROM (
                    SELECT winner_id as player_id, winner_display_name as player_name
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                ) GROUP BY player_id ORDER BY match_count DESC LIMIT 1
                """,
                (start, end, start, end),
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
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                                             AND winner_lifetime_elo_change IS NOT NULL
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name,
                           loser_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                                             AND loser_lifetime_elo_change IS NOT NULL
                ) GROUP BY player_id ORDER BY net_change DESC LIMIT 1
                """,
                (start, end, start, end),
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
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                                             AND winner_lifetime_elo_change IS NOT NULL
                    UNION ALL
                    SELECT losser_id as player_id, losser_display_name as player_name,
                           loser_lifetime_elo_change as elo_change
                    FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                                             AND loser_lifetime_elo_change IS NOT NULL
                ) GROUP BY player_id ORDER BY net_change ASC LIMIT 1
                """,
                (start, end, start, end),
            )
            row = cur.fetchone()
            if row and row[2] < 0:
                stats["biggest_loser"] = (row[0], row[1], row[2])  # (user_id, name, change)

            # 7. Average match duration
            cur.execute(
                "SELECT AVG(match_time) FROM match_records WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked' AND match_time > 0",
                (start, end),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                stats["avg_duration"] = row[0]

            # 8. Biggest upset (highest winner_lifetime_elo_change = lower-rated winner)
            cur.execute(
                """
                SELECT winner_id, winner_display_name, losser_id, losser_display_name, winner_lifetime_elo_change
                FROM match_records
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                      AND winner_lifetime_elo_change IS NOT NULL
                      AND winner_lifetime_elo_change > 0
                ORDER BY winner_lifetime_elo_change DESC LIMIT 1
                """,
                (start, end),
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
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                GROUP BY p1_id, p2_id
                HAVING match_count >= 2
                ORDER BY match_count DESC LIMIT 1
                """,
                (start, end),
            )
            pair = cur.fetchone()
            if pair:
                p1_id, p2_id, total = pair
                cur.execute(
                    """
                    SELECT winner_id, winner_display_name, losser_display_name
                    FROM match_records
                    WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                          AND ((winner_id = ? AND losser_id = ?)
                               OR (winner_id = ? AND losser_id = ?))
                    """,
                    (start, end, p1_id, p2_id, p2_id, p1_id),
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
                    WHERE m.timestamp >= ? AND m.timestamp < ? AND m.match_type = 'ranked'
                    ORDER BY (COALESCE(w.online_elo, w.elo, 1500)
                              + COALESCE(l.online_elo, l.elo, 1500)) DESC
                    LIMIT 1
                    """,
                    (start, end),
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
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked' AND match_time > 0
                """,
                (start, end),
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
                    WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                          AND curiosa_url_winner IS NOT NULL
                          AND curiosa_url_winner != ''
                    UNION ALL
                    SELECT losser_id as player_id,
                           losser_display_name as player_name,
                           curiosa_url_loser as deck_url
                    FROM match_records
                    WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                          AND curiosa_url_loser IS NOT NULL
                          AND curiosa_url_loser != ''
                )
                GROUP BY player_id
                HAVING deck_count >= 2
                ORDER BY deck_count DESC LIMIT 1
                """,
                (start, end, start, end),
            )
            row = cur.fetchone()
            if row:
                stats["deck_variety"] = (row[0], row[1], row[2])  # (user_id, name, count)

            # 13. Busiest day (only shown on the weekly recap)
            cur.execute(
                """
                SELECT substr(timestamp, 1, 10) as day, COUNT(*) as match_count
                FROM match_records
                WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                GROUP BY day ORDER BY match_count DESC LIMIT 1
                """,
                (start, end),
            )
            row = cur.fetchone()
            if row:
                stats["busiest_day"] = (row[0], row[1])  # (YYYY-MM-DD, count)

        finally:
            conn.close()

        return stats

    # ------------------------------------------------------------------
    # Streak detection
    # ------------------------------------------------------------------

    def _compute_streaks(self, start: str, end: str) -> dict:
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
                    WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                    UNION
                    SELECT losser_id as player_id FROM match_records
                    WHERE timestamp >= ? AND timestamp < ? AND match_type = 'ranked'
                )
                """,
                (start, end, start, end),
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

                # Broken streak: did this player lose in the period and have a 6+ streak before that loss?
                # Find the most recent loss in the period
                first_loss_idx = None
                for i, m in enumerate(matches):
                    if m[1] == player_id and start <= m[4] < end:  # player is loser, in period
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


def _build_embed(period: dict, stats: dict, previous: dict, guild) -> discord.Embed:
    """Build the recap embed from the period's stats and the previous period's counts."""

    def p(user_id, name):
        return _player(guild, user_id, name)

    compare = period["compare_label"]
    embed = discord.Embed(
        title=period["title"],
        url=f"{WEB_APP_URL}/match-history",
        color=0xFFD700,
    )
    embed.set_footer(text=period["footer"])

    links = (
        f"🔗 [Leaderboard]({WEB_APP_URL}/elo) • "
        f"[Match History]({WEB_APP_URL}/match-history) • "
        f"[Fun Stats]({WEB_APP_URL}/fun-stats)"
    )

    total = _total(stats)
    prev_total = _total(previous)
    if total == 0:
        quiet = "today" if period["kind"] == "daily" else "this week"
        embed.description = (
            f"No matches were played {quiet} ({prev_total} {compare}). Queue up! 🃏\n\n{links}"
        )
        return embed

    # --- At a glance (description) ---
    counts = [f"**{stats[key]}** {label}" for key, label in MATCH_TYPES if stats.get(key)]
    glance = [" • ".join(counts)]
    glance.append(f"📅 **{total}** matches total — {_delta(total, prev_total)} vs {compare} ({prev_total})")

    extras = []
    if stats.get("unique_players"):
        extras.append(
            f"👥 **{stats['unique_players']}** players "
            f"({_delta(stats['unique_players'], previous.get('unique_players'))})"
        )
    if stats.get("ironman"):
        extras.append(f"🕒 **{stats['ironman']}** hrs played")
    if stats.get("avg_duration") is not None:
        extras.append(f"⏱️ **{round(stats['avg_duration'])}** min avg")
    if extras:
        glance.append(" • ".join(extras))

    if period["kind"] == "weekly" and stats.get("busiest_day"):
        day, count = stats["busiest_day"]
        try:
            day = datetime.date.fromisoformat(day).strftime("%A")
        except ValueError:
            pass
        glance.append(f"📆 Busiest day: **{day}** ({count} ranked matches)")
    embed.description = "\n".join(glance)

    # --- Top performers ---
    performers = []
    if stats.get("top_gainer"):
        user_id, name, change = stats["top_gainer"]
        if change and change > 0:
            performers.append(f"📈 **Top Gainer:** {p(user_id, name)} `+{change}`")
    if stats.get("biggest_loser"):
        user_id, name, change = stats["biggest_loser"]
        performers.append(f"📉 **Biggest Drop:** {p(user_id, name)} `{change}`")
    if stats.get("most_active"):
        user_id, name, count = stats["most_active"]
        performers.append(f"👑 **Most Active:** {p(user_id, name)} — {count} matches")
    if stats.get("deck_variety"):
        user_id, name, count = stats["deck_variety"]
        performers.append(f"🎴 **Deck Variety:** {p(user_id, name)} — {count} decks")
    if performers:
        embed.add_field(name="🏅 Top Performers", value=_join_lines(performers), inline=False)

    # --- Match highlights ---
    highlights = []
    if stats.get("biggest_upset"):
        winner_id, winner_name, loser_id, loser_name, change = stats["biggest_upset"]
        highlights.append(
            f"🎯 **Biggest Upset:** {p(winner_id, winner_name)} beat {p(loser_id, loser_name)} `+{change}`"
        )
    if stats.get("highest_rated"):
        w_id, w_name, l_id, l_name, w_elo, l_elo = stats["highest_rated"]
        highlights.append(
            f"🏆 **Highest Rated:** {p(w_id, w_name)} `{w_elo}` vs {p(l_id, l_name)} `{l_elo}`"
        )
    if stats.get("rivalry"):
        p1_id, p1, p2_id, p2, p1w, p2w, rivalry_total = stats["rivalry"]
        highlights.append(
            f"⚔️ **Rivalry:** {p(p1_id, p1)} vs {p(p2_id, p2)} — `{p1w}-{p2w}` ({rivalry_total} games)"
        )
    if highlights:
        embed.add_field(name="✨ Match Highlights", value=_join_lines(highlights), inline=False)

    # --- Streaks ---
    streak_lines = []
    hot = stats.get("hot_streaks") or []
    for user_id, name, streak in hot[:5]:
        streak_lines.append(f"🔥 {p(user_id, name)} — **{streak}** wins in a row")
    if len(hot) > 5:
        streak_lines.append(f"…and {len(hot) - 5} more")
    for entry in (stats.get("broken_streaks") or [])[:5]:
        streak_lines.append(
            f"💔 {p(entry['player_id'], entry['player'])}'s **{entry['streak']}**-win streak "
            f"ended by {p(entry['broken_by_id'], entry['broken_by'])}"
        )
    if streak_lines:
        embed.add_field(name="🔥 Streaks", value=_join_lines(streak_lines), inline=False)

    embed.add_field(name="​", value=links, inline=False)
    return embed


async def setup(bot):
    await bot.add_cog(DailySummaryCog(bot))
