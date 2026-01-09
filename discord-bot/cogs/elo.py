import datetime
import discord
from discord.ext import commands
import sqlite3
import json
import logging
import random

from cogs.lfg import LFGReportButtons

logger = logging.getLogger("discord_bot")


class EloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def levenshtein_distance(self, s1, s2):
        """Calculate the Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

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
        }

        # Check for exact matches
        if failed_command in command_suggestions:
            suggestion = command_suggestions[failed_command]
            await ctx.send(f"{ctx.author.mention}, did you mean `{suggestion}`?")
            return

        # Check for partial matches (fuzzy matching)
        for key, suggestion in command_suggestions.items():
            if key in failed_command or failed_command in key:
                await ctx.send(f"{ctx.author.mention}, did you mean `{suggestion}`?")
                return

        # Check for spelling mistakes using Levenshtein distance
        # Get all actual command names
        actual_commands = {
            "rank": "!rank",
            "leaderboard": "!leaderboard",
            "masters_bracket": "!masters_bracket",
            "mastersbracket": "!masters_bracket",
            "mystats": "!mystats",
        }

        # Find closest match based on edit distance
        best_match = None
        min_distance = float("inf")

        for command_name in actual_commands.keys():
            distance = self.levenshtein_distance(failed_command, command_name)
            # Consider it a typo if distance is 3 or less and length is similar
            if distance <= 3 and distance < min_distance:
                # Also check if the length difference isn't too large
                if abs(len(failed_command) - len(command_name)) <= 3:
                    min_distance = distance
                    best_match = actual_commands[command_name]

        if best_match and min_distance <= 3:
            await ctx.send(f"{ctx.author.mention}, did you mean `{best_match}`?")
            return

    @commands.command()
    async def rank(self, ctx, user: discord.Member = None):
        """Check your current Elo ranking, or check another user's rank by tagging them."""
        # Determine which user to check
        target_user = user if user else ctx.author
        is_self = target_user == ctx.author

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT elo FROM overall_standings WHERE user_id=?", (target_user.id,)
        )
        row = cur.fetchone()
        if row:
            elo = row[0]
            cur.execute("SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (elo,))
            rank = cur.fetchone()[0] + 1

            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, your current Elo rating is {elo} and your rank is #{rank}."
                )
            else:
                await ctx.send(
                    f"{target_user.display_name}'s current Elo rating is {elo} and their rank is #{rank}."
                )
        else:
            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, you don't have an Elo rating yet. "
                    "Play some matches to get started!"
                )
            else:
                await ctx.send(
                    f"{target_user.display_name} doesn't have an Elo rating yet. "
                    "They need to play some matches to get started!"
                )
        conn.close()

    @commands.command()
    async def leaderboard(self, ctx):
        """Check the top 16 Elo rankings."""
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_display_name, elo FROM overall_standings ORDER BY elo DESC LIMIT 16"
        )
        rows = cur.fetchall()
        if rows:
            leaderboard = "🏆 **Elo Leaderboard** 🏆\n"
            for i, (user_display_name, elo) in enumerate(rows, start=1):
                leaderboard += f"#{i}: {user_display_name} - {elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send("No Elo ratings found. Play some matches to get started!")
        conn.close()

    @commands.command()
    async def masters_bracket(self, ctx):
        """Check the top 16 Elo rankings for masters bracket members only."""
        # Role IDs to filter by
        masters_role_ids = [1455669646370799667, 1445433610609102990]

        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_display_name, elo FROM overall_standings ORDER BY elo DESC"
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
                filtered_players[:16], start=1
            ):
                leaderboard += f"#{i}: {user_display_name} - {elo} Elo\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send("No masters bracket members found with Elo ratings!")

    @commands.command()
    async def mystats(self, ctx):
        """Check your match statistics. Includes win rate, first player win rate,
        avatar performance, and Elo."""
        try:
            conn = sqlite3.connect("match_records.db")
            cur = conn.cursor()

            # Query matches where user is winner OR loser
            # Since we record each match twice (once for winner, once for loser),
            # we need to deduplicate by selecting DISTINCT based on the unique match
            cur.execute(
                """
                SELECT DISTINCT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                    first_player, 
                    json_deck_data, 
                    match_time,
                    CASE 
                        WHEN winner_id < losser_id THEN winner_id || '-' || losser_id || '-' || timestamp
                        ELSE losser_id || '-' || winner_id || '-' || timestamp
                    END as match_key
                FROM match_records 
                WHERE winner_id = ? OR losser_id = ?
                UNION ALL
                SELECT DISTINCT
                    is_winner as did_win,
                    first_player,
                    json_deck_data,
                    match_time,
                    reporter_id || '-solo-' || report_date as match_key
                FROM solo_match_reports
                WHERE reporter_id = ?
            """,
                (ctx.author.id, ctx.author.id, ctx.author.id, ctx.author.id),
            )

            all_rows = cur.fetchall()

            # Remove the match_key column and keep only the stats fields
            rows = [row[:4] for row in all_rows]

            if not rows:
                await ctx.send(
                    f"{ctx.author.mention}, you don't have any match records yet. "
                    "Play some matches to get started!"
                )
                conn.close()
                return

            # General stats
            total_matches = len(rows)
            wins = sum(1 for row in rows if row[0])
            win_rate = (wins / total_matches) * 100 if total_matches > 0 else 0
            first_player_wins = sum(
                1 for row in rows if row[0] and row[1] and "y" in str(row[1]).lower()
            )
            first_player_matches = sum(
                1 for row in rows if row[1] and "y" in str(row[1]).lower()
            )
            first_player_win_rate = (
                (first_player_wins / first_player_matches) * 100
                if first_player_matches > 0
                else 0
            )

            # Calculate on the draw stats
            draw_matches = sum(
                1 for row in rows if row[1] and "y" not in str(row[1]).lower()
            )
            draw_wins = sum(
                1
                for row in rows
                if row[0] and row[1] and "y" not in str(row[1]).lower()
            )
            draw_win_rate = (draw_wins / draw_matches) * 100 if draw_matches > 0 else 0

            # Avatar stats
            avatar_win_loss = {}
            rows_with_deck_data = [row for row in rows if row[2] is not None]

            for row in rows_with_deck_data:
                try:
                    json_deck_data = json.loads(row[2])
                    avatar = json_deck_data.get("avatar", [{}])
                    avatar_name = (
                        avatar[0].get("name", "Unknown") if avatar else "Unknown"
                    )

                    if row[0]:  # did_win/is_winner
                        avatar_win_loss[avatar_name] = (
                            avatar_win_loss.get(avatar_name, (0, 0))[0] + 1,
                            avatar_win_loss.get(avatar_name, (0, 0))[1],
                        )
                    else:
                        avatar_win_loss[avatar_name] = (
                            avatar_win_loss.get(avatar_name, (0, 0))[0],
                            avatar_win_loss.get(avatar_name, (0, 0))[1] + 1,
                        )
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            # Calculate average match time
            match_times = [
                float(row[3])
                for row in rows
                if row[3] and str(row[3]).replace(".", "").isdigit()
            ]
            avg_match_time = sum(match_times) / len(match_times) if match_times else 0

            # Build response message
            response = f"{ctx.author.mention}, here is your player report:\n\n"
            response += f"**Overall Stats:**\n"
            response += f"Total Matches: {total_matches}\n"
            response += f"Wins: {wins}\n"
            response += f"Win Rate: {win_rate:.2f}%\n"
            response += f"Average Match Time: {avg_match_time:.1f} minutes\n"
            response += f"On the Play Wins: {first_player_wins}\n"
            response += f"On the Play Matches: {first_player_matches}\n"
            response += f"On the Play Win Rate: {first_player_win_rate:.2f}%\n"
            response += f"On the Draw Wins: {draw_wins}\n"
            response += f"On the Draw Matches: {draw_matches}\n"
            response += f"On the Draw Win Rate: {draw_win_rate:.2f}%\n"

            if avatar_win_loss:
                response += f"\n**Avatar Performance:**\n"
                for avatar_name, (wins, losses) in avatar_win_loss.items():
                    total_avatar_matches = wins + losses
                    avatar_win_rate = (
                        (wins / total_avatar_matches) * 100
                        if total_avatar_matches > 0
                        else 0
                    )
                    response += f"{avatar_name}: {wins}-{losses} (W-L) - {avatar_win_rate:.1f}%\n"
            else:
                response += f"\nNo avatar data found in your match records."

            # Get the user's elo
            try:
                conn_elo = sqlite3.connect("elo.db")
                cur_elo = conn_elo.cursor()

                # Verify the table exists
                cur_elo.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='overall_standings'"
                )
                if not cur_elo.fetchone():
                    logger.error("Table 'overall_standings' not found in elo.db")
                    response += (
                        f"\nError accessing Elo data. Please contact an administrator."
                    )
                else:
                    cur_elo.execute(
                        "SELECT elo FROM overall_standings WHERE user_id=?",
                        (ctx.author.id,),
                    )
                    elo_row = cur_elo.fetchone()
                    if elo_row:
                        elo = elo_row[0]
                        cur_elo.execute(
                            "SELECT COUNT(*) FROM overall_standings WHERE elo > ?",
                            (elo,),
                        )
                        rank = cur_elo.fetchone()[0] + 1
                        response += f"\n**Your Elo:** {elo} (Rank #{rank})"
                    else:
                        response += f"\nYou don't have an Elo rating yet."

            except sqlite3.Error as e:
                logger.error(f"Database error accessing elo.db: {e}")
                response += (
                    f"\nError accessing Elo data. Please contact an administrator."
                )

            await ctx.send(response)

        except Exception as e:
            logger.error(f"Error in mystats command: {e}")
            await ctx.send(
                "An error occurred while retrieving your stats. Please try again later."
            )

        finally:
            if "conn" in locals():
                conn.close()
            if "conn_elo" in locals():
                conn_elo.close()

    @commands.command()
    async def replay(self, ctx):
        """Replay your last match."""
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT winner_id, winner_display_name, losser_id, losser_display_name "
            "FROM match_records WHERE winner_id=? OR losser_id=? ORDER BY timestamp DESC LIMIT 1",
            (ctx.author.id, ctx.author.id),
        )
        row = cur.fetchone()
        if row:
            winner_id, winner_display_name, losser_id, losser_display_name = row
            if ctx.author.id == winner_id:
                opponent_id = losser_id
                opponent_display_name = losser_display_name
            else:
                opponent_id = winner_id
                opponent_display_name = winner_display_name

            opponent = await self.bot.fetch_user(opponent_id)

            # Record match start time for the rematch
            match_start_time = datetime.datetime.now()

            # Randomly select which player gets the report buttons
            requester_global = ctx.author.global_name or ctx.author.display_name
            opponent_global = opponent.global_name or opponent.display_name

            players = [
                (ctx.author.id, requester_global, ctx.author, True),  # True = requester
                (opponent_id, opponent_global, opponent, False),  # False = opponent
            ]
            reporter_player, other_player = random.sample(players, 2)
            reporter_id, reporter_global, reporter_user, reporter_is_requester = (
                reporter_player
            )
            other_id, other_global, other_user, other_is_requester = other_player

            view_reporter = LFGReportButtons(
                reporter_id,
                reporter_id,
                reporter_global,
                other_id,
                other_global,
                self.bot,
                None,  # channel
                match_start_time=match_start_time,
            )

            # Send buttons to the selected reporter
            try:
                await reporter_user.send(
                    f"**Rematch!** You're playing against {other_user.mention} (**{other_global}**)!\n\nReport the match result below:",
                    view=view_reporter,
                )
            except discord.Forbidden:
                logger.warning(f"Cannot DM {reporter_global} for rematch")

            # Send info message to the other player (no buttons)
            try:
                await other_user.send(
                    f"**Rematch!** You're playing against {reporter_user.mention} (**{reporter_global}**)!\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                )
            except discord.Forbidden:
                logger.warning(f"Cannot DM {other_global} for rematch")

            await ctx.send(
                f"{ctx.author.mention}, rematch request sent to {opponent.mention}!"
            )
        else:
            await ctx.send(
                f"{ctx.author.mention}, you have not played any matches yet. "
                "Use the `!lfg` command to find a match!"
            )
        conn.close()

    @commands.command()
    async def mygames(self, ctx):
        """View your match history with details for games you reported."""
        try:
            conn = sqlite3.connect("match_records.db")
            cur = conn.cursor()

            try:
                # Query both tables with appropriate field mappings
                # Get matches where user was either winner or loser (not just reporter)
                cur.execute(
                    """
                    SELECT 
                        winner_display_name as winner,
                        losser_display_name as loser,
                        CASE 
                            WHEN winner_id = ? THEN 1
                            ELSE 0
                        END as did_win,
                        first_player,
                        match_time,
                        curiosa_url as replay_url,
                        match_comment,
                        timestamp as match_date,
                        'match_records' as source,
                        CASE 
                            WHEN winner_id = ? THEN COALESCE(winner_elo_change, 0)
                            ELSE COALESCE(loser_elo_change, 0)
                        END as elo_change
                    FROM match_records 
                    WHERE winner_id = ? OR losser_id = ?
                    UNION ALL
                    SELECT 
                        CASE 
                            WHEN is_winner = 1 THEN reporter_name 
                            ELSE opponent_name 
                        END as winner,
                        CASE 
                            WHEN is_winner = 1 THEN opponent_name 
                            ELSE reporter_name 
                        END as loser,
                        is_winner as did_win,
                        first_player,
                        match_time,
                        curiosa_link as replay_url,
                        match_comment,
                        report_date as match_date,
                        'solo_reports' as source,
                        0 as elo_change
                    FROM solo_match_reports
                    WHERE reporter_id = ?
                    ORDER BY match_date DESC
                    LIMIT 10
                    """,
                    (
                        ctx.author.id,
                        ctx.author.id,
                        ctx.author.id,
                        ctx.author.id,
                        ctx.author.id,
                    ),
                )

                rows = cur.fetchall()

                if not rows:
                    await ctx.send(
                        f"{ctx.author.mention}, you haven't reported any matches yet!"
                    )
                    return

                # Build text message with ASCII art (without emojis in code block)
                message = "```\n"
                message += (
                    "╔══════════════════════════════════════════════════════════╗\n"
                )
                message += (
                    "║            M A T C H   H I S T O R Y                   ║\n"
                )
                message += (
                    f"║            {ctx.author.display_name.center(44)}            ║\n"
                )
                message += (
                    "╚══════════════════════════════════════════════════════════╝\n"
                )
                message += "```\n"
                message += "📜 **Your 10 most recent reported matches:**\n"
                message += "─" * 60 + "\n"

                for i, row in enumerate(rows, 1):
                    try:
                        (
                            winner,
                            loser,
                            did_win,
                            first_player,
                            match_time,
                            replay_url,
                            match_comment,
                            match_date,
                            source,
                            elo_change,
                        ) = row

                        # Format match date based on source
                        if source == "match_records":
                            date_obj = datetime.datetime.fromisoformat(match_date)
                        else:
                            date_obj = datetime.datetime.strptime(
                                match_date, "%Y-%m-%d %H:%M:%S"
                            )
                        formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")

                        # Build compact game line
                        result_emoji = "✅" if did_win else "❌"

                        # Format ELO change display
                        if elo_change and elo_change != 0:
                            if elo_change > 0:
                                elo_display = f"📈 +{elo_change}"
                            else:
                                elo_display = f"📉 {elo_change}"
                        else:
                            elo_display = ""

                        game_line = f"{result_emoji} **Game {i}** ({formatted_date})"
                        if elo_display:
                            game_line += f" {elo_display}"
                        game_line += "\n"
                        game_line += f"   ⚔️ {winner} beat {loser}"

                        if match_time:
                            game_line += f" • ⏱️ {float(match_time):.1f}min"

                        game_line += f" "

                        if replay_url and replay_url != "No URL provided":
                            game_line += f" • <{replay_url}>"

                        if match_comment:
                            game_line += f"\n   💬 {match_comment}"

                        message += game_line + "\n"

                        # Add separator between games
                        if i < len(rows):
                            message += "   " + "·" * 50 + "\n"

                    except (ValueError, TypeError) as e:
                        logger.error(f"Error processing game record: {e}")
                        continue

                message += "─" * 60

                # Check if message is too long (Discord limit is 2000 characters)
                if len(message) > 2000:
                    logger.warning(
                        f"Message too long ({len(message)} chars), truncating..."
                    )
                    message = message[:1950] + "\n... (truncated)"

                await ctx.send(message)

            except sqlite3.Error as e:
                logger.error(f"Database error in mygames command: {e}")
                await ctx.send(
                    "There was an error retrieving your game history. Please try again later."
                )

        except Exception as e:
            logger.error(f"Unexpected error in mygames command: {e}", exc_info=True)
            await ctx.send("An unexpected error occurred. Please try again later.")

        finally:
            if "conn" in locals():
                conn.close()


async def setup(bot):
    await bot.add_cog(EloCog(bot))
