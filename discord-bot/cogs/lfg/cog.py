import discord
from discord.ext import commands, tasks
import datetime
import logging
import random
from random import randrange
import asyncio
import sqlite3

import config
from cogs.lfg import state as lfg_state
from cogs.lfg.state import (
    lfg_queue,
    lfg_queue_lock,
    lfg_status_lock,
    pending_match_reports,
    processed_matches,
    active_ladder_challenges,
    ladder_challenge_lock,
    LADDER_CHALLENGE_MAX_JOINERS,
)
from cogs.lfg.helpers import scrub_urls, send_milestone_announcement
from cogs.lfg.match_reporting import WentFirstView, LFGReportButtons
from cogs.lfg.challenge import ChallengeInitView, ChallengerDeckModal
from cogs.lfg.ladder import (
    LadderChallengeJoinButton,
    LadderChallengeReportButtons,
    _build_ladder_challenge_embed,
    _resolve_ladder_challenge,
    _ladder_challenge_timeout,
)
from cogs.lfg.queue import DeckURLModal, JoinQueueButtons, ActiveQueueButtons
from utils.database import (
    winner_report,
    losser_report,
    check_milestone,
    get_top_16_user_ids,
    get_ladder_challenge_today,
    save_ladder_challenge,
    complete_ladder_challenge,
    update_elo_db_ladder,
    get_user_elo,
    update_elo_db,
    log_admin_action,
    cleanup_old_pairings,
)
from utils.constants import SORCERY_NICKNAMES
from utils.text import find_best_command_match
from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")


class LFGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lfg_channel_id = config.LFG_CHANNEL_ID
        self.check_expired_queue.start()  # Start the background task
        self.cleanup_old_status_messages.start()  # Clean up old messages on startup
        self.cleanup_old_leaderboard_messages.start()  # Clean up old leaderboard on startup
        self.cleanup_database_pairings.start()  # Clean up old pairings periodically

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.check_expired_queue.cancel()
        self.cleanup_old_status_messages.cancel()
        self.cleanup_old_leaderboard_messages.cancel()
        self.cleanup_database_pairings.cancel()

    @tasks.loop(count=1)
    async def cleanup_old_status_messages(self):
        """One-time cleanup of old status messages on bot startup"""
        try:
            lfg_channel = self.bot.get_channel(self.lfg_channel_id)
            if not lfg_channel:
                logger.warning(f"LFG channel {self.lfg_channel_id} not found")
                return

            # Fetch recent messages (limit to last 50 messages to avoid rate limits)
            async for message in lfg_channel.history(limit=50):
                # Check if message is from the bot and has an embed with "LFG Queue" or "Queue Status"
                if (
                    message.author.id == self.bot.user.id
                    and message.embeds
                    and any(
                        "Queue" in str(embed.title) or "LFG" in str(embed.title)
                        for embed in message.embeds
                    )
                ):
                    try:
                        await message.delete()
                        logger.info(f"Deleted old LFG status message: {message.id}")
                    except Exception as e:
                        logger.warning(f"Could not delete old status message: {e}")

            # After cleanup, create a new status message
            await self.update_lfg_status()
            logger.info("Old LFG status messages cleaned up and new one created")

        except Exception as e:
            logger.error(f"Error cleaning up old status messages: {e}")

    @cleanup_old_status_messages.before_loop
    async def before_cleanup_old_status_messages(self):
        """Wait for bot to be ready before cleanup"""
        await self.bot.wait_until_ready()

    @tasks.loop(count=1)
    async def cleanup_old_leaderboard_messages(self):
        """One-time cleanup of old leaderboard messages on bot startup"""
        try:
            leaderboard_channel_id = config.LEADERBOARD_CHANNEL_ID
            leaderboard_channel = self.bot.get_channel(leaderboard_channel_id)

            if not leaderboard_channel:
                logger.warning(
                    f"Leaderboard channel {leaderboard_channel_id} not found"
                )
                return

            # Fetch recent messages (limit to last 50 messages to avoid rate limits)
            async for message in leaderboard_channel.history(limit=50):
                # Check if message is from the bot and has an embed with "Leaderboard"
                if (
                    message.author.id == self.bot.user.id
                    and message.embeds
                    and any(
                        "Leaderboard" in str(embed.title) for embed in message.embeds
                    )
                ):
                    try:
                        await message.delete()
                        logger.info(f"Deleted old leaderboard message: {message.id}")
                    except Exception as e:
                        logger.warning(f"Could not delete old leaderboard message: {e}")

            # After cleanup, create a new leaderboard
            await self.update_leaderboard()
            logger.info("Old leaderboard messages cleaned up and new one created")

        except Exception as e:
            logger.error(f"Error cleaning up old leaderboard messages: {e}")

    @cleanup_old_leaderboard_messages.before_loop
    async def before_cleanup_old_leaderboard_messages(self):
        """Wait for bot to be ready before cleanup"""
        await self.bot.wait_until_ready()

    async def update_leaderboard(self):
        """Update the leaderboard in the designated channel"""
        import sqlite3
        from utils.database import get_active_event

        leaderboard_channel_id = config.LEADERBOARD_CHANNEL_ID
        leaderboard_channel = self.bot.get_channel(leaderboard_channel_id)

        if not leaderboard_channel:
            logger.warning(f"Leaderboard channel {leaderboard_channel_id} not found")
            return

        TICKET_HOLDER_ROLE_IDS = config.TICKET_HOLDER_ROLE_IDS

        try:
            # Get active event info for filtering matches
            active_event = get_active_event()
            event_start_str = None
            event_name = "Current Season"
            if active_event:
                event_start_str = active_event["start_date"].isoformat()
                event_name = active_event["event_name"]

            # Fetch all ranked players from database
            # Use event_elo when an active event exists, otherwise lifetime elo
            conn_elo = sqlite3.connect("elo.db")
            cursor_elo = conn_elo.cursor()
            if active_event:
                cursor_elo.execute("""
                    SELECT user_id, user_display_name, event_elo
                    FROM overall_standings
                    WHERE event_elo != 1500
                    ORDER BY event_elo DESC
                """)
            else:
                cursor_elo.execute("""
                    SELECT user_id, user_display_name, elo
                    FROM overall_standings
                    ORDER BY elo DESC
                """)
            all_players = cursor_elo.fetchall()
            conn_elo.close()

            # Connect to match records to get game counts
            conn_matches = sqlite3.connect("match_records.db")
            cursor_matches = conn_matches.cursor()

            # Calculate total games played in current event only
            if event_start_str:
                cursor_matches.execute(
                    "SELECT COUNT(*) FROM match_records WHERE timestamp >= ?",
                    (event_start_str,),
                )
            else:
                cursor_matches.execute("SELECT COUNT(*) FROM match_records")
            total_games_played = cursor_matches.fetchone()[0]

            # Create leaderboard embed with event name and game count
            embed = discord.Embed(
                title=f"{event_name} Leaderboard ({total_games_played} games played)",
                description="Current ELO Rankings | Started: 2/7/2026 | End: 3/14/2026",
                color=discord.Color.gold(),
            )

            if all_players:
                # Get guild for role checking
                guild = self.bot.get_guild(config.GUILD_ID)

                # Build player data with resolved names and game counts
                player_data = []
                for user_id, display_name, elo in all_players:
                    # Fetch current username from Discord if stored name is None or empty
                    if not display_name or display_name == "None":
                        try:
                            user = await self.bot.fetch_user(user_id)
                            display_name = user.global_name or user.display_name

                            # Update database with correct name
                            conn = sqlite3.connect("elo.db")
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE overall_standings SET user_display_name = ? WHERE user_id = ?",
                                (display_name, user_id),
                            )
                            conn.commit()
                            conn.close()
                        except Exception as e:
                            logger.warning(f"Could not fetch user {user_id}: {e}")
                            display_name = f"User#{user_id}"

                    # Count games played by this user in current event only
                    if event_start_str:
                        cursor_matches.execute(
                            """
                            SELECT COUNT(*) FROM match_records
                            WHERE (winner_id = ? OR losser_id = ?) AND timestamp >= ?
                            """,
                            (user_id, user_id, event_start_str),
                        )
                    else:
                        cursor_matches.execute(
                            """
                            SELECT COUNT(*) FROM match_records
                            WHERE winner_id = ? OR losser_id = ?
                            """,
                            (user_id, user_id),
                        )
                    total_games = cursor_matches.fetchone()[0]

                    # Check if user has ticket holder role
                    has_ticket = False
                    if guild:
                        member = guild.get_member(user_id)
                        if member:
                            has_ticket = any(
                                role.id in TICKET_HOLDER_ROLE_IDS
                                for role in member.roles
                            )

                    player_data.append(
                        {
                            "user_id": user_id,
                            "display_name": display_name,
                            "elo": elo,
                            "games": total_games,
                            "has_ticket": has_ticket,
                        }
                    )

                conn_matches.close()

                # Overall Rankings (top 16 of all players)
                overall_text = []
                for idx, p in enumerate(player_data[:16], 1):
                    overall_text.append(
                        f"**{idx}.** {p['display_name']} - **{p['elo']}** ELO ({p['games']} games)"
                    )
                embed.add_field(
                    name="Overall Rankings",
                    value="\n".join(overall_text)
                    if overall_text
                    else "No players ranked yet.",
                    inline=False,
                )

                # Ticket Holders section (top 16 players with the ticket holder role)
                ticket_players = [p for p in player_data if p["has_ticket"]]
                ticket_text = []
                for idx, p in enumerate(ticket_players[:16], 1):
                    ticket_text.append(
                        f"**{idx}.** {p['display_name']} - **{p['elo']}** ELO ({p['games']} games)"
                    )
                embed.add_field(
                    name="Ticket Holders",
                    value="\n".join(ticket_text)
                    if ticket_text
                    else "No ticket holders ranked yet.",
                    inline=False,
                )

                # Free Play section (top 16 from non-ticket holders)
                free_players = [p for p in player_data if not p["has_ticket"]]
                free_text = []
                for idx, p in enumerate(free_players[:16], 1):
                    free_text.append(
                        f"**{idx}.** {p['display_name']} - **{p['elo']}** ELO ({p['games']} games)"
                    )
                embed.add_field(
                    name="Free Play",
                    value="\n".join(free_text)
                    if free_text
                    else "No free play players ranked yet.",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Rankings", value="No players ranked yet.", inline=False
                )

            embed.set_footer(text="Updates automatically after each match")

            # Delete old leaderboard message
            if lfg_state.leaderboard_message_id:
                try:
                    old_message = await leaderboard_channel.fetch_message(
                        lfg_state.leaderboard_message_id
                    )
                    await old_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.warning(f"Could not delete old leaderboard message: {e}")

            # Send new leaderboard message
            new_message = await leaderboard_channel.send(embed=embed)
            lfg_state.leaderboard_message_id = new_message.id
            logger.info("Leaderboard updated successfully")

        except Exception as e:
            logger.error(f"Error updating leaderboard: {e}")

    @tasks.loop(minutes=1)
    async def check_expired_queue(self):
        """Background task to check for expired queue entries every minute"""
        try:
            initial_count = len(lfg_queue)
            self.clean_expired_lfg()
            final_count = len(lfg_queue)

            # If someone was removed, update the status message
            if initial_count != final_count:
                logger.info(
                    f"Auto-removed {initial_count - final_count} expired queue entries"
                )
                await self.update_lfg_status()

            # Clean up old processed matches (older than 1 hour)
            self.clean_expired_processed_matches()
        except Exception as e:
            logger.error(f"Error in check_expired_queue task: {e}")

    @check_expired_queue.before_loop
    async def before_check_expired_queue(self):
        """Wait for bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=6)
    async def cleanup_database_pairings(self):
        """Background task to clean up old database pairings every 6 hours"""
        try:
            logger.info("Running periodic database pairing cleanup...")
            cleanup_old_pairings(hours=24)  # Expire pairings older than 24 hours
            logger.info("Database pairing cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error in cleanup_database_pairings task: {e}", exc_info=True)

    @cleanup_database_pairings.before_loop
    async def before_cleanup_database_pairings(self):
        """Wait for bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()

    async def update_lfg_status(self):
        """Update the persistent LFG status message"""
        async with lfg_status_lock:
            await self._update_lfg_status_inner()

    async def _update_lfg_status_inner(self):
        """Inner implementation of update_lfg_status (called under lfg_status_lock)"""
        lfg_channel = self.bot.get_channel(self.lfg_channel_id)
        if not lfg_channel:
            return

        # Clean expired entries first
        self.clean_expired_lfg()

        # Create embed based on queue status
        if len(lfg_queue) == 0:
            # RED - Empty queue
            embed = discord.Embed(
                title="\U0001f534 LFG Queue Status",
                description="**Queue is empty**\n\nClick a button below to find a match!",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Status updates automatically")
        else:
            # GREEN - Active queue
            now = datetime.datetime.now()

            # Build ranked queue details (ranked + both players)
            ranked_details = []
            for user_id, info in lfg_queue.items():
                qt = info.get("queue_type", "ranked")
                if qt in ("ranked", "both"):
                    time_elapsed = (now - info["timestamp"]).total_seconds() / 60
                    time_remaining = info["timeframe"] - time_elapsed
                    placeholder = SORCERY_NICKNAMES[
                        randrange(0, len(SORCERY_NICKNAMES))
                    ]
                    ranked_details.append(
                        f"`\u2022 {placeholder} \u2014 {int(time_remaining)} min`"
                    )

            # Build testing queue details (testing + both players)
            testing_details = []
            for user_id, info in lfg_queue.items():
                qt = info.get("queue_type", "ranked")
                if qt in ("testing", "both"):
                    time_elapsed = (now - info["timestamp"]).total_seconds() / 60
                    time_remaining = info["timeframe"] - time_elapsed
                    placeholder = SORCERY_NICKNAMES[
                        randrange(0, len(SORCERY_NICKNAMES))
                    ]
                    testing_details.append(
                        f"`\u2022 {placeholder} \u2014 {int(time_remaining)} min`"
                    )

            embed = discord.Embed(
                title="\U0001f7e2 LFG Queue Status",
                description=f"**{len(lfg_queue)} player(s) looking for a game!!**\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                color=discord.Color.green(),
            )

            # Ranked queue section
            if ranked_details:
                embed.add_field(
                    name="\u2694\ufe0f Ranked Queue",
                    value="\n".join(ranked_details),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="\u2694\ufe0f Ranked Queue",
                    value="`Empty`",
                    inline=False,
                )

            # Casual queue section
            if testing_details:
                embed.add_field(
                    name="\U0001f9ea Casual Queue",
                    value="\n".join(testing_details),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="\U0001f9ea Casual Queue",
                    value="`Empty`",
                    inline=False,
                )

            embed.set_footer(text="Status updates automatically")

        # Create the appropriate button view based on queue status
        if len(lfg_queue) == 0:
            # Empty queue (red) - no leave button
            view = JoinQueueButtons(self.bot)
        else:
            # Active queue (green) - includes leave button
            view = ActiveQueueButtons(self.bot)

        # Delete old message and send new one
        try:
            if lfg_state.lfg_status_message_id:
                try:
                    old_message = await lfg_channel.fetch_message(
                        lfg_state.lfg_status_message_id
                    )
                    await old_message.delete()
                except discord.NotFound:
                    # Message was already deleted, no problem
                    pass
                except Exception as e:
                    logger.warning(f"Could not delete old status message: {e}")

            # Send new status message with button
            new_message = await lfg_channel.send(embed=embed, view=view)
            lfg_state.lfg_status_message_id = new_message.id

        except Exception as e:
            logger.error(f"Error updating LFG status message: {e}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Monitor for invalid commands in LFG channel and suggest corrections"""
        # Only handle CommandNotFound errors
        if not isinstance(error, commands.CommandNotFound):
            return

        # Only respond in the LFG channel
        if ctx.channel.id != self.lfg_channel_id:
            return

        # Extract the failed command from the message
        message_content = ctx.message.content.lower()
        if not message_content.startswith("!"):
            return

        failed_command = message_content.split()[0][1:]  # Remove the !

        # Common LFG-related commands and suggestions
        command_suggestions = {
            # LFG variations
            "looking": "!lfg",
            "lookingforgame": "!lfg",
            "findgame": "!lfg",
            "game": "!lfg",
            "play": "!lfg",
            "match": "!lfg",
            "lf": "!lfg",
            "lfgame": "!lfg",
            "queue": "!lfg",
            "search": "!lfg",
            "searching": "!lfg",
            "find": "!lfg",
            "looking4game": "!lfg",
            "lookingfor": "!lfg",
            "findmatch": "!lfg",
            "getgame": "!lfg",
            "wantgame": "!lfg",
            "needgame": "!lfg",
            "joingame": "!lfg",
            "joinqueue": "!lfg",
            "queueup": "!lfg",
            "playermatch": "!lfg",
            "seek": "!lfg",
            "seeking": "!lfg",
            "want": "!lfg",
            "need": "!lfg",
            # Cancel variations
            "leave": "!cancel",
            "exit": "!cancel",
            "quit": "!cancel",
            "cancel": "!cancel",
            "stop": "!cancel",
            "leavequeue": "!cancel",
            "remove": "!cancel",
            "removeme": "!cancel",
            "leavelfg": "!cancel",
            "quitqueue": "!cancel",
            "exitqueue": "!cancel",
            "out": "!cancel",
            "stoplfg": "!cancel",
            "unqueue": "!cancel",
            "dequeue": "!cancel",
            # Check LFG variations
            "check": "!check_lfg",
            "status": "!check_lfg",
            "who": "!check_lfg",
            "whoislfg": "!check_lfg",
            "whosinqueue": "!check_lfg",
            "queuestatus": "!check_lfg",
            "checkqueue": "!check_lfg",
            "anyone": "!check_lfg",
            "whosthere": "!check_lfg",
            # Challenge variations
            "challenge": "!challenge",
            "duel": "!challenge",
            "fight": "!challenge",
            "battle": "!challenge",
            "vs": "!challenge",
            "versus": "!challenge",
            "1v1": "!challenge",
            # Ladder challenge variations
            "ladderchallenge": "!issue_challenge",
            "ladder_challenge": "!issue_challenge",
            "ladder": "!issue_challenge",
            "issuechallenge": "!issue_challenge",
            "issue_challenge": "!issue_challenge",
            "top16challenge": "!issue_challenge",
            "challenge_top16": "!issue_challenge",
            # Record game variations
            "record": "!record_game",
            "report": "!record_game",
            "reportgame": "!record_game",
            "recordmatch": "!record_game",
            "recordgame": "!record_game",
            "reportmatch": "!record_game",
            "submitmatch": "!record_game",
            "submitgame": "!record_game",
            "log": "!record_game",
            "loggame": "!record_game",
            "logmatch": "!record_game",
            # Help variations
            "help": "!lfg_help",
            "commands": "!lfg_help",
            "info": "!lfg_help",
            "?": "!lfg_help",
            "lfghelp": "!lfg_help",
            "howto": "!lfg_help",
            "guide": "!lfg_help",
            "instructions": "!lfg_help",
        }

        actual_commands = {
            "lfg": "!lfg",
            "cancel": "!cancel",
            "check_lfg": "!check_lfg",
            "checklfg": "!check_lfg",
            "challenge": "!challenge",
            "record_game": "!record_game",
            "recordgame": "!record_game",
            "lfg_help": "!lfg_help",
            "lfghelp": "!lfg_help",
        }

        suggestion = find_best_command_match(
            failed_command, command_suggestions, actual_commands
        )
        if suggestion:
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!lfg_help` to see all available commands."
            )
            return

        # Generic suggestion if no match found
        await ctx.send(
            f"{ctx.author.mention}, that command doesn't exist. Use the **Join Queue** button in the LFG channel to find a game, or `!lfg_help` to see all available commands."
        )

    def check_last_match_opponent(self, player1_id, player2_id):
        """Check if two players played each other in their most recent match.
        Returns True if they should NOT be matched (played each other recently).
        """
        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()

        try:
            # Get player1's last match
            cur.execute(
                """SELECT winner_id, losser_id FROM match_records
                WHERE (winner_id = ? OR losser_id = ?)
                ORDER BY timestamp DESC LIMIT 1""",
                (player1_id, player1_id),
            )
            player1_last_match = cur.fetchone()

            # Get player2's last match
            cur.execute(
                """SELECT winner_id, losser_id FROM match_records
                WHERE (winner_id = ? OR losser_id = ?)
                ORDER BY timestamp DESC LIMIT 1""",
                (player2_id, player2_id),
            )
            player2_last_match = cur.fetchone()

            # If either player has no match history, allow the match
            if not player1_last_match or not player2_last_match:
                return False

            # Check if they played each other in their last match
            p1_opponents = {player1_last_match[0], player1_last_match[1]}
            if player2_id in p1_opponents:
                logger.info(
                    f"Anti-rematch: {player1_id} and {player2_id} played each other in their last match"
                )
                return True

            return False

        finally:
            conn.close()

    @staticmethod
    def are_queue_types_compatible(type_a, type_b):
        """Check if two queue types can match together.
        ranked <-> ranked, both
        testing <-> testing, both
        both <-> ranked, testing, both
        """
        if type_a == "both" or type_b == "both":
            return True
        return type_a == type_b

    @staticmethod
    def resolve_match_type(type_a, type_b):
        """Determine the match type when two players are matched.
        If either player explicitly chose 'testing' (casual), it's casual (no ELO).
        Otherwise it's ranked (including both vs both).
        Note: 'testing' is the internal value for casual matches.
        """
        if type_a == "testing" or type_b == "testing":
            return "testing"
        return "ranked"

    def check_if_someone_is_lfg(self, ctx, queue_type="ranked"):
        """Find oldest player in queue who didn't play against ctx.author recently
        and is compatible with the given queue_type.
        Returns None if no valid match found.
        """
        now = datetime.datetime.now()
        oldest_valid_match = None
        oldest_timestamp = None

        for user_id, info in lfg_queue.items():
            if user_id == ctx.author.id:
                continue

            timestamp = info["timestamp"]
            timeframe = info["timeframe"]

            # Check if still within timeframe
            if (now - timestamp).total_seconds() >= timeframe * 60:
                continue

            # Check queue type compatibility
            their_type = info.get("queue_type", "ranked")
            if not self.are_queue_types_compatible(queue_type, their_type):
                continue

            # Check if they played each other recently
            if self.check_last_match_opponent(ctx.author.id, user_id):
                logger.info(
                    f"Skipping {user_id} - played against {ctx.author.id} in last match"
                )
                continue

            # Find the oldest eligible player (FIFO)
            if oldest_timestamp is None or timestamp < oldest_timestamp:
                oldest_timestamp = timestamp
                oldest_valid_match = user_id

        return oldest_valid_match

    def add_to_lfg_queue(self, ctx, timeframe, deck_url=None, queue_type="ranked"):
        lfg_queue[ctx.author.id] = {
            "timestamp": datetime.datetime.now(),
            "timeframe": int(timeframe),
            "deck_url": deck_url,
            "queue_type": queue_type,
        }

    def pair_players(self, ctx):
        now = datetime.datetime.now()
        for user_id, info in lfg_queue.items():
            if (
                user_id != ctx.author.id
                and (now - info["timestamp"]).total_seconds() < info["timeframe"] * 60
            ):
                matched_user_id = user_id
                lfg_queue.pop(matched_user_id, None)
                lfg_queue.pop(ctx.author.id, None)
                logger.info(f"Pairing {matched_user_id} with {ctx.author.id}")
                return matched_user_id
        return None

    def clean_expired_lfg(self):
        now = datetime.datetime.now()
        expired = [
            user_id
            for user_id, info in lfg_queue.items()
            if (now - info["timestamp"]).total_seconds() > info["timeframe"] * 60
        ]
        for user_id in expired:
            lfg_queue.pop(user_id)

    def clean_expired_processed_matches(self):
        """Remove processed match entries older than 1 hour to prevent memory growth"""
        now = datetime.datetime.now()
        expired = [
            match_key
            for match_key, timestamp in processed_matches.items()
            if (now - timestamp).total_seconds() > 3600  # 1 hour
        ]
        for match_key in expired:
            processed_matches.pop(match_key, None)
        if expired:
            logger.info(f"Cleaned up {len(expired)} old processed match entries")

    @commands.command(aliases=["LFG"])
    async def lfg(self, ctx, timeframe: int = 30, *, deck_url: str = None):
        """Usage: !lfg - Directs you to join the queue via the Join Queue button

        Examples:
            !lfg - Get instructions to join the queue
        """
        logger.info(
            f"LFG command started - User: {ctx.author} (ID: {ctx.author.id}), Channel: {ctx.channel}"
        )

        # Delete the user's command message
        try:
            await ctx.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete command message: {e}")

        # Check if user is already in queue
        if ctx.author.id in lfg_queue:
            try:
                await ctx.author.send(
                    "You're already in the queue! Use `!cancel` to leave the queue if needed."
                )
            except discord.Forbidden:
                pass
            return

        # Get LFG channel reference
        lfg_channel = self.bot.get_channel(self.lfg_channel_id)
        channel_mention = lfg_channel.mention if lfg_channel else "#lfg-matchmaking"

        # Send message directing user to the LFG channel
        try:
            await ctx.author.send(
                f"**Ready to find a match?**\n\n"
                f"Head over to {channel_mention} and click the **Join Queue** button to enter your deck URL and join the matchmaking queue!"
            )
        except discord.Forbidden:
            # If DM fails, assign role and send to the channel
            logger.warning(
                f"Cannot DM {ctx.author} (ID: {ctx.author.id}) - DMs disabled or bot blocked"
            )

            # Try to assign the DM-disabled role
            try:
                if ctx.guild:
                    role = ctx.guild.get_role(config.DM_DISABLED_ROLE_ID)
                    member = ctx.guild.get_member(ctx.author.id)
                    if role and member and role not in member.roles:
                        await member.add_roles(role)
                        logger.info(f"Added DM-disabled role to {ctx.author}")
            except Exception as e:
                logger.error(f"Failed to add DM-disabled role to {ctx.author}: {e}")

            # Send to the DM-disabled channel
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                await dm_channel.send(
                    scrub_urls(
                        f"{ctx.author.mention} **Ready to find a match?**\n\n"
                        f"Head over to {channel_mention} and click the **Join Queue** button to enter your deck URL and join the matchmaking queue!"
                    )
                )
            return

        # Remove old code that directly added to queue
        # Now all queue joins happen through the modal via the button
        logger.info(f"LFG command completed for {ctx.author} (ID: {ctx.author.id})")

    @commands.command()
    async def check_lfg(self, ctx):
        """Check if anyone is currently in the LFG queue."""
        async with lfg_queue_lock:
            self.clean_expired_lfg()
            queue_size = len(lfg_queue)

        if queue_size > 0:
            await ctx.send(f"{ctx.author.mention}, yes, someone is in the queue!")
        else:
            await ctx.send(f"{ctx.author.mention}, no one is currently in the queue.")

    @commands.command()
    async def cancel(self, ctx):
        """Cancel your LFG queue status."""
        # Delete the user's command message
        try:
            await ctx.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete cancel command message: {e}")

        async with lfg_queue_lock:
            was_in_queue = ctx.author.id in lfg_queue
            if was_in_queue:
                lfg_queue.pop(ctx.author.id)

        if was_in_queue:
            # Send DM to user
            try:
                await ctx.author.send("You have been removed from the LFG queue.")
            except discord.Forbidden:
                logger.warning(
                    f"Could not send DM to {ctx.author} (ID: {ctx.author.id}) - DMs might be disabled"
                )
                # If DM fails, send ephemeral message in channel
                await ctx.send(
                    f"{ctx.author.mention}, you have been removed from the LFG queue.",
                    delete_after=5,
                )
            except Exception as e:
                logger.error(f"Error sending DM to {ctx.author}: {e}")

            # Update status message after leaving queue
            await self.update_lfg_status()
        else:
            # Send DM to user
            try:
                await ctx.author.send("You are not currently in the LFG queue.")
            except discord.Forbidden:
                logger.warning(
                    f"Could not send DM to {ctx.author} (ID: {ctx.author.id}) - DMs might be disabled"
                )
                # If DM fails, send ephemeral message in channel
                await ctx.send(
                    f"{ctx.author.mention}, you are not currently in the LFG queue.",
                    delete_after=5,
                )
            except Exception as e:
                logger.error(f"Error sending DM to {ctx.author}: {e}")

    @commands.command()
    async def challenge(self, ctx, opponent: discord.Member = None):
        """Challenge a specific player to a match

        Usage: !challenge @username
        A modal will open for you to optionally enter your deck URL.
        """
        if opponent is None:
            await ctx.send(
                "Please mention a user to challenge. Example: `!challenge @username`"
            )
            return

        if opponent.id == ctx.author.id:
            await ctx.send("You cannot challenge yourself!")
            return

        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        channel_id = config.LFG_CHANNEL_ID
        lfg_channel = self.bot.get_channel(channel_id)

        # Show modal to get challenger's deck URL
        modal = ChallengerDeckModal(
            challenger=ctx.author,
            opponent=opponent,
            lfg_channel=lfg_channel,
            bot=self.bot,
            guild_id=ctx.guild.id if ctx.guild else None,
        )

        # Create a temporary interaction to send the modal
        # Since this is a prefix command, we need to use a button to trigger the modal
        view = ChallengeInitView(modal)
        await ctx.send(
            f"Click below to enter your deck URL and send the challenge to {opponent.mention}:",
            view=view,
            delete_after=60,
        )

    @commands.command()
    async def issue_challenge(self, ctx):
        """Issue a ladder challenge (Top 16 event players only, once per day).

        Creates a special queue in the LFG channel. Up to 3 players can join,
        and one is randomly selected to play against you.

        Stakes:
        - If the non-Top 16 player WINS: 2x ELO gain
        - If the Top 16 player LOSES: 0.5x ELO loss
        - If ELO difference < 100: Normal stakes
        """
        # Delete command message
        try:
            await ctx.message.delete()
        except Exception:
            pass

        user_id = ctx.author.id
        user_global = ctx.author.global_name or ctx.author.display_name

        # Check if user is in Top 16 of current event
        top_16 = get_top_16_user_ids()
        if user_id not in top_16:
            try:
                await ctx.author.send(
                    "Only Top 16 event players can issue challenges! "
                    "Check `!event_leaderboard` to see the current event rankings."
                )
            except discord.Forbidden:
                await ctx.send(
                    f"{ctx.author.mention}, only Top 16 event players can issue challenges!",
                    delete_after=10,
                )
            return

        # Check if already used today
        if get_ladder_challenge_today(user_id):
            try:
                await ctx.author.send(
                    "You've already issued a ladder challenge today. Try again tomorrow!"
                )
            except discord.Forbidden:
                await ctx.send(
                    f"{ctx.author.mention}, you've already issued a ladder challenge today!",
                    delete_after=10,
                )
            return

        # Check if they have an active ladder challenge already
        if user_id in active_ladder_challenges:
            try:
                await ctx.author.send("You already have an active ladder challenge!")
            except discord.Forbidden:
                await ctx.send(
                    f"{ctx.author.mention}, you already have an active ladder challenge!",
                    delete_after=10,
                )
            return

        # Save challenge to DB
        challenge_id = save_ladder_challenge(user_id)

        # Get LFG channel
        lfg_channel = self.bot.get_channel(self.lfg_channel_id)
        if not lfg_channel:
            try:
                await ctx.author.send("LFG channel not found.")
            except Exception:
                pass
            return

        # Build initial embed
        embed = _build_ladder_challenge_embed(user_global, [], user_id)

        # Create join button view
        join_view = LadderChallengeJoinButton(self.bot, user_id)

        # Send the challenge message
        challenge_msg = await lfg_channel.send(embed=embed, view=join_view)

        # Start the timeout task
        timeout_task = asyncio.create_task(_ladder_challenge_timeout(self.bot, user_id))

        # Store in active challenges
        active_ladder_challenges[user_id] = {
            "challenger_global": user_global,
            "joiners": [],
            "message": challenge_msg,
            "channel": lfg_channel,
            "challenge_id": challenge_id,
            "task": timeout_task,
        }

        # Notify challenger
        try:
            await ctx.author.send(
                f"Your ladder challenge has been posted in {lfg_channel.mention}! "
                f"Waiting up to 5 minutes for up to {LADDER_CHALLENGE_MAX_JOINERS} challengers to join."
            )
        except discord.Forbidden:
            await ctx.send(
                f"{ctx.author.mention}, your ladder challenge has been posted!",
                delete_after=10,
            )

        logger.info(
            f"Ladder challenge created by {user_global} (ID: {user_id}), challenge_id: {challenge_id}"
        )

    @commands.command()
    async def lfg_help(self, ctx):
        """Get detailed help for the Looking For Game (LFG) system."""
        embed = discord.Embed(
            title="Looking For Game (LFG) System",
            description="Find matches, challenge players, and track your games!",
            color=discord.Color.blue(),
        )

        # Queue Commands
        embed.add_field(
            name="Queue Commands",
            value=(
                "`!lfg [minutes] [deck_url]` - Join the matchmaking queue (default 30 min)\n"
                "**When to use:** When you want to find an opponent for a game. "
                "You'll be matched automatically with another player in queue.\n"
                "**Tip:** Use the **Join Queue** button to enter your deck URL!\n\n"
                "`!check_lfg` - See if anyone is currently in queue\n"
                "**When to use:** Before joining, to see if someone is already waiting.\n\n"
                "`!cancel` - Leave the queue (clears your deck)\n"
                "**When to use:** If you need to step away or no longer want to play."
            ),
            inline=False,
        )

        # Challenge System
        embed.add_field(
            name="Challenge System",
            value=(
                "`!challenge @user` - Challenge a specific player to a match\n"
                "**When to use:** When you want to play against a specific person "
                "instead of being matched randomly. They have 5 minutes to accept.\n\n"
                "`!issue_challenge` or `/issue-challenge` - Issue a ladder challenge (Top 16 event players only)\n"
                "**When to use:** Top 16 event players can issue once per day. Up to 3 players join, "
                "one is randomly selected. Special ELO stakes: challenger wins = 2x ELO, "
                "Top 16 loses = 0.5x ELO loss."
            ),
            inline=False,
        )

        # Match Reporting
        embed.add_field(
            name="Match Reporting",
            value=(
                "`!record_game` - Report a match played outside the bot\n"
                "**When to use:** When you played a game in person, on TTS, or "
                "anywhere else without using the LFG system. This still tracks your ELO!\n\n"
                "\u2022 Matched games: Use buttons sent to your DMs after being paired\n"
                "\u2022 You can add deck URL and match details (optional)"
            ),
            inline=False,
        )

        # Statistics
        embed.add_field(
            name="Statistics",
            value=(
                "`!game_activity [hours]` - View games reported in last X hours (default 24)\n"
                "**When to use:** To see how active the community has been, "
                "check if games are being played, or review server activity."
            ),
            inline=False,
        )

        # Admin Commands
        embed.add_field(
            name="Admin Commands",
            value="`!admin_help` - View all admin commands (requires admin permissions)",
            inline=False,
        )

        # Tips
        embed.add_field(
            name="Tips",
            value=(
                "\u2022 Queue time: 5-120 minutes\n"
                "\u2022 Challenges expire after 5 minutes\n"
                "\u2022 Enable DMs to receive match reports"
            ),
            inline=False,
        )

        embed.set_footer(text="Use !help for more commands")

        await ctx.send(embed=embed)

    @commands.command()
    @is_bot_admin()
    async def admin_help(self, ctx):
        """Get detailed help for admin commands (requires administrator permissions)."""
        embed = discord.Embed(
            title="Admin Commands",
            description="Administrative commands for managing ELO, matches, players, and the server.",
            color=discord.Color.orange(),
        )

        # Match Reporting
        embed.add_field(
            name="Match Reporting",
            value=(
                "`!admin_report @winner @loser`\n"
                "Manually report a match result between two players.\n"
                "**When to use:** When a match wasn't reported through normal channels, "
                "or to correct a missed game."
            ),
            inline=False,
        )

        # ELO Management
        embed.add_field(
            name="ELO Management",
            value=(
                "`!spot_elo_reset @user [elo]`\n"
                "Set a specific user's ELO to a custom value (0-5000).\n"
                "**When to use:** To correct ELO errors, set starting ELO for "
                "experienced players, or adjust ratings after disputes."
            ),
            inline=False,
        )

        # Match Correction & Removal
        embed.add_field(
            name="Match Correction & Removal",
            value=(
                "`!correct_match <match_id>`\n"
                "Flip the winner/loser and recalculate ALL affected ELO.\n"
                "**Recommended** for incorrect reports.\n\n"
                "`!remove_match <match_id>`\n"
                "Remove a match and revert its ELO changes.\n"
                "**When to use:** Test games or matches that never happened."
            ),
            inline=False,
        )

        # Player Removal
        embed.add_field(
            name="Player Removal",
            value=(
                "`!remove_player @user`\n"
                "Remove a player and revert ALL ELO changes from their matches.\n"
                "**Warning:** This affects all opponents' ELO as well!"
            ),
            inline=False,
        )

        # Event Management
        embed.add_field(
            name="Event Management",
            value=(
                "`!start_event <event_name>` - Start a new event/season\n"
                "`!end_event` - End the current event\n"
                "`!event_status` - View current event status\n"
                "`!recalculate_event_elo` - Recalculate all event ELO from match records\n"
                "`!reset_elo` - **DANGER:** Reset ALL ELO ratings and match history"
            ),
            inline=False,
        )

        # Activity Monitoring
        embed.add_field(
            name="Activity Monitoring",
            value=(
                "`!game_activity [hours]`\n"
                "View game statistics for the last X hours (default 24, max 8760)."
            ),
            inline=False,
        )

        # Community Management
        embed.add_field(
            name="Community Management",
            value=(
                "`!add_discord Name | invite_url | location | description`\n"
                "`!add_youtube Name | channel_id | channel_url`\n"
                "`!add_website Name | url | description`\n"
                "`!remove_community discord|youtube|website <id>`\n"
                "`!list_community` - List all community entries with IDs"
            ),
            inline=False,
        )

        # Streaming
        embed.add_field(
            name="Streaming",
            value=(
                "`!refresh_streamers` - Manually refresh the streamers list\n"
                "`!debug_activities` - Show all members with any activity\n"
                "`!debug_voice` - Show members in voice channels"
            ),
            inline=False,
        )

        # Purchase Tracking
        embed.add_field(
            name="Purchase Tracking",
            value=(
                "`!purchase_history [@user] [limit]` - View purchase history\n"
                "`!purchase_stats` - View purchase statistics\n"
                "`!test_purchase_log` - Log a test purchase"
            ),
            inline=False,
        )

        # Utility
        embed.add_field(
            name="Utility",
            value=(
                "`!giveaway [hours]` - Pick a random winner from recent posters (default 24h)"
            ),
            inline=False,
        )

        embed.set_footer(text="All admin commands require admin permissions or Bot Admin role")

        await ctx.send(embed=embed)

    @admin_help.error
    async def admin_help_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def reset_elo(self, ctx):
        """Admin command to reset all ELO ratings and match history"""
        import sqlite3

        try:
            # Capture state before reset for audit log
            _audit_conn = sqlite3.connect("elo.db")
            _audit_cur = _audit_conn.cursor()
            _audit_cur.execute("SELECT COUNT(*) FROM overall_standings")
            _total_players = _audit_cur.fetchone()[0]
            _audit_conn.close()
            _audit_conn2 = sqlite3.connect("match_records.db")
            _audit_cur2 = _audit_conn2.cursor()
            _audit_cur2.execute("SELECT COUNT(*) FROM match_records")
            _total_matches = _audit_cur2.fetchone()[0]
            _audit_conn2.close()

            # Drop and recreate elo.db
            conn_elo = sqlite3.connect("elo.db")
            cur_elo = conn_elo.cursor()

            # Drop the table
            cur_elo.execute("DROP TABLE IF EXISTS overall_standings")

            # Recreate the table
            cur_elo.execute("""CREATE TABLE overall_standings
                               (user_id INTEGER PRIMARY KEY,
                                user_display_name TEXT,
                                elo INTEGER DEFAULT 1500
                               )""")

            conn_elo.commit()
            conn_elo.close()

            # Drop and recreate match_records.db
            conn_matches = sqlite3.connect("match_records.db")
            cur_matches = conn_matches.cursor()

            # Drop all tables
            cur_matches.execute("DROP TABLE IF EXISTS match_records")
            cur_matches.execute("DROP TABLE IF EXISTS challenge_matches")

            # Recreate match_records table
            cur_matches.execute("""CREATE TABLE match_records
                                   (reporter_id INTEGER,
                                    winner_id INTEGER,
                                    winner_display_name TEXT,
                                    losser_id INTEGER,
                                    losser_display_name TEXT,
                                    did_win BOOLEAN,
                                    timestamp TEXT,
                                    first_player TEXT,
                                    match_time INTEGER,
                                    curiosa_url TEXT,
                                    match_comment TEXT,
                                    json_deck_data TEXT
                                   )""")

            # Recreate challenge_matches table
            cur_matches.execute("""CREATE TABLE challenge_matches
                                   (match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    challenger_id INTEGER NOT NULL,
                                    challenged_id INTEGER NOT NULL,
                                    status TEXT NOT NULL,
                                    match_time DATETIME NOT NULL,
                                    winner_id INTEGER,
                                    curiosa_url TEXT,
                                    match_comment TEXT,
                                    json_deck_data TEXT
                                   )""")

            conn_matches.commit()
            conn_matches.close()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "reset_elo",
                previous_state={
                    "total_players": _total_players,
                    "total_matches": _total_matches,
                },
                new_state={"result": "all data wiped"},
                details=f"Full database reset: {_total_players} players, {_total_matches} matches deleted",
            )

            success_embed = discord.Embed(
                title="Database Reset Complete",
                description="All databases have been dropped and recreated:\n\u2022 ELO database reset\n\u2022 Match records cleared\n\u2022 Challenge matches cleared\n\nAll tables are ready to use.",
                color=discord.Color.green(),
            )
            await ctx.send(embed=success_embed)
            logger.info(
                f"Database reset completed by {ctx.author} (ID: {ctx.author.id})"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Database Reset Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Database reset failed: {e}")

    @reset_elo.error
    async def reset_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def admin_report(
        self, ctx, winner: discord.Member = None, loser: discord.Member = None
    ):
        """Admin command to manually report a match result. Usage: !admin_report @winner @loser"""

        # Validate arguments
        if winner is None or loser is None:
            await ctx.send(
                "Please mention both players. Usage: `!admin_report @winner @loser`"
            )
            return

        if winner.id == loser.id:
            await ctx.send("Winner and loser cannot be the same player!")
            return

        if winner.bot or loser.bot:
            await ctx.send("Cannot report matches for bots!")
            return

        try:
            # Get display names with fallback
            winner_name = winner.global_name or winner.display_name
            loser_name = loser.global_name or loser.display_name

            # Report the match using the existing database functions
            match_id, _, _, event_active = await winner_report(
                ctx.author.id,  # reporter_id (admin who is reporting)
                winner.id,
                winner_name,
                True,
                loser.id,
                loser_name,
                "n",  # first_player default
                0,  # match_time default
                "Admin reported match",  # curiosa_link
                "Match reported by admin",  # match_comment
                winner.id,  # interaction_user_id
                winner_name,  # interaction_global
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first=None,  # Not specified for admin reports
                loser_went_first=None,
            )

            # Update ELO for the loser as well
            update_elo_db(loser.id, loser_name, False, winner.id)

            # Update leaderboard
            await self.update_leaderboard()

            # Check for milestone and send announcement if needed
            await send_milestone_announcement(self.bot, winner.id, loser.id, match_id)

            # Send confirmation
            elo_status = (
                "ELO updated" if event_active else "ELO not affected (no active event)"
            )
            success_embed = discord.Embed(
                title="Match Reported",
                description=f"**Match ID:** #{match_id}\n**Winner:** {winner.mention} ({winner_name})\n**Loser:** {loser.mention} ({loser_name})\n**Status:** {elo_status}",
                color=discord.Color.green(),
            )
            success_embed.set_footer(text=f"Reported by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "admin_report",
                target_id=winner.id,
                target_name=winner_name,
                previous_state={"winner_id": winner.id, "loser_id": loser.id},
                new_state={"match_id": match_id, "elo_status": elo_status},
                details=f"Admin reported match #{match_id}: {winner_name} beat {loser_name}",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) reported match: {winner_name} beat {loser_name}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Match Report Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Admin match report failed: {e}")

    @admin_report.error
    async def admin_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def start_event(self, ctx, *, event_name: str = None):
        """
        Start a new event/season. Archives current event and resets event ELO.
        Usage: !start_event Event Name Here
        """
        from utils.database import (
            start_new_event,
            get_active_event,
            calculate_event_k_value,
        )

        if not event_name:
            await ctx.send(
                "Please provide an event name. Usage: `!start_event Event Name Here`"
            )
            return

        try:
            # Start the new event
            result = start_new_event(event_name)

            # Build response embed
            embed = discord.Embed(
                title="New Event Started!",
                description=f"**{result['event_name']}** has begun!",
                color=discord.Color.green(),
            )

            embed.add_field(
                name="Event Details",
                value=(
                    f"**Event ID:** {result['event_id']}\n"
                    f"**Started:** {result['start_date'].strftime('%Y-%m-%d %H:%M')}\n"
                    f"**Starting K-Value:** 16\n"
                    f"**All event ELO reset to:** 1500"
                ),
                inline=False,
            )

            # Add previous event summary if there was one
            if result.get("previous_event"):
                prev = result["previous_event"]
                top_players_str = (
                    "\n".join(
                        [
                            f"  {i + 1}. {name} ({elo} ELO)"
                            for i, (name, elo) in enumerate(prev["top_players"])
                        ]
                    )
                    if prev["top_players"]
                    else "No ranked players"
                )

                embed.add_field(
                    name=f"Previous Event Archived: {prev['event_name']}",
                    value=(
                        f"**Total Matches:** {prev['total_matches']}\n"
                        f"**Ranked Players:** {prev['total_players']}\n"
                        f"**Top 3:**\n{top_players_str}"
                    ),
                    inline=False,
                )

            embed.set_footer(text=f"Started by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            # Update leaderboard
            await self.update_leaderboard()

            _prev_event = result.get("previous_event")
            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "start_event",
                previous_state={
                    "previous_event": _prev_event["event_name"] if _prev_event else None
                },
                new_state={"event_name": event_name, "event_id": result["event_id"]},
                details=f"Started event '{event_name}'"
                + (f" (archived '{_prev_event['event_name']}')" if _prev_event else ""),
            )

            logger.info(
                f"Event '{event_name}' started by {ctx.author} (ID: {ctx.author.id})"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Failed to Start Event",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Failed to start event: {e}")

    @start_event.error
    async def start_event_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def end_event(self, ctx):
        """
        End the current event without starting a new one.
        Archives standings and matches, then leaves no active event.
        """
        from utils.database import get_active_event, end_current_event

        active_event = get_active_event()
        if not active_event:
            await ctx.send("There is no active event to end.")
            return

        try:
            # End and archive the current event
            summary = end_current_event()

            if not summary:
                await ctx.send("Failed to end event - no data returned.")
                return

            # Build response embed
            embed = discord.Embed(
                title="Event Ended",
                description=f"**{summary['event_name']}** has been archived.",
                color=discord.Color.orange(),
            )

            # Top players
            if summary["top_players"]:
                top_players_str = "\n".join(
                    [
                        f"  {i + 1}. {name} ({elo} ELO)"
                        for i, (name, elo) in enumerate(summary["top_players"])
                    ]
                )
            else:
                top_players_str = "No ranked players"

            embed.add_field(
                name="Final Results",
                value=(
                    f"**Total Matches:** {summary['total_matches']}\n"
                    f"**Ranked Players:** {summary['total_players']}\n"
                    f"**Top 3:**\n{top_players_str}"
                ),
                inline=False,
            )

            embed.add_field(
                name="What's Next?",
                value=(
                    "No event is currently active.\n"
                    "Matches can still be reported but ELO will not be affected.\n"
                    "Use `!start_event <name>` to begin a new event."
                ),
                inline=False,
            )

            embed.set_footer(text=f"Ended by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            # Update leaderboard
            await self.update_leaderboard()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "end_event",
                previous_state={
                    "event_name": summary["event_name"],
                    "total_matches": summary["total_matches"],
                    "total_players": summary["total_players"],
                },
                new_state={"result": "event archived"},
                details=f"Ended event '{summary['event_name']}' ({summary['total_matches']} matches, {summary['total_players']} players archived)",
            )

            logger.info(
                f"Event '{summary['event_name']}' ended by {ctx.author} (ID: {ctx.author.id})"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Failed to End Event",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Failed to end event: {e}")

    @end_event.error
    async def end_event_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    async def event_status(self, ctx):
        """View current event status including K-value and days elapsed."""
        from utils.database import get_active_event, calculate_event_k_value

        active_event = get_active_event()

        if not active_event:
            embed = discord.Embed(
                title="No Active Event",
                description="There is no event currently running.\nMatches can still be recorded, but ELO will not be affected.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        # Calculate event stats
        start_date = active_event["start_date"]
        days_elapsed = (datetime.datetime.now() - start_date).days
        current_k = calculate_event_k_value(start_date)

        # Get match count for current event
        import sqlite3

        conn = sqlite3.connect("match_records.db")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM match_records")
        match_count = cur.fetchone()[0]
        conn.close()

        embed = discord.Embed(
            title=f"Current Event: {active_event['event_name']}",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Event Details",
            value=(
                f"**Event ID:** {active_event['event_id']}\n"
                f"**Started:** {start_date.strftime('%Y-%m-%d %H:%M')}\n"
                f"**Days Elapsed:** {days_elapsed}\n"
                f"**Matches Played:** {match_count}"
            ),
            inline=False,
        )

        embed.add_field(
            name="K-Value Info",
            value=(
                f"**Current K-Value:** {current_k}\n"
                f"**K-Value Range:** 16 \u2192 32\n"
                f"**Increases:** +2 per day"
            ),
            inline=False,
        )

        # K-value progression
        if current_k < 32:
            days_to_max = (32 - current_k) // 2
            embed.add_field(
                name="K-Value Progression",
                value=f"K-value will reach maximum (32) in {days_to_max} day(s)",
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.command()
    @is_bot_admin()
    async def recalculate_event_elo(self, ctx):
        """
        Recalculate all event ELO from scratch based on match records.
        This fixes any event_elo discrepancies by replaying all matches since event start.
        Usage: !recalculate_event_elo
        """
        from utils.database import get_active_event, update_elo, calculate_event_k_value
        import sqlite3

        active_event = get_active_event()
        if not active_event:
            await ctx.send("No active event. Nothing to recalculate.")
            return

        event_start = active_event["start_date"]
        event_start_str = event_start.isoformat()
        event_name = active_event["event_name"]

        await ctx.send(
            f"\U0001f504 Recalculating event ELO for **{event_name}**... This may take a moment."
        )

        try:
            # Connect to databases
            elo_conn = sqlite3.connect("elo.db")
            elo_cur = elo_conn.cursor()

            match_conn = sqlite3.connect("match_records.db")
            match_cur = match_conn.cursor()

            # Step 1: Reset all event_elo to 1500
            elo_cur.execute("UPDATE overall_standings SET event_elo = 1500")
            reset_count = elo_cur.rowcount
            elo_conn.commit()

            # Step 2: Get all matches since event started
            match_cur.execute(
                """
                SELECT rowid, winner_id, winner_display_name, losser_id, losser_display_name, timestamp
                FROM match_records
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """,
                (event_start_str,),
            )
            matches = match_cur.fetchall()

            # Step 3: Replay each match
            player_elos = {}  # user_id -> event_elo

            for match in matches:
                _, winner_id, _, loser_id, _, _ = match
                k_value = calculate_event_k_value(event_start)

                winner_elo = player_elos.get(winner_id, 1500)
                loser_elo = player_elos.get(loser_id, 1500)

                new_winner_elo = update_elo(winner_elo, loser_elo, True, k=k_value)
                new_loser_elo = update_elo(loser_elo, winner_elo, False, k=k_value)

                player_elos[winner_id] = new_winner_elo
                player_elos[loser_id] = new_loser_elo

            # Step 4: Write updated event_elos to database
            updates = 0
            for user_id, event_elo in player_elos.items():
                if event_elo != 1500:
                    elo_cur.execute(
                        "UPDATE overall_standings SET event_elo = ? WHERE user_id = ?",
                        (event_elo, user_id),
                    )
                    updates += 1

            elo_conn.commit()

            # Get top players
            elo_cur.execute("""
                SELECT user_display_name, event_elo
                FROM overall_standings
                WHERE event_elo != 1500
                ORDER BY event_elo DESC
                LIMIT 5
            """)
            top_players = elo_cur.fetchall()

            elo_conn.close()
            match_conn.close()

            # Build response
            embed = discord.Embed(
                title="Event ELO Recalculated",
                description=f"Successfully recalculated ELO for **{event_name}**",
                color=discord.Color.green(),
            )

            embed.add_field(
                name="Summary",
                value=(
                    f"**Players Reset:** {reset_count}\n"
                    f"**Matches Replayed:** {len(matches)}\n"
                    f"**Players with Non-1500 ELO:** {updates}"
                ),
                inline=False,
            )

            if top_players:
                top_str = "\n".join(
                    [
                        f"{i + 1}. {name} ({elo})"
                        for i, (name, elo) in enumerate(top_players)
                    ]
                )
                embed.add_field(
                    name="Top 5 Players",
                    value=top_str,
                    inline=False,
                )

            embed.set_footer(text=f"Recalculated by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            # Update leaderboard
            await self.update_leaderboard()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "recalculate_event_elo",
                previous_state={"players_reset": reset_count},
                new_state={
                    "matches_replayed": len(matches),
                    "players_updated": updates,
                },
                details=f"Recalculated event ELO for '{event_name}': {len(matches)} matches replayed, {updates} players updated",
            )

            logger.info(
                f"Event ELO recalculated by {ctx.author} - {len(matches)} matches replayed"
            )

        except Exception as e:
            await ctx.send(f"\u274c Error recalculating ELO: {str(e)}")
            logger.error(f"Failed to recalculate event ELO: {e}")

    @recalculate_event_elo.error
    async def recalculate_event_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def spot_elo_reset(self, ctx, user: discord.Member = None, elo: int = None):
        """Admin command to set a specific user's event ELO. Usage: !spot_elo_reset @user 1500"""
        import sqlite3
        from utils.database import get_active_event

        # Validate arguments
        if user is None:
            await ctx.send("Please mention a user. Usage: `!spot_elo_reset @user 1500`")
            return

        if elo is None:
            await ctx.send(
                "Please specify an ELO value. Usage: `!spot_elo_reset @user 1500`"
            )
            return

        if elo < 0 or elo > 5000:
            await ctx.send("ELO must be between 0 and 5000.")
            return

        if user.bot:
            await ctx.send("Cannot set ELO for bots!")
            return

        # Require an active event
        active_event = get_active_event()
        if not active_event:
            await ctx.send("No active event. Start an event first before updating ELO.")
            return

        try:
            # Get display name with fallback
            user_name = user.global_name or user.display_name

            # Connect to database
            conn = sqlite3.connect("elo.db")
            cursor = conn.cursor()

            # Check if user exists in database
            cursor.execute(
                "SELECT event_elo FROM overall_standings WHERE user_id = ?", (user.id,)
            )
            result = cursor.fetchone()

            old_elo = result[0] if result else None

            if result:
                # Update existing user's event ELO
                cursor.execute(
                    "UPDATE overall_standings SET event_elo = ?, user_display_name = ? WHERE user_id = ?",
                    (elo, user_name, user.id),
                )
            else:
                # Insert new user with event ELO
                cursor.execute(
                    "INSERT INTO overall_standings (user_id, user_display_name, elo, event_elo) VALUES (?, ?, 1500, ?)",
                    (user.id, user_name, elo),
                )

            conn.commit()
            conn.close()

            # Update leaderboard
            await self.update_leaderboard()

            # Send confirmation
            if old_elo is not None:
                success_embed = discord.Embed(
                    title="Event ELO Updated",
                    description=f"**User:** {user.mention} ({user_name})\n**Event:** {active_event['event_name']}\n**Old Event ELO:** {old_elo}\n**New Event ELO:** {elo}",
                    color=discord.Color.blue(),
                )
            else:
                success_embed = discord.Embed(
                    title="Event ELO Set",
                    description=f"**User:** {user.mention} ({user_name})\n**Event:** {active_event['event_name']}\n**Event ELO:** {elo}\n\n*User was not in database, created new entry.*",
                    color=discord.Color.green(),
                )

            success_embed.set_footer(text=f"Updated by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "spot_elo_reset",
                target_id=user.id,
                target_name=user_name,
                previous_state={"event_elo": old_elo},
                new_state={"event_elo": elo},
                details=f"Set {user_name}'s event ELO from {old_elo} to {elo} during '{active_event['event_name']}'",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) set event ELO for {user_name} (ID: {user.id}) to {elo} (was: {old_elo}) during event '{active_event['event_name']}'"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="ELO Update Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Spot ELO reset failed: {e}")

    @spot_elo_reset.error
    async def spot_elo_reset_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @is_bot_admin()
    async def correct_match(self, ctx, match_id: int = None):
        """Admin command to correct a match by flipping the outcome and recalculating all affected ELO.
        Usage: !correct_match <match_id>

        This command will:
        1. Flip the winner/loser of the specified match
        2. Recalculate ELO for all matches that happened after it involving either player
        """
        import sqlite3
        from utils.database import update_elo

        # Validate arguments
        if match_id is None:
            await ctx.send(
                "Please provide a match ID. Usage: `!correct_match <match_id>`"
            )
            return

        try:
            # Send initial status message
            status_msg = await ctx.send("Analyzing match history...")

            # Connect to databases
            elo_conn = sqlite3.connect("elo.db")
            elo_cursor = elo_conn.cursor()

            match_conn = sqlite3.connect("match_records.db")
            match_cursor = match_conn.cursor()

            # Get the match to correct
            match_cursor.execute(
                """
                SELECT rowid, winner_id, losser_id, winner_display_name, losser_display_name,
                       timestamp, winner_elo_change, loser_elo_change
                FROM match_records
                WHERE rowid = ?
                """,
                (match_id,),
            )
            target_match = match_cursor.fetchone()

            if not target_match:
                await status_msg.edit(content=f"Match ID #{match_id} not found.")
                elo_conn.close()
                match_conn.close()
                return

            (
                target_match_id,
                original_winner_id,
                original_loser_id,
                original_winner_name,
                original_loser_name,
                target_timestamp,
                target_winner_elo_change,
                target_loser_elo_change,
            ) = target_match

            # Get all affected players (both from the target match)
            affected_players = {original_winner_id, original_loser_id}

            # Find ALL matches after this one that involve either player
            # We need to recalculate these in order
            match_cursor.execute(
                """
                SELECT rowid, winner_id, losser_id, winner_display_name, losser_display_name,
                       timestamp, winner_elo_change, loser_elo_change
                FROM match_records
                WHERE timestamp > ?
                AND (winner_id IN (?, ?) OR losser_id IN (?, ?))
                ORDER BY timestamp ASC
                """,
                (
                    target_timestamp,
                    original_winner_id,
                    original_loser_id,
                    original_winner_id,
                    original_loser_id,
                ),
            )
            subsequent_matches = match_cursor.fetchall()

            await status_msg.edit(
                content=f"Found {len(subsequent_matches)} matches to recalculate..."
            )

            # Collect all players that will be affected (cascade effect)
            all_affected_matches = [target_match] + list(subsequent_matches)
            for match in subsequent_matches:
                affected_players.add(match[1])  # winner_id
                affected_players.add(match[2])  # loser_id

            # Step 1: Revert ELO for all affected matches (in REVERSE order)
            await status_msg.edit(content="Reverting ELO changes...")

            # First, revert subsequent matches in reverse chronological order
            for match in reversed(subsequent_matches):
                m_id, w_id, l_id, w_name, l_name, ts, w_elo_change, l_elo_change = match

                if w_elo_change:
                    elo_cursor.execute(
                        "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ? WHERE user_id = ?",
                        (w_elo_change, w_elo_change, w_id),
                    )
                if l_elo_change:
                    elo_cursor.execute(
                        "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ? WHERE user_id = ?",
                        (l_elo_change, l_elo_change, l_id),
                    )

            # Then revert the target match
            if target_winner_elo_change:
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ? WHERE user_id = ?",
                    (
                        target_winner_elo_change,
                        target_winner_elo_change,
                        original_winner_id,
                    ),
                )
            if target_loser_elo_change:
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ? WHERE user_id = ?",
                    (
                        target_loser_elo_change,
                        target_loser_elo_change,
                        original_loser_id,
                    ),
                )

            elo_conn.commit()

            # Step 2: Flip the target match outcome in the database
            await status_msg.edit(content="Flipping match outcome...")

            # Swap winner and loser
            new_winner_id = original_loser_id
            new_winner_name = original_loser_name
            new_loser_id = original_winner_id
            new_loser_name = original_winner_name

            # Step 3: Recalculate ELO for the corrected match
            # Get current ELO for both players
            elo_cursor.execute(
                "SELECT elo, event_elo FROM overall_standings WHERE user_id = ?",
                (new_winner_id,),
            )
            row = elo_cursor.fetchone()
            new_winner_elo_before = row[0] if row else 1500
            new_winner_event_elo_before = row[1] if row and row[1] else 1500

            elo_cursor.execute(
                "SELECT elo, event_elo FROM overall_standings WHERE user_id = ?",
                (new_loser_id,),
            )
            row = elo_cursor.fetchone()
            new_loser_elo_before = row[0] if row else 1500
            new_loser_event_elo_before = row[1] if row and row[1] else 1500

            # Calculate new ELO changes (lifetime K=32)
            new_winner_elo_after = update_elo(
                new_winner_elo_before, new_loser_elo_before, True
            )
            new_loser_elo_after = update_elo(
                new_loser_elo_before, new_winner_elo_before, False
            )

            # Calculate new event ELO changes
            new_winner_event_elo_after = update_elo(
                new_winner_event_elo_before, new_loser_event_elo_before, True
            )
            new_loser_event_elo_after = update_elo(
                new_loser_event_elo_before, new_winner_event_elo_before, False
            )

            new_winner_elo_change = new_winner_elo_after - new_winner_elo_before
            new_loser_elo_change = new_loser_elo_after - new_loser_elo_before

            # Update both lifetime and event ELO in database
            elo_cursor.execute(
                "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
                (new_winner_elo_after, new_winner_event_elo_after, new_winner_id),
            )
            elo_cursor.execute(
                "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
                (new_loser_elo_after, new_loser_event_elo_after, new_loser_id),
            )

            # Update the match record with flipped outcome
            match_cursor.execute(
                """
                UPDATE match_records
                SET winner_id = ?, winner_display_name = ?,
                    losser_id = ?, losser_display_name = ?,
                    winner_elo_change = ?, loser_elo_change = ?
                WHERE rowid = ?
                """,
                (
                    new_winner_id,
                    new_winner_name,
                    new_loser_id,
                    new_loser_name,
                    new_winner_elo_change,
                    new_loser_elo_change,
                    match_id,
                ),
            )

            elo_conn.commit()
            match_conn.commit()

            # Step 4: Recalculate ELO for all subsequent matches in chronological order
            await status_msg.edit(
                content=f"Recalculating {len(subsequent_matches)} subsequent matches..."
            )

            recalculated_count = 0
            for match in subsequent_matches:
                (
                    m_id,
                    w_id,
                    l_id,
                    w_name,
                    l_name,
                    ts,
                    old_w_elo_change,
                    old_l_elo_change,
                ) = match

                # Get current ELO for both players
                elo_cursor.execute(
                    "SELECT elo, event_elo FROM overall_standings WHERE user_id = ?",
                    (w_id,),
                )
                row = elo_cursor.fetchone()
                winner_elo_before = row[0] if row else 1500
                winner_event_elo_before = row[1] if row and row[1] else 1500

                elo_cursor.execute(
                    "SELECT elo, event_elo FROM overall_standings WHERE user_id = ?",
                    (l_id,),
                )
                row = elo_cursor.fetchone()
                loser_elo_before = row[0] if row else 1500
                loser_event_elo_before = row[1] if row and row[1] else 1500

                # Calculate new lifetime ELO
                winner_elo_after = update_elo(winner_elo_before, loser_elo_before, True)
                loser_elo_after = update_elo(loser_elo_before, winner_elo_before, False)

                # Calculate new event ELO
                winner_event_elo_after = update_elo(
                    winner_event_elo_before, loser_event_elo_before, True
                )
                loser_event_elo_after = update_elo(
                    loser_event_elo_before, winner_event_elo_before, False
                )

                w_elo_change = winner_elo_after - winner_elo_before
                l_elo_change = loser_elo_after - loser_elo_before

                # Update both lifetime and event ELO in database
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
                    (winner_elo_after, winner_event_elo_after, w_id),
                )
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = ?, event_elo = ? WHERE user_id = ?",
                    (loser_elo_after, loser_event_elo_after, l_id),
                )

                # Update the match record with new ELO changes
                match_cursor.execute(
                    """
                    UPDATE match_records
                    SET winner_elo_change = ?, loser_elo_change = ?
                    WHERE rowid = ?
                    """,
                    (w_elo_change, l_elo_change, m_id),
                )

                recalculated_count += 1

            elo_conn.commit()
            match_conn.commit()
            elo_conn.close()
            match_conn.close()

            # Update leaderboard
            await self.update_leaderboard()

            # Send confirmation
            success_embed = discord.Embed(
                title="Match Corrected",
                description=(
                    f"**Match ID:** #{match_id}\n\n"
                    f"**Original Result:**\n"
                    f"~~Winner: {original_winner_name}~~\n"
                    f"~~Loser: {original_loser_name}~~\n\n"
                    f"**Corrected Result:**\n"
                    f"Winner: **{new_winner_name}** ({new_winner_elo_change:+d} ELO)\n"
                    f"Loser: **{new_loser_name}** ({new_loser_elo_change:+d} ELO)"
                ),
                color=discord.Color.green(),
            )
            success_embed.add_field(
                name="Cascade Recalculation",
                value=f"Recalculated **{recalculated_count}** subsequent matches\nAffected **{len(affected_players)}** players",
                inline=False,
            )
            success_embed.set_footer(text=f"Corrected by {ctx.author.display_name}")

            await status_msg.edit(content=None, embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "correct_match",
                target_id=match_id,
                previous_state={
                    "winner_id": original_winner_id,
                    "winner_name": original_winner_name,
                    "loser_id": original_loser_id,
                    "loser_name": original_loser_name,
                },
                new_state={
                    "winner_id": new_winner_id,
                    "winner_name": new_winner_name,
                    "loser_id": new_loser_id,
                    "loser_name": new_loser_name,
                    "recalculated_matches": recalculated_count,
                },
                details=f"Corrected match #{match_id}: winner flipped from {original_winner_name} to {new_winner_name}, {recalculated_count} subsequent matches recalculated",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) corrected match #{match_id}: "
                f"{original_winner_name} -> {new_winner_name} (winner). "
                f"Recalculated {recalculated_count} subsequent matches."
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Match Correction Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Match correction failed: {e}")
            import traceback

            traceback.print_exc()

    @correct_match.error
    async def correct_match_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid match ID. Please provide a valid number.")

    @commands.command()
    @is_bot_admin()
    async def remove_match(self, ctx, match_id: int = None):
        """Admin command to remove a match report and revert ELO changes. Usage: !remove_match <match_id>"""
        import sqlite3

        # Validate arguments
        if match_id is None:
            await ctx.send(
                "Please provide a match ID. Usage: `!remove_match <match_id>`"
            )
            return

        try:
            # Connect to databases
            elo_conn = sqlite3.connect("elo.db")
            elo_cursor = elo_conn.cursor()

            match_conn = sqlite3.connect("match_records.db")
            match_cursor = match_conn.cursor()

            # Get the match record (use ROWID as fallback if match_id column doesn't exist)
            try:
                match_cursor.execute(
                    """
                    SELECT match_id, winner_id, losser_id, winner_display_name, losser_display_name,
                           winner_elo_change, loser_elo_change,
                           winner_lifetime_elo_change, loser_lifetime_elo_change, timestamp
                    FROM match_records
                    WHERE match_id = ?
                    """,
                    (match_id,),
                )
            except sqlite3.OperationalError:
                # Fallback: column might be named differently or use ROWID, or old schema without lifetime columns
                match_cursor.execute(
                    """
                    SELECT ROWID, winner_id, losser_id, winner_display_name, losser_display_name,
                           winner_elo_change, loser_elo_change, timestamp
                    FROM match_records
                    WHERE ROWID = ?
                    """,
                    (match_id,),
                )
            match = match_cursor.fetchone()

            if not match:
                await ctx.send(f"Match ID #{match_id} not found.")
                elo_conn.close()
                match_conn.close()
                return

            # Parse match data based on number of columns returned
            if len(match) == 10:  # New schema with lifetime changes
                (
                    match_id_db,
                    winner_id,
                    loser_id,
                    winner_name,
                    loser_name,
                    winner_elo_change,
                    loser_elo_change,
                    winner_lifetime_elo_change,
                    loser_lifetime_elo_change,
                    timestamp,
                ) = match
            else:  # Old schema without lifetime changes
                (
                    match_id_db,
                    winner_id,
                    loser_id,
                    winner_name,
                    loser_name,
                    winner_elo_change,
                    loser_elo_change,
                    timestamp,
                ) = match
                # Fallback: use event change for lifetime (same as old behavior)
                winner_lifetime_elo_change = winner_elo_change
                loser_lifetime_elo_change = loser_elo_change

            # Revert ELO changes using separate lifetime and event changes
            reverted_info = []

            # Revert winner's ELO
            if winner_lifetime_elo_change or winner_elo_change:
                # Revert lifetime ELO (using online_elo and elo for backwards compat)
                lifetime_revert = winner_lifetime_elo_change if winner_lifetime_elo_change else 0
                # Revert event ELO
                event_revert = winner_elo_change if winner_elo_change else 0

                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ?, online_elo = online_elo - ?, online_event_elo = online_event_elo - ? WHERE user_id = ?",
                    (lifetime_revert, event_revert, lifetime_revert, event_revert, winner_id),
                )
                reverted_info.append(f"**{winner_name}**: Lifetime -{lifetime_revert}, Event -{event_revert} ELO")

            # Revert loser's ELO
            if loser_lifetime_elo_change or loser_elo_change:
                # Revert lifetime ELO (loser_lifetime_elo_change is negative, so subtracting adds it back)
                lifetime_revert = loser_lifetime_elo_change if loser_lifetime_elo_change else 0
                # Revert event ELO (loser_elo_change is negative, so subtracting adds it back)
                event_revert = loser_elo_change if loser_elo_change else 0

                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ?, online_elo = online_elo - ?, online_event_elo = online_event_elo - ? WHERE user_id = ?",
                    (lifetime_revert, event_revert, lifetime_revert, event_revert, loser_id),
                )
                reverted_info.append(
                    f"**{loser_name}**: Lifetime +{-lifetime_revert if lifetime_revert else 0}, Event +{-event_revert if event_revert else 0} ELO"
                )

            # Delete the match record (use ROWID to be compatible with older schema)
            try:
                match_cursor.execute(
                    "DELETE FROM match_records WHERE match_id = ?", (match_id,)
                )
            except sqlite3.OperationalError:
                match_cursor.execute(
                    "DELETE FROM match_records WHERE ROWID = ?", (match_id,)
                )

            elo_conn.commit()
            match_conn.commit()
            elo_conn.close()
            match_conn.close()

            # Update leaderboard
            await self.update_leaderboard()

            # Send confirmation
            success_embed = discord.Embed(
                title="Match Removed",
                description=f"**Match ID:** #{match_id}\n**Winner:** {winner_name}\n**Loser:** {loser_name}\n**Date:** {timestamp}\n\n**ELO Reverted:**\n"
                + "\n".join(reverted_info),
                color=discord.Color.orange(),
            )
            success_embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "remove_match",
                target_id=match_id,
                previous_state={
                    "match_id": match_id,
                    "winner_id": winner_id,
                    "winner_name": winner_name,
                    "loser_id": loser_id,
                    "loser_name": loser_name,
                    "timestamp": timestamp,
                },
                new_state={"result": "match deleted"},
                details=f"Removed match #{match_id}: {winner_name} vs {loser_name} ({timestamp})",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) removed match #{match_id}: {winner_name} vs {loser_name}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Match Removal Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Match removal failed: {e}")

    @remove_match.error
    async def remove_match_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid match ID. Please provide a valid number.")

    @commands.command()
    async def eligible_for_masters_braket(self, ctx):
        """Show top 16 ELO players who have one of the required roles."""
        import sqlite3

        ROLE_IDS = config.MASTERS_ROLE_IDS

        if ctx.guild is None:
            await ctx.send("This command must be run inside a server (guild).")
            return

        try:
            conn = sqlite3.connect("elo.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, user_display_name, elo FROM overall_standings ORDER BY elo DESC"
            )
            rows = cur.fetchall()
            conn.close()

            eligible = []
            for user_id, display_name, elo in rows:
                try:
                    uid = int(user_id)
                except Exception:
                    continue
                member = ctx.guild.get_member(uid)
                if not member:
                    continue
                if any(r.id in ROLE_IDS for r in member.roles):
                    mention = member.mention
                    name = display_name or (member.global_name or member.display_name)
                    eligible.append((elo, mention, name))
                if len(eligible) >= 16:
                    break

            if not eligible:
                await ctx.send("No eligible players found with the required role.")
                return

            lines = [
                f"**{i + 1}.** {mention} \u2014 **{elo}** ELO ({name})"
                for i, (elo, mention, name) in enumerate(eligible)
            ]

            embed = discord.Embed(
                title="Eligible for Masters Bracket \u2014 Top 16 with required role",
                description="\n".join(lines),
                color=discord.Color.purple(),
            )
            embed.set_footer(
                text=f"Role requirement: IDs {', '.join(str(r) for r in config.MASTERS_ROLE_IDS)}"
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"eligible_for_masters_braket error: {e}")
            await ctx.send("Error fetching eligible players. See logs for details.")

    @commands.command(name="top_16_free_entry")
    async def top_16_free_entry(self, ctx):
        """Show top 16 ELO players (no role requirement)."""
        import sqlite3

        try:
            conn = sqlite3.connect("elo.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, user_display_name, elo FROM overall_standings ORDER BY elo DESC"
            )
            rows = cur.fetchall()
            conn.close()

            if not rows:
                await ctx.send("No ELO standings available.")
                return

            ROLE_IDS = config.MASTERS_ROLE_IDS

            lines = []
            count = 0
            for user_id, display_name, elo in rows:
                if count >= 16:
                    break

                mention = None
                display = display_name or ""
                try:
                    uid = int(user_id)
                except Exception:
                    uid = None

                # If member exists in this guild and has any excluded role, skip them
                if ctx.guild and uid:
                    member = ctx.guild.get_member(uid)
                    if member:
                        if any(r.id in ROLE_IDS for r in member.roles):
                            continue
                        mention = member.mention
                        display = display_name or (member.display_name or member.name)

                if not mention:
                    # If user not in guild, assume they don't have the excluded roles and include them
                    mention = display or str(user_id)

                count += 1
                lines.append(f"**{count}.** {mention} \u2014 **{elo}** ELO ({display})")

            embed = discord.Embed(
                title="Top 16 \u2014 Eligible (without specified roles)",
                description="\n".join(lines) if lines else "No eligible players found.",
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"top16 error: {e}")
            await ctx.send("Error fetching top 16. See logs for details.")

    @commands.command()
    @is_bot_admin()
    async def remove_player(self, ctx, user: discord.Member = None):
        """Admin command to remove a player and revert all ELO changes from their matches. Usage: !remove_player @user"""
        import sqlite3

        # Validate arguments
        if user is None:
            await ctx.send("Please mention a user. Usage: `!remove_player @user`")
            return

        if user.bot:
            await ctx.send("Cannot remove bots!")
            return

        try:
            user_name = user.global_name or user.display_name

            # Connect to databases
            elo_conn = sqlite3.connect("elo.db")
            elo_cursor = elo_conn.cursor()

            match_conn = sqlite3.connect("match_records.db")
            match_cursor = match_conn.cursor()

            # Get all matches involving this player
            match_cursor.execute(
                """
                SELECT winner_id, losser_id, winner_elo_change, loser_elo_change, winner_display_name, losser_display_name
                FROM match_records
                WHERE winner_id = ? OR losser_id = ?
                """,
                (user.id, user.id),
            )
            matches = match_cursor.fetchall()

            if not matches:
                await ctx.send(
                    f"No matches found for {user.mention}. Nothing to remove."
                )
                elo_conn.close()
                match_conn.close()
                return

            # Track ELO adjustments for opponents
            elo_adjustments = {}  # {user_id: (adjustment, display_name)}

            for (
                winner_id,
                loser_id,
                winner_elo_change,
                loser_elo_change,
                winner_name,
                loser_name,
            ) in matches:
                if winner_id == user.id:
                    # User won this match - revert ELO gain for opponent (loser)
                    if loser_id and loser_elo_change:
                        if loser_id not in elo_adjustments:
                            elo_adjustments[loser_id] = (0, loser_name)
                        current_adj, name = elo_adjustments[loser_id]
                        elo_adjustments[loser_id] = (
                            current_adj - loser_elo_change,
                            name,
                        )
                else:
                    # User lost this match - revert ELO gain for opponent (winner)
                    if winner_id and winner_elo_change:
                        if winner_id not in elo_adjustments:
                            elo_adjustments[winner_id] = (0, winner_name)
                        current_adj, name = elo_adjustments[winner_id]
                        elo_adjustments[winner_id] = (
                            current_adj - winner_elo_change,
                            name,
                        )

            # Apply ELO adjustments to opponents (both lifetime and event)
            adjustments_made = []
            for opponent_id, (adjustment, opponent_name) in elo_adjustments.items():
                if adjustment != 0:
                    elo_cursor.execute(
                        "UPDATE overall_standings SET elo = elo + ?, event_elo = event_elo + ? WHERE user_id = ?",
                        (adjustment, adjustment, opponent_id),
                    )
                    adjustments_made.append(f"{opponent_name}: {adjustment:+d}")

            # Delete all matches involving this player from match_records
            match_cursor.execute(
                "DELETE FROM match_records WHERE winner_id = ? OR losser_id = ?",
                (user.id, user.id),
            )
            matches_deleted = match_cursor.rowcount

            # Remove player from ELO standings
            elo_cursor.execute(
                "DELETE FROM overall_standings WHERE user_id = ?", (user.id,)
            )
            player_removed = elo_cursor.rowcount > 0

            # Commit changes
            elo_conn.commit()
            match_conn.commit()
            elo_conn.close()
            match_conn.close()

            # Update leaderboard
            await self.update_leaderboard()

            # Send confirmation
            embed = discord.Embed(
                title="Player Removed",
                description=f"**Player:** {user.mention} ({user_name})",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="Matches Deleted",
                value=f"{matches_deleted} ranked match(es)",
                inline=False,
            )

            if adjustments_made:
                adjustments_text = "\n".join(adjustments_made[:10])
                if len(adjustments_made) > 10:
                    adjustments_text += f"\n... and {len(adjustments_made) - 10} more"
                embed.add_field(
                    name="ELO Adjustments", value=adjustments_text, inline=False
                )
            else:
                embed.add_field(
                    name="ELO Adjustments",
                    value="No ELO data to revert (matches may have been missing ELO change data)",
                    inline=False,
                )

            embed.add_field(
                name="Player ELO Removed",
                value="Yes" if player_removed else "Player was not in ELO standings",
                inline=False,
            )

            embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "remove_player",
                target_id=user.id,
                target_name=user_name,
                previous_state={
                    "matches": matches_deleted,
                    "opponents_adjusted": len(adjustments_made),
                },
                new_state={"result": "player removed"},
                details=f"Removed player {user_name}: {matches_deleted} matches deleted, {len(adjustments_made)} opponents adjusted",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) removed player {user_name} (ID: {user.id}). "
                f"Deleted {matches_deleted} matches. "
                f"ELO adjustments: {elo_adjustments}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Player Removal Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Remove player failed: {e}")

    @remove_player.error
    async def remove_player_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    async def game_activity(self, ctx, hours: int = 24):
        """Check how many games were reported in the last X hours. Usage: !game_activity [hours]"""
        import sqlite3
        from datetime import datetime, timedelta

        # Validate hours parameter
        if hours < 1:
            await ctx.send("Hours must be at least 1.")
            return

        if hours > 8760:  # 1 year
            await ctx.send("Hours cannot exceed 8760 (1 year).")
            return

        try:
            # Calculate cutoff time
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # Connect to match records database
            conn = sqlite3.connect("match_records.db")
            cursor = conn.cursor()

            # Count matches from match_records table
            cursor.execute(
                """
                SELECT COUNT(*) FROM match_records
                WHERE timestamp >= ?
            """,
                (cutoff_time.isoformat(),),
            )
            total_games = cursor.fetchone()[0]

            # Get unique players who participated
            cursor.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM (
                    SELECT winner_id as user_id FROM match_records WHERE timestamp >= ?
                    UNION ALL
                    SELECT losser_id as user_id FROM match_records WHERE timestamp >= ?
                )
            """,
                (
                    cutoff_time.isoformat(),
                    cutoff_time.isoformat(),
                ),
            )
            unique_players = cursor.fetchone()[0]

            conn.close()

            # Create response embed
            embed = discord.Embed(
                title=f"Game Activity Report",
                description=f"Statistics for the last **{hours}** hours",
                color=discord.Color.blue(),
            )

            embed.add_field(
                name="Total Games Reported",
                value=f"**{total_games}** games",
                inline=True,
            )

            embed.add_field(
                name="Unique Players",
                value=f"**{unique_players}** players",
                inline=True,
            )

            if total_games > 0:
                avg_per_hour = total_games / hours
                embed.add_field(
                    name="Average",
                    value=f"{avg_per_hour:.1f} games/hour",
                    inline=True,
                )

            embed.set_footer(
                text=f"Since {cutoff_time.strftime('%Y-%m-%d %H:%M')} | Requested by {ctx.author.display_name}"
            )

            await ctx.send(embed=embed)

            logger.info(
                f"Game activity command used by {ctx.author} for last {hours} hours: {total_games} games"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Activity Check Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Game activity command failed: {e}")
