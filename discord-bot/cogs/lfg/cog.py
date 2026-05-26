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
from cogs.lfg.match_reporting import MatchCardView, LFGReportButtons, _apply_ladder_elo
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
    record_match,
    check_milestone,
    get_top_16_user_ids,
    get_top_8_user_ids,
    get_ladder_challenge_today,
    save_ladder_challenge,
    delete_ladder_challenge,
    complete_ladder_challenge,
    get_user_elo,
    get_user_event_elo,
    update_elo_db_lifetime_only,
    log_admin_action,
    cleanup_old_pairings,
    save_pairing,
    recalculate_event_elo,
    correct_match_record,
    remove_match_record,
    remove_player_service,
    set_player_event_elo,
)
from utils.constants import SORCERY_NICKNAMES
from utils.text import find_best_command_match
from utils.checks import is_bot_admin
from services.pilots_service import is_pilot_active
from services.limited_service import limited_winner_report, limited_elo_only_report, get_run_summary, forfeit_arena_run, start_arena_run
from repositories.limited_repo import get_active_arena_run, get_limited_elo, upsert_limited_elo

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
        from repositories.elo_repo import ELO_COUNTING_MATCH_FILTER
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
                # Get event participants from match_records
                from repositories.elo_repo import get_event_participant_ids
                event_participants = get_event_participant_ids(event_start_str)

                cursor_elo.execute("""
                    SELECT user_id, user_display_name, online_event_elo
                    FROM overall_standings
                    ORDER BY online_event_elo DESC
                """)
                # Filter to only players who have played event matches
                all_players = [row for row in cursor_elo.fetchall() if row[0] in event_participants]
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
                    f"""
                    SELECT COUNT(*) FROM match_records
                    WHERE timestamp >= ? AND {ELO_COUNTING_MATCH_FILTER}
                    """,
                    (event_start_str,),
                )
            else:
                cursor_matches.execute("SELECT COUNT(*) FROM match_records")
            total_games_played = cursor_matches.fetchone()[0]

            # Create leaderboard embed with event name and game count
            embed = discord.Embed(
                title=f"{event_name} Leaderboard ({total_games_played} games played)",
                description=None,
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
                            f"""
                            SELECT COUNT(*) FROM match_records
                            WHERE (winner_id = ? OR losser_id = ?)
                              AND timestamp >= ?
                              AND {ELO_COUNTING_MATCH_FILTER}
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

                # Overall Rankings (top 8 of all players)
                overall_text = []
                for idx, p in enumerate(player_data[:8], 1):
                    overall_text.append(
                        f"{idx}. {p['display_name']} - {p['elo']} ({p['games']}g)"
                    )
                embed.add_field(
                    name="Overall Rankings",
                    value="\n".join(overall_text)
                    if overall_text
                    else "No players ranked yet.",
                    inline=False,
                )

                # Ticket Holders section (top 24 players with the ticket holder role)
                ticket_players = [p for p in player_data if p["has_ticket"]]
                ticket_text = []
                for idx, p in enumerate(ticket_players[:24], 1):
                    ticket_text.append(
                        f"{idx}. {p['display_name']} - {p['elo']} ({p['games']}g)"
                    )
                embed.add_field(
                    name="Ticket Holders",
                    value="\n".join(ticket_text)
                    if ticket_text
                    else "No ticket holders ranked yet.",
                    inline=False,
                )

                # Free Play section (top 8 from non-ticket holders)
                free_players = [p for p in player_data if not p["has_ticket"]]
                free_text = []
                for idx, p in enumerate(free_players[:8], 1):
                    free_text.append(
                        f"{idx}. {p['display_name']} - {p['elo']} ({p['games']}g)"
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

            # Send new leaderboard message first (before deleting old one)
            new_message = await leaderboard_channel.send(embed=embed)
            old_message_id = lfg_state.leaderboard_message_id
            lfg_state.leaderboard_message_id = new_message.id

            # Delete old leaderboard message
            if old_message_id:
                try:
                    old_message = await leaderboard_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.warning(f"Could not delete old leaderboard message: {e}")

            # Ensure only one leaderboard message exists in the channel
            async for message in leaderboard_channel.history(limit=50):
                if (
                    message.id != new_message.id
                    and message.author.id == self.bot.user.id
                    and message.embeds
                    and any(
                        "Leaderboard" in str(embed.title)
                        for embed in message.embeds
                    )
                ):
                    try:
                        await message.delete()
                        logger.info(f"Cleaned up duplicate leaderboard message: {message.id}")
                    except Exception as e:
                        logger.warning(f"Could not clean up duplicate leaderboard: {e}")

            logger.info("Leaderboard updated successfully")

        except Exception as e:
            logger.error(f"Error updating leaderboard: {e}", exc_info=True)
            try:
                if leaderboard_channel:
                    await leaderboard_channel.send(f"Error updating leaderboard: ```{e}```")
            except Exception:
                pass

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

        # Log queue state for debugging
        queue_types = [qt for user_data in lfg_queue.values() for qt in user_data.get("queues", {})]
        logger.debug(f"Updating LFG status: {len(lfg_queue)} players, types={queue_types}")

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

            # Build ranked queue details
            ranked_details = []
            for user_id, user_data in lfg_queue.items():
                entry = user_data.get("queues", {}).get("ranked")
                if entry:
                    time_elapsed = (now - entry["timestamp"]).total_seconds() / 60
                    time_remaining = entry["timeframe"] - time_elapsed
                    placeholder = SORCERY_NICKNAMES[
                        randrange(0, len(SORCERY_NICKNAMES))
                    ]
                    ranked_details.append(
                        f"`\u2022 {placeholder} \u2014 {int(time_remaining)} min`"
                    )

            # Build testing queue details
            testing_details = []
            for user_id, user_data in lfg_queue.items():
                entry = user_data.get("queues", {}).get("testing")
                if entry:
                    time_elapsed = (now - entry["timestamp"]).total_seconds() / 60
                    time_remaining = entry["timeframe"] - time_elapsed
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

            # Limited queue section (only show when pilot is active)
            if is_pilot_active("GrewWolves"):
                limited_details = []
                for user_id, user_data in lfg_queue.items():
                    entry = user_data.get("queues", {}).get("limited")
                    if entry:
                        time_elapsed = (now - entry["timestamp"]).total_seconds() / 60
                        time_remaining = entry["timeframe"] - time_elapsed
                        placeholder = SORCERY_NICKNAMES[
                            randrange(0, len(SORCERY_NICKNAMES))
                        ]
                        limited_details.append(
                            f"`\u2022 {placeholder} \u2014 {int(time_remaining)} min`"
                        )

                if limited_details:
                    embed.add_field(
                        name="\U0001f3b2 Limited Queue",
                        value="\n".join(limited_details),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="\U0001f3b2 Limited Queue",
                        value="`Empty`",
                        inline=False,
                    )

            # Rumble queue section (only show when pilot is active)
            if is_pilot_active("RumbleQueue"):
                rumble_details = []
                for user_id, user_data in lfg_queue.items():
                    entry = user_data.get("queues", {}).get("rumble")
                    if entry:
                        time_elapsed = (now - entry["timestamp"]).total_seconds() / 60
                        time_remaining = entry["timeframe"] - time_elapsed
                        placeholder = SORCERY_NICKNAMES[
                            randrange(0, len(SORCERY_NICKNAMES))
                        ]
                        rumble_details.append(
                            f"`\u2022 {placeholder} \u2014 {int(time_remaining)} min`"
                        )

                if rumble_details:
                    embed.add_field(
                        name="\U0001f4a5 Rumble Queue",
                        value="\n".join(rumble_details),
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="\U0001f4a5 Rumble Queue",
                        value="`Empty`",
                        inline=False,
                    )

            embed.set_footer(text="Status updates automatically")

        # Create the appropriate button view based on queue status
        try:
            if len(lfg_queue) == 0:
                view = JoinQueueButtons(self.bot)
            else:
                view = ActiveQueueButtons(self.bot)
        except Exception as e:
            logger.error(f"Error creating queue buttons view: {e}")
            view = None

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

            # Also check if player1 was in player2's last match (bidirectional check)
            p2_opponents = {player2_last_match[0], player2_last_match[1]}
            if player1_id in p2_opponents:
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
        ranked <-> ranked
        testing <-> testing
        limited <-> limited
        """
        return type_a == type_b

    @staticmethod
    def resolve_match_type(type_a, type_b):
        """Determine the match type when two players are matched.
        Players now only match within the same queue type.
        Note: 'testing' is the internal value for casual matches.
        """
        if type_a == "limited" or type_b == "limited":
            return "limited"
        if type_a == "rumble" or type_b == "rumble":
            return "rumble"
        if type_a == "testing" or type_b == "testing":
            return "testing"
        return "ranked"

    def check_if_someone_is_lfg(self, ctx, queue_type="ranked"):
        """Find a player in queue compatible with the given queue_type.
        All queue types use FIFO order (oldest first) with anti-rematch for ranked/limited.
        Casual (testing): No pairing restrictions, FIFO order (oldest first).
        Returns user_id if a valid match is found, None otherwise.
        """
        now = datetime.datetime.now()
        best_match = None
        best_timestamp = None

        # Casual (testing) and rumble have no pairing restrictions
        is_casual = queue_type in ("testing", "rumble")

        for user_id, user_data in lfg_queue.items():
            if user_id == ctx.author.id:
                continue

            # Check if this user has a compatible queue entry
            entry = user_data.get("queues", {}).get(queue_type)
            if not entry:
                continue

            timestamp = entry["timestamp"]
            timeframe = entry["timeframe"]

            # Check if still within timeframe
            if (now - timestamp).total_seconds() >= timeframe * 60:
                continue

            # Ranked/Limited: skip if they played each other in their last match
            if not is_casual and self.check_last_match_opponent(ctx.author.id, user_id):
                logger.info(
                    f"Skipping {user_id} - played against {ctx.author.id} in last match"
                )
                continue

            # All queue types: FIFO - match with oldest player
            if best_timestamp is None or timestamp < best_timestamp:
                best_timestamp = timestamp
                best_match = user_id

        return best_match

    def add_to_lfg_queue(
        self, ctx, timeframe, deck_url=None, queue_type="ranked", ladder_info=None, run_id=None
    ):
        queue_entry = {
            "timestamp": datetime.datetime.now(),
            "timeframe": int(timeframe),
            "deck_url": deck_url,
        }
        if ladder_info:
            queue_entry["ladder_info"] = ladder_info
        if run_id is not None:
            queue_entry["run_id"] = run_id

        if ctx.author.id not in lfg_queue:
            lfg_queue[ctx.author.id] = {"queues": {}}
        lfg_queue[ctx.author.id]["queues"][queue_type] = queue_entry

    def pair_players(self, ctx):
        now = datetime.datetime.now()
        for user_id, user_data in lfg_queue.items():
            if user_id == ctx.author.id:
                continue
            # Check if any queue entry is still valid
            for qt, entry in user_data.get("queues", {}).items():
                if (now - entry["timestamp"]).total_seconds() < entry["timeframe"] * 60:
                    matched_user_id = user_id
                    lfg_queue.pop(matched_user_id, None)
                    lfg_queue.pop(ctx.author.id, None)
                    logger.info(f"Pairing {matched_user_id} with {ctx.author.id}")
                    return matched_user_id
        return None

    def clean_expired_lfg(self):
        now = datetime.datetime.now()
        users_to_remove = []
        for user_id, user_data in lfg_queue.items():
            queues = user_data.get("queues", {})
            expired_types = [
                qt for qt, entry in queues.items()
                if (now - entry["timestamp"]).total_seconds() > entry["timeframe"] * 60
            ]
            for qt in expired_types:
                queues.pop(qt)
            if not queues:
                users_to_remove.append(user_id)
        for user_id in users_to_remove:
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

        # Check if user is already in all available queues
        if ctx.author.id in lfg_queue:
            try:
                await ctx.author.send(
                    "You're already in a queue! Use `!cancel` to leave the queue if needed."
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
        # Delete the user's command message (only in guild channels, not DMs)
        if ctx.guild:
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
        """Issue a ladder challenge (Top 16 players or admins, once per day).

        Adds you to the ranked queue. The next person who matches with you will play
        for modified ELO stakes. Can be used in DMs with the bot.
        The challenge only counts against your daily limit when a match is found.
        Disabled during the first week of a new event.

        Stakes:
        - If the non-Top 16 player WINS: 2x ELO gain
        - If the Top 16 player LOSES: 0.5x ELO loss
        - If ELO difference < 100: Normal stakes
        """
        # Delete command message (only works in guild channels)
        if ctx.guild:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        user_id = ctx.author.id
        user_global = ctx.author.global_name or ctx.author.display_name

        # Check if challenges are disabled during the first week of an event
        from utils.database import get_active_event
        from datetime import datetime, timedelta
        active_event = get_active_event()
        if active_event:
            event_start = active_event["start_date"]
            if datetime.now() - event_start < timedelta(days=7):
                days_left = 7 - (datetime.now() - event_start).days
                try:
                    await ctx.author.send(
                        f"Ladder challenges are disabled during the first week of a new event. "
                        f"Available in {days_left} day(s)!"
                    )
                except discord.Forbidden:
                    if ctx.guild:
                        await ctx.send(
                            f"{ctx.author.mention}, ladder challenges are disabled during the first week of a new event.",
                            delete_after=10,
                        )
                return

        # Resolve guild and member for permission checks (works in DMs too)
        guild_id = ctx.guild.id if ctx.guild else config.GUILD_ID
        guild_obj = ctx.guild or self.bot.get_guild(config.GUILD_ID)
        member = None
        if guild_obj:
            member = guild_obj.get_member(user_id)
            if member is None:
                try:
                    member = await guild_obj.fetch_member(user_id)
                except discord.NotFound:
                    pass

        # Check if user is an admin (admins can always issue challenges)
        is_admin = False
        if member:
            if member.guild_permissions.administrator:
                is_admin = True
            elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in member.roles):
                is_admin = True

        # Check if user is in Top 16 overall (unless they're an admin)
        if not is_admin:
            top_16 = get_top_16_user_ids()
            if user_id not in top_16:
                try:
                    await ctx.author.send(
                        "Only Top 16 players can issue challenges! "
                        "Check `!event_leaderboard` to see the current rankings."
                    )
                except discord.Forbidden:
                    if ctx.guild:
                        await ctx.send(
                            f"{ctx.author.mention}, only Top 16 players can issue challenges!",
                            delete_after=10,
                        )
                return

        # Check if already used today (only counts matched challenges)
        if get_ladder_challenge_today(user_id):
            try:
                await ctx.author.send(
                    "You've already issued a ladder challenge today that was matched. Try again tomorrow!"
                )
            except discord.Forbidden:
                if ctx.guild:
                    await ctx.send(
                        f"{ctx.author.mention}, you've already issued a ladder challenge today!",
                        delete_after=10,
                    )
            return

        # Check if already in queue + attempt to match
        matched_user_id = None
        matched_user_deck_url = None
        match_type = None
        challenge_id = None
        ladder_info = None

        async with lfg_queue_lock:
            # Check if already in the ranked queue specifically
            user_queues = lfg_queue.get(user_id, {}).get("queues", {})
            if "ranked" in user_queues:
                try:
                    await ctx.author.send("You're already in the ranked queue!")
                except discord.Forbidden:
                    if ctx.guild:
                        await ctx.send(
                            f"{ctx.author.mention}, you're already in the ranked queue!",
                            delete_after=10,
                        )
                return

            # Create ladder_info with placeholder multipliers and no challenge_id yet
            # challenge_id will be set only when a match is found
            ladder_info = {
                "challenger_id": user_id,
                "challenge_id": None,
                "elo_multiplier_winner": 2.0,  # Non-Top16 winner gets 2x
                "elo_multiplier_loser": 0.5,  # Top16 loser gets 0.5x
                "guild_id": guild_id,
            }

            # Check for an existing match in the ranked queue
            self.clean_expired_lfg()
            matched_user_id = self.check_if_someone_is_lfg(ctx, "ranked")

            if matched_user_id:
                # Match found - NOW save the challenge to DB (counts against daily limit)
                challenge_id = save_ladder_challenge(user_id)
                ladder_info["challenge_id"] = challenge_id

                # Get matched user info before removing from queue
                matched_entry = lfg_queue.get(matched_user_id, {}).get("queues", {}).get("ranked", {})
                matched_user_deck_url = matched_entry.get("deck_url")
                matched_queue_type = "ranked"

                # Adjust ladder multipliers based on ELO difference
                challenger_elo = get_user_event_elo(user_id)
                opponent_elo = get_user_event_elo(matched_user_id)
                elo_diff = abs(challenger_elo - opponent_elo)

                if elo_diff < 100:
                    ladder_info["elo_multiplier_winner"] = 1.0
                    ladder_info["elo_multiplier_loser"] = 1.0
                    logger.info(
                        f"Ladder challenge match: ELO diff {elo_diff} < 100 - normal stakes"
                    )
                else:
                    logger.info(
                        f"Ladder challenge match: ELO diff {elo_diff} >= 100 - special stakes (2x/0.5x)"
                    )

                match_type = self.resolve_match_type("ranked", matched_queue_type)

                # Remove both players from all queues
                lfg_queue.pop(matched_user_id, None)
                lfg_queue.pop(user_id, None)
                logger.info(
                    f"Lock acquired: Matching challenger {user_id} with {matched_user_id} (match_type={match_type})"
                )
            else:
                # No match found - add to queue (does NOT count against daily limit)
                self.add_to_lfg_queue(
                    ctx,
                    timeframe=30,
                    deck_url=None,
                    queue_type="ranked",
                    ladder_info=ladder_info,
                )

        # Handle result outside the lock
        if matched_user_id:
            # Match found! Process the match
            try:
                matched_user = await self.bot.fetch_user(matched_user_id)
            except Exception as e:
                logger.error(f"Failed to fetch matched user {matched_user_id}: {e}")
                # Rollback: delete the challenge so daily usage is not consumed
                if challenge_id:
                    delete_ladder_challenge(challenge_id)
                try:
                    await ctx.author.send(
                        "Error: Could not find matched player. Your daily challenge was not consumed — try again!"
                    )
                except discord.Forbidden:
                    pass
                return

            lfg_channel = self.bot.get_channel(self.lfg_channel_id)
            matched_global = matched_user.global_name or matched_user.display_name

            match_start_time = datetime.datetime.now()

            # Save pairing
            if not guild_id:
                logger.error(
                    f"Cannot save pairing: guild_id is None for challenge by {user_id}"
                )
                # Rollback: delete the challenge so daily usage is not consumed
                if challenge_id:
                    delete_ladder_challenge(challenge_id)
                return

            try:
                pairing_id = save_pairing(
                    guild_id=guild_id,
                    player1_id=user_id,
                    player2_id=matched_user_id,
                    player1_deck_url=None,
                    player2_deck_url=matched_user_deck_url,
                    match_type=match_type or "ranked",
                )
                logger.info(
                    f"Saved pairing {pairing_id} in guild {guild_id}: "
                    f"{user_id} ({user_global}) vs {matched_user_id} ({matched_global})"
                )
            except Exception as e:
                logger.error(
                    f"Failed to save pairing for ladder challenge: {e}",
                    exc_info=True,
                )
                # Rollback: delete the challenge so daily usage is not consumed
                if challenge_id:
                    delete_ladder_challenge(challenge_id)
                try:
                    await ctx.author.send(
                        "Error: Could not save match pairing. Your daily challenge was not consumed — try again!"
                    )
                except discord.Forbidden:
                    pass
                return

            # Randomly select which player gets the report buttons
            players = [
                (user_id, user_global, ctx.author, None, True),
                (
                    matched_user_id,
                    matched_global,
                    matched_user,
                    matched_user_deck_url,
                    False,
                ),
            ]
            reporter_player, other_player = random.sample(players, 2)
            (
                reporter_id,
                reporter_global,
                reporter_user,
                reporter_deck_url,
                reporter_is_joiner,
            ) = reporter_player
            other_id, other_global, other_user, other_deck_url, other_is_joiner = (
                other_player
            )

            reporter_deck_text = (
                f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""
            )

            match_type_emoji = "⚔️" if match_type == "ranked" else "⭐"
            match_type_label = "Ranked" if match_type == "ranked" else "Casual"

            match_card_view = MatchCardView(
                bot=self.bot,
                pairing_id=pairing_id,
                player1_id=reporter_id,
                player1_global=reporter_global,
                player2_id=other_id,
                player2_global=other_global,
                player1_deck_url=reporter_deck_url,
                player2_deck_url=other_deck_url,
                match_start_time=match_start_time,
                guild_id=guild_id,
                ladder_info=ladder_info,
                match_type=match_type,
            )

            try:
                await reporter_user.send(
                    f"{match_type_emoji} **{match_type_label} Match Found!** You've been matched with {other_user.mention} (**{other_global}**)!{reporter_deck_text}\n\n"
                    f"Use the button below to report the result when your match is done.",
                    view=match_card_view,
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        guild_obj = self.bot.get_guild(config.GUILD_ID)
                        if guild_obj:
                            member = guild_obj.get_member(reporter_user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member,
                                    read_messages=True,
                                    send_messages=True,
                                )

                        await dm_channel.send(
                            scrub_urls(
                                f"{reporter_user.mention} {match_type_emoji} **{match_type_label} Match Found!**\n\nYou've been matched with {other_user.mention} (**{other_global}**)!\n\n"
                                f"Use the button below to report the result when your match is done."
                            ),
                            view=match_card_view,
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for reporter: {e}")

            other_own_deck_text = (
                f"\n**Your Deck:** {other_deck_url}" if other_deck_url else ""
            )
            try:
                await other_user.send(
                    f"🎮 **Match Found!** You've been matched with {reporter_user.mention} (**{reporter_global}**)!{other_own_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome."
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        guild_obj = self.bot.get_guild(config.GUILD_ID)
                        if guild_obj:
                            member = guild_obj.get_member(other_user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member,
                                    read_messages=True,
                                    send_messages=True,
                                )

                        await dm_channel.send(
                            scrub_urls(
                                f"{other_user.mention} 🎮 **Match Found!**\n\nYou've been matched with {reporter_user.mention} (**{reporter_global}**)!\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome."
                            )
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to handle DM failure for other player: {e}"
                    )

            # Announce match in LFG channel
            if lfg_channel:
                elo_diff_display = abs(
                    get_user_event_elo(ladder_info["challenger_id"])
                    - get_user_event_elo(matched_user_id)
                )
                if elo_diff_display >= 100:
                    ladder_note = " 🏆 **Ladder Challenge!** Top 16 player - Special stakes (2x/0.5x ELO)!"
                else:
                    ladder_note = " 🏆 **Ladder Challenge!** Top 16 player (normal stakes - ELO diff < 100)"

                await lfg_channel.send(
                    f"{match_type_emoji} **{match_type_label} Match Found!** {ctx.author.mention} matched with {matched_user.mention}!{ladder_note}"
                )

            await self.update_lfg_status()

            logger.info(
                f"Ladder challenge by {user_global} (ID: {user_id}) immediately matched with {matched_global} (ID: {matched_user_id})"
            )
        else:
            # No match - user was added to queue, notify them
            # Challenge is NOT saved to DB yet - doesn't count against daily limit
            try:
                await ctx.author.send(
                    "You've been added to the ranked queue with ladder challenge stakes!\n"
                    "The next player to match with you will play for modified ELO:\n"
                    "**•** If they win: 2x ELO gain\n"
                    "**•** If you lose: 0.5x ELO loss\n"
                    "**•** If ELO difference < 100: Normal stakes\n\n"
                    "⏳ **Note:** This does not count as your daily challenge until a match is found. "
                    "If no one matches before the queue expires, you can use `!issue_challenge` again!\n"
                    "💡 **Tip:** You can use `!issue_challenge` in DMs with the bot anytime!"
                )
            except discord.Forbidden:
                if ctx.guild:
                    await ctx.send(
                        f"{ctx.author.mention}, you've joined the ranked queue with ladder challenge stakes!",
                        delete_after=10,
                    )

            # Update status
            await self.update_lfg_status()

            logger.info(
                f"Ladder challenge issued by {user_global} (ID: {user_id}) - added to ranked queue (not yet counted)"
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
                "`!issue_challenge` or `/issue-challenge` - Issue a ladder challenge (Top 16 or admins)\n"
                "**When to use:** Top 16 players or admins can issue once per day (disabled first week of event). "
                "Adds you to the ranked queue - the next player to match with you plays for special stakes. "
                "Non-Top 16 wins = 2x ELO gain, Top 16 loses = 0.5x ELO loss (normal stakes if ELO diff < 100)."
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
        """Get detailed help for admin commands (requires administrator, Bot Admin, or Judge role)."""
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
                "or to correct a missed game.\n\n"
                "`!admin_challenge_report @winner @loser @top16_player`\n"
                "Manually report a ladder challenge match. `@top16_player` is the **Top 16 player who issued `!issue_challenge`** (NOT the non-Top16 player).\n"
                "**When to use:** When a challenge match wasn't reported correctly or the challenge feature broke. "
                "Applies the same ELO rules as normal challenges (2x/0.5x if 100+ ELO apart).\n\n"
                "`!top_cut_report @winner @loser`\n"
                "Report a top cut match that only affects lifetime ELO (event ELO unchanged).\n"
                "**When to use:** For top cut matches where only lifetime ELO should be updated.\n\n"
                "`!reset_challenge @user`\n"
                "Reset a player's daily ladder challenge so they can use `!issue_challenge` again.\n"
                "**When to use:** When a player's challenge was wasted due to a bug or other issue."
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

        # Limited Management
        embed.add_field(
            name="Limited Management",
            value=(
                "`!admin_start_run @player <deck_url>`\n"
                "Manually start a limited arena run for a player.\n"
                "**When to use:** When a player's run was lost due to a reset or bug.\n\n"
                "`!admin_limited_report @winner @loser`\n"
                "Manually report a limited match result.\n\n"
                "`!remove_limited_match <match_id>`\n"
                "Remove a limited match and revert ELO changes.\n\n"
                "`!spot_limited_elo @user <elo>`\n"
                "Set a specific user's limited ELO to a custom value.\n\n"
                "`!reset_limited_elo` - **DANGER:** Reset ALL limited data"
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
                "`!refresh_leaderboard` - Force-refresh the leaderboard message\n"
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

        # Feature Pilots
        embed.add_field(
            name="Feature Pilots",
            value=(
                "`!pilot_on <name>` - Enable a feature pilot\n"
                "`!pilot_off <name>` - Disable a feature pilot\n"
                "`!pilots` - List all pilots and their status"
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

        embed.set_footer(
            text="All admin commands require admin permissions, Bot Admin role, or Judge role"
        )

        await ctx.send(embed=embed)

    @admin_help.error
    async def admin_help_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"admin_help error: {error}")
            await ctx.send(f"An error occurred: {error}")

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

            # Drop and recreate match_records table
            cur_matches.execute("DROP TABLE IF EXISTS match_records")
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
                description="All databases have been dropped and recreated:\n\u2022 ELO database reset\n\u2022 Match records cleared\n\nAll tables are ready to use.",
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
        else:
            logger.error(f"reset_elo error: {error}")
            await ctx.send(f"An error occurred: {error}")

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

            match_id, _, _, _, _, event_active = await record_match(
                reporter_id=ctx.author.id,
                winner_id=winner.id,
                winner_global=winner_name,
                loser_id=loser.id,
                loser_global=loser_name,
                first_player="n",
                match_time=0,
                match_comment="Match reported by admin",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first=None,
                loser_went_first=None,
            )

            # Update leaderboard
            await self.update_leaderboard()

            # Check for milestone and send announcement if needed
            await send_milestone_announcement(self.bot, winner.id, loser.id, match_id)

            # Get new ELOs for both players
            winner_elo = get_user_elo(winner.id)
            winner_event_elo = get_user_event_elo(winner.id)
            loser_elo = get_user_elo(loser.id)
            loser_event_elo = get_user_event_elo(loser.id)

            # Send confirmation
            elo_status = (
                "ELO updated" if event_active else "ELO not affected (no active event)"
            )
            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner.mention} ({winner_name})\n"
                f"**Loser:** {loser.mention} ({loser_name})\n"
                f"**Status:** {elo_status}"
            )
            if event_active:
                description += (
                    f"\n\n**New Ranks:**\n"
                    f"{winner_name}: **{winner_event_elo}** event\n"
                    f"{loser_name}: **{loser_event_elo}** event"
                )
            success_embed = discord.Embed(
                title="Match Reported",
                description=description,
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
        else:
            logger.error(f"admin_report error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def top_cut_report(
        self, ctx, winner: discord.Member = None, loser: discord.Member = None
    ):
        """Admin command to report a top cut match. Only affects lifetime ELO. Usage: !top_cut_report @winner @loser"""

        # Validate arguments
        if winner is None or loser is None:
            await ctx.send(
                "Please mention both players. Usage: `!top_cut_report @winner @loser`"
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

            # Record the match (match_type="testing" skips event ELO; lifetime handled below)
            match_id, _, _, _, _, _ = await record_match(
                reporter_id=ctx.author.id,
                winner_id=winner.id,
                winner_global=winner_name,
                loser_id=loser.id,
                loser_global=loser_name,
                first_player="n",
                match_time=0,
                match_comment="Top cut match reported by admin",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first=None,
                loser_went_first=None,
                match_type="testing",
            )

            # Update only lifetime ELO for both players
            new_winner_elo, winner_change = update_elo_db_lifetime_only(
                winner.id, winner_name, True, loser.id
            )
            new_loser_elo, loser_change = update_elo_db_lifetime_only(
                loser.id, loser_name, False, winner.id
            )

            # Update leaderboard
            await self.update_leaderboard()

            # Get event ELOs (unchanged) for display
            winner_event_elo = get_user_event_elo(winner.id)
            loser_event_elo = get_user_event_elo(loser.id)

            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner.mention} ({winner_name})\n"
                f"**Loser:** {loser.mention} ({loser_name})\n"
                f"**Type:** Top Cut (lifetime ELO only)\n\n"
                f"**Updated Ranks:**\n"
                f"{winner_name}: **{new_winner_elo}** lifetime ({winner_change:+d}) / **{winner_event_elo}** event (unchanged)\n"
                f"{loser_name}: **{new_loser_elo}** lifetime ({loser_change:+d}) / **{loser_event_elo}** event (unchanged)"
            )
            success_embed = discord.Embed(
                title="Top Cut Match Reported",
                description=description,
                color=discord.Color.gold(),
            )
            success_embed.set_footer(text=f"Reported by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "top_cut_report",
                target_id=winner.id,
                target_name=winner_name,
                previous_state={"winner_id": winner.id, "loser_id": loser.id},
                new_state={"match_id": match_id, "lifetime_only": True},
                details=f"Top cut match #{match_id}: {winner_name} beat {loser_name} (lifetime ELO only)",
            )

            logger.info(
                f"Admin {ctx.author} reported top cut match: {winner_name} beat {loser_name} (lifetime only)"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Top Cut Report Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Top cut report failed: {e}")

    @top_cut_report.error
    async def top_cut_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"top_cut_report error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    async def admin_limited_report(
        self, ctx, winner: discord.Member = None, loser: discord.Member = None
    ):
        """Admin command to manually report a limited match result. Usage: !admin_limited_report @winner @loser"""
        DRAFT_SORCERY_USER_ID = 247563860746305536

        # Permission check: bot admins OR the Draft Sorcery user
        is_admin = False
        if ctx.author.id == DRAFT_SORCERY_USER_ID:
            is_admin = True
        elif ctx.author.guild_permissions.administrator:
            is_admin = True
        elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in ctx.author.roles):
            is_admin = True
        elif any(role.id == config.JUDGE_ROLE_ID for role in ctx.author.roles):
            is_admin = True

        if not is_admin:
            await ctx.send("You don't have permission to use this command.")
            return

        # Validate arguments
        if winner is None or loser is None:
            await ctx.send(
                "Please mention both players. Usage: `!admin_limited_report @winner @loser`"
            )
            return

        if winner.id == loser.id:
            await ctx.send("Winner and loser cannot be the same player!")
            return

        if winner.bot or loser.bot:
            await ctx.send("Cannot report matches for bots!")
            return

        try:
            winner_name = winner.global_name or winner.display_name
            loser_name = loser.global_name or loser.display_name

            # Verify both players have active arena runs
            winner_run = get_active_arena_run(winner.id)
            loser_run = get_active_arena_run(loser.id)

            if not winner_run:
                await ctx.send(f"{winner.mention} ({winner_name}) does not have an active limited arena run.")
                return
            if not loser_run:
                await ctx.send(f"{loser.mention} ({loser_name}) does not have an active limited arena run.")
                return

            # Report the limited match
            match_id, winner_run_complete, loser_run_complete = limited_winner_report(
                reporter_id=ctx.author.id,
                winner_id=winner.id,
                winner_display_name=winner_name,
                loser_id=loser.id,
                loser_display_name=loser_name,
                first_player="n",
                match_time=0,
                curiosa_url_winner=winner_run["deck_url"],
                curiosa_url_loser=loser_run["deck_url"],
                match_comment="Admin reported limited match",
                winner_went_first="n",
                loser_went_first="n",
                winner_run_id=winner_run["run_id"],
                loser_run_id=loser_run["run_id"],
            )

            # Get updated ELOs and run info
            winner_elo = get_limited_elo(winner.id)
            loser_elo = get_limited_elo(loser.id)
            winner_run_summary = get_run_summary(winner_run["run_id"])
            loser_run_summary = get_run_summary(loser_run["run_id"])

            # Build confirmation embed
            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner.mention} ({winner_name})\n"
                f"**Loser:** {loser.mention} ({loser_name})\n\n"
                f"**Limited ELO:**\n"
                f"{winner_name}: **{winner_elo}**\n"
                f"{loser_name}: **{loser_elo}**\n\n"
                f"**{winner_name}'s Run:** {'Completed!' if winner_run_complete else 'Still active'}\n"
                f"**{loser_name}'s Run:** {'Completed!' if loser_run_complete else 'Still active'}"
            )

            success_embed = discord.Embed(
                title="Limited Match Reported",
                description=description,
                color=discord.Color.green(),
            )
            success_embed.set_footer(text=f"Reported by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "admin_limited_report",
                target_id=winner.id,
                target_name=winner_name,
                previous_state={"winner_id": winner.id, "loser_id": loser.id},
                new_state={"match_id": match_id, "winner_run_complete": winner_run_complete, "loser_run_complete": loser_run_complete},
                details=f"Admin reported limited match #{match_id}: {winner_name} beat {loser_name}",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) reported limited match: {winner_name} beat {loser_name}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Limited Match Report Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Admin limited match report failed: {e}")

    @admin_limited_report.error
    async def admin_limited_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error(f"admin_limited_report error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    async def limited_report(
        self, ctx, winner: discord.Member = None, loser: discord.Member = None
    ):
        """Report a limited match that only affects ELO (not arena runs). Usage: !limited_report @winner @loser"""
        DRAFT_SORCERY_USER_ID = 788152825325551647

        # Permission check: bot admins OR the Draft Sorcery user
        is_admin = False
        if ctx.author.id == DRAFT_SORCERY_USER_ID:
            is_admin = True
        elif ctx.author.guild_permissions.administrator:
            is_admin = True
        elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in ctx.author.roles):
            is_admin = True
        elif any(role.id == config.JUDGE_ROLE_ID for role in ctx.author.roles):
            is_admin = True

        if not is_admin:
            await ctx.send("You don't have permission to use this command.")
            return

        # Validate arguments
        if winner is None or loser is None:
            await ctx.send(
                "Please mention both players. Usage: `!limited_report @winner @loser`"
            )
            return

        if winner.id == loser.id:
            await ctx.send("Winner and loser cannot be the same player!")
            return

        if winner.bot or loser.bot:
            await ctx.send("Cannot report matches for bots!")
            return

        try:
            winner_name = winner.global_name or winner.display_name
            loser_name = loser.global_name or loser.display_name

            # Report the limited match (ELO only, no run impact)
            match_id, winner_new_elo, loser_new_elo = limited_elo_only_report(
                reporter_id=ctx.author.id,
                winner_id=winner.id,
                winner_display_name=winner_name,
                loser_id=loser.id,
                loser_display_name=loser_name,
                match_comment="Limited ELO-only match report",
            )

            # Build confirmation embed
            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner.mention} ({winner_name})\n"
                f"**Loser:** {loser.mention} ({loser_name})\n\n"
                f"**Limited ELO:**\n"
                f"{winner_name}: **{winner_new_elo}**\n"
                f"{loser_name}: **{loser_new_elo}**\n\n"
                f"*This match does not affect arena runs.*"
            )

            success_embed = discord.Embed(
                title="Limited Match Reported (ELO Only)",
                description=description,
                color=discord.Color.green(),
            )
            success_embed.set_footer(text=f"Reported by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "limited_report",
                target_id=winner.id,
                target_name=winner_name,
                previous_state={"winner_id": winner.id, "loser_id": loser.id},
                new_state={"match_id": match_id},
                details=f"Limited ELO-only match #{match_id}: {winner_name} beat {loser_name}",
            )

            logger.info(
                f"Limited ELO-only match reported by {ctx.author} (ID: {ctx.author.id}): {winner_name} beat {loser_name}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Limited Match Report Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Limited ELO-only match report failed: {e}")

    @limited_report.error
    async def limited_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        else:
            logger.error(f"limited_report error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def admin_challenge_report(
        self, ctx, winner: discord.Member = None, loser: discord.Member = None, top16_player: discord.Member = None
    ):
        """Admin command to manually report a ladder challenge result. Usage: !admin_challenge_report @winner @loser @top16_player"""

        # Validate arguments
        if winner is None or loser is None or top16_player is None:
            await ctx.send(
                "Please mention all three players. Usage: `!admin_challenge_report @winner @loser @top16_player`\n"
                "`@top16_player` is the **Top 16 player** who issued the `!issue_challenge` (NOT the non-Top16 challenger)."
            )
            return

        if winner.id == loser.id:
            await ctx.send("Winner and loser cannot be the same player!")
            return

        if winner.bot or loser.bot:
            await ctx.send("Cannot report matches for bots!")
            return

        if top16_player.id != winner.id and top16_player.id != loser.id:
            await ctx.send("The Top 16 player must be either the winner or the loser!")
            return

        try:
            winner_name = winner.global_name or winner.display_name
            loser_name = loser.global_name or loser.display_name

            # Check ELO difference to determine multipliers
            challenger_elo = get_user_event_elo(top16_player.id)
            opponent_id = loser.id if top16_player.id == winner.id else winner.id
            opponent_elo = get_user_event_elo(opponent_id)
            elo_diff = abs(challenger_elo - opponent_elo)

            if elo_diff < 100:
                elo_multiplier_winner = 1.0
                elo_multiplier_loser = 1.0
                stakes_label = "Normal stakes (ELO diff < 100)"
            else:
                elo_multiplier_winner = 2.0
                elo_multiplier_loser = 0.5
                stakes_label = f"Special stakes (ELO diff {elo_diff} >= 100)"

            guild_id = ctx.guild.id if ctx.guild else None

            ladder_info = {
                "challenger_id": top16_player.id,
                "challenge_id": None,  # No DB challenge record for admin reports
                "elo_multiplier_winner": elo_multiplier_winner,
                "elo_multiplier_loser": elo_multiplier_loser,
                "guild_id": guild_id,
            }

            # Determine ELO multipliers (non-Top16 wins → stakes apply)
            challenge_elo_mult_winner = 1.0
            challenge_elo_mult_loser = 1.0
            if winner.id != top16_player.id:
                challenge_elo_mult_winner = elo_multiplier_winner
                challenge_elo_mult_loser = elo_multiplier_loser

            match_id, _, _, _, _, event_active = await record_match(
                reporter_id=ctx.author.id,
                winner_id=winner.id,
                winner_global=winner_name,
                loser_id=loser.id,
                loser_global=loser_name,
                first_player="n",
                match_time=0,
                match_comment="Challenge match reported by admin",
                winner_deck_url=None,
                loser_deck_url=None,
                winner_went_first=None,
                loser_went_first=None,
                elo_multiplier_winner=challenge_elo_mult_winner,
                elo_multiplier_loser=challenge_elo_mult_loser,
            )

            # Assign role if non-Top16 won; complete challenge record
            stakes_msg = await _apply_ladder_elo(
                self.bot, ladder_info,
                winner.id, winner_name,
                loser.id, loser_name,
                match_id, event_active,
            )

            # Update leaderboard
            await self.update_leaderboard()

            # Check for milestone
            await send_milestone_announcement(self.bot, winner.id, loser.id, match_id)

            # Get new ELOs
            winner_elo = get_user_elo(winner.id)
            winner_event_elo = get_user_event_elo(winner.id)
            loser_elo = get_user_elo(loser.id)
            loser_event_elo = get_user_event_elo(loser.id)

            # Send confirmation
            elo_status = (
                "ELO updated" if event_active else "ELO not affected (no active event)"
            )
            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner.mention} ({winner_name})\n"
                f"**Loser:** {loser.mention} ({loser_name})\n"
                f"**Top 16 Player:** {top16_player.mention}\n"
                f"**Stakes:** {stakes_label}\n"
                f"**Status:** {elo_status}"
            )
            if event_active:
                description += (
                    f"\n\n**New Ranks:**\n"
                    f"{winner_name}: **{winner_event_elo}** event\n"
                    f"{loser_name}: **{loser_event_elo}** event"
                )
            if stakes_msg:
                description += stakes_msg

            success_embed = discord.Embed(
                title="Challenge Match Reported",
                description=description,
                color=discord.Color.gold(),
            )
            success_embed.set_footer(text=f"Reported by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "admin_challenge_report",
                target_id=winner.id,
                target_name=winner_name,
                previous_state={"winner_id": winner.id, "loser_id": loser.id, "top16_player_id": top16_player.id},
                new_state={"match_id": match_id, "elo_status": elo_status, "stakes": stakes_label},
                details=f"Admin reported challenge match #{match_id}: {winner_name} beat {loser_name} (top16_player: {top16_player.display_name})",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) reported challenge match: "
                f"{winner_name} beat {loser_name} (top16_player: {top16_player.display_name}, {stakes_label})"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Challenge Match Report Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Admin challenge match report failed: {e}")

    @admin_challenge_report.error
    async def admin_challenge_report_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"admin_challenge_report error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def reset_challenge(self, ctx, member: discord.Member = None):
        """Reset a player's daily ladder challenge so they can use !issue_challenge again.
        Usage: !reset_challenge @user
        """
        if member is None:
            await ctx.send("Usage: `!reset_challenge @user`")
            return

        from utils.database import reset_ladder_challenge_today

        deleted = reset_ladder_challenge_today(member.id)

        if deleted > 0:
            user_global = member.global_name or member.display_name
            await ctx.send(
                f"Reset {deleted} ladder challenge(s) for **{user_global}**. They can now use `!issue_challenge` again today."
            )
            log_admin_action(
                admin_id=ctx.author.id,
                admin_name=ctx.author.global_name or ctx.author.display_name,
                action="reset_challenge",
                details=f"Reset {deleted} ladder challenge(s) for {user_global} (ID: {member.id})",
            )
            logger.info(
                f"Admin {ctx.author.id} reset ladder challenge for {member.id} ({user_global}), deleted {deleted} record(s)"
            )
        else:
            await ctx.send(
                f"**{member.global_name or member.display_name}** has no ladder challenges today to reset."
            )

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
                    name=f"Previous Event Archived: {prev['event_name']} (Constructed)",
                    value=(
                        f"**Total Matches:** {prev['total_matches']}\n"
                        f"**Ranked Players:** {prev['total_players']}\n"
                        f"**Top 3:**\n{top_players_str}"
                    ),
                    inline=False,
                )

                limited_prev = prev.get("limited_summary")
                if limited_prev:
                    limited_top_str = (
                        "\n".join(
                            [f"  {i+1}. {name} ({elo} ELO)" for i, (name, elo) in enumerate(limited_prev["top_players"])]
                        ) or "No ranked players"
                    )
                    embed.add_field(
                        name=f"Previous Event Archived: {prev['event_name']} (Limited)",
                        value=(
                            f"**Total Matches:** {limited_prev['total_matches']}\n"
                            f"**Arena Runs:** {limited_prev['total_runs']}\n"
                            f"**Ranked Players:** {limited_prev['total_players']}\n"
                            f"**Top 3:**\n{limited_top_str}"
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
        else:
            logger.error(f"start_event error: {error}")
            await ctx.send(f"An error occurred: {error}")

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
                name="Constructed Final Results",
                value=(
                    f"**Total Matches:** {summary['total_matches']}\n"
                    f"**Ranked Players:** {summary['total_players']}\n"
                    f"**Top 3:**\n{top_players_str}"
                ),
                inline=False,
            )

            # Limited summary
            limited = summary.get("limited_summary")
            if limited:
                limited_top_str = "\n".join(
                    [f"  {i+1}. {name} ({elo} ELO)" for i, (name, elo) in enumerate(limited["top_players"])]
                ) or "No ranked players"
                embed.add_field(
                    name="Limited Final Results",
                    value=(
                        f"**Total Matches:** {limited['total_matches']}\n"
                        f"**Arena Runs:** {limited['total_runs']}\n"
                        f"**Ranked Players:** {limited['total_players']}\n"
                        f"**Top 3:**\n{limited_top_str}"
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
        else:
            logger.error(f"end_event error: {error}")
            await ctx.send(f"An error occurred: {error}")

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
        """Recalculate all event ELO from scratch by replaying match records. Usage: !recalculate_event_elo"""
        await ctx.send("\U0001f504 Recalculating event ELO... This may take a moment.")
        try:
            result = recalculate_event_elo()

            embed = discord.Embed(
                title="Event ELO Recalculated",
                description=f"Successfully recalculated ELO for **{result['event_name']}**",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Summary",
                value=(
                    f"**Players Reset:** {result['players_reset']}\n"
                    f"**Matches Replayed:** {result['matches_replayed']}\n"
                    f"**Players Updated:** {result['players_updated']}"
                ),
                inline=False,
            )
            if result["top_players"]:
                top_str = "\n".join(
                    f"{i + 1}. {name} ({elo})"
                    for i, (name, elo) in enumerate(result["top_players"])
                )
                embed.add_field(name="Top 5 Players", value=top_str, inline=False)

            embed.set_footer(text=f"Recalculated by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            await self.update_leaderboard()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "recalculate_event_elo",
                previous_state={"players_reset": result["players_reset"]},
                new_state={
                    "matches_replayed": result["matches_replayed"],
                    "players_updated": result["players_updated"],
                },
                details=f"Recalculated event ELO for '{result['event_name']}': {result['matches_replayed']} matches replayed, {result['players_updated']} players updated",
            )
        except ValueError as e:
            await ctx.send(str(e))
        except Exception as e:
            await ctx.send(f"\u274c Error recalculating ELO: {str(e)}")
            logger.error(f"Failed to recalculate event ELO: {e}")

    @recalculate_event_elo.error
    async def recalculate_event_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"recalculate_event_elo error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def refresh_leaderboard(self, ctx):
        """Admin command to force-refresh the leaderboard message. Usage: !refresh_leaderboard"""
        try:
            channel_id = config.LEADERBOARD_CHANNEL_ID
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await ctx.send(f"Leaderboard channel not found! `LEADERBOARD_CHANNEL_ID` = `{channel_id}` — check your config.")
                return
            await ctx.send(f"Refreshing leaderboard in <#{channel_id}>...")
            # Inline the core logic so errors aren't swallowed by update_leaderboard's try/except
            import sqlite3
            from utils.database import get_active_event

            active_event = get_active_event()
            event_start_str = None
            event_name = "Current Season"
            if active_event:
                event_start_str = active_event["start_date"].isoformat()
                event_name = active_event["event_name"]
            await ctx.send(f"Active event: **{event_name}** (start: `{event_start_str}`)")

            conn_elo = sqlite3.connect("elo.db")
            cursor_elo = conn_elo.cursor()
            if active_event:
                from repositories.elo_repo import get_event_participant_ids
                event_participants = get_event_participant_ids(event_start_str)
                cursor_elo.execute("SELECT COUNT(*) FROM overall_standings")
                total_in_db = cursor_elo.fetchone()[0]
                await ctx.send(f"Total players in DB: {total_in_db}, event participants: {len(event_participants)}")
            else:
                cursor_elo.execute("SELECT COUNT(*) FROM overall_standings")
                total_in_db = cursor_elo.fetchone()[0]
                await ctx.send(f"No active event. Total players in DB: {total_in_db}")
            conn_elo.close()

            await self.update_leaderboard()
            await ctx.send("Leaderboard refreshed.")
        except Exception as e:
            logger.error(f"Failed to refresh leaderboard: {e}")
            await ctx.send(f"Error refreshing leaderboard: {e}")

    @refresh_leaderboard.error
    async def refresh_leaderboard_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"refresh_leaderboard error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def spot_elo_reset(self, ctx, user: discord.Member = None, elo: int = None):
        """Admin command to set a specific user's event ELO. Usage: !spot_elo_reset @user 1500"""
        from utils.database import get_active_event

        if user is None:
            await ctx.send("Please mention a user. Usage: `!spot_elo_reset @user 1500`")
            return
        if elo is None:
            await ctx.send("Please specify an ELO value. Usage: `!spot_elo_reset @user 1500`")
            return
        if elo < 0 or elo > 5000:
            await ctx.send("ELO must be between 0 and 5000.")
            return
        if user.bot:
            await ctx.send("Cannot set ELO for bots!")
            return

        active_event = get_active_event()
        if not active_event:
            await ctx.send("No active event. Start an event first before updating ELO.")
            return

        try:
            user_name = user.global_name or user.display_name
            old_elo = set_player_event_elo(user.id, user_name, elo)

            await self.update_leaderboard()

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
        else:
            logger.error(f"spot_elo_reset error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def spot_limited_elo(self, ctx, user: discord.Member = None, elo: int = None):
        """Admin command to set a specific user's limited ELO. Usage: !spot_limited_elo @user 1587"""
        if user is None:
            await ctx.send("Please mention a user. Usage: `!spot_limited_elo @user 1587`")
            return
        if elo is None:
            await ctx.send("Please specify an ELO value. Usage: `!spot_limited_elo @user 1587`")
            return
        if elo < 0 or elo > 5000:
            await ctx.send("ELO must be between 0 and 5000.")
            return
        if user.bot:
            await ctx.send("Cannot set ELO for bots!")
            return

        try:
            user_name = user.global_name or user.display_name
            old_elo = get_limited_elo(user.id)
            upsert_limited_elo(user.id, user_name, elo)

            success_embed = discord.Embed(
                title="Limited ELO Updated",
                description=f"**User:** {user.mention} ({user_name})\n**Old Limited ELO:** {old_elo}\n**New Limited ELO:** {elo}",
                color=discord.Color.blue(),
            )
            success_embed.set_footer(text=f"Updated by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "spot_limited_elo",
                target_id=user.id,
                target_name=user_name,
                previous_state={"limited_elo": old_elo},
                new_state={"limited_elo": elo},
                details=f"Set {user_name}'s limited ELO from {old_elo} to {elo}",
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Limited ELO Update Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Spot limited ELO reset failed: {e}")

    @spot_limited_elo.error
    async def spot_limited_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"spot_limited_elo error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    async def correct_match(self, ctx, match_id: int = None):
        """Correct a match by flipping outcome and cascade-recalculating ELO. Usage: !correct_match <match_id>"""
        from cogs.lfg.persistent_confirm import (
            ensure_pending_corrections_table,
            save_pending_correction,
            PersistentCorrectionConfirmView,
        )
        from utils.database import get_match_players

        if match_id is None:
            await ctx.send("Please provide a match ID. Usage: `!correct_match <match_id>`")
            return

        # Check if user is an admin
        is_admin = False
        if ctx.author.guild_permissions.administrator:
            is_admin = True
        elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in ctx.author.roles):
            is_admin = True
        elif any(role.id == config.JUDGE_ROLE_ID for role in ctx.author.roles):
            is_admin = True

        # Admin flow - immediate correction (existing behavior)
        if is_admin:
            status_msg = await ctx.send("Analyzing match history...")
            try:
                result = correct_match_record(match_id)

                success_embed = discord.Embed(
                    title="Match Corrected",
                    description=(
                        f"**Match ID:** #{match_id}\n\n"
                        f"**Original Result:**\n"
                        f"~~Winner: {result['original_winner_name']}~~\n"
                        f"~~Loser: {result['original_loser_name']}~~\n\n"
                        f"**Corrected Result:**\n"
                        f"Winner: **{result['new_winner_name']}** ({result['new_winner_elo_change']:+d} ELO)\n"
                        f"Loser: **{result['new_loser_name']}** ({result['new_loser_elo_change']:+d} ELO)"
                    ),
                    color=discord.Color.green(),
                )
                success_embed.add_field(
                    name="Cascade Recalculation",
                    value=f"Recalculated **{result['recalculated_count']}** subsequent matches\nAffected **{len(result['affected_players'])}** players",
                    inline=False,
                )
                success_embed.set_footer(text=f"Corrected by {ctx.author.display_name}")
                await status_msg.edit(content=None, embed=success_embed)
                await self.update_leaderboard()

                log_admin_action(
                    ctx.author.id,
                    ctx.author.display_name,
                    "correct_match",
                    target_id=match_id,
                    previous_state={
                        "winner_name": result["original_winner_name"],
                        "loser_name": result["original_loser_name"],
                    },
                    new_state={
                        "winner_name": result["new_winner_name"],
                        "loser_name": result["new_loser_name"],
                        "recalculated_matches": result["recalculated_count"],
                    },
                    details=f"Corrected match #{match_id}: winner flipped from {result['original_winner_name']} to {result['new_winner_name']}, {result['recalculated_count']} subsequent matches recalculated",
                )
            except ValueError as e:
                await status_msg.edit(content=str(e))
            except Exception as e:
                error_embed = discord.Embed(
                    title="Match Correction Failed",
                    description=f"An error occurred: {str(e)}",
                    color=discord.Color.red(),
                )
                await status_msg.edit(content=None, embed=error_embed)
                logger.error(f"Match correction failed: {e}")
            return

        # Non-admin flow - verify participant and send confirmation to other player
        try:
            match_info = get_match_players(match_id)
        except ValueError as e:
            await ctx.send(str(e))
            return

        author_id = ctx.author.id
        winner_id = match_info["winner_id"]
        loser_id = match_info["loser_id"]

        # Check if user was part of this match
        if author_id != winner_id and author_id != loser_id:
            await ctx.send("You were not a part of that match.")
            return

        # Determine the other player
        if author_id == winner_id:
            other_player_id = loser_id
            other_player_name = match_info["loser_name"]
        else:
            other_player_id = winner_id
            other_player_name = match_info["winner_name"]

        # Save the pending correction request
        ensure_pending_corrections_table()
        correction_id = save_pending_correction({
            "match_id": match_id,
            "requester_id": author_id,
            "requester_name": ctx.author.display_name,
            "other_player_id": other_player_id,
            "other_player_name": other_player_name,
        })

        # Send confirmation request to the other player
        confirm_embed = discord.Embed(
            title="Match Correction Request",
            description=(
                f"**{ctx.author.display_name}** is requesting to correct Match #{match_id}.\n\n"
                f"**Current Result:**\n"
                f"Winner: {match_info['winner_name']}\n"
                f"Loser: {match_info['loser_name']}\n\n"
                f"**If corrected, the result will be flipped:**\n"
                f"Winner: {match_info['loser_name']}\n"
                f"Loser: {match_info['winner_name']}\n\n"
                f"Do you confirm this correction?"
            ),
            color=discord.Color.orange(),
        )

        view = PersistentCorrectionConfirmView(correction_id)

        try:
            other_user = await self.bot.fetch_user(other_player_id)
            await other_user.send(embed=confirm_embed, view=view)
            await ctx.send(
                f"A correction request for Match #{match_id} has been sent to **{other_player_name}** for confirmation."
            )
        except discord.Forbidden:
            # If DMs are disabled, send in a channel
            match_report_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    f"<@{other_player_id}>", embed=confirm_embed, view=view
                )
                await ctx.send(
                    f"A correction request for Match #{match_id} has been sent to **{other_player_name}** for confirmation."
                )
            else:
                await ctx.send(
                    "Could not send the correction request. The other player has DMs disabled and no fallback channel is configured."
                )
        except Exception as e:
            logger.error(f"Failed to send correction request: {e}")
            await ctx.send(f"An error occurred while sending the correction request: {e}")

    @correct_match.error
    async def correct_match_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid match ID. Please provide a valid number.")
        else:
            logger.error(f"correct_match error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def remove_match(self, ctx, match_id: int = None):
        """Remove a match report and revert ELO changes. Usage: !remove_match <match_id>"""
        if match_id is None:
            await ctx.send("Please provide a match ID. Usage: `!remove_match <match_id>`")
            return

        try:
            result = remove_match_record(match_id)

            success_embed = discord.Embed(
                title="Match Removed",
                description=(
                    f"**Match ID:** #{match_id}\n"
                    f"**Winner:** {result['winner_name']}\n"
                    f"**Loser:** {result['loser_name']}\n"
                    f"**Date:** {result['timestamp']}\n\n"
                    f"**ELO Reverted:**\n" + "\n".join(result["reverted_info"])
                ),
                color=discord.Color.orange(),
            )
            success_embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)
            await self.update_leaderboard()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "remove_match",
                target_id=match_id,
                previous_state={
                    "winner_name": result["winner_name"],
                    "loser_name": result["loser_name"],
                    "timestamp": result["timestamp"],
                },
                new_state={"result": "match deleted"},
                details=f"Removed match #{match_id}: {result['winner_name']} vs {result['loser_name']} ({result['timestamp']})",
            )
        except ValueError as e:
            await ctx.send(str(e))
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
        else:
            logger.error(f"remove_match error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def remove_limited_match(self, ctx, match_id: int = None):
        """Admin command to remove a limited match report and revert limited ELO changes. Usage: !remove_limited_match <match_id>"""
        if match_id is None:
            await ctx.send(
                "Please provide a match ID. Usage: `!remove_limited_match <match_id>`"
            )
            return

        try:
            match_conn = sqlite3.connect("match_records.db")
            match_cursor = match_conn.cursor()

            match_cursor.execute(
                """SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                          winner_elo_change, loser_elo_change, timestamp, winner_run_id, loser_run_id
                   FROM limited_match_records WHERE match_id = ?""",
                (match_id,),
            )
            match = match_cursor.fetchone()

            if not match:
                await ctx.send(f"Limited match ID #{match_id} not found.")
                match_conn.close()
                return

            (
                match_id_db, winner_id, winner_name, loser_id, loser_name,
                winner_elo_change, loser_elo_change, timestamp, winner_run_id, loser_run_id,
            ) = match

            # Revert limited ELO
            elo_conn = sqlite3.connect("elo.db")
            elo_cursor = elo_conn.cursor()

            reverted_info = []
            if winner_elo_change:
                elo_cursor.execute(
                    "UPDATE limited_elo SET elo = elo - ? WHERE user_id = ?",
                    (winner_elo_change, winner_id),
                )
                reverted_info.append(f"**{winner_name}**: -{winner_elo_change} Limited ELO")

            if loser_elo_change:
                elo_cursor.execute(
                    "UPDATE limited_elo SET elo = elo - ? WHERE user_id = ?",
                    (loser_elo_change, loser_id),
                )
                reverted_info.append(
                    f"**{loser_name}**: +{-loser_elo_change} Limited ELO"
                )

            elo_conn.commit()
            elo_conn.close()

            # Revert arena run W/L records
            run_revert_info = []
            for run_id, player_name, won in [
                (winner_run_id, winner_name, True),
                (loser_run_id, loser_name, False),
            ]:
                if run_id:
                    match_cursor.execute(
                        "SELECT wins, losses, status FROM limited_arena_runs WHERE run_id = ?",
                        (run_id,),
                    )
                    run_row = match_cursor.fetchone()
                    if run_row:
                        wins, losses, status = run_row
                        if won:
                            new_wins = max(0, wins - 1)
                            match_cursor.execute(
                                "UPDATE limited_arena_runs SET wins = ? WHERE run_id = ?",
                                (new_wins, run_id),
                            )
                            run_revert_info.append(f"**{player_name}** run #{run_id}: wins {wins} → {new_wins}")
                        else:
                            new_losses = max(0, losses - 1)
                            match_cursor.execute(
                                "UPDATE limited_arena_runs SET losses = ? WHERE run_id = ?",
                                (new_losses, run_id),
                            )
                            run_revert_info.append(f"**{player_name}** run #{run_id}: losses {losses} → {new_losses}")

            # Delete the limited match record
            match_cursor.execute(
                "DELETE FROM limited_match_records WHERE match_id = ?", (match_id,)
            )
            match_conn.commit()
            match_conn.close()

            description = (
                f"**Match ID:** #{match_id}\n"
                f"**Winner:** {winner_name}\n"
                f"**Loser:** {loser_name}\n"
                f"**Date:** {timestamp}\n\n"
                f"**Limited ELO Reverted:**\n" + "\n".join(reverted_info)
            )
            if run_revert_info:
                description += "\n\n**Arena Run Records Reverted:**\n" + "\n".join(run_revert_info)

            success_embed = discord.Embed(
                title="Limited Match Removed",
                description=description,
                color=discord.Color.orange(),
            )
            success_embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "remove_limited_match",
                target_id=match_id,
                previous_state={
                    "match_id": match_id,
                    "winner_id": winner_id,
                    "winner_name": winner_name,
                    "loser_id": loser_id,
                    "loser_name": loser_name,
                    "timestamp": timestamp,
                },
                new_state={"result": "limited match deleted"},
                details=f"Removed limited match #{match_id}: {winner_name} vs {loser_name} ({timestamp})",
            )

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) removed limited match #{match_id}: {winner_name} vs {loser_name}"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Limited Match Removal Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"remove_limited_match failed: {e}")

    @remove_limited_match.error
    async def remove_limited_match_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid match ID. Please provide a valid number.")
        else:
            logger.error(f"remove_limited_match error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    @is_bot_admin()
    async def reset_limited_elo(self, ctx):
        """Admin command to reset all limited ELO ratings, match records, and arena runs."""
        try:
            # Capture counts for audit log
            elo_conn = sqlite3.connect("elo.db")
            elo_cur = elo_conn.cursor()
            elo_cur.execute("SELECT COUNT(*) FROM limited_elo")
            total_players = elo_cur.fetchone()[0]
            elo_conn.close()

            match_conn = sqlite3.connect("match_records.db")
            match_cur = match_conn.cursor()
            match_cur.execute("SELECT COUNT(*) FROM limited_match_records")
            total_matches = match_cur.fetchone()[0]
            match_cur.execute("SELECT COUNT(*) FROM limited_arena_runs")
            total_runs = match_cur.fetchone()[0]
            match_conn.close()

            # Wipe limited ELO
            elo_conn = sqlite3.connect("elo.db")
            elo_conn.execute("DELETE FROM limited_elo")
            elo_conn.commit()
            elo_conn.close()

            # Wipe limited match records and arena runs
            match_conn = sqlite3.connect("match_records.db")
            match_conn.execute("DELETE FROM limited_match_records")
            match_conn.execute("DELETE FROM limited_arena_runs")
            match_conn.execute("DELETE FROM limited_active_pairings")
            match_conn.commit()
            match_conn.close()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "reset_limited_elo",
                previous_state={
                    "total_players": total_players,
                    "total_matches": total_matches,
                    "total_runs": total_runs,
                },
                new_state={"result": "all limited data wiped"},
                details=f"Limited reset: {total_players} players, {total_matches} matches, {total_runs} runs deleted",
            )

            success_embed = discord.Embed(
                title="Limited Data Reset Complete",
                description=(
                    f"All limited format data has been cleared:\n"
                    f"• **{total_players}** limited ELO ratings reset\n"
                    f"• **{total_matches}** limited match records deleted\n"
                    f"• **{total_runs}** arena runs deleted\n"
                    f"• Active limited pairings cleared\n\n"
                    f"All limited tables are ready to use."
                ),
                color=discord.Color.green(),
            )
            await ctx.send(embed=success_embed)
            logger.info(
                f"Limited data reset completed by {ctx.author} (ID: {ctx.author.id})"
            )

        except Exception as e:
            error_embed = discord.Embed(
                title="Limited Reset Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"reset_limited_elo failed: {e}")

    @reset_limited_elo.error
    async def reset_limited_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")
        else:
            logger.error(f"reset_limited_elo error: {error}")
            await ctx.send(f"An error occurred: {error}")

    @commands.command()
    async def admin_start_run(self, ctx, player: discord.Member = None, deck_url: str = None):
        """Admin command to manually start a limited arena run for a player. Usage: !admin_start_run @player <deck_url>"""
        DRAFT_SORCERY_ROLE_ID = 1499801776772354160

        is_admin = False
        if ctx.author.guild_permissions.administrator:
            is_admin = True
        elif any(role.id == config.BOT_ADMIN_ROLE_ID for role in ctx.author.roles):
            is_admin = True
        elif any(role.id == config.JUDGE_ROLE_ID for role in ctx.author.roles):
            is_admin = True
        elif any(role.id == DRAFT_SORCERY_ROLE_ID for role in ctx.author.roles):
            is_admin = True

        if not is_admin:
            await ctx.send("You don't have permission to use this command.")
            return

        if player is None or deck_url is None:
            await ctx.send("Usage: `!admin_start_run @player <deck_url>`")
            return

        if player.bot:
            await ctx.send("Cannot start runs for bots!")
            return

        try:
            display_name = player.global_name or player.display_name
            run = start_arena_run(player.id, display_name, deck_url)

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "admin_start_run",
                new_state={"run_id": run["run_id"], "player_id": player.id, "deck_url": deck_url},
                details=f"Admin started arena run #{run['run_id']} for {display_name} (ID: {player.id})",
            )

            embed = discord.Embed(
                title="Arena Run Started",
                description=(
                    f"Started a new limited arena run for {player.mention}\n"
                    f"• **Run ID:** {run['run_id']}\n"
                    f"• **Deck:** {deck_url}\n"
                    f"• **Starting ELO:** {run['starting_elo']}"
                ),
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)
            logger.info(f"Admin {ctx.author} started arena run #{run['run_id']} for {display_name} (ID: {player.id})")

        except ValueError as e:
            await ctx.send(f"Cannot start run: {e}")
        except Exception as e:
            await ctx.send(f"Error starting run: {e}")
            logger.error(f"admin_start_run failed: {e}")

    @admin_start_run.error
    async def admin_start_run_error(self, ctx, error):
        logger.error(f"admin_start_run error: {error}")
        await ctx.send(f"An error occurred: {error}")

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
                "SELECT user_id, user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC"
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
                "SELECT user_id, user_display_name, online_elo FROM overall_standings ORDER BY online_elo DESC"
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
        """Remove a player and revert all ELO changes from their matches. Usage: !remove_player @user"""
        if user is None:
            await ctx.send("Please mention a user. Usage: `!remove_player @user`")
            return
        if user.bot:
            await ctx.send("Cannot remove bots!")
            return

        try:
            user_name = user.global_name or user.display_name
            result = remove_player_service(user.id, user_name)

            embed = discord.Embed(
                title="Player Removed",
                description=f"**Player:** {user.mention} ({user_name})",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="Matches Deleted",
                value=f"{result['matches_deleted']} ranked match(es)",
                inline=False,
            )

            adjustments_made = result["adjustments_made"]
            if adjustments_made:
                adjustments_text = "\n".join(adjustments_made[:10])
                if len(adjustments_made) > 10:
                    adjustments_text += f"\n... and {len(adjustments_made) - 10} more"
                embed.add_field(name="ELO Adjustments", value=adjustments_text, inline=False)
            else:
                embed.add_field(
                    name="ELO Adjustments",
                    value="No ELO data to revert (matches may have been missing ELO change data)",
                    inline=False,
                )

            embed.add_field(
                name="Player ELO Removed",
                value="Yes" if result["player_removed"] else "Player was not in ELO standings",
                inline=False,
            )
            embed.set_footer(text=f"Removed by {ctx.author.display_name}")
            await ctx.send(embed=embed)
            await self.update_leaderboard()

            log_admin_action(
                ctx.author.id,
                ctx.author.display_name,
                "remove_player",
                target_id=user.id,
                target_name=user_name,
                previous_state={
                    "matches": result["matches_deleted"],
                    "opponents_adjusted": len(adjustments_made),
                },
                new_state={"result": "player removed"},
                details=f"Removed player {user_name}: {result['matches_deleted']} matches deleted, {len(adjustments_made)} opponents adjusted",
            )
        except ValueError as e:
            await ctx.send(str(e))
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
        else:
            logger.error(f"remove_player error: {error}")
            await ctx.send(f"An error occurred: {error}")

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

    @commands.command()
    async def forfeit(self, ctx):
        """Forfeit your active limited arena run. Usage: !forfeit"""
        user_id = ctx.author.id

        # Check if the user has an active arena run
        active_run = get_active_arena_run(user_id)
        if not active_run:
            await ctx.send("You don't have an active limited arena run to forfeit.")
            return

        try:
            forfeit_summary = forfeit_arena_run(user_id)
            await ctx.send(f"💀 **Arena Run Forfeited**\n\n{forfeit_summary}")
            logger.info(f"User {ctx.author} ({user_id}) forfeited their limited arena run")
        except ValueError as e:
            await ctx.send(f"Could not forfeit: {e}")
        except Exception as e:
            await ctx.send("An error occurred while forfeiting your run.")
            logger.error(f"Forfeit command failed for {ctx.author} ({user_id}): {e}")
