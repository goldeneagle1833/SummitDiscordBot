import datetime
import discord
from discord.ext import commands
import sqlite3
import logging

import config
from utils.database import get_current_event_match_elo_snapshot
from utils.text import find_best_command_match

logger = logging.getLogger("discord_bot")


class EloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Monitor for invalid commands and suggest elo-related corrections"""
        # Only handle CommandNotFound errors
        if not isinstance(error, commands.CommandNotFound):
            return

        # Extract the failed command from the message
        message_content = ctx.message.content.lower()
        if not message_content.startswith("!"):
            return

        failed_command = message_content.split()[0][1:]  # Remove the !

        # Common elo-related commands and suggestions
        command_suggestions = {
            # Rank variations
            "rating": "!rank",
            "elo": "!rank",
            "myrank": "!rank",
            "myrating": "!rank",
            "myelo": "!rank",
            "checkrank": "!rank",
            "checkrating": "!rank",
            "checkelo": "!rank",
            "gerank": "!rank",
            "getrating": "!rank",
            "getelo": "!rank",
            "ranking": "!rank",
            "elorank": "!rank",
            "elorating": "!rank",
            "score": "!rank",
            "myscore": "!rank",
            "points": "!rank",
            "mypoints": "!rank",
            # Leaderboard variations
            "leaderboards": "!leaderboard",
            "leaders": "!leaderboard",
            "ladder": "!leaderboard",
            "rankings": "!leaderboard",
            "top": "!leaderboard",
            "top16": "!leaderboard",
            "topplayers": "!leaderboard",
            "topranks": "!leaderboard",
            "topelo": "!leaderboard",
            "board": "!leaderboard",
            "lb": "!leaderboard",
            "leaderbord": "!leaderboard",
            "leaderborad": "!leaderboard",
            "eloleaderboard": "!leaderboard",
            "showleaderboard": "!leaderboard",
            "checkleaderboard": "!leaderboard",
            "viewleaderboard": "!leaderboard",
            # Masters bracket variations
            "masters": "!masters_bracket",
            "mastersbracket": "!masters_bracket",
            "master": "!masters_bracket",
            "masterbracket": "!masters_bracket",
            "mastersboard": "!masters_bracket",
            "mastersleaderboard": "!masters_bracket",
            "masterstop": "!masters_bracket",
            "mastersladder": "!masters_bracket",
            "masterranks": "!masters_bracket",
            "masterrankings": "!masters_bracket",
            "mastersrank": "!masters_bracket",
            "mastersranking": "!masters_bracket",
            "premium": "!masters_bracket",
            "premiumleaderboard": "!masters_bracket",
            # Mystats variations
            "stats": "!mystats",
            "statistics": "!mystats",
            "mystatistics": "!mystats",
            "matchstats": "!mystats",
            "mymatchstats": "!mystats",
            "playerstats": "!mystats",
            "myplayerstats": "!mystats",
            "profile": "!mystats",
            "myprofile": "!mystats",
            "record": "!mystats",
            "myrecord": "!mystats",
            "history": "!mystats",
            "myhistory": "!mystats",
            "winrate": "!mystats",
            "mywinrate": "!mystats",
            "performance": "!mystats",
            "myperformance": "!mystats",
            "stat": "!mystats",
            "mystat": "!mystats",
            # Event leaderboard variations
            "eventleaderboard": "!event_leaderboard",
            "eventboard": "!event_leaderboard",
            "eventlb": "!event_leaderboard",
            "eventranking": "!event_leaderboard",
            "eventrankings": "!event_leaderboard",
            "seasonleaderboard": "!event_leaderboard",
            "seasonboard": "!event_leaderboard",
            # Event status variations
            "eventstatus": "!event_status",
            "event": "!event_status",
            "currentevent": "!event_status",
            "season": "!event_status",
            # Match ELO lookup variations
            "matchelo": "!match_elo",
            "matchrating": "!match_elo",
            "gameelo": "!match_elo",
            "eloaftermatch": "!match_elo",
        }

        actual_commands = {
            "rank": "!rank",
            "leaderboard": "!leaderboard",
            "masters_bracket": "!masters_bracket",
            "mastersbracket": "!masters_bracket",
            "mystats": "!mystats",
            "event_leaderboard": "!event_leaderboard",
            "event_status": "!event_status",
            "match_elo": "!match_elo",
        }

        suggestion = find_best_command_match(failed_command, command_suggestions, actual_commands)
        if suggestion:
            await ctx.send(f"{ctx.author.mention}, did you mean `{suggestion}`?")
            return

    @commands.command()
    async def rank(self, ctx, user: discord.Member = None):
        """Check your current Elo ranking and event rank, or check another user's rank by tagging them."""
        from utils.database import get_active_event, has_player_played_event, get_event_participant_ids
        from utils.checks import check_is_admin

        # Determine which user to check
        target_user = user if user else ctx.author
        is_self = target_user == ctx.author
        target_name = target_user.display_name

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()

        # Get both lifetime and event ELO
        cur.execute(
            "SELECT online_elo, online_event_elo FROM overall_standings WHERE user_id=?", (target_user.id,)
        )
        row = cur.fetchone()

        if row:
            lifetime_elo = row[0] if row[0] else 1500
            event_elo = row[1] if row[1] else 1500

            # Get lifetime rank
            cur.execute("SELECT COUNT(*) FROM overall_standings WHERE online_elo > ?", (lifetime_elo,))
            lifetime_rank = cur.fetchone()[0] + 1

            # Check if there's an active event
            active_event = get_active_event()

            # Check event participation via match_records
            has_event_games = False
            event_rank = 1
            if active_event:
                event_start_str = active_event["start_date"].isoformat()
                if active_event.get("avatar_specific"):
                    cur.execute(
                        """SELECT user_id, avatar_name, event_elo
                           FROM event_avatar_standings
                           WHERE event_id = ? AND source = 'online'
                           ORDER BY event_elo DESC, user_display_name COLLATE NOCASE,
                                    avatar_name COLLATE NOCASE""",
                        (active_event["event_id"],),
                    )
                    avatar_rows = cur.fetchall()
                    player_avatar_rows = [
                        (rank, avatar, elo_value)
                        for rank, (user_id, avatar, elo_value) in enumerate(avatar_rows, 1)
                        if str(user_id) == str(target_user.id)
                    ]
                    has_event_games = bool(player_avatar_rows)
                else:
                    has_event_games = has_player_played_event(target_user.id, event_start_str)
                    event_participants = get_event_participant_ids(event_start_str)
                    cur.execute("SELECT user_id, online_event_elo FROM overall_standings WHERE online_event_elo > ?", (event_elo,))
                    event_rank = sum(1 for r in cur.fetchall() if r[0] in event_participants) + 1

            if is_self:
                msg = f"{ctx.author.mention}\n"
            else:
                msg = f"**{target_name}**\n"

            if check_is_admin(ctx):
                msg += f"**Lifetime ELO:** {lifetime_elo} (Rank #{lifetime_rank})\n"

            if active_event:
                if active_event.get("avatar_specific") and has_event_games:
                    msg += f"**Event ELO ({active_event['event_name']}):**\n"
                    msg += "\n".join(
                        f"#{rank}: {avatar} — {elo_value}"
                        for rank, avatar, elo_value in player_avatar_rows
                    )
                elif active_event.get("avatar_specific"):
                    msg += f"**Event ELO ({active_event['event_name']}):** 1500 (No matches yet)"
                elif has_event_games:
                    msg += f"**Event ELO ({active_event['event_name']}):** {event_elo} (Rank #{event_rank})"
                else:
                    msg += f"**Event ELO ({active_event['event_name']}):** 1500 (No matches yet)"
            else:
                msg += "*No active event*"

            await ctx.send(msg)
        else:
            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, you don't have an Elo rating yet. "
                    "Play some matches to get started!"
                )
            else:
                await ctx.send(
                    f"{target_name} doesn't have an Elo rating yet. "
                    "They need to play some matches to get started!"
                )
        conn.close()

    @commands.command()
    async def leaderboard(self, ctx):
        """Check the top 16 lifetime Elo rankings (admin only)."""
        from utils.checks import check_is_admin

        if not check_is_admin(ctx):
            await ctx.send("The lifetime leaderboard is only available to admins. Use `!event_leaderboard` instead.")
            return

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC LIMIT 16"
        )
        rows = cur.fetchall()
        if rows:
            leaderboard = "🏆 **Lifetime Elo Leaderboard** 🏆\n"
            for i, (user_display_name, elo) in enumerate(rows, start=1):
                leaderboard += f"#{i}: {user_display_name} - {elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send("No Elo ratings found. Play some matches to get started!")
        conn.close()

    @commands.command()
    async def event_leaderboard(self, ctx):
        """Check the top 16 event Elo rankings for the current event."""
        from utils.database import get_active_event, get_event_participant_ids

        active_event = get_active_event()
        if not active_event:
            await ctx.send("No active event. Check back when a new event starts!")
            return

        event_start_str = active_event["start_date"].isoformat()

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        if active_event.get("avatar_specific"):
            cur.execute(
                """SELECT user_display_name, avatar_name, event_elo
                   FROM event_avatar_standings
                   WHERE event_id = ? AND source = 'online'
                   ORDER BY event_elo DESC, user_display_name COLLATE NOCASE,
                            avatar_name COLLATE NOCASE LIMIT 16""",
                (active_event["event_id"],),
            )
            rows = [(f"{name} — {avatar}", elo) for name, avatar, elo in cur.fetchall()]
        else:
            event_participants = get_event_participant_ids(event_start_str)
            cur.execute(
                """SELECT user_id, user_display_name, online_event_elo FROM overall_standings
                   ORDER BY online_event_elo DESC"""
            )
            all_rows = cur.fetchall()
            rows = [(name, elo) for uid, name, elo in all_rows if uid in event_participants][:16]
        conn.close()

        if rows:
            leaderboard = f"🏆 **{active_event['event_name']} Leaderboard** 🏆\n"
            for i, (user_display_name, elo) in enumerate(rows, start=1):
                leaderboard += f"#{i}: {user_display_name} - {elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send(f"No rankings yet for {active_event['event_name']}. Play some matches to get started!")

    @commands.command()
    async def masters_bracket(self, ctx):
        """Check the top 16 Elo rankings for masters bracket members only (admin only)."""
        from utils.checks import check_is_admin

        if not check_is_admin(ctx):
            await ctx.send("The masters bracket leaderboard is only available to admins.")
            return

        # Role IDs to filter by
        masters_role_ids = config.MASTERS_ROLE_IDS

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC"
        )
        all_players = cur.fetchall()
        conn.close()

        # Filter players who have one of the masters roles
        guild = ctx.guild
        if not guild:
            await ctx.send("This command can only be used in a server.")
            return

        filtered_players = []
        for user_id, display_name, elo in all_players:
            member = guild.get_member(user_id)
            if member:
                # Check if member has any of the masters roles
                has_masters = any(role.id in masters_role_ids for role in member.roles)
                if has_masters:
                    filtered_players.append((display_name, elo))

        if filtered_players:
            leaderboard = "🏆 **Masters Bracket Leaderboard** 🏆\n"
            for i, (user_display_name, elo) in enumerate(
                filtered_players[:24], start=1
            ):
                leaderboard += f"#{i}: {user_display_name} - {elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send("No masters bracket members found with Elo ratings!")

    @commands.command()
    async def match_elo(self, ctx, match_id=None):
        """Show event Elo before and after a specific current-event match."""
        from utils.checks import check_is_admin
        if match_id is None:
            await ctx.send("Please provide a match ID. Usage: `!match_elo <match_id>`")
            return

        try:
            parsed_match_id = int(match_id)
        except (TypeError, ValueError):
            await ctx.send("Invalid match ID. Usage: `!match_elo <match_id>`")
            return

        try:
            snapshot = get_current_event_match_elo_snapshot(parsed_match_id)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        except sqlite3.Error as exc:
            logger.error(f"Database error in match_elo command: {exc}")
            await ctx.send(
                "There was an error retrieving that match's Elo details. Please try again later."
            )
            return
        except Exception as exc:
            logger.error(f"Unexpected error in match_elo command: {exc}", exc_info=True)
            await ctx.send("An unexpected error occurred. Please try again later.")
            return

        timestamp_str = snapshot["match_timestamp"].strftime("%Y-%m-%d %H:%M")
        is_admin = check_is_admin(ctx)
        lines = [
            f"**Match #{snapshot['match_id']} Elo Snapshot**",
            f"**Event:** {snapshot['event_name']}",
            f"**Played:** {timestamp_str}",
            f"**Winner:** {snapshot['winner_display_name']}",
        ]
        if is_admin:
            lines.append(
                f"Lifetime: {snapshot['winner']['lifetime_before']} -> {snapshot['winner']['lifetime_after']}"
                if snapshot["winner"]["lifetime_before"] is not None
                else "Lifetime: unavailable"
            )
        lines.append(f"Event: {snapshot['winner']['event_before']} -> {snapshot['winner']['event_after']}")
        lines.append(f"**Loser:** {snapshot['loser_display_name']}")
        if is_admin:
            lines.append(
                f"Lifetime: {snapshot['loser']['lifetime_before']} -> {snapshot['loser']['lifetime_after']}"
                if snapshot["loser"]["lifetime_before"] is not None
                else "Lifetime: unavailable"
            )
        lines.append(f"Event: {snapshot['loser']['event_before']} -> {snapshot['loser']['event_after']}")

        if snapshot["notes"]:
            lines.append("**Notes:**")
            lines.extend(f"- {note}" for note in snapshot["notes"])

        await ctx.send("\n".join(lines))



async def setup(bot):
    await bot.add_cog(EloCog(bot))
