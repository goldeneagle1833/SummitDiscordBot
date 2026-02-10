import discord
from discord.ext import commands, tasks
import datetime
import logging
import random
from random import randrange
import asyncio
import re
import sqlite3
from openai import OpenAI

import config
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
)
from utils.constants import SORCERY_NICKNAMES

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

logger = logging.getLogger("discord_bot")

# Constants for DM failure handling
DM_DISABLED_ROLE_ID = 1445222741686095994
DM_DISABLED_CHANNEL_ID = 1456299008023728302

# Milestone announcements channel
MILESTONE_ANNOUNCEMENT_CHANNEL_ID = 1319121592499961886

# URL pattern for scrubbing URLs from public fallback channel messages
_URL_PATTERN = re.compile(r"https?://\S+")


def scrub_urls(text: str) -> str:
    """Remove URLs from a message to avoid leaking deck links in public channels."""
    return _URL_PATTERN.sub("[link removed]", text)


def generate_milestone_message(count: int) -> str:
    """
    Generate a milestone message using ChatGPT.
    The message is from the perspective of a tired/frantic bot.
    """
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-nano",
            instructions=(
                "You are a Discord bot that tracks match results for a card game called Sorcery. and a little snarky "
                "You just recorded a milestone match. Respond in 1-2 sentences from your perspective as Matthew McConaughey, "
                "with an existential crisis that only he can solve while trying to keep up with all these matches. Be sarcastic. "
                "Do NOT use any emojis. Keep it under 50 words."
            ),
            input=f"We just hit {count} total matches recorded! Announce this milestone.",
        )
        return response.output_text
    except Exception as e:
        logger.error(f"OpenAI API error for milestone message: {e}")
        return f"Phew... {count} matches recorded. My circuits are working overtime. Thanks to PLAYER1 and PLAYER2 for this milestone."


async def send_milestone_announcement(
    bot, winner_id: int, loser_id: int, match_id: int
):
    """
    Check if we hit a milestone and send an announcement if so.

    Args:
        bot: The Discord bot instance
        winner_id: The ID of the winning player
        loser_id: The ID of the losing player
        match_id: The match ID that was just recorded
    """
    milestone = check_milestone(match_id)
    if milestone:
        try:
            channel = bot.get_channel(MILESTONE_ANNOUNCEMENT_CHANNEL_ID)
            if channel:
                # Generate message from ChatGPT and replace placeholders with actual mentions
                message = generate_milestone_message(milestone)
                message = message.replace("PLAYER1", f"<@{winner_id}>")
                message = message.replace("PLAYER2", f"<@{loser_id}>")
                await channel.send(message)
                logger.info(f"Sent milestone announcement for {milestone} matches!")
            else:
                logger.warning(
                    f"Could not find milestone channel {MILESTONE_ANNOUNCEMENT_CHANNEL_ID}"
                )
        except Exception as e:
            logger.error(f"Error sending milestone announcement: {e}")


# In-memory LFG queue (user_id: {timestamp, timeframe, deck_url})
lfg_queue = {}

# Lock to prevent race conditions when accessing the queue
lfg_queue_lock = asyncio.Lock()

# Track pending match reports awaiting confirmation
# Key: (reporter_id, opponent_id), Value: match report data
pending_match_reports = {}

# Track processed matches to prevent double reporting
# Key: frozenset({player1_id, player2_id}), Value: timestamp
processed_matches = {}

# Store the persistent status message ID
lfg_status_message_id = None

# Store the leaderboard message ID
leaderboard_message_id = None


class MatchReportModal(discord.ui.Modal, title="Match Report"):
    curiosa_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="Enter Your Curiosa Deck URL",
        required=False,
    )

    first_player = discord.ui.TextInput(
        label="Did you go first? (y/n)",
        placeholder="Enter YES or NO",
        required=False,
        max_length=3,
    )

    match_time = discord.ui.TextInput(
        label="Match time",
        placeholder="Estimate match time in minutes (eg. 30)",
        required=False,
        max_length=3,
        min_length=1,
    )

    match_comment = discord.ui.TextInput(
        label="Notes",
        placeholder="Anything else about the match?",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(
        self, winner_id, winner_global, loser_id, loser_global, is_winner, bot
    ):
        super().__init__()
        self.winner_id = winner_id
        self.winner_global = winner_global
        self.loser_id = loser_id
        self.loser_global = loser_global
        self.is_winner = is_winner
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction_user_id = interaction.user.id
        interaction_global = (
            interaction.user.global_name or interaction.user.display_name
        )

        curiosa_link = (
            self.curiosa_url.value if self.curiosa_url.value else "No URL provided"
        )
        match_comment = self.match_comment.value if self.match_comment.value else ""
        first_player = self.first_player.value if self.first_player.value else "n"
        match_time = (
            int(self.match_time.value) if self.match_time.value.isdigit() else 0
        )

        # Determine winner_went_first and loser_went_first
        # first_player is what the reporter answered about whether THEY went first
        reporter_went_first = "y" in str(first_player).lower()

        if self.is_winner:
            # Reporter is the winner
            winner_went_first = "y" if reporter_went_first else "n"
            loser_went_first = "n" if reporter_went_first else "y"
            match_id, _, _, event_active = await winner_report(
                interaction_user_id,
                self.winner_id,
                self.winner_global,
                True,
                self.loser_id,
                self.loser_global,
                first_player,
                match_time,
                curiosa_link,
                match_comment,
                interaction_user_id,
                interaction_global,
                winner_deck_url=curiosa_link,
                loser_deck_url=None,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
            )
        else:
            # Reporter is the loser
            winner_went_first = "n" if reporter_went_first else "y"
            loser_went_first = "y" if reporter_went_first else "n"
            match_id, _, _, event_active = await losser_report(
                interaction_user_id,
                self.winner_id,
                self.winner_global,
                False,
                self.loser_id,
                self.loser_global,
                first_player,
                match_time,
                curiosa_link,
                match_comment,
                interaction_user_id,
                interaction_global,
                winner_deck_url=None,
                loser_deck_url=curiosa_link,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
            )

        elo_msg = "" if event_active else "\n*(No active event - ELO not affected)*"
        await interaction.followup.send(
            f"Match report submitted! **Match ID: #{match_id}**\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}{elo_msg}",
            ephemeral=True,
        )

        # Check for milestone and send announcement if needed
        if self.bot:
            await send_milestone_announcement(
                self.bot, self.winner_id, self.loser_id, match_id
            )


class MatchConfirmationButtons(discord.ui.View):
    """Buttons for confirming a match report from opponent"""

    def __init__(
        self,
        reporter_id: int,
        opponent_id: int,
        winner_id: int,
        winner_global: str,
        loser_id: int,
        loser_global: str,
        is_winner: bool,
        bot=None,
        channel=None,
        match_start_time=None,
        curiosa_link: str = "No URL provided",
        first_player: str = "n",
        match_time: int = 0,
        match_comment: str = "",
        reporter_global: str = None,
        opponent_global: str = None,
        winner_deck_url: str = None,
        loser_deck_url: str = None,
    ):
        super().__init__(timeout=86400)  # 24 hour timeout - plenty of time to confirm
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.opponent_id = opponent_id
        self.opponent_global = opponent_global
        self.winner_id = winner_id
        self.winner_global = winner_global
        self.loser_id = loser_id
        self.loser_global = loser_global
        self.is_winner = is_winner
        self.bot = bot
        self.channel = channel
        self.match_start_time = match_start_time
        self.curiosa_link = curiosa_link
        self.first_player = first_player
        self.match_time = match_time
        self.match_comment = match_comment
        self.winner_deck_url = winner_deck_url
        self.loser_deck_url = loser_deck_url

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.success,
        custom_id="confirm_match_report",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if confirmer needs to provide a deck URL
        # is_winner=True means confirmer won (their deck is winner_deck_url)
        # is_winner=False means confirmer lost (their deck is loser_deck_url)
        confirmer_deck_url = (
            self.winner_deck_url if self.is_winner else self.loser_deck_url
        )
        if not confirmer_deck_url:
            # Show modal to collect deck URL before proceeding
            modal = ConfirmerDeckURLModal(self, interaction)
            await interaction.response.send_modal(modal)
            return

        # Disable button immediately to prevent double-clicks
        button.disabled = True
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # Check for duplicate match (already processed between these two players recently)
        match_key = frozenset({self.winner_id, self.loser_id})
        now = datetime.datetime.now()
        if match_key in processed_matches:
            last_report_time = processed_matches[match_key]
            # If a match between these players was reported in the last 5 minutes, reject
            if (now - last_report_time).total_seconds() < 300:
                await interaction.response.send_message(
                    "This match has already been recorded. Duplicate report prevented.",
                    ephemeral=True,
                )
                await interaction.message.edit(
                    content="Match already recorded (duplicate prevented).",
                    view=None,
                )
                return

        # Mark this match as processed
        processed_matches[match_key] = now

        await interaction.response.defer()

        # Use provided match_time, or calculate from start to confirmation if not provided
        match_time = self.match_time
        if match_time == 0 and self.match_start_time:
            time_diff = datetime.datetime.now() - self.match_start_time
            match_time = int(time_diff.total_seconds() / 60)  # Convert to minutes

        # Use winner and loser deck URLs properly
        winner_deck = self.winner_deck_url or "No URL provided"
        loser_deck = self.loser_deck_url or "No URL provided"
        combined_comment = f"Winner deck: {winner_deck} | Loser deck: {loser_deck}"
        if self.match_comment:
            combined_comment = f"{self.match_comment} | {combined_comment}"

        # Determine winner_went_first and loser_went_first based on reporter
        # first_player indicates if the REPORTER went first
        # We need to translate this to winner/loser perspective
        reporter_went_first = (
            self.first_player and "y" in str(self.first_player).lower()
        )
        reporter_is_winner = self.reporter_id == self.winner_id

        if reporter_is_winner:
            # Reporter is winner
            winner_went_first = "y" if reporter_went_first else "n"
            loser_went_first = "n" if reporter_went_first else "y"
        else:
            # Reporter is loser
            winner_went_first = "n" if reporter_went_first else "y"
            loser_went_first = "y" if reporter_went_first else "n"

        # Submit match report only ONCE (not twice)
        # This will insert one record and update ELO for the winner
        match_id, _, _, event_active = await winner_report(
            self.reporter_id,  # reporter_id (who originally reported)
            self.winner_id,
            self.winner_global,
            True,
            self.loser_id,
            self.loser_global,
            self.first_player,
            match_time,
            winner_deck,  # Use winner's deck URL as primary (backward compatibility)
            combined_comment,  # Include both decks in comment
            self.winner_id,  # interaction_user_id
            self.winner_global,  # interaction_global
            winner_deck_url=self.winner_deck_url,
            loser_deck_url=self.loser_deck_url,
            winner_went_first=winner_went_first,
            loser_went_first=loser_went_first,
        )

        # Update ELO for the loser as well
        from utils.database import update_elo_db

        update_elo_db(self.loser_id, self.loser_global, False, self.winner_id)

        elo_msg = "" if event_active else " *(No active event - ELO not affected)*"
        # Remove the confirmation message
        await interaction.message.edit(
            content=f"Match confirmed! **Match ID: #{match_id}** - {self.winner_global} won against {self.loser_global}.{elo_msg}",
            view=None,
        )

        # Send confirmation to confirming user
        await interaction.followup.send(
            f"Match report confirmed and submitted! **Match ID: #{match_id}**\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}{elo_msg}",
            ephemeral=True,
        )

        # Notify the reporter
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"{self.opponent_global} has confirmed your match report! Match has been recorded."
            )
        except discord.Forbidden:
            # If DM fails, send to match-report channel
            match_report_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    scrub_urls(
                        f"{reporter.mention} {self.opponent_global} has confirmed your match report! Match has been recorded."
                    )
                )
        except Exception:
            pass

        # Remove from pending
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)

        # Update leaderboard in designated channel
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

        # Check for milestone and send announcement if needed
        await send_milestone_announcement(
            self.bot, self.winner_id, self.loser_id, match_id
        )

    @discord.ui.button(
        label="Dispute",
        style=discord.ButtonStyle.danger,
        custom_id="dispute_match_report",
    )
    async def dispute_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            f"You have disputed the match report. This dispute will not log an entry.\n\n"
            f"To submit a corrected report, use `!challenge @{self.reporter_global}` to trigger a new report.",
            ephemeral=True,
        )

        # Remove the confirmation message
        await interaction.message.edit(
            content=f"Match report disputed by {self.opponent_global}. No entry was logged.\n\n"
            f"To submit a corrected report, use `!challenge @opponent` to trigger a new report.",
            view=None,
        )

        # Notify the reporter
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"{self.opponent_global} has disputed your match report. The dispute did not log an entry.\n\n"
                f"To submit a corrected report, use `!challenge @{self.opponent_global}` to trigger a new report."
            )
        except discord.Forbidden:
            # If DM fails, send to match-report channel
            match_report_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    scrub_urls(
                        f"{reporter.mention} {self.opponent_global} has disputed your match report. The dispute did not log an entry.\n\n"
                        f"To submit a corrected report, use `!challenge @{self.opponent_global}` to trigger a new report."
                    )
                )
        except Exception:
            pass

        # Remove from pending
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)


class ReporterDeckURLModal(discord.ui.Modal, title="Enter Your Deck"):
    """Modal for capturing deck URL when reporter didn't provide one at queue join"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL (Optional)",
        placeholder="Enter your deck URL or leave blank",
        required=False,
    )

    def __init__(
        self, view: "LFGReportButtons", interaction: discord.Interaction, is_win: bool
    ):
        super().__init__()
        self.view = view
        self.original_interaction = interaction
        self.is_win = is_win

    async def on_submit(self, interaction: discord.Interaction):
        # Update the reporter's deck URL
        self.view.reporter_deck_url = (
            self.deck_url.value.strip() if self.deck_url.value else None
        )

        # Continue with the original flow
        if self.is_win:
            await self._process_win_report(interaction)
        else:
            await self._process_loss_report(interaction)

    async def _process_win_report(self, interaction: discord.Interaction):
        """Process win report after collecting deck URL"""
        view = self.view
        original_interaction = self.original_interaction

        # Disable buttons immediately to prevent double-clicks
        for item in view.children:
            item.disabled = True
        try:
            await original_interaction.message.edit(view=view)
        except Exception:
            pass

        opponent_id = (
            view.player2_id
            if original_interaction.user.id == view.player1_id
            else view.player1_id
        )
        opponent_global = (
            view.player2_global
            if original_interaction.user.id == view.player1_id
            else view.player1_global
        )

        # Check if a report is already pending for this match
        if (original_interaction.user.id, opponent_id) in pending_match_reports or (
            opponent_id,
            original_interaction.user.id,
        ) in pending_match_reports:
            await interaction.response.send_message(
                "A report for this match is already pending confirmation.",
                ephemeral=True,
            )
            return

        # Store pending report with deck URLs
        pending_match_reports[(original_interaction.user.id, opponent_id)] = {
            "winner_id": original_interaction.user.id,
            "winner_global": original_interaction.user.global_name
            or original_interaction.user.display_name,
            "loser_id": opponent_id,
            "loser_global": opponent_global,
            "reporter_id": original_interaction.user.id,
            "reporter_global": original_interaction.user.global_name
            or original_interaction.user.display_name,
            "is_winner": True,
            "opponent_message": None,
            "match_start_time": view.match_start_time,
            "reporter_deck_url": view.reporter_deck_url,
            "opponent_deck_url": view.opponent_deck_url,
            "first_player": view.first_player,
        }

        # Send confirmation to opponent
        try:
            opponent = await view.bot.fetch_user(opponent_id)

            confirmation_view = MatchConfirmationButtons(
                reporter_id=original_interaction.user.id,
                reporter_global=original_interaction.user.global_name
                or original_interaction.user.display_name,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=original_interaction.user.id,
                winner_global=original_interaction.user.global_name
                or original_interaction.user.display_name,
                loser_id=opponent_id,
                loser_global=opponent_global,
                is_winner=False,
                bot=view.bot,
                channel=view.channel,
                match_start_time=view.match_start_time,
                first_player=view.first_player,
                winner_deck_url=view.reporter_deck_url,
                loser_deck_url=view.opponent_deck_url,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = original_interaction.guild
            if guild:
                role = guild.get_role(DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            if opponent_has_dm_issue:
                dm_channel = view.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **LOST** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    try:
                        if guild:
                            role = guild.get_role(DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)

                        dm_channel = view.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                        if dm_channel:
                            if guild:
                                member = guild.get_member(opponent_id)
                                if member:
                                    await dm_channel.set_permissions(
                                        member, read_messages=True, send_messages=True
                                    )
                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                        else:
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )

            # Remove buttons from original message
            if original_interaction.message:
                try:
                    await original_interaction.message.edit(view=None)
                except Exception:
                    pass

        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error in ReporterDeckURLModal win report: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )

    async def _process_loss_report(self, interaction: discord.Interaction):
        """Process loss report after collecting deck URL"""
        view = self.view
        original_interaction = self.original_interaction

        # Disable buttons immediately to prevent double-clicks
        for item in view.children:
            item.disabled = True
        try:
            await original_interaction.message.edit(view=view)
        except Exception:
            pass

        opponent_id = (
            view.player2_id
            if original_interaction.user.id == view.player1_id
            else view.player1_id
        )
        opponent_global = (
            view.player2_global
            if original_interaction.user.id == view.player1_id
            else view.player1_global
        )

        # Check if a report is already pending for this match
        if (original_interaction.user.id, opponent_id) in pending_match_reports or (
            opponent_id,
            original_interaction.user.id,
        ) in pending_match_reports:
            await interaction.response.send_message(
                "A report for this match is already pending confirmation.",
                ephemeral=True,
            )
            return

        # Store pending report with deck URLs
        pending_match_reports[(original_interaction.user.id, opponent_id)] = {
            "winner_id": opponent_id,
            "winner_global": opponent_global,
            "loser_id": original_interaction.user.id,
            "loser_global": original_interaction.user.global_name
            or original_interaction.user.display_name,
            "reporter_id": original_interaction.user.id,
            "reporter_global": original_interaction.user.global_name
            or original_interaction.user.display_name,
            "is_winner": False,
            "opponent_message": None,
            "match_start_time": view.match_start_time,
            "reporter_deck_url": view.reporter_deck_url,
            "opponent_deck_url": view.opponent_deck_url,
            "first_player": view.first_player,
        }

        # Send confirmation to opponent
        try:
            opponent = await view.bot.fetch_user(opponent_id)

            confirmation_view = MatchConfirmationButtons(
                reporter_id=original_interaction.user.id,
                reporter_global=original_interaction.user.global_name
                or original_interaction.user.display_name,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=opponent_id,
                winner_global=opponent_global,
                loser_id=original_interaction.user.id,
                loser_global=original_interaction.user.global_name
                or original_interaction.user.display_name,
                is_winner=True,
                bot=view.bot,
                channel=view.channel,
                match_start_time=view.match_start_time,
                first_player=view.first_player,
                winner_deck_url=view.opponent_deck_url,
                loser_deck_url=view.reporter_deck_url,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = original_interaction.guild
            if guild:
                role = guild.get_role(DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            if opponent_has_dm_issue:
                dm_channel = view.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    try:
                        if guild:
                            role = guild.get_role(DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)

                        dm_channel = view.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                        if dm_channel:
                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                        else:
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )

            # Remove buttons from original message
            if original_interaction.message:
                try:
                    await original_interaction.message.edit(view=None)
                except Exception:
                    pass

        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error in ReporterDeckURLModal loss report: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )


class ConfirmerDeckURLModal(discord.ui.Modal, title="Enter Your Deck"):
    """Modal for capturing deck URL when confirmer didn't provide one at queue join"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL (Optional)",
        placeholder="Enter your deck URL or leave blank",
        required=False,
    )

    def __init__(
        self, view: "MatchConfirmationButtons", interaction: discord.Interaction
    ):
        super().__init__()
        self.view = view
        self.original_interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        deck_url = self.deck_url.value.strip() if self.deck_url.value else None

        # Update the confirmer's deck URL based on whether they won or lost
        if self.view.is_winner:
            # Confirmer won, so their deck is winner_deck_url
            self.view.winner_deck_url = deck_url
        else:
            # Confirmer lost, so their deck is loser_deck_url
            self.view.loser_deck_url = deck_url

        # Continue with the confirmation process
        await self._process_confirmation(interaction)

    async def _process_confirmation(self, interaction: discord.Interaction):
        """Process confirmation after collecting deck URL"""
        view = self.view
        original_interaction = self.original_interaction

        # Disable buttons immediately to prevent double-clicks
        for item in view.children:
            item.disabled = True
        try:
            await original_interaction.message.edit(view=view)
        except Exception:
            pass

        # Check for duplicate match
        match_key = frozenset({view.winner_id, view.loser_id})
        now = datetime.datetime.now()
        if match_key in processed_matches:
            last_report_time = processed_matches[match_key]
            if (now - last_report_time).total_seconds() < 300:
                await interaction.response.send_message(
                    "This match has already been recorded. Duplicate report prevented.",
                    ephemeral=True,
                )
                await original_interaction.message.edit(
                    content="Match already recorded (duplicate prevented).",
                    view=None,
                )
                return

        # Mark this match as processed
        processed_matches[match_key] = now

        await interaction.response.defer()

        # Calculate match time
        match_time = view.match_time
        if match_time == 0 and view.match_start_time:
            time_diff = datetime.datetime.now() - view.match_start_time
            match_time = int(time_diff.total_seconds() / 60)

        # Use winner and loser deck URLs properly
        winner_deck = view.winner_deck_url or "No URL provided"
        loser_deck = view.loser_deck_url or "No URL provided"
        combined_comment = f"Winner deck: {winner_deck} | Loser deck: {loser_deck}"
        if view.match_comment:
            combined_comment = f"{view.match_comment} | {combined_comment}"

        # Determine winner_went_first and loser_went_first based on reporter
        reporter_went_first = (
            view.first_player and "y" in str(view.first_player).lower()
        )
        reporter_is_winner = view.reporter_id == view.winner_id

        if reporter_is_winner:
            winner_went_first = "y" if reporter_went_first else "n"
            loser_went_first = "n" if reporter_went_first else "y"
        else:
            winner_went_first = "n" if reporter_went_first else "y"
            loser_went_first = "y" if reporter_went_first else "n"

        # Submit match report
        match_id, _, _, event_active = await winner_report(
            view.reporter_id,
            view.winner_id,
            view.winner_global,
            True,
            view.loser_id,
            view.loser_global,
            view.first_player,
            match_time,
            winner_deck,
            combined_comment,
            view.winner_id,
            view.winner_global,
            winner_deck_url=view.winner_deck_url,
            loser_deck_url=view.loser_deck_url,
            winner_went_first=winner_went_first,
            loser_went_first=loser_went_first,
        )

        # Update ELO for the loser
        from utils.database import update_elo_db

        update_elo_db(view.loser_id, view.loser_global, False, view.winner_id)

        elo_msg = "" if event_active else " *(No active event - ELO not affected)*"
        # Update the confirmation message
        await original_interaction.message.edit(
            content=f"Match confirmed! **Match ID: #{match_id}** - {view.winner_global} won against {view.loser_global}.{elo_msg}",
            view=None,
        )

        # Send confirmation to confirming user
        await interaction.followup.send(
            f"Match report confirmed and submitted! **Match ID: #{match_id}**\n**Winner:** {view.winner_global}\n**Loser:** {view.loser_global}{elo_msg}",
            ephemeral=True,
        )

        # Notify the reporter
        try:
            reporter = await view.bot.fetch_user(view.reporter_id)
            await reporter.send(
                f"{view.opponent_global} has confirmed your match report! Match has been recorded."
            )
        except discord.Forbidden:
            match_report_channel = view.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    scrub_urls(
                        f"<@{view.reporter_id}> {view.opponent_global} has confirmed your match report! Match has been recorded."
                    )
                )
        except Exception:
            pass

        # Remove from pending
        pending_match_reports.pop((view.reporter_id, view.opponent_id), None)

        # Update leaderboard
        lfg_cog = view.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

        # Check for milestone
        await send_milestone_announcement(
            view.bot, view.winner_id, view.loser_id, match_id
        )


class DeckURLModal(discord.ui.Modal, title="Join LFG Queue"):
    """Modal for entering a deck URL when joining the LFG queue"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/... (optional)",
        required=False,
        max_length=200,
    )

    timeframe = discord.ui.TextInput(
        label="Queue Duration (minutes)",
        placeholder="30",
        required=False,
        default="30",
        max_length=3,
    )

    def __init__(self, bot, is_button_join=True):
        super().__init__()
        self.bot = bot
        self.is_button_join = (
            is_button_join  # True if from button, False if from !lfg command
        )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Parse timeframe
        try:
            timeframe_value = int(self.timeframe.value) if self.timeframe.value else 30
            if timeframe_value < 5:
                timeframe_value = 5
            elif timeframe_value > 120:
                timeframe_value = 120
        except ValueError:
            timeframe_value = 30

        deck_url = self.deck_url.value.strip() if self.deck_url.value else None

        # Create a fake context for compatibility
        class FakeContext:
            def __init__(self, bot, interaction):
                self.bot = bot
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
                self.message = None

            async def send(self, *args, **kwargs):
                pass

        ctx = FakeContext(self.bot, interaction)
        lfg_cog = self.bot.get_cog("LFGCog")

        if not lfg_cog:
            await interaction.followup.send(
                "LFG system is not available.", ephemeral=True
            )
            return

        # Use lock to prevent race conditions
        async with lfg_queue_lock:
            # Check if user is already in queue
            if interaction.user.id in lfg_queue:
                await interaction.followup.send(
                    "You're already in the queue!", ephemeral=True
                )
                return

            # Check for a match
            lfg_cog.clean_expired_lfg()
            matched_user_id = lfg_cog.check_if_someone_is_lfg(ctx)

            if matched_user_id and matched_user_id != interaction.user.id:
                # Get matched user's deck URL before removing from queue
                matched_user_deck_url = lfg_queue.get(matched_user_id, {}).get(
                    "deck_url"
                )
                # Remove matched user from queue
                lfg_queue.pop(matched_user_id, None)
                logger.info(
                    f"Lock acquired: Matching {interaction.user.id} with {matched_user_id}"
                )
            else:
                matched_user_id = None
                matched_user_deck_url = None

        # Handle the result outside the lock
        if matched_user_id:
            # Match found!
            matched_user = await self.bot.fetch_user(matched_user_id)
            lfg_channel = self.bot.get_channel(lfg_cog.lfg_channel_id)
            joiner_global = (
                interaction.user.global_name or interaction.user.display_name
            )
            matched_global = matched_user.global_name or matched_user.display_name

            # Record match start time
            match_start_time = datetime.datetime.now()

            # Randomly select which player gets the report buttons
            players = [
                (interaction.user.id, joiner_global, interaction.user, deck_url, True),
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

            # Build match message with deck info
            reporter_deck_text = (
                f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""
            )

            # Create "Did you go first?" view (step before win/lose buttons)
            went_first_view = WentFirstView(
                reporter_id,
                reporter_id,
                reporter_global,
                other_id,
                other_global,
                self.bot,
                lfg_channel,
                match_start_time=match_start_time,
                reporter_deck_url=reporter_deck_url,
                opponent_deck_url=other_deck_url,
                opponent_user=other_user,
                reporter_deck_text=reporter_deck_text,
            )

            # Send "Did you go first?" question to the selected reporter
            try:
                await reporter_user.send(
                    f"**Match Found!** You've been matched with {other_user.mention} (**{other_global}**)!{reporter_deck_text}\n\n**Did you go first?**",
                    view=went_first_view,
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        # Grant channel access to user who can't receive DMs
                        guild = self.bot.get_guild(config.GUILD_ID)
                        if guild:
                            member = guild.get_member(reporter_user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )
                                logger.info(
                                    f"Granted channel access to {reporter_user.global_name} (can't receive DMs)"
                                )

                        # Post without deck URL in public channel
                        await dm_channel.send(
                            scrub_urls(
                                f"{reporter_user.mention} **Match Found!**\n\nYou've been matched with {other_user.mention} (**{other_global}**)!\n\n**Did you go first?**"
                            ),
                            view=went_first_view,
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for reporter: {e}")

            # Build match info message for the other player
            other_own_deck_text = (
                f"\n**Your Deck:** {other_deck_url}" if other_deck_url else ""
            )

            # Send informational message to the other player (no buttons)
            try:
                await other_user.send(
                    f"**Match Found!** You've been matched with {reporter_user.mention} (**{reporter_global}**)!{other_own_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        # Grant channel access to user who can't receive DMs
                        guild = self.bot.get_guild(config.GUILD_ID)
                        if guild:
                            member = guild.get_member(other_user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )
                                logger.info(
                                    f"Granted channel access to {other_user.global_name} (can't receive DMs)"
                                )

                        # Post without deck URL in public channel
                        await dm_channel.send(
                            scrub_urls(
                                f"{other_user.mention} **Match Found!**\n\nYou've been matched with {reporter_user.mention} (**{reporter_global}**)!\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                            )
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for other player: {e}")

            # Announce match in LFG channel
            if lfg_channel:
                await lfg_channel.send(
                    f"**Match Found!** {interaction.user.mention} matched with {matched_user.mention}!"
                )

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"Match found! You've been paired with {matched_global}. Check your DMs!",
                ephemeral=True,
            )
        else:
            # Add to queue with deck URL
            async with lfg_queue_lock:
                if interaction.user.id in lfg_queue:
                    await interaction.followup.send(
                        "You're already in the queue!", ephemeral=True
                    )
                    return

                lfg_cog.add_to_lfg_queue(ctx, timeframe_value, deck_url)

            deck_msg = f"\n**Deck:** {deck_url}" if deck_url else ""
            try:
                await interaction.user.send(
                    f"You have been added to the queue for {timeframe_value} minutes.{deck_msg}"
                )
            except discord.Forbidden:
                pass

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"You've joined the queue for {timeframe_value} minutes!{deck_msg}",
                ephemeral=True,
            )


class WentFirstView(discord.ui.View):
    """View that asks the reporter if they went first before showing win/lose buttons."""

    def __init__(
        self,
        match_id: int,
        player1_id: int,
        player1_global: str,
        player2_id: int,
        player2_global: str,
        bot=None,
        channel=None,
        match_start_time=None,
        reporter_deck_url=None,
        opponent_deck_url=None,
        opponent_user=None,
        reporter_deck_text: str = "",
    ):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.player1_id = player1_id
        self.player1_global = player1_global
        self.player2_id = player2_id
        self.player2_global = player2_global
        self.bot = bot
        self.channel = channel
        self.match_start_time = match_start_time or datetime.datetime.now()
        self.reporter_deck_url = reporter_deck_url
        self.opponent_deck_url = opponent_deck_url
        self.opponent_user = opponent_user
        self.reporter_deck_text = reporter_deck_text

    @discord.ui.button(
        label="Yes, I went first",
        style=discord.ButtonStyle.primary,
        custom_id="went_first_yes",
    )
    async def yes_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._send_report_buttons(interaction, first_player="y")

    @discord.ui.button(
        label="No, opponent went first",
        style=discord.ButtonStyle.secondary,
        custom_id="went_first_no",
    )
    async def no_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._send_report_buttons(interaction, first_player="n")

    async def _send_report_buttons(
        self, interaction: discord.Interaction, first_player: str
    ):
        """Delete this message and send the actual report buttons."""
        # Delete the "Did you go first?" message
        try:
            await interaction.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete went first message: {e}")

        # Create report buttons with the first_player info
        view_reporter = LFGReportButtons(
            self.match_id,
            self.player1_id,
            self.player1_global,
            self.player2_id,
            self.player2_global,
            self.bot,
            self.channel,
            match_start_time=self.match_start_time,
            reporter_deck_url=self.reporter_deck_url,
            opponent_deck_url=self.opponent_deck_url,
            first_player=first_player,
        )

        # Send the report buttons
        try:
            await interaction.response.send_message(
                f"**Match Found!** You've been matched with {self.opponent_user.mention} (**{self.player2_global}**)!{self.reporter_deck_text}\n\nReport the match result below:",
                view=view_reporter,
            )
        except Exception as e:
            logger.error(f"Error sending report buttons after went first: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True,
                )


class LFGReportButtons(discord.ui.View):
    def __init__(
        self,
        match_id: int,
        player1_id: int,
        player1_global: str,
        player2_id: int,
        player2_global: str,
        bot=None,
        channel=None,
        match_start_time=None,
        reporter_deck_url=None,
        opponent_deck_url=None,
        first_player: str = "n",
    ):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_global = player1_global
        self.reporter_deck_url = reporter_deck_url
        self.opponent_deck_url = opponent_deck_url
        self.player2_global = player2_global
        self.bot = bot
        self.channel = channel
        self.first_player = first_player
        # Track when the match started for automatic match time calculation
        self.match_start_time = match_start_time or datetime.datetime.now()

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if reporter needs to provide a deck URL
        if not self.reporter_deck_url:
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=True)
            await interaction.response.send_modal(modal)
            return

        # Disable buttons immediately to prevent double-clicks
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        opponent_id = (
            self.player2_id
            if interaction.user.id == self.player1_id
            else self.player1_id
        )
        opponent_global = (
            self.player2_global
            if interaction.user.id == self.player1_id
            else self.player1_global
        )

        # Check if a report is already pending for this match
        if (interaction.user.id, opponent_id) in pending_match_reports or (
            opponent_id,
            interaction.user.id,
        ) in pending_match_reports:
            await interaction.response.send_message(
                "A report for this match is already pending confirmation.",
                ephemeral=True,
            )
            return

        # Store pending report with deck URLs
        pending_match_reports[(interaction.user.id, opponent_id)] = {
            "winner_id": interaction.user.id,
            "winner_global": interaction.user.global_name
            or interaction.user.display_name,
            "loser_id": opponent_id,
            "loser_global": opponent_global,
            "reporter_id": interaction.user.id,
            "reporter_global": interaction.user.global_name
            or interaction.user.display_name,
            "is_winner": True,
            "opponent_message": None,  # Will be set after fetching opponent's DM
            "match_start_time": self.match_start_time,  # Track when match started
            "reporter_deck_url": self.reporter_deck_url,  # Reporter's deck URL
            "opponent_deck_url": self.opponent_deck_url,  # Opponent's deck URL
            "first_player": self.first_player,  # Did reporter go first
        }

        # Send confirmation to opponent
        try:
            opponent = await self.bot.fetch_user(opponent_id)

            # Reporter won, so reporter's deck is winner's deck, opponent's deck is loser's deck
            confirmation_view = MatchConfirmationButtons(
                reporter_id=interaction.user.id,
                reporter_global=interaction.user.global_name
                or interaction.user.display_name,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=interaction.user.id,
                winner_global=interaction.user.global_name
                or interaction.user.display_name,
                loser_id=opponent_id,
                loser_global=opponent_global,
                is_winner=False,  # For opponent, they lost
                bot=self.bot,
                channel=self.channel,
                match_start_time=self.match_start_time,
                first_player=self.first_player,
                winner_deck_url=self.reporter_deck_url,  # Reporter won, so their deck is winner's
                loser_deck_url=self.opponent_deck_url,  # Opponent lost, so their deck is loser's
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = interaction.guild
            if guild:
                role = guild.get_role(DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            # Try to send via DM first (unless they have the DM-disabled role)
            if opponent_has_dm_issue:
                # Send to designated channel instead
                dm_channel = interaction.client.get_channel(DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                    logger.info(
                        f"Posted confirmation in DM-disabled channel for {opponent_global}"
                    )
                else:
                    await interaction.response.send_message(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **LOST** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )

                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    # DM failed - add role, grant channel access, and post in designated channel
                    try:
                        if guild:
                            role = guild.get_role(DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)
                                logger.info(
                                    f"Added DM-disabled role to {opponent_global}"
                                )

                        dm_channel = interaction.client.get_channel(
                            DM_DISABLED_CHANNEL_ID
                        )
                        if dm_channel:
                            # Grant channel access
                            if guild:
                                member = guild.get_member(opponent_id)
                                if member:
                                    await dm_channel.set_permissions(
                                        member, read_messages=True, send_messages=True
                                    )
                                    logger.info(
                                        f"Granted channel access to {opponent_global}"
                                    )

                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )

            # Remove buttons from this user's message
            if interaction.message:
                try:
                    await interaction.message.edit(view=None)
                except Exception:
                    pass

        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error in won_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )

    @discord.ui.button(
        label="I Lost", style=discord.ButtonStyle.danger, custom_id="lose_button"
    )
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if reporter needs to provide a deck URL
        if not self.reporter_deck_url:
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=False)
            await interaction.response.send_modal(modal)
            return

        # Disable buttons immediately to prevent double-clicks
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        opponent_id = (
            self.player2_id
            if interaction.user.id == self.player1_id
            else self.player1_id
        )
        opponent_global = (
            self.player2_global
            if interaction.user.id == self.player1_id
            else self.player1_global
        )

        # Check if a report is already pending for this match
        if (interaction.user.id, opponent_id) in pending_match_reports or (
            opponent_id,
            interaction.user.id,
        ) in pending_match_reports:
            await interaction.response.send_message(
                "A report for this match is already pending confirmation.",
                ephemeral=True,
            )
            return

        # Store pending report with deck URLs
        pending_match_reports[(interaction.user.id, opponent_id)] = {
            "winner_id": opponent_id,
            "winner_global": opponent_global,
            "loser_id": interaction.user.id,
            "loser_global": interaction.user.global_name
            or interaction.user.display_name,
            "reporter_id": interaction.user.id,
            "reporter_global": interaction.user.global_name
            or interaction.user.display_name,
            "is_winner": False,
            "opponent_message": None,  # Will be set after fetching opponent's DM
            "match_start_time": self.match_start_time,  # Track when match started
            "reporter_deck_url": self.reporter_deck_url,  # Reporter's deck URL
            "opponent_deck_url": self.opponent_deck_url,  # Opponent's deck URL
            "first_player": self.first_player,  # Did reporter go first
        }

        # Send confirmation to opponent
        try:
            opponent = await self.bot.fetch_user(opponent_id)

            # Reporter lost, so opponent's deck is winner's deck, reporter's deck is loser's deck
            confirmation_view = MatchConfirmationButtons(
                reporter_id=interaction.user.id,
                reporter_global=interaction.user.global_name
                or interaction.user.display_name,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=opponent_id,
                winner_global=opponent_global,
                loser_id=interaction.user.id,
                loser_global=interaction.user.global_name
                or interaction.user.display_name,
                is_winner=True,  # For opponent, they won
                bot=self.bot,
                channel=self.channel,
                match_start_time=self.match_start_time,
                first_player=self.first_player,
                winner_deck_url=self.opponent_deck_url,  # Opponent won, so their deck is winner's
                loser_deck_url=self.reporter_deck_url,  # Reporter lost, so their deck is loser's
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = interaction.guild
            if guild:
                role = guild.get_role(DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            # Try to send via DM first (unless they have the DM-disabled role)
            if opponent_has_dm_issue:
                # Send to designated channel instead
                dm_channel = interaction.client.get_channel(DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                    logger.info(
                        f"Posted confirmation in DM-disabled channel for {opponent_global}"
                    )
                else:
                    await interaction.response.send_message(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )

                    await interaction.response.send_message(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    # DM failed - add role and post in designated channel
                    try:
                        if guild:
                            role = guild.get_role(DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)
                                logger.info(
                                    f"Added DM-disabled role to {opponent_global}"
                                )

                        dm_channel = interaction.client.get_channel(
                            DM_DISABLED_CHANNEL_ID
                        )
                        if dm_channel:
                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )

            # Remove buttons from this user's message
            if interaction.message:
                try:
                    await interaction.message.edit(view=None)
                except Exception:
                    pass

        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error in lost_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "An error occurred while processing your match report.",
                    ephemeral=True,
                )

    @discord.ui.button(
        label="Cancel match",
        style=discord.ButtonStyle.secondary,
        custom_id="cancel_match",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Only the matched players can cancel
        if interaction.user.id not in (self.player1_id, self.player2_id):
            await interaction.response.send_message(
                "Only the matched players can cancel this match.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.mention} clicked **cancel match**", ephemeral=True
        )
        await interaction.message.edit(view=None)


class ChallengeInitView(discord.ui.View):
    """View with a button to open the challenge modal"""

    def __init__(self, modal, challenger_id: int = None):
        super().__init__(timeout=60)
        self.modal = modal
        self.challenger_id = challenger_id or modal.challenger.id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="⚔️ Send Challenge", style=discord.ButtonStyle.primary)
    async def send_challenge_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(self.modal)
        await interaction.message.delete()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message("Challenge cancelled.", ephemeral=True)
        await interaction.message.delete()


class ChallengerDeckModal(discord.ui.Modal, title="Challenge Player"):
    """Modal for entering deck URL when sending a challenge"""

    deck_url = discord.ui.TextInput(
        label="Your Curiosa Deck URL (optional)",
        placeholder="https://curiosa.io/decks/...",
        required=False,
        max_length=200,
    )

    def __init__(self, challenger, opponent, lfg_channel, bot):
        super().__init__()
        self.challenger = challenger
        self.opponent = opponent
        self.lfg_channel = lfg_channel
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        url = self.deck_url.value if self.deck_url.value else None
        challenger_global = self.challenger.global_name or self.challenger.display_name
        opponent_global = self.opponent.global_name or self.opponent.display_name

        view = ChallengeButtons(
            self.challenger.id,
            challenger_global,
            self.lfg_channel,
            challenger_deck_url=url,
        )

        try:
            # Send challenge to opponent (don't show challenger's deck)
            await self.opponent.send(
                f"{challenger_global} has challenged you to a match!",
                view=view,
            )
            # Notify challenger
            deck_confirm = f" Your deck: {url}" if url else ""
            await interaction.followup.send(
                f"Challenge sent to {opponent_global}! They have 5 minutes to accept.{deck_confirm}",
                ephemeral=True,
            )

            # Confirm in channel (find original context channel)
            if self.lfg_channel:
                await self.lfg_channel.send(
                    f"{self.challenger.mention} has challenged {self.opponent.mention} to a match!"
                )

        except discord.Forbidden:
            # If DM fails, create a public thread
            if self.lfg_channel:
                try:
                    temp_msg = await self.lfg_channel.send(
                        f"{self.opponent.mention} You have been challenged!"
                    )
                    thread = await temp_msg.create_thread(
                        name=f"Challenge from {self.challenger.display_name}",
                        auto_archive_duration=60,
                    )
                    await thread.send(
                        f"{self.opponent.mention} {challenger_global} has challenged you to a match!",
                        view=view,
                    )
                    await interaction.followup.send(
                        f"Challenge sent to {self.opponent.mention} in a thread (they have DMs disabled).",
                        ephemeral=True,
                    )
                except Exception as thread_error:
                    logger.error(f"Failed to create challenge thread: {thread_error}")
                    await interaction.followup.send(
                        f"I couldn't send a DM or create a thread for {opponent_global}. They might have DMs disabled.",
                        ephemeral=True,
                    )
            else:
                await interaction.followup.send(
                    f"I couldn't send a DM to {opponent_global}. They might have DMs disabled.",
                    ephemeral=True,
                )
        except Exception as e:
            await interaction.followup.send(
                f"An error occurred: {str(e)}", ephemeral=True
            )
            logger.error(f"Challenge modal error: {e}")


class ChallengeAcceptModal(discord.ui.Modal, title="Accept Challenge"):
    """Modal for entering deck URL when accepting a challenge"""

    deck_url = discord.ui.TextInput(
        label="Your Curiosa Deck URL (optional)",
        placeholder="https://curiosa.io/decks/...",
        required=False,
        max_length=200,
    )

    def __init__(
        self,
        challenger_id: int,
        challenger_global: str,
        channel=None,
        challenger_deck_url: str = None,
    ):
        super().__init__()
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        challenger = await interaction.client.fetch_user(self.challenger_id)
        accepter_global = interaction.user.global_name or interaction.user.display_name
        accepter_deck_url = self.deck_url.value if self.deck_url.value else None

        # Remove both players from the LFG queue if they're in it
        if self.challenger_id in lfg_queue:
            lfg_queue.pop(self.challenger_id, None)
            logger.info(
                f"Removed challenger {self.challenger_id} from LFG queue (accepted challenge)"
            )
        if interaction.user.id in lfg_queue:
            lfg_queue.pop(interaction.user.id, None)
            logger.info(
                f"Removed accepter {interaction.user.id} from LFG queue (accepted challenge)"
            )

        # Record match start time when challenge is accepted
        match_start_time = datetime.datetime.now()

        # Randomly select which player gets the report buttons
        # Both challenger and accepter can have deck URLs
        players = [
            (
                self.challenger_id,
                self.challenger_global,
                challenger,
                self.challenger_deck_url,  # Challenger's deck URL (if provided)
                False,
            ),
            (
                interaction.user.id,
                accepter_global,
                interaction.user,
                accepter_deck_url,  # Accepter's deck URL
                True,
            ),
        ]
        reporter_player, other_player = random.sample(players, 2)
        (
            reporter_id,
            reporter_global,
            reporter_user,
            reporter_deck_url,
            reporter_is_accepter,
        ) = reporter_player
        other_id, other_global, other_user, other_deck_url, other_is_accepter = (
            other_player
        )

        # Build deck message
        reporter_deck_text = (
            f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""
        )
        other_deck_text = f"\n**Your Deck:** {other_deck_url}" if other_deck_url else ""

        # Create "Did you go first?" view for the reporter
        went_first_view = WentFirstView(
            0,  # match_id not needed for direct challenges
            reporter_id,
            reporter_global,
            other_id,
            other_global,
            interaction.client,
            self.channel,
            match_start_time=match_start_time,
            reporter_deck_url=reporter_deck_url,
            opponent_deck_url=other_deck_url,
            opponent_user=other_user,
            reporter_deck_text=reporter_deck_text,
        )

        # Send "Did you go first?" question to the selected reporter
        if reporter_is_accepter:
            # Reporter is the one who accepted - use followup since we deferred
            try:
                await interaction.followup.send(
                    f"**Challenge Accepted!** You're playing against {other_user.mention} (**{other_global}**)!{reporter_deck_text}\n\n**Did you go first?**",
                    view=went_first_view,
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to send went first question to accepter: {e}")
        else:
            # Reporter is the challenger - send via DM
            try:
                await challenger.send(
                    f"**Challenge Accepted!** **{accepter_global}** accepted your challenge!{reporter_deck_text}\n\n**Did you go first?**",
                    view=went_first_view,
                )
            except discord.Forbidden:
                try:
                    dm_channel = interaction.client.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            scrub_urls(
                                f"{challenger.mention} **Challenge Accepted!** **{accepter_global}** accepted your challenge!{reporter_deck_text}\n\n**Did you go first?**"
                            ),
                            view=went_first_view,
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for challenger: {e}")

        # Send info to the other player (no buttons)
        if other_is_accepter:
            # Other is the accepter - send followup
            try:
                await interaction.followup.send(
                    f"**Challenge Accepted!** You're playing against {reporter_user.mention} (**{reporter_global}**)!{other_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to send info to accepter: {e}")
        else:
            # Other is the challenger - send via DM
            try:
                await challenger.send(
                    f"**Challenge Accepted!** **{accepter_global}** accepted your challenge!{other_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button."
                )
            except discord.Forbidden:
                try:
                    dm_channel = interaction.client.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            scrub_urls(
                                f"{challenger.mention} **Challenge Accepted!** **{accepter_global}** accepted your challenge!{other_deck_text}\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button."
                            )
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to handle DM failure for challenger info: {e}"
                    )

        # Announce in LFG channel
        if self.channel:
            await self.channel.send(
                f"**Challenge Accepted!** {challenger.mention} vs {interaction.user.mention}!"
            )


class ChallengeButtons(discord.ui.View):
    def __init__(
        self,
        challenger_id: int,
        challenger_global: str,
        channel=None,
        challenger_deck_url: str = None,
    ):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url

    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.success)
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Open modal for deck URL entry
        modal = ChallengeAcceptModal(
            challenger_id=self.challenger_id,
            challenger_global=self.challenger_global,
            channel=self.channel,
            challenger_deck_url=self.challenger_deck_url,
        )
        await interaction.response.send_modal(modal)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Decline Challenge", style=discord.ButtonStyle.danger)
    async def decline_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        challenger = await interaction.client.fetch_user(self.challenger_id)
        await challenger.send(
            f"{interaction.user.global_name} has declined your challenge."
        )
        await interaction.response.send_message(
            "You have declined the challenge.", ephemeral=True
        )
        await interaction.message.edit(view=None)


# ==================== LADDER CHALLENGE SYSTEM ====================

# In-memory ladder challenge queues
# Key: challenger_id, Value: {challenger_global, joiners: [{user_id, global_name}], message, channel, challenge_id, task}
active_ladder_challenges = {}

# Lock for ladder challenge operations
ladder_challenge_lock = asyncio.Lock()

LADDER_CHALLENGE_MAX_JOINERS = 3
LADDER_CHALLENGE_TIMEOUT_SECONDS = 300  # 5 minutes


class LadderChallengeJoinButton(discord.ui.View):
    """Button for joining a ladder challenge queue"""

    def __init__(self, bot, challenger_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.challenger_id = challenger_id

    @discord.ui.button(
        label="Accept Challenge!",
        style=discord.ButtonStyle.green,
        custom_id="join_ladder_challenge",
    )
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle a player joining the ladder challenge queue"""
        user_id = interaction.user.id
        user_global = interaction.user.global_name or interaction.user.display_name

        # Can't join your own challenge
        if user_id == self.challenger_id:
            await interaction.response.send_message(
                "You can't join your own challenge!", ephemeral=True
            )
            return

        async with ladder_challenge_lock:
            challenge_data = active_ladder_challenges.get(self.challenger_id)
            if not challenge_data:
                await interaction.response.send_message(
                    "This ladder challenge is no longer active.", ephemeral=True
                )
                return

            # Check if already joined
            if any(j["user_id"] == user_id for j in challenge_data["joiners"]):
                await interaction.response.send_message(
                    "You've already joined this challenge!", ephemeral=True
                )
                return

            # Add joiner
            challenge_data["joiners"].append(
                {
                    "user_id": user_id,
                    "global_name": user_global,
                }
            )
            joiner_count = len(challenge_data["joiners"])

            # Update the embed
            challenger_global = challenge_data["challenger_global"]
            embed = _build_ladder_challenge_embed(
                challenger_global, challenge_data["joiners"], self.challenger_id
            )

            try:
                msg = challenge_data.get("message")
                if msg:
                    if joiner_count >= LADDER_CHALLENGE_MAX_JOINERS:
                        # Queue full - disable button
                        for item in self.children:
                            item.disabled = True
                        await msg.edit(embed=embed, view=self)
                    else:
                        await msg.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"Error updating ladder challenge message: {e}")

        await interaction.response.send_message(
            f"You've entered the ladder challenge queue! ({joiner_count}/{LADDER_CHALLENGE_MAX_JOINERS})",
            ephemeral=True,
        )

        # If queue is full, immediately select opponent
        if joiner_count >= LADDER_CHALLENGE_MAX_JOINERS:
            # Cancel the timeout task
            task = challenge_data.get("task")
            if task and not task.done():
                task.cancel()
            await _resolve_ladder_challenge(self.bot, self.challenger_id)


class LadderChallengeReportButtons(discord.ui.View):
    """Win/Lose buttons for reporting a ladder challenge match"""

    def __init__(
        self,
        bot,
        challenger_id: int,
        challenger_global: str,
        opponent_id: int,
        opponent_global: str,
        challenge_id: int,
        is_ladder_match: bool = True,
        elo_multiplier_winner: float = 1.0,
        elo_multiplier_loser: float = 1.0,
        channel=None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.opponent_id = opponent_id
        self.opponent_global = opponent_global
        self.challenge_id = challenge_id
        self.is_ladder_match = is_ladder_match
        self.elo_multiplier_winner = elo_multiplier_winner
        self.elo_multiplier_loser = elo_multiplier_loser
        self.channel = channel
        self.match_start_time = datetime.datetime.now()

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="ladder_win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if (
            interaction.user.id != self.challenger_id
            and interaction.user.id != self.opponent_id
        ):
            await interaction.response.send_message(
                "You are not part of this match!", ephemeral=True
            )
            return

        # Disable buttons
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        reporter_id = interaction.user.id
        reporter_global = interaction.user.global_name or interaction.user.display_name

        if reporter_id == self.challenger_id:
            winner_id, winner_global = self.challenger_id, self.challenger_global
            loser_id, loser_global = self.opponent_id, self.opponent_global
        else:
            winner_id, winner_global = self.opponent_id, self.opponent_global
            loser_id, loser_global = self.challenger_id, self.challenger_global

        opponent_id = (
            self.opponent_id
            if reporter_id == self.challenger_id
            else self.challenger_id
        )
        opponent_global = (
            self.opponent_global
            if reporter_id == self.challenger_id
            else self.challenger_global
        )

        # Store pending report - send confirmation to opponent
        pending_match_reports[(reporter_id, opponent_id)] = {
            "winner_id": winner_id,
            "winner_global": winner_global,
            "loser_id": loser_id,
            "loser_global": loser_global,
            "reporter_id": reporter_id,
            "reporter_global": reporter_global,
            "is_winner": True,
            "is_ladder_match": True,
            "challenge_id": self.challenge_id,
            "elo_multiplier_winner": self.elo_multiplier_winner,
            "elo_multiplier_loser": self.elo_multiplier_loser,
            "challenger_id": self.challenger_id,
        }

        try:
            opponent_user = await self.bot.fetch_user(opponent_id)
            confirmation_view = LadderMatchConfirmationButtons(
                reporter_id=reporter_id,
                reporter_global=reporter_global,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=winner_id,
                winner_global=winner_global,
                loser_id=loser_id,
                loser_global=loser_global,
                bot=self.bot,
                challenge_id=self.challenge_id,
                elo_multiplier_winner=self.elo_multiplier_winner,
                elo_multiplier_loser=self.elo_multiplier_loser,
                challenger_id=self.challenger_id,
                match_start_time=self.match_start_time,
            )

            result_text = "LOST" if reporter_id == winner_id else "WON"
            await opponent_user.send(
                f"**Ladder Challenge Match Report**\n\n"
                f"{reporter_global} reports that you **{result_text}** the ladder challenge match.\n\n"
                f"Please confirm or dispute this result:",
                view=confirmation_view,
            )
            await interaction.response.send_message(
                f"Match report sent to {opponent_global}. Waiting for confirmation...",
                ephemeral=True,
            )
        except discord.Forbidden:
            dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                opponent_user = await self.bot.fetch_user(opponent_id)
                confirmation_view = LadderMatchConfirmationButtons(
                    reporter_id=reporter_id,
                    reporter_global=reporter_global,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=winner_id,
                    winner_global=winner_global,
                    loser_id=loser_id,
                    loser_global=loser_global,
                    bot=self.bot,
                    challenge_id=self.challenge_id,
                    elo_multiplier_winner=self.elo_multiplier_winner,
                    elo_multiplier_loser=self.elo_multiplier_loser,
                    challenger_id=self.challenger_id,
                    match_start_time=self.match_start_time,
                )
                result_text = "LOST" if reporter_id == winner_id else "WON"
                await dm_channel.send(
                    scrub_urls(
                        f"{opponent_user.mention} **Ladder Challenge Match Report**\n\n"
                        f"{reporter_global} reports that you **{result_text}** the ladder challenge match.\n\n"
                        f"Please confirm or dispute this result:"
                    ),
                    view=confirmation_view,
                )
                await interaction.response.send_message(
                    f"Match report sent to {opponent_global}. Waiting for confirmation...",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error sending ladder match confirmation: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred sending the confirmation.", ephemeral=True
                )

    @discord.ui.button(
        label="I Lost", style=discord.ButtonStyle.danger, custom_id="ladder_lose_button"
    )
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if (
            interaction.user.id != self.challenger_id
            and interaction.user.id != self.opponent_id
        ):
            await interaction.response.send_message(
                "You are not part of this match!", ephemeral=True
            )
            return

        # Disable buttons
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        reporter_id = interaction.user.id
        reporter_global = interaction.user.global_name or interaction.user.display_name

        # Reporter lost
        if reporter_id == self.challenger_id:
            winner_id, winner_global = self.opponent_id, self.opponent_global
            loser_id, loser_global = self.challenger_id, self.challenger_global
        else:
            winner_id, winner_global = self.challenger_id, self.challenger_global
            loser_id, loser_global = self.opponent_id, self.opponent_global

        opponent_id = (
            self.opponent_id
            if reporter_id == self.challenger_id
            else self.challenger_id
        )
        opponent_global = (
            self.opponent_global
            if reporter_id == self.challenger_id
            else self.challenger_global
        )

        pending_match_reports[(reporter_id, opponent_id)] = {
            "winner_id": winner_id,
            "winner_global": winner_global,
            "loser_id": loser_id,
            "loser_global": loser_global,
            "reporter_id": reporter_id,
            "reporter_global": reporter_global,
            "is_winner": False,
            "is_ladder_match": True,
            "challenge_id": self.challenge_id,
            "elo_multiplier_winner": self.elo_multiplier_winner,
            "elo_multiplier_loser": self.elo_multiplier_loser,
            "challenger_id": self.challenger_id,
        }

        try:
            opponent_user = await self.bot.fetch_user(opponent_id)
            confirmation_view = LadderMatchConfirmationButtons(
                reporter_id=reporter_id,
                reporter_global=reporter_global,
                opponent_id=opponent_id,
                opponent_global=opponent_global,
                winner_id=winner_id,
                winner_global=winner_global,
                loser_id=loser_id,
                loser_global=loser_global,
                bot=self.bot,
                challenge_id=self.challenge_id,
                elo_multiplier_winner=self.elo_multiplier_winner,
                elo_multiplier_loser=self.elo_multiplier_loser,
                challenger_id=self.challenger_id,
                match_start_time=self.match_start_time,
            )

            result_text = "WON" if reporter_id != winner_id else "LOST"
            await opponent_user.send(
                f"**Ladder Challenge Match Report**\n\n"
                f"{reporter_global} reports that you **{result_text}** the ladder challenge match.\n\n"
                f"Please confirm or dispute this result:",
                view=confirmation_view,
            )
            await interaction.response.send_message(
                f"Match report sent to {opponent_global}. Waiting for confirmation...",
                ephemeral=True,
            )
        except discord.Forbidden:
            dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                opponent_user = await self.bot.fetch_user(opponent_id)
                confirmation_view = LadderMatchConfirmationButtons(
                    reporter_id=reporter_id,
                    reporter_global=reporter_global,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=winner_id,
                    winner_global=winner_global,
                    loser_id=loser_id,
                    loser_global=loser_global,
                    bot=self.bot,
                    challenge_id=self.challenge_id,
                    elo_multiplier_winner=self.elo_multiplier_winner,
                    elo_multiplier_loser=self.elo_multiplier_loser,
                    challenger_id=self.challenger_id,
                    match_start_time=self.match_start_time,
                )
                result_text = "WON" if reporter_id != winner_id else "LOST"
                await dm_channel.send(
                    scrub_urls(
                        f"{opponent_user.mention} **Ladder Challenge Match Report**\n\n"
                        f"{reporter_global} reports that you **{result_text}** the ladder challenge match.\n\n"
                        f"Please confirm or dispute this result:"
                    ),
                    view=confirmation_view,
                )
                await interaction.response.send_message(
                    f"Match report sent to {opponent_global}. Waiting for confirmation...",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error sending ladder match confirmation: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred sending the confirmation.", ephemeral=True
                )


class LadderMatchConfirmationButtons(discord.ui.View):
    """Buttons for confirming a ladder challenge match report"""

    def __init__(
        self,
        reporter_id: int,
        reporter_global: str,
        opponent_id: int,
        opponent_global: str,
        winner_id: int,
        winner_global: str,
        loser_id: int,
        loser_global: str,
        bot=None,
        challenge_id: int = None,
        elo_multiplier_winner: float = 1.0,
        elo_multiplier_loser: float = 1.0,
        challenger_id: int = None,
        match_start_time=None,
    ):
        super().__init__(timeout=86400)
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.opponent_id = opponent_id
        self.opponent_global = opponent_global
        self.winner_id = winner_id
        self.winner_global = winner_global
        self.loser_id = loser_id
        self.loser_global = loser_global
        self.bot = bot
        self.challenge_id = challenge_id
        self.elo_multiplier_winner = elo_multiplier_winner
        self.elo_multiplier_loser = elo_multiplier_loser
        self.challenger_id = challenger_id
        self.match_start_time = match_start_time or datetime.datetime.now()

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.success,
        custom_id="confirm_ladder_match",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Disable buttons
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # Check for duplicate
        match_key = frozenset({self.winner_id, self.loser_id})
        now = datetime.datetime.now()
        if match_key in processed_matches:
            last_report_time = processed_matches[match_key]
            if (now - last_report_time).total_seconds() < 300:
                await interaction.response.send_message(
                    "This match has already been recorded.", ephemeral=True
                )
                return

        processed_matches[match_key] = now
        await interaction.response.defer()

        # Calculate match time
        match_time = 0
        if self.match_start_time:
            time_diff = datetime.datetime.now() - self.match_start_time
            match_time = int(time_diff.total_seconds() / 60)

        # Record the match using winner_report
        match_id, _, _, event_active = await winner_report(
            self.reporter_id,
            self.winner_id,
            self.winner_global,
            True,
            self.loser_id,
            self.loser_global,
            "n",  # first_player not tracked for ladder challenges
            match_time,
            "No URL provided",
            f"Ladder Challenge Match (Challenge #{self.challenge_id})",
            self.winner_id,
            self.winner_global,
        )

        # Now apply the special ladder ELO (undo the normal ELO update from winner_report and apply multiplied version)
        # winner_report already called update_elo_db for the winner. We need to revert and re-apply with multiplier.
        # Instead, we'll update the loser with multiplier too.
        from utils.database import update_elo_db

        # The winner_report already updated winner's ELO normally.
        # We need to revert that and apply multiplied versions.
        # Simpler approach: just apply the multiplier difference on top.

        # Actually let's just update loser ELO with the appropriate multiplier
        # Winner ELO was already set by winner_report - we need to adjust it

        # Determine multipliers based on who won
        # challenger_id is the Top 16 player
        if self.winner_id == self.challenger_id:
            # Top 16 player won - normal ELO for both
            winner_mult = 1.0
            loser_mult = 1.0
        else:
            # Non-Top16 player won - they get 2x, Top16 loses only 0.5x
            winner_mult = self.elo_multiplier_winner
            loser_mult = self.elo_multiplier_loser

        # Revert the winner's normal ELO update and apply multiplied version
        if winner_mult != 1.0:
            import sqlite3 as _sqlite3

            # The winner_report used update_elo_db which already changed the winner's ELO
            # Read what match_records recorded as the normal elo change and apply extra
            conn_match = _sqlite3.connect("match_records.db")
            cur_match = conn_match.cursor()
            cur_match.execute(
                "SELECT winner_elo_change FROM match_records WHERE match_id=?",
                (match_id,),
            )
            elo_row = cur_match.fetchone()
            conn_match.close()

            if elo_row and elo_row[0]:
                normal_change = elo_row[0]
                extra_change = round(normal_change * (winner_mult - 1.0))
                conn_fix = _sqlite3.connect("elo.db")
                cur_fix = conn_fix.cursor()
                cur_fix.execute(
                    "UPDATE overall_standings SET elo = elo + ?, event_elo = event_elo + ? WHERE user_id = ?",
                    (extra_change, extra_change, self.winner_id),
                )
                conn_fix.commit()
                conn_fix.close()
                logger.info(
                    f"Ladder bonus: Winner {self.winner_id} gets extra {extra_change:+d} ELO (mult={winner_mult})"
                )

        # Update loser ELO with multiplier
        if loser_mult != 1.0:
            # Normal update_elo_db would give full loss. Apply with multiplier.
            update_elo_db_ladder(
                self.loser_id,
                self.loser_global,
                False,
                self.winner_id,
                elo_multiplier=loser_mult,
            )
        else:
            update_elo_db(self.loser_id, self.loser_global, False, self.winner_id)

        # Complete the ladder challenge record
        if self.challenge_id:
            complete_ladder_challenge(self.challenge_id, self.winner_id, match_id)

        # Build ELO info message
        stakes_msg = ""
        if winner_mult != 1.0 or loser_mult != 1.0:
            if self.winner_id != self.challenger_id:
                stakes_msg = "\n**Ladder Bonus:** Winner gained 2x ELO! Top 16 player lost only 0.5x ELO."
            else:
                stakes_msg = "\n*Normal ELO stakes (Top 16 player won)*"

        elo_msg = "" if event_active else " *(No active event - ELO not affected)*"

        await interaction.message.edit(
            content=f"Ladder Challenge Match confirmed! **Match ID: #{match_id}** - {self.winner_global} won against {self.loser_global}.{elo_msg}{stakes_msg}",
            view=None,
        )

        await interaction.followup.send(
            f"Match confirmed! **Match ID: #{match_id}**\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}{elo_msg}{stakes_msg}",
            ephemeral=True,
        )

        # Notify reporter
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"Your ladder challenge match report has been confirmed! Match recorded.{stakes_msg}"
            )
        except Exception:
            pass

        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)

        # Update leaderboard
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

        # Milestone check
        await send_milestone_announcement(
            self.bot, self.winner_id, self.loser_id, match_id
        )

    @discord.ui.button(
        label="Dispute",
        style=discord.ButtonStyle.danger,
        custom_id="dispute_ladder_match",
    )
    async def dispute_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "You have disputed the ladder challenge match report. No entry was logged.",
            ephemeral=True,
        )
        await interaction.message.edit(
            content=f"Ladder challenge match disputed by {self.opponent_global}. No entry logged.",
            view=None,
        )
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"{self.opponent_global} has disputed your ladder challenge match report. No entry was logged."
            )
        except Exception:
            pass
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)


def _build_ladder_challenge_embed(challenger_global, joiners, challenger_id):
    """Build the embed for a ladder challenge queue status."""
    joiner_count = len(joiners)

    if joiner_count >= LADDER_CHALLENGE_MAX_JOINERS:
        color = discord.Color.gold()
        status = "Queue Full - Selecting opponent..."
    elif joiner_count > 0:
        color = discord.Color.green()
        status = f"**{joiner_count}/{LADDER_CHALLENGE_MAX_JOINERS}** challengers joined"
    else:
        color = discord.Color.blue()
        status = "Waiting for challengers..."

    embed = discord.Embed(
        title="Ladder Challenge!",
        description=(
            f"**{challenger_global}** (Top 16) is looking for a challenger!\n\n"
            f"{status}\n\n"
            f"Click **Accept Challenge!** to enter. "
            f"One person will be randomly selected to play.\n"
            f"Queue closes in 5 minutes or when {LADDER_CHALLENGE_MAX_JOINERS} players join."
        ),
        color=color,
    )

    # Show joined players
    if joiners:
        joiner_names = [f"• {j['global_name']}" for j in joiners]
        embed.add_field(
            name=f"Challengers ({joiner_count}/{LADDER_CHALLENGE_MAX_JOINERS}):",
            value="\n".join(joiner_names),
            inline=False,
        )

    # Stakes info
    embed.add_field(
        name="Stakes",
        value=(
            "If the challenger **WINS** against the Top 16 player: **2x ELO gain!**\n"
            "If the Top 16 player **LOSES**: Only **0.5x ELO loss**\n"
            "If ELO difference < 100: Normal ELO stakes"
        ),
        inline=False,
    )

    embed.set_footer(text="Ladder Challenge • Top 16 vs The Field")
    return embed


async def _resolve_ladder_challenge(bot, challenger_id):
    """Resolve a ladder challenge by randomly selecting an opponent from joiners."""
    async with ladder_challenge_lock:
        challenge_data = active_ladder_challenges.pop(challenger_id, None)

    if not challenge_data:
        return

    joiners = challenge_data["joiners"]
    challenger_global = challenge_data["challenger_global"]
    challenge_id = challenge_data["challenge_id"]
    channel = challenge_data["channel"]
    msg = challenge_data.get("message")

    if not joiners:
        # No one joined
        try:
            if msg:
                embed = discord.Embed(
                    title="Ladder Challenge Expired",
                    description=f"**{challenger_global}**'s ladder challenge expired with no challengers.",
                    color=discord.Color.red(),
                )
                embed.set_footer(text="Better luck next time!")
                await msg.edit(embed=embed, view=None)
        except Exception as e:
            logger.error(f"Error updating expired ladder challenge message: {e}")

        # Notify challenger
        try:
            challenger = await bot.fetch_user(challenger_id)
            await challenger.send(
                "Your ladder challenge expired with no challengers. You can try again tomorrow."
            )
        except Exception:
            pass
        return

    # Randomly select one opponent
    selected = random.choice(joiners)
    selected_id = selected["user_id"]
    selected_global = selected["global_name"]

    # Determine ELO multipliers
    challenger_elo = get_user_elo(challenger_id)
    opponent_elo = get_user_elo(selected_id)
    elo_diff = abs(challenger_elo - opponent_elo)

    if elo_diff < 100:
        # Normal stakes
        winner_mult = 1.0
        loser_mult = 1.0
        stakes_text = "ELO difference < 100 — **Normal ELO stakes** apply."
    else:
        # Special stakes
        winner_mult = 2.0  # Non-Top16 winner gets 2x
        loser_mult = 0.5  # Top16 loser gets 0.5x
        stakes_text = "**Special Stakes:** Challenger wins = 2x ELO. Top 16 loses = 0.5x ELO loss."

    # Update the challenge record with selected opponent
    from utils.database import create_ladder_challenge_table
    import sqlite3 as _sqlite3

    create_ladder_challenge_table()
    conn = _sqlite3.connect("match_records.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE ladder_challenges SET selected_opponent_id = ? WHERE challenge_id = ?",
        (selected_id, challenge_id),
    )
    conn.commit()
    conn.close()

    # Update the channel message
    try:
        if msg:
            embed = discord.Embed(
                title="Ladder Challenge - Opponent Selected!",
                description=(
                    f"**{challenger_global}** (Top 16) vs **{selected_global}**!\n\n"
                    f"{stakes_text}\n\n"
                    f"Both players have been DM'd with match report buttons. Good luck!"
                ),
                color=discord.Color.gold(),
            )
            not_selected = [j for j in joiners if j["user_id"] != selected_id]
            if not_selected:
                embed.add_field(
                    name="Not Selected",
                    value="\n".join(f"• {j['global_name']}" for j in not_selected),
                    inline=False,
                )
            embed.set_footer(text="Ladder Challenge • May the best sorcerer win!")
            await msg.edit(embed=embed, view=None)
    except Exception as e:
        logger.error(f"Error updating ladder challenge result message: {e}")

    # Send report buttons to BOTH players
    report_view_challenger = LadderChallengeReportButtons(
        bot=bot,
        challenger_id=challenger_id,
        challenger_global=challenger_global,
        opponent_id=selected_id,
        opponent_global=selected_global,
        challenge_id=challenge_id,
        elo_multiplier_winner=winner_mult,
        elo_multiplier_loser=loser_mult,
        channel=channel,
    )

    report_view_opponent = LadderChallengeReportButtons(
        bot=bot,
        challenger_id=challenger_id,
        challenger_global=challenger_global,
        opponent_id=selected_id,
        opponent_global=selected_global,
        challenge_id=challenge_id,
        elo_multiplier_winner=winner_mult,
        elo_multiplier_loser=loser_mult,
        channel=channel,
    )

    # DM the challenger
    try:
        challenger_user = await bot.fetch_user(challenger_id)
        await challenger_user.send(
            f"**Ladder Challenge Match!** Your opponent is **{selected_global}**!\n\n"
            f"{stakes_text}\n\n"
            f"Report the match result below:",
            view=report_view_challenger,
        )
    except discord.Forbidden:
        dm_channel = bot.get_channel(DM_DISABLED_CHANNEL_ID)
        if dm_channel:
            await dm_channel.send(
                scrub_urls(
                    f"<@{challenger_id}> **Ladder Challenge Match!** Your opponent is **{selected_global}**!\n\n"
                    f"{stakes_text}\n\nReport the match result below:"
                ),
                view=report_view_challenger,
            )
    except Exception as e:
        logger.error(f"Error DMing challenger for ladder match: {e}")

    # DM the selected opponent
    try:
        opponent_user = await bot.fetch_user(selected_id)
        await opponent_user.send(
            f"**You've been selected for a Ladder Challenge!**\n\n"
            f"You're playing against **{challenger_global}** (Top 16)!\n\n"
            f"{stakes_text}\n\n"
            f"Report the match result below:",
            view=report_view_opponent,
        )
    except discord.Forbidden:
        dm_channel = bot.get_channel(DM_DISABLED_CHANNEL_ID)
        if dm_channel:
            await dm_channel.send(
                scrub_urls(
                    f"<@{selected_id}> **You've been selected for a Ladder Challenge!**\n\n"
                    f"You're playing against **{challenger_global}** (Top 16)!\n\n"
                    f"{stakes_text}\n\nReport the match result below:"
                ),
                view=report_view_opponent,
            )
    except Exception as e:
        logger.error(f"Error DMing opponent for ladder match: {e}")

    # Announce in channel
    if channel:
        try:
            await channel.send(
                f"**Ladder Challenge!** <@{challenger_id}> (Top 16) vs <@{selected_id}>! "
                f"{'Normal stakes.' if winner_mult == 1.0 else 'Special stakes: 2x/0.5x ELO!'}"
            )
        except Exception:
            pass


async def _ladder_challenge_timeout(bot, challenger_id):
    """Wait for the timeout period, then resolve the ladder challenge."""
    try:
        await asyncio.sleep(LADDER_CHALLENGE_TIMEOUT_SECONDS)
        # Only resolve if it's still active (wasn't already resolved by full queue)
        if challenger_id in active_ladder_challenges:
            await _resolve_ladder_challenge(bot, challenger_id)
    except asyncio.CancelledError:
        pass  # Task was cancelled because queue filled up


class JoinQueueButton(discord.ui.View):
    """Button for joining the LFG queue from the status message"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Join Queue", style=discord.ButtonStyle.green, custom_id="join_lfg_queue"
    )
    async def join_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle join queue button click - shows the deck URL modal"""
        # Check if user is already in queue before showing modal
        if interaction.user.id in lfg_queue:
            await interaction.response.send_message(
                "You're already in the queue!", ephemeral=True
            )
            return

        # Show the modal to collect deck URL and queue duration
        modal = DeckURLModal(self.bot, is_button_join=True)
        await interaction.response.send_modal(modal)


class LFGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lfg_channel_id = 1336912830867439676
        self.check_expired_queue.start()  # Start the background task
        self.cleanup_old_status_messages.start()  # Clean up old messages on startup
        self.cleanup_old_leaderboard_messages.start()  # Clean up old leaderboard on startup

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.check_expired_queue.cancel()
        self.cleanup_old_status_messages.cancel()
        self.cleanup_old_leaderboard_messages.cancel()

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
            leaderboard_channel_id = 1457113321118629889
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

        global leaderboard_message_id

        leaderboard_channel_id = 1457113321118629889
        leaderboard_channel = self.bot.get_channel(leaderboard_channel_id)

        if not leaderboard_channel:
            logger.warning(f"Leaderboard channel {leaderboard_channel_id} not found")
            return

        TICKET_HOLDER_ROLE_ID = 1468583538642128947

        try:
            # Get active event info for filtering matches
            active_event = get_active_event()
            event_start_str = None
            event_name = "Current Season"
            if active_event:
                event_start_str = active_event["start_date"].isoformat()
                event_name = active_event["event_name"]

            # Fetch top 16 players from database with game counts
            conn_elo = sqlite3.connect("elo.db")
            cursor_elo = conn_elo.cursor()
            cursor_elo.execute("""
                SELECT user_id, user_display_name, elo 
                FROM overall_standings 
                ORDER BY elo DESC 
                LIMIT 16
            """)
            top_players = cursor_elo.fetchall()
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
                description="Current ELO Rankings",
                color=discord.Color.gold(),
            )

            if top_players:
                # Get guild for role checking
                guild = self.bot.get_guild(config.GUILD_ID)

                # Build player data with resolved names and game counts
                player_data = []
                for user_id, display_name, elo in top_players:
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
                                role.id == TICKET_HOLDER_ROLE_ID
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

                # Overall Rankings (all top 16)
                overall_text = []
                for idx, p in enumerate(player_data, 1):
                    overall_text.append(
                        f"**{idx}.** {p['display_name']} - **{p['elo']}** ELO ({p['games']} games)"
                    )
                embed.add_field(
                    name="🏆 Overall Rankings",
                    value="\n".join(overall_text)
                    if overall_text
                    else "No players ranked yet.",
                    inline=False,
                )

                # Ticket Holders section (top 16 from ticket holders)
                ticket_players = [p for p in player_data if p["has_ticket"]]
                ticket_text = []
                for idx, p in enumerate(ticket_players[:16], 1):
                    ticket_text.append(
                        f"**{idx}.** {p['display_name']} - **{p['elo']}** ELO ({p['games']} games)"
                    )
                embed.add_field(
                    name="🎟️ Ticket Holders",
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
                    name="🎮 Free Play",
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
            if leaderboard_message_id:
                try:
                    old_message = await leaderboard_channel.fetch_message(
                        leaderboard_message_id
                    )
                    await old_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logger.warning(f"Could not delete old leaderboard message: {e}")

            # Send new leaderboard message
            new_message = await leaderboard_channel.send(embed=embed)
            leaderboard_message_id = new_message.id
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

    async def update_lfg_status(self):
        """Update the persistent LFG status message"""
        global lfg_status_message_id

        lfg_channel = self.bot.get_channel(self.lfg_channel_id)
        if not lfg_channel:
            return

        # Clean expired entries first
        self.clean_expired_lfg()

        # Create embed based on queue status
        if len(lfg_queue) == 0:
            # RED - Empty queue
            embed = discord.Embed(
                title="🔴 LFG Queue Status",
                description="**Queue is empty**\n\nClick the **Join Queue** button below to find a match!\nUse `!cancel` to leave the queue.",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Status updates automatically")
        else:
            # GREEN - Active queue
            embed = discord.Embed(
                title="🟢 LFG Queue Status",
                description=f"**{len(lfg_queue)} player(s) looking for a game!!**\n\nClick **Join Queue** button below to get matched!\nUse `!cancel` to leave the queue.",
                color=discord.Color.green(),
            )

            # Add details for each player in queue
            now = datetime.datetime.now()
            queue_details = []
            for user_id, info in lfg_queue.items():
                time_elapsed = (now - info["timestamp"]).total_seconds() / 60
                time_remaining = info["timeframe"] - time_elapsed

                # Use a random funny placeholder instead of actual name
                placeholder = SORCERY_NICKNAMES[randrange(0, len(SORCERY_NICKNAMES))]
                queue_details.append(
                    f"• **{placeholder}** - {int(time_remaining)} min remaining"
                )

            if queue_details:
                embed.add_field(
                    name="Players in Queue:",
                    value="\n".join(queue_details),
                    inline=False,
                )

            embed.set_footer(text="Status updates automatically")

        # Create the Join Queue button view
        view = JoinQueueButton(self.bot)

        # Delete old message and send new one
        try:
            if lfg_status_message_id:
                try:
                    old_message = await lfg_channel.fetch_message(lfg_status_message_id)
                    await old_message.delete()
                except discord.NotFound:
                    # Message was already deleted, no problem
                    pass
                except Exception as e:
                    logger.warning(f"Could not delete old status message: {e}")

            # Send new status message with button
            new_message = await lfg_channel.send(embed=embed, view=view)
            lfg_status_message_id = new_message.id

        except Exception as e:
            logger.error(f"Error updating LFG status message: {e}")

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

        # Check for exact matches
        if failed_command in command_suggestions:
            suggestion = command_suggestions[failed_command]
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!lfg_help` to see all available commands."
            )
            return

        # Check for partial matches (fuzzy matching)
        for key, suggestion in command_suggestions.items():
            if key in failed_command or failed_command in key:
                await ctx.send(
                    f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!lfg_help` to see all available commands."
                )
                return

        # Check for spelling mistakes using Levenshtein distance
        # Get all actual command names
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
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{best_match}`? Type `!lfg_help` to see all available commands."
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

    def check_if_someone_is_lfg(self, ctx):
        """Find oldest player in queue who didn't play against ctx.author recently.
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

    def add_to_lfg_queue(self, ctx, timeframe, deck_url=None):
        lfg_queue[ctx.author.id] = {
            "timestamp": datetime.datetime.now(),
            "timeframe": int(timeframe),
            "deck_url": deck_url,
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
                    role = ctx.guild.get_role(DM_DISABLED_ROLE_ID)
                    member = ctx.guild.get_member(ctx.author.id)
                    if role and member and role not in member.roles:
                        await member.add_roles(role)
                        logger.info(f"Added DM-disabled role to {ctx.author}")
            except Exception as e:
                logger.error(f"Failed to add DM-disabled role to {ctx.author}: {e}")

            # Send to the DM-disabled channel
            dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
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

        channel_id = 1336912830867439676
        lfg_channel = self.bot.get_channel(channel_id)

        # Show modal to get challenger's deck URL
        modal = ChallengerDeckModal(
            challenger=ctx.author,
            opponent=opponent,
            lfg_channel=lfg_channel,
            bot=self.bot,
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
                "• Matched games: Use buttons sent to your DMs after being paired\n"
                "• You can add deck URL and match details (optional)"
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
                "• Queue time: 5-120 minutes\n"
                "• Challenges expire after 5 minutes\n"
                "• Enable DMs to receive match reports"
            ),
            inline=False,
        )

        embed.set_footer(text="Use !help for more commands")

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def admin_help(self, ctx):
        """Get detailed help for admin commands (requires administrator permissions)."""
        embed = discord.Embed(
            title="Admin Commands",
            description="Administrative commands for managing ELO, matches, and players.",
            color=discord.Color.orange(),
        )

        # Match Reporting
        embed.add_field(
            name="Manual Match Reporting",
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

        # Match Correction
        embed.add_field(
            name="Match Correction",
            value=(
                "`!correct_match <match_id>`\n"
                "Flip the winner/loser of a match and recalculate ALL affected ELO.\n"
                "**When to use:** When someone reported the wrong outcome. This will:\n"
                "• Swap the winner and loser\n"
                "• Recalculate ELO for all subsequent matches involving those players\n"
                "**Recommended over !remove_match** for incorrect reports."
            ),
            inline=False,
        )

        # Match Removal
        embed.add_field(
            name="Match Removal",
            value=(
                "`!remove_match <match_id>`\n"
                "Remove a specific match and revert the ELO changes from that match.\n"
                "**When to use:** When a match was a test game or never actually happened.\n"
                "Does NOT recalculate subsequent matches. Use `!correct_match` instead for wrong reports."
            ),
            inline=False,
        )

        # Player Removal
        embed.add_field(
            name="Player Removal",
            value=(
                "`!remove_player @user`\n"
                "Remove a player from the system and revert ALL ELO changes from their matches.\n"
                "**When to use:** When a player was cheating, using multiple accounts, "
                "or needs to be completely removed from the ranking system.\n"
                "**Warning:** This affects all opponents' ELO as well!"
            ),
            inline=False,
        )

        # Full Reset
        embed.add_field(
            name="Full Database Reset",
            value=(
                "`!reset_elo`\n"
                "**DANGER:** Completely reset ALL ELO ratings and match history.\n"
                "**When to use:** At the start of a new season, or when starting fresh.\n"
                "**This action cannot be undone!**"
            ),
            inline=False,
        )

        # Activity Monitoring
        embed.add_field(
            name="Activity Monitoring",
            value=(
                "`!game_activity [hours]`\n"
                "View game statistics for the last X hours (default 24, max 8760).\n"
                "**When to use:** To monitor server activity, check for unusual patterns, "
                "or generate activity reports."
            ),
            inline=False,
        )

        # Event Management
        embed.add_field(
            name="Event Management",
            value=(
                "`!start_event <event_name>`\n"
                "Start a new event/season. Archives current event (if any) and resets event ELO.\n"
                "**When to use:** At the start of a new tournament or season.\n\n"
                "`!end_event`\n"
                "End the current event without starting a new one.\n"
                "**When to use:** To have a break between seasons.\n\n"
                "`!event_status`\n"
                "View current event status including name, K-value, and days elapsed."
            ),
            inline=False,
        )

        embed.set_footer(text="All admin commands require administrator permissions")

        await ctx.send(embed=embed)

    @admin_help.error
    async def admin_help_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def reset_elo(self, ctx):
        """Admin command to reset all ELO ratings and match history"""
        import sqlite3

        try:
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

            success_embed = discord.Embed(
                title="Database Reset Complete",
                description="All databases have been dropped and recreated:\n• ELO database reset\n• Match records cleared\n• Challenge matches cleared\n\nAll tables are ready to use.",
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
    @commands.has_permissions(administrator=True)
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
            from utils.database import update_elo_db

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
    @commands.has_permissions(administrator=True)
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
    @commands.has_permissions(administrator=True)
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
                f"**K-Value Range:** 16 → 32\n"
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
    @commands.has_permissions(administrator=True)
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
            f"🔄 Recalculating event ELO for **{event_name}**... This may take a moment."
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

            logger.info(
                f"Event ELO recalculated by {ctx.author} - {len(matches)} matches replayed"
            )

        except Exception as e:
            await ctx.send(f"❌ Error recalculating ELO: {str(e)}")
            logger.error(f"Failed to recalculate event ELO: {e}")

    @recalculate_event_elo.error
    async def recalculate_event_elo_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def spot_elo_reset(self, ctx, user: discord.Member = None, elo: int = None):
        """Admin command to set a specific user's ELO. Usage: !spot_elo_reset @user 1500"""
        import sqlite3

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

        try:
            # Get display name with fallback
            user_name = user.global_name or user.display_name

            # Connect to database
            conn = sqlite3.connect("elo.db")
            cursor = conn.cursor()

            # Check if user exists in database
            cursor.execute(
                "SELECT elo FROM overall_standings WHERE user_id = ?", (user.id,)
            )
            result = cursor.fetchone()

            old_elo = result[0] if result else None

            if result:
                # Update existing user
                cursor.execute(
                    "UPDATE overall_standings SET elo = ?, user_display_name = ? WHERE user_id = ?",
                    (elo, user_name, user.id),
                )
            else:
                # Insert new user
                cursor.execute(
                    "INSERT INTO overall_standings (user_id, user_display_name, elo) VALUES (?, ?, ?)",
                    (user.id, user_name, elo),
                )

            conn.commit()
            conn.close()

            # Update leaderboard
            await self.update_leaderboard()

            # Send confirmation
            if old_elo is not None:
                success_embed = discord.Embed(
                    title="ELO Updated",
                    description=f"**User:** {user.mention} ({user_name})\n**Old ELO:** {old_elo}\n**New ELO:** {elo}",
                    color=discord.Color.blue(),
                )
            else:
                success_embed = discord.Embed(
                    title="ELO Set",
                    description=f"**User:** {user.mention} ({user_name})\n**ELO:** {elo}\n\n*User was not in database, created new entry.*",
                    color=discord.Color.green(),
                )

            success_embed.set_footer(text=f"Updated by {ctx.author.display_name}")
            await ctx.send(embed=success_embed)

            logger.info(
                f"Admin {ctx.author} (ID: {ctx.author.id}) set ELO for {user_name} (ID: {user.id}) to {elo} (was: {old_elo})"
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
    @commands.has_permissions(administrator=True)
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
                        "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                        (w_elo_change, w_id),
                    )
                if l_elo_change:
                    elo_cursor.execute(
                        "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                        (l_elo_change, l_id),
                    )

            # Then revert the target match
            if target_winner_elo_change:
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                    (target_winner_elo_change, original_winner_id),
                )
            if target_loser_elo_change:
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                    (target_loser_elo_change, original_loser_id),
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
                "SELECT elo FROM overall_standings WHERE user_id = ?", (new_winner_id,)
            )
            row = elo_cursor.fetchone()
            new_winner_elo_before = row[0] if row else 1500

            elo_cursor.execute(
                "SELECT elo FROM overall_standings WHERE user_id = ?", (new_loser_id,)
            )
            row = elo_cursor.fetchone()
            new_loser_elo_before = row[0] if row else 1500

            # Calculate new ELO changes
            new_winner_elo_after = update_elo(
                new_winner_elo_before, new_loser_elo_before, True
            )
            new_loser_elo_after = update_elo(
                new_loser_elo_before, new_winner_elo_before, False
            )

            new_winner_elo_change = new_winner_elo_after - new_winner_elo_before
            new_loser_elo_change = new_loser_elo_after - new_loser_elo_before

            # Update ELO in database
            elo_cursor.execute(
                "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
                (new_winner_elo_after, new_winner_id),
            )
            elo_cursor.execute(
                "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
                (new_loser_elo_after, new_loser_id),
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
                    "SELECT elo FROM overall_standings WHERE user_id = ?", (w_id,)
                )
                row = elo_cursor.fetchone()
                winner_elo_before = row[0] if row else 1500

                elo_cursor.execute(
                    "SELECT elo FROM overall_standings WHERE user_id = ?", (l_id,)
                )
                row = elo_cursor.fetchone()
                loser_elo_before = row[0] if row else 1500

                # Calculate new ELO
                winner_elo_after = update_elo(winner_elo_before, loser_elo_before, True)
                loser_elo_after = update_elo(loser_elo_before, winner_elo_before, False)

                w_elo_change = winner_elo_after - winner_elo_before
                l_elo_change = loser_elo_after - loser_elo_before

                # Update ELO in database
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
                    (winner_elo_after, w_id),
                )
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = ? WHERE user_id = ?",
                    (loser_elo_after, l_id),
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
    @commands.has_permissions(administrator=True)
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
                           winner_elo_change, loser_elo_change, timestamp
                    FROM match_records 
                    WHERE match_id = ?
                    """,
                    (match_id,),
                )
            except sqlite3.OperationalError:
                # Fallback: column might be named differently or use ROWID
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

            # Revert ELO changes
            reverted_info = []

            if winner_elo_change:
                # Winner gained ELO, so subtract it
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                    (winner_elo_change, winner_id),
                )
                reverted_info.append(f"**{winner_name}**: -{winner_elo_change} ELO")

            if loser_elo_change:
                # Loser lost ELO (negative value), so add it back (subtract the negative)
                elo_cursor.execute(
                    "UPDATE overall_standings SET elo = elo - ? WHERE user_id = ?",
                    (loser_elo_change, loser_id),
                )
                reverted_info.append(
                    f"**{loser_name}**: {-loser_elo_change if loser_elo_change else 0} ELO"
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

        ROLE_IDS = {1445433610609102990, 1455669646370799667}

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
                f"**{i + 1}.** {mention} — **{elo}** ELO ({name})"
                for i, (elo, mention, name) in enumerate(eligible)
            ]

            embed = discord.Embed(
                title="Eligible for Masters Bracket — Top 16 with required role",
                description="\n".join(lines),
                color=discord.Color.purple(),
            )
            embed.set_footer(
                text="Role requirement: IDs 1445433610609102990 or 1455669646370799667"
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

            ROLE_IDS = {1445433610609102990, 1455669646370799667}

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
                lines.append(f"**{count}.** {mention} — **{elo}** ELO ({display})")

            embed = discord.Embed(
                title="Top 16 — Eligible (without specified roles)",
                description="\n".join(lines) if lines else "No eligible players found.",
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"top16 error: {e}")
            await ctx.send("Error fetching top 16. See logs for details.")

    @commands.command()
    @commands.has_permissions(administrator=True)
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

            # Apply ELO adjustments to opponents
            adjustments_made = []
            for opponent_id, (adjustment, opponent_name) in elo_adjustments.items():
                if adjustment != 0:
                    elo_cursor.execute(
                        "UPDATE overall_standings SET elo = elo + ? WHERE user_id = ?",
                        (adjustment, opponent_id),
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


async def setup(bot):
    await bot.add_cog(LFGCog(bot))
