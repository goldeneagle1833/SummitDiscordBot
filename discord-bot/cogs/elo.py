import datetime
import discord
from discord.ext import commands
import sqlite3
import json
import logging

from cogs.lfg import LFGReportButtons

logger = logging.getLogger("discord_bot")


class EloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def rank(self, ctx):
        """Check your current Elo ranking."""
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT elo FROM overall_standings WHERE user_id=?", (ctx.author.id,)
        )
        row = cur.fetchone()
        if row:
            elo = row[0]
            cur.execute("SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (elo,))
            rank = cur.fetchone()[0] + 1
            await ctx.send(
                f"{ctx.author.mention}, your current Elo rating is {elo} and your rank is #{rank}."
            )
        else:
            await ctx.send(
                f"{ctx.author.mention}, you don't have an Elo rating yet. "
                "Play some matches to get started!"
            )
        conn.close()

    @commands.command()
    async def leaderboard(self, ctx):
        """Check the top 10 Elo rankings."""
        conn = sqlite3.connect("elo.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_display_name, elo FROM overall_standings ORDER BY elo DESC LIMIT 10"
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
    async def mystats(self, ctx):
        """Check your match statistics. Includes win rate, first player win rate,
        avatar performance, and Elo."""
        try:
            conn = sqlite3.connect("match_records.db")
            cur = conn.cursor()

            # Query both tables with UNION ALL
            cur.execute(
                """
                SELECT did_win, first_player, json_deck_data, match_time
                FROM match_records 
                WHERE reporter_id = ?
                UNION ALL
                SELECT 
                    is_winner as did_win,
                    first_player,
                    json_deck_data,
                    match_time
                FROM solo_match_reports
                WHERE reporter_id = ?
            """,
                (ctx.author.id, ctx.author.id),
            )

            rows = cur.fetchall()

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
            view_ctx = LFGReportButtons(
                ctx.author.id,
                ctx.author.id,
                ctx.author.global_name,
                opponent_id,
                opponent.global_name,
            )
            await ctx.author.send(f"Rematch with {opponent.mention}?", view=view_ctx)
            await opponent.send(f"{ctx.author.mention} wants a rematch!", view=view_ctx)
            await ctx.send(
                f"{ctx.author.mention}, you have been sent a rematch request to {opponent.mention}!"
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
                cur.execute(
                    """
                    SELECT 
                        winner_display_name as winner,
                        losser_display_name as loser,
                        did_win,
                        first_player,
                        match_time,
                        curiosa_url as replay_url,
                        match_comment,
                        timestamp as match_date,
                        'match_records' as source
                    FROM match_records 
                    WHERE reporter_id = ?
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
                        'solo_reports' as source
                    FROM solo_match_reports
                    WHERE reporter_id = ?
                    ORDER BY match_date DESC
                    LIMIT 10
                    """,
                    (ctx.author.id, ctx.author.id),
                )

                rows = cur.fetchall()

                if not rows:
                    await ctx.send(
                        f"{ctx.author.mention}, you haven't reported any matches yet!"
                    )
                    return

                embed = discord.Embed(
                    title=f"Match History for {ctx.author.display_name}",
                    description="Your 10 most recent reported matches",
                    color=discord.Color.blue(),
                )

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
                        ) = row

                        # Format match date based on source
                        if source == "match_records":
                            date_obj = datetime.datetime.fromisoformat(match_date)
                        else:
                            date_obj = datetime.datetime.strptime(
                                match_date, "%Y-%m-%d %H:%M:%S"
                            )
                        formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")

                        # Build game information
                        game_info = []
                        game_info.append(f"**Date:** {formatted_date}")
                        game_info.append(f"**Winner:** {winner}")
                        game_info.append(f"**Loser:** {loser}")
                        game_info.append(
                            f"**First Player:** {'Yes' if first_player and first_player.lower() == 'y' else 'No'}"
                        )

                        if match_time:
                            game_info.append(
                                f"**Duration:** {float(match_time):.1f} minutes"
                            )

                        if replay_url and replay_url != "No URL provided":
                            game_info.append(
                                f"**Replay:** [View on Curiosa]({replay_url})"
                            )

                        if match_comment:
                            game_info.append(f"**Notes:** {match_comment}")

                        embed.add_field(
                            name=f"Game #{i}",
                            value="\n".join(game_info),
                            inline=False,
                        )

                    except (ValueError, TypeError) as e:
                        logger.error(f"Error processing game record: {e}")
                        continue

                await ctx.send(embed=embed)

            except sqlite3.Error as e:
                logger.error(f"Database error in mygames command: {e}")
                await ctx.send(
                    "There was an error retrieving your game history. Please try again later."
                )

        except Exception as e:
            logger.error(f"Unexpected error in mygames command: {e}")
            await ctx.send("An unexpected error occurred. Please try again later.")

        finally:
            if "conn" in locals():
                conn.close()


async def setup(bot):
    await bot.add_cog(EloCog(bot))
