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
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        # Update the SELECT query to include match_time
        cur.execute(
            "SELECT did_win, first_player, json_deck_data, match_time FROM match_records WHERE reporter_id=?",
            (ctx.author.id,),
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
        first_player_wins = sum(1 for row in rows if row[0] and "y" in row[1].lower())
        first_player_matches = sum(1 for row in rows if "y" in row[1].lower())
        first_player_win_rate = (
            (first_player_wins / first_player_matches) * 100
            if first_player_matches > 0
            else 0
        )

        # Avatar stats
        avatar_win_loss = {}
        rows_with_deck_data = [row for row in rows if row[2] is not None]

        for row in rows_with_deck_data:
            try:
                json_deck_data = json.loads(row[2])
                avatar = json_deck_data.get("avatar", [{}])
                avatar_name = avatar[0].get("name", "Unknown") if avatar else "Unknown"

                if row[0] == 1:  # did_win
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

        # Add average match time calculation after the first_player_win_rate calculation
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
        response += (
            f"Average Match Time: {avg_match_time:.1f} minutes\n"  # Add this line
        )
        response += f"On the Play Wins: {first_player_wins}\n"
        response += f"On the Play Matches: {first_player_matches}\n"
        response += f"On the Play Win Rate: {first_player_win_rate:.2f}%\n"

        if avatar_win_loss:
            response += f"\n**Avatar Performance:**\n"
            for avatar_name, (wins, losses) in avatar_win_loss.items():
                total_avatar_matches = wins + losses
                avatar_win_rate = (
                    (wins / total_avatar_matches) * 100
                    if total_avatar_matches > 0
                    else 0
                )
                response += (
                    f"{avatar_name}: {wins}-{losses} (W-L) - {avatar_win_rate:.1f}%\n"
                )
        else:
            response += f"\nNo avatar data found in your match records."

        # Get the user's elo
        conn_elo = sqlite3.connect("elo.db")
        cur_elo = conn_elo.cursor()
        cur_elo.execute(
            "SELECT elo FROM overall_standings WHERE user_id=?", (ctx.author.id,)
        )
        elo_row = cur_elo.fetchone()
        if elo_row:
            elo = elo_row[0]
            cur_elo.execute(
                "SELECT COUNT(*) FROM overall_standings WHERE elo > ?", (elo,)
            )
            rank = cur_elo.fetchone()[0] + 1
            response += f"\n**Your Elo:** {elo} (Rank #{rank})"
        else:
            response += f"\nYou don't have an Elo rating yet."

        await ctx.send(response)
        conn.close()
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
        """View your match history with details."""
        try:
            conn = sqlite3.connect("match_records.db")
            cur = conn.cursor()

            try:
                cur.execute(
                    """
                    SELECT
                        winner_display_name,
                        losser_display_name,
                        did_win,
                        first_player,
                        match_time,
                        curiosa_url,
                        match_comment
                    FROM match_records
                    WHERE winner_id = ? OR losser_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """,
                    (ctx.author.id, ctx.author.id),
                )

                rows = cur.fetchall()

                if not rows:
                    await ctx.send(
                        f"{ctx.author.mention}, you haven't played any matches yet!"
                    )
                    return

                embed = discord.Embed(
                    title=f"Match History for {ctx.author.display_name}",
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
                            curiosa_url,
                            match_comment,
                        ) = row

                        # Format game information
                        game_info = f"**Winner:** {winner}\n**Loser:** {loser}\n"
                        game_info += f"**First Player:** {'Yes' if first_player and first_player.lower() == 'y' else 'No'}\n"

                        if match_time:
                            try:
                                match_duration = float(match_time)
                                game_info += (
                                    f"**Duration:** {match_duration:.1f} minutes\n"
                                )
                            except (ValueError, TypeError):
                                pass

                        if curiosa_url:
                            game_info += (
                                f"**Replay:** [View on Curiosa]({curiosa_url})\n"
                            )

                        if match_comment:
                            game_info += f"**Notes:** {match_comment}\n"

                        embed.add_field(
                            name=f"Game #{i}",
                            value=game_info,
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
