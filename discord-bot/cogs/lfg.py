import discord
from discord.ext import commands, tasks
import datetime
import logging
from random import randrange

from utils.database import winner_report, losser_report, solo_match_report
from utils.constants import SORCERY_NICKNAMES

logger = logging.getLogger("discord_bot")

# Constants for DM failure handling
DM_DISABLED_ROLE_ID = 1445222741686095994
DM_DISABLED_CHANNEL_ID = 1456299008023728302

# In-memory LFG queue (user_id: {timestamp, timeframe})
lfg_queue = {}

# Track pending match reports awaiting confirmation
# Key: (reporter_id, opponent_id), Value: match report data
pending_match_reports = {}

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

        if self.is_winner:
            await winner_report(
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
                self.bot,
            )
        else:
            await losser_report(
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
                self.bot,
            )

        await interaction.followup.send(
            f"Match report submitted!\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}",
            ephemeral=True,
        )


class MatchConfirmationButtons(discord.ui.View):
    """Buttons for confirming a match report from opponent"""

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
        is_winner: bool,
        bot=None,
        channel=None,
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

    @discord.ui.button(
        label="Confirm",
        style=discord.ButtonStyle.success,
        custom_id="confirm_match_report",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Only the opponent can confirm
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message(
                "Only the opponent can confirm this report.", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Submit match report only ONCE (not twice)
        # This will insert one record and update ELO for the winner
        await winner_report(
            self.reporter_id,  # reporter_id (who originally reported)
            self.winner_id,
            self.winner_global,
            True,
            self.loser_id,
            self.loser_global,
            "n",  # first_player default
            0,  # match_time default
            "No URL provided",  # curiosa_link default
            "",  # match_comment default
            self.winner_id,  # interaction_user_id
            self.winner_global,  # interaction_global
            self.bot,
        )

        # Update ELO for the loser as well
        from utils.database import update_elo_db

        update_elo_db(self.loser_id, self.loser_global, False, self.winner_id)

        # Remove the confirmation message
        await interaction.message.edit(
            content=f"Match confirmed! {self.winner_global} won against {self.loser_global}.",
            view=None,
        )

        # Send confirmation to confirming user
        await interaction.followup.send(
            f"Match report confirmed and submitted!\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}",
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
                    f"{reporter.mention} {self.opponent_global} has confirmed your match report! Match has been recorded."
                )
        except Exception:
            pass

        # Remove from pending
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)

        # Update leaderboard in designated channel
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

    @discord.ui.button(
        label="Dispute",
        style=discord.ButtonStyle.danger,
        custom_id="dispute_match_report",
    )
    async def dispute_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Only the opponent can dispute
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message(
                "Only the opponent can dispute this report.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"You have disputed the match report. Please contact the reporter {self.reporter_global} to resolve this.",
            ephemeral=True,
        )

        # Remove the confirmation message
        await interaction.message.edit(
            content=f"Match report disputed. Please resolve with {self.reporter_global}.",
            view=None,
        )

        # Notify the reporter
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"{self.opponent_global} has disputed your match report. Please discuss and resolve."
            )
        except discord.Forbidden:
            # If DM fails, send to match-report channel
            match_report_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    f"{reporter.mention} {self.opponent_global} has disputed your match report. Please discuss and resolve."
                )
        except Exception:
            pass

        # Remove from pending
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)


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
    ):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_global = player1_global
        self.player2_global = player2_global
        self.bot = bot
        self.channel = channel

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
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

        # Store pending report with opponent's message reference
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
        }

        # Send confirmation to opponent
        try:
            opponent = await self.bot.fetch_user(opponent_id)

            # Find opponent's match report message to remove their buttons
            try:
                opponent_dm_channel = await opponent.create_dm()
                opponent_report_message = None

                async for message in opponent_dm_channel.history(limit=50):
                    if message.author.id == self.bot.user.id and message.components:
                        # Check if this is the match report message for these two players
                        for component in message.components:
                            for button in component.children:
                                if hasattr(
                                    button, "custom_id"
                                ) and button.custom_id in [
                                    "win_button",
                                    "lose_button",
                                    "cancel_match",
                                ]:
                                    opponent_report_message = message
                                    break
                            if opponent_report_message:
                                break
                        if opponent_report_message:
                            break

                # Remove opponent's buttons
                if opponent_report_message:
                    await opponent_report_message.edit(view=None)
            except discord.Forbidden:
                logger.warning(
                    f"Cannot access DM channel for user {opponent_id} - DMs disabled or bot blocked"
                )
            except Exception as e:
                logger.error(f"Error accessing opponent DM history: {e}")

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
                        f"{opponent.mention} **Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **won** against you.\n\nPlease confirm or dispute this report:",
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
                        f"**Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **won** against you.\n\nPlease confirm or dispute this report:",
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
                                f"{opponent.mention} 🎮 **Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **won** against you.\n\nPlease confirm or dispute this report:",
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "✅ Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.response.send_message(
                                f"❌ Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"❌ Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ Could not send confirmation to {opponent_global}.",
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

        # Store pending report with opponent's message reference
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
        }

        # Send confirmation to opponent
        try:
            opponent = await self.bot.fetch_user(opponent_id)

            # Find opponent's match report message to remove their buttons
            try:
                opponent_dm_channel = await opponent.create_dm()
                opponent_report_message = None

                async for message in opponent_dm_channel.history(limit=50):
                    if message.author.id == self.bot.user.id and message.components:
                        # Check if this is the match report message for these two players
                        for component in message.components:
                            for button in component.children:
                                if hasattr(
                                    button, "custom_id"
                                ) and button.custom_id in [
                                    "win_button",
                                    "lose_button",
                                    "cancel_match",
                                ]:
                                    opponent_report_message = message
                                    break
                            if opponent_report_message:
                                break
                        if opponent_report_message:
                            break

                # Remove opponent's buttons
                if opponent_report_message:
                    await opponent_report_message.edit(view=None)
            except discord.Forbidden:
                logger.warning(
                    f"Cannot access DM channel for user {opponent_id} - DMs disabled or bot blocked"
                )
            except Exception as e:
                logger.error(f"Error accessing opponent DM history: {e}")

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
                        f"{opponent.mention} **Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **lost** to you (you won).\n\nPlease confirm or dispute this report:",
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
                        f"**Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **lost** to you (you won).\n\nPlease confirm or dispute this report:",
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
                                f"{opponent.mention} 🎮 **Match Report Confirmation**\n\n{interaction.user.global_name} reported that they **lost** to you (you won).\n\nPlease confirm or dispute this report:",
                                view=confirmation_view,
                            )
                            await interaction.response.send_message(
                                "✅ Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.response.send_message(
                                f"❌ Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"❌ Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ Could not send confirmation to {opponent_global}.",
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
        label="We didn't play/cancel match",
        style=discord.ButtonStyle.blurple,
        custom_id="cancel_match",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            f"{interaction.user.mention} clicked **cancel match**", ephemeral=True
        )
        await interaction.message.edit(view=None)


class ChallengeButtons(discord.ui.View):
    def __init__(self, challenger_id: int, challenger_global: str, channel=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel

    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.success)
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        challenger = await interaction.client.fetch_user(self.challenger_id)

        # Send match report buttons to both players
        challenger_view = LFGReportButtons(
            0,  # match_id not needed for direct challenges
            self.challenger_id,
            self.challenger_global,
            interaction.user.id,
            interaction.user.global_name or interaction.user.display_name,
            interaction.client,
            self.channel,
        )

        opponent_view = LFGReportButtons(
            0,  # match_id not needed for direct challenges
            interaction.user.id,
            interaction.user.global_name or interaction.user.display_name,
            self.challenger_id,
            self.challenger_global,
            interaction.client,
            self.channel,
        )

        try:
            await challenger.send("Match report:", view=challenger_view)
        except discord.Forbidden:
            # DM failed - add role and post in designated channel
            try:
                guild = interaction.guild
                if guild:
                    role = guild.get_role(DM_DISABLED_ROLE_ID)
                    member = guild.get_member(self.challenger_id)
                    if role and member:
                        await member.add_roles(role)
                        logger.info(
                            f"Added DM-disabled role to {challenger.display_name}"
                        )

                dm_channel = interaction.client.get_channel(DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        f"{challenger.mention} **Match Report**\n\nYour challenge was accepted! Report the match result below:",
                        view=challenger_view,
                    )
                    logger.info(
                        f"Posted match report in DM-disabled channel for {challenger.display_name}"
                    )
            except Exception as e:
                logger.error(f"Failed to handle DM failure for challenger: {e}")

        # Send match report to the opponent (who accepted the challenge)
        try:
            await interaction.response.send_message(
                "Match report:", view=opponent_view, ephemeral=True
            )
        except Exception:
            pass

        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

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


class ReportButtonsSolo(discord.ui.View):
    def __init__(self, reporter_id: int, reporter_global: str, bot=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.bot = bot

    @discord.ui.button(label="I Won!", style=discord.ButtonStyle.success)
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            SoloMatchReportModal(
                reporter_id=self.reporter_id,
                reporter_global=self.reporter_global,
                is_winner=True,
                bot=self.bot,
            )
        )
        await interaction.message.edit(view=None)

    @discord.ui.button(label="I Lost", style=discord.ButtonStyle.danger)
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            SoloMatchReportModal(
                reporter_id=self.reporter_id,
                reporter_global=self.reporter_global,
                is_winner=False,
                bot=self.bot,
            )
        )
        await interaction.message.edit(view=None)


class SoloMatchReportModal(discord.ui.Modal, title="Solo Match Report"):
    opponent_name = discord.ui.TextInput(
        label="Opponent's Name",
        placeholder="Enter your opponent's name",
        required=False,
    )

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
        self, reporter_id: int, reporter_global: str, is_winner: bool, bot=None
    ):
        super().__init__()
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.is_winner = is_winner
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        curiosa_link = (
            self.curiosa_url.value if self.curiosa_url.value else "No URL provided"
        )
        match_comment = self.match_comment.value if self.match_comment.value else ""
        first_player = self.first_player.value if self.first_player.value else "n"
        match_time = (
            int(self.match_time.value) if self.match_time.value.isdigit() else 0
        )

        await solo_match_report(
            reporter_id=self.reporter_id,
            reporter_global=self.reporter_global,
            opponent_name=self.opponent_name.value,
            is_winner=self.is_winner,
            first_player=first_player,
            match_time=match_time,
            curiosa_link=curiosa_link,
            match_comment=match_comment,
            bot=self.bot,
        )

        result = "Won" if self.is_winner else "Lost"
        await interaction.followup.send(
            f"Solo match report submitted!\n**Result:** {result}\n**Opponent:** {self.opponent_name.value}",
            ephemeral=True,
        )


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
        """Handle join queue button click"""

        # Create a fake context to use with existing lfg command
        class FakeContext:
            def __init__(self, bot, interaction):
                self.bot = bot
                self.author = interaction.user
                self.guild = interaction.guild
                self.channel = interaction.channel
                self.message = None

            async def send(self, *args, **kwargs):
                # Don't send to channel, will use interaction response
                pass

        ctx = FakeContext(self.bot, interaction)
        lfg_cog = self.bot.get_cog("LFGCog")

        if not lfg_cog:
            await interaction.response.send_message(
                "LFG system is not available.", ephemeral=True
            )
            return

        # Check if user is already in queue
        if interaction.user.id in lfg_queue:
            await interaction.response.send_message(
                "You're already in the queue!", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Use the existing lfg logic
        lfg_cog.clean_expired_lfg()
        matched_user_id = lfg_cog.check_if_someone_is_lfg(ctx)

        if matched_user_id and matched_user_id != interaction.user.id:
            # Match found!
            matched_user = await self.bot.fetch_user(matched_user_id)
            lfg_channel = self.bot.get_channel(lfg_cog.lfg_channel_id)

            view_ctx = LFGReportButtons(
                interaction.user.id,
                interaction.user.id,
                interaction.user.global_name or interaction.user.display_name,
                matched_user_id,
                matched_user.global_name or matched_user.display_name,
                self.bot,
                lfg_channel,
            )

            try:
                await interaction.user.send("Match report:", view=view_ctx)
            except discord.Forbidden:
                # Handle DM failure
                try:
                    guild = interaction.guild
                    if guild:
                        role = guild.get_role(DM_DISABLED_ROLE_ID)
                        member = guild.get_member(interaction.user.id)
                        if role and member:
                            await member.add_roles(role)

                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            f"{interaction.user.mention} **Match Report**\n\nYou've been matched with {matched_user.mention}! Report the match result below:",
                            view=view_ctx,
                        )
                except Exception:
                    pass

            # Announce match in LFG channel
            if lfg_channel:
                await lfg_channel.send(
                    f"**Match Found!** {interaction.user.mention} matched with {matched_user.mention}!"
                )

            view_matched = LFGReportButtons(
                matched_user_id,
                matched_user_id,
                matched_user.global_name or matched_user.display_name,
                interaction.user.id,
                interaction.user.global_name or interaction.user.display_name,
                self.bot,
                lfg_channel,
            )

            try:
                await matched_user.send(
                    f"You've been matched with {interaction.user.mention} for a game!",
                    view=view_matched,
                )
            except discord.Forbidden:
                # Handle DM failure
                try:
                    guild = interaction.guild
                    if guild:
                        role = guild.get_role(DM_DISABLED_ROLE_ID)
                        member = guild.get_member(matched_user_id)
                        if role and member:
                            await member.add_roles(role)

                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            f"{matched_user.mention} **Match Report**\n\nYou've been matched with {interaction.user.mention}! Report the match result below:",
                            view=view_matched,
                        )
                except Exception:
                    pass

            lfg_cog.pair_players(ctx)
            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"Match found! You've been paired with {matched_user.global_name}. Check your DMs for the match report.",
                ephemeral=True,
            )
        else:
            # Add to queue
            default_timeframe = 30
            lfg_cog.add_to_lfg_queue(ctx, default_timeframe)

            try:
                await interaction.user.send(
                    f"You have been added to the queue for looking for a game for {default_timeframe} minutes."
                )
            except discord.Forbidden:
                pass

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"You've joined the queue for {default_timeframe} minutes! You'll be notified when a match is found.",
                ephemeral=True,
            )


class LFGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lfg_channel_id = 1336912830867439676
        self.check_expired_queue.start()  # Start the background task

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.check_expired_queue.cancel()

    async def update_leaderboard(self):
        """Update the leaderboard in the designated channel"""
        import sqlite3

        global leaderboard_message_id

        leaderboard_channel_id = 1457113321118629889
        leaderboard_channel = self.bot.get_channel(leaderboard_channel_id)

        if not leaderboard_channel:
            logger.warning(f"Leaderboard channel {leaderboard_channel_id} not found")
            return

        try:
            # Fetch top 16 players from database
            conn = sqlite3.connect("elo.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, user_display_name, elo 
                FROM overall_standings 
                ORDER BY elo DESC 
                LIMIT 16
            """)
            top_players = cursor.fetchall()
            conn.close()

            # Create leaderboard embed
            embed = discord.Embed(
                title="Top 16 Leaderboard",
                description="Current ELO Rankings",
                color=discord.Color.gold(),
            )

            if top_players:
                leaderboard_text = []
                for idx, (user_id, display_name, elo) in enumerate(top_players, 1):
                    leaderboard_text.append(
                        f"**{idx}.** {display_name} - **{elo}** ELO"
                    )

                embed.add_field(
                    name="Rankings", value="\n".join(leaderboard_text), inline=False
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
                description="**Queue is empty**\n\nUse `!lfg` to join the queue and find a match!",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Status updates automatically")
        else:
            # GREEN - Active queue
            embed = discord.Embed(
                title="🟢 LFG Queue Status",
                description=f"**{len(lfg_queue)} player(s) looking for a game!**\n\nUse `!lfg` to join and get matched instantly!\nUse `!cancel` to leave the queue.",
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
            f"{ctx.author.mention}, that command doesn't exist. Use `!lfg` to find a game or `!lfg_help` to see all available commands."
        )

    def check_if_someone_is_lfg(self, ctx):
        now = datetime.datetime.now()
        for user_id, info in lfg_queue.items():
            timestamp = info["timestamp"]
            timeframe = info["timeframe"]
            if (now - timestamp).total_seconds() < timeframe * 60:
                return user_id
        return None

    def add_to_lfg_queue(self, ctx, timeframe):
        lfg_queue[ctx.author.id] = {
            "timestamp": datetime.datetime.now(),
            "timeframe": int(timeframe),
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

    @commands.command(aliases=["LFG"])
    async def lfg(self, ctx, timeframe: int = 30):
        """Usage: !lfg [minutes]"""
        logger.info(
            f"LFG command started - User: {ctx.author} (ID: {ctx.author.id}), Channel: {ctx.channel}, Timeframe: {timeframe}"
        )

        # Delete the user's command message
        try:
            await ctx.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete command message: {e}")

        self.clean_expired_lfg()
        logger.info(
            f"Cleaned expired LFG entries. Current queue size: {len(lfg_queue)}"
        )

        owner_id = 296846802924208130
        channel_id = 1336912830867439676
        owner = await self.bot.fetch_user(owner_id)
        lfg_channel = self.bot.get_channel(channel_id)

        if owner:
            logger.info(
                f"Sending notification to owner about {ctx.author}'s LFG request"
            )
            await owner.send(f"{ctx.author} used the !lfg command in #{ctx.channel}.")

        matched_user_id = self.check_if_someone_is_lfg(ctx)
        logger.info(
            f"Checked for existing LFG users. Matched user ID: {matched_user_id}"
        )
        if matched_user_id and matched_user_id != ctx.author.id:
            logger.info(f"Match found! Pairing {ctx.author.id} with {matched_user_id}")
            matched_user = await self.bot.fetch_user(matched_user_id)
            view_ctx = LFGReportButtons(
                ctx.author.id,
                ctx.author.id,
                ctx.author.global_name or ctx.author.display_name,
                matched_user_id,
                matched_user.global_name or matched_user.display_name,
                self.bot,
                lfg_channel,
            )
            logger.info(
                f"Sending match report to {ctx.author} (ID: {ctx.author.id}) via DM"
            )
            try:
                await ctx.author.send("Match report:", view=view_ctx)
            except discord.Forbidden:
                logger.error(
                    f"Cannot DM {ctx.author} (ID: {ctx.author.id}) - DMs disabled or bot blocked"
                )
                # DM failed - add role and post in designated channel
                try:
                    guild = ctx.guild
                    if guild:
                        role = guild.get_role(DM_DISABLED_ROLE_ID)
                        member = guild.get_member(ctx.author.id)
                        if role and member:
                            await member.add_roles(role)
                            logger.info(
                                f"Added DM-disabled role to {ctx.author.display_name}"
                            )

                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            f"{ctx.author.mention} **Match Report**\n\nYou've been matched with {matched_user.mention}! Report the match result below:",
                            view=view_ctx,
                        )
                        logger.info(
                            f"Posted match report in DM-disabled channel for {ctx.author.display_name}"
                        )
                    else:
                        await ctx.send(
                            f"{ctx.author.mention}, matched with {matched_user.mention} who is also looking for a game! (I couldn't send you the match report. Please enable DMs.)"
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for {ctx.author}: {e}")
                    await ctx.send(
                        f"{ctx.author.mention}, matched with {matched_user.mention} who is also looking for a game! (I couldn't send you the match report. Please enable DMs.)"
                    )
            except Exception as e:
                logger.error(
                    f"Error sending DM to {ctx.author} (ID: {ctx.author.id}): {e}"
                )
                await ctx.send(
                    f"{ctx.author.mention}, matched with {matched_user.mention} who is also looking for a game!"
                )
                return

            # Always announce match in LFG channel
            if lfg_channel:
                await lfg_channel.send(
                    f"**Match Found!** {ctx.author.mention} matched with {matched_user.mention}!"
                )

            view_matched = LFGReportButtons(
                matched_user_id,
                matched_user_id,
                matched_user.global_name or matched_user.display_name,
                ctx.author.id,
                ctx.author.global_name or ctx.author.display_name,
                self.bot,
                lfg_channel,
            )
            logger.info(
                f"Sending match report to {matched_user} (ID: {matched_user_id}) via DM"
            )
            try:
                await matched_user.send(
                    f"You've been matched with {ctx.author.mention} for a game!",
                    view=view_matched,
                )
            except discord.Forbidden:
                logger.error(
                    f"Cannot DM {matched_user} (ID: {matched_user_id}) - DMs disabled or bot blocked"
                )
                # DM failed - add role and post in designated channel
                try:
                    guild = ctx.guild
                    if guild:
                        role = guild.get_role(DM_DISABLED_ROLE_ID)
                        member = guild.get_member(matched_user_id)
                        if role and member:
                            await member.add_roles(role)
                            logger.info(
                                f"Added DM-disabled role to {matched_user.display_name}"
                            )

                    dm_channel = self.bot.get_channel(DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        await dm_channel.send(
                            f"{matched_user.mention} **Match Report**\n\nYou've been matched with {ctx.author.mention}! Report the match result below:",
                            view=view_matched,
                        )
                        logger.info(
                            f"Posted match report in DM-disabled channel for {matched_user.display_name}"
                        )
                    else:
                        await ctx.send(
                            f"{matched_user.mention}, I couldn't send you the match report. Please enable DMs."
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for {matched_user}: {e}")
            except Exception as e:
                logger.error(
                    f"Error sending DM to {matched_user} (ID: {matched_user_id}): {e}"
                )
            self.pair_players(ctx)

            # Update status message after match
            await self.update_lfg_status()

            # Notify owner about the match
            if owner:
                logger.info("Sending match notification to owner")
                try:
                    await owner.send(
                        f"**Match Found!**\n"
                        f"{ctx.author} (ID: {ctx.author.id}) matched with "
                        f"{matched_user} (ID: {matched_user_id})"
                    )
                except Exception as e:
                    logger.error(f"Error sending match notification to owner: {e}")
        elif matched_user_id == ctx.author.id:
            logger.info(f"User {ctx.author.id} is already in queue")
            await ctx.send(
                f"{ctx.author.mention}, you are already in the LFG queue. Please wait for someone to match with you."
            )
        else:
            logger.info(
                f"No match found. Adding {ctx.author.id} to queue for {timeframe} minutes"
            )
            self.add_to_lfg_queue(ctx, timeframe)
            logger.info(f"User added to queue. Queue contents: {lfg_queue}")

            try:
                await ctx.author.send(
                    f"You have been added to the queue for looking for a game for "
                    f"{timeframe} minutes. You can also use the `!lfg` command here to join the queue privately."
                )
                logger.info(f"DM sent successfully to {ctx.author}")
            except discord.Forbidden:
                logger.warning(
                    f"Could not send DM to {ctx.author} (ID: {ctx.author.id}) - DMs might be disabled"
                )
            except Exception as e:
                logger.error(f"Error sending DM to {ctx.author}: {e}")

            # Update status message after joining queue
            await self.update_lfg_status()

        logger.info(f"LFG command completed for {ctx.author} (ID: {ctx.author.id})")

    @commands.command()
    async def check_lfg(self, ctx):
        """Check if anyone is currently in the LFG queue."""
        self.clean_expired_lfg()
        if len(lfg_queue) > 0:
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

        if ctx.author.id in lfg_queue:
            lfg_queue.pop(ctx.author.id)

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
        """Challenge a specific player to a match"""
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

        view = ChallengeButtons(
            ctx.author.id,
            ctx.author.global_name or ctx.author.display_name,
            lfg_channel,
        )

        try:
            # Send challenge to opponent
            await opponent.send(
                f"{ctx.author.global_name or ctx.author.display_name} has challenged you to a match!",
                view=view,
            )
            # Notify challenger in DM
            try:
                await ctx.author.send(
                    f"Challenge sent to {opponent.global_name}! They have 5 minutes to accept."
                )
            except discord.Forbidden:
                pass

            # Confirm in channel
            await ctx.send(
                f"{ctx.author.mention} has challenged {opponent.mention} to a match!"
            )

        except discord.Forbidden:
            # If DM fails, create a public thread
            if lfg_channel:
                try:
                    temp_msg = await lfg_channel.send(
                        f"{opponent.mention} You have been challenged!"
                    )
                    thread = await temp_msg.create_thread(
                        name=f"Challenge from {ctx.author.display_name}",
                        auto_archive_duration=60,
                    )
                    await thread.send(
                        f"{opponent.mention} {ctx.author.global_name} has challenged you to a match!",
                        view=view,
                    )
                    await ctx.send(
                        f"Challenge sent to {opponent.mention} in a thread (they have DMs disabled)."
                    )
                except Exception as thread_error:
                    logger.error(f"Failed to create challenge thread: {thread_error}")
                    await ctx.send(
                        f"I couldn't send a DM or create a thread for {opponent.global_name}. They might have DMs disabled."
                    )
            else:
                await ctx.send(
                    f"I couldn't send a DM to {opponent.global_name}. They might have DMs disabled."
                )
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            logger.error(f"Challenge command error: {e}")

    @commands.command()
    async def lfg_help(self, ctx):
        """Get detailed help for the Looking For Game (LFG) system."""
        embed = discord.Embed(
            title="Looking For Game (LFG) System",
            description="Find matches and challenge other players with these commands:",
            color=discord.Color.blue(),
        )

        # Queue Commands
        embed.add_field(
            name="🔍 Queue Commands",
            value=(
                "`!lfg [minutes]` - Join queue for X minutes (default 30)\n"
                "`!check_lfg` - See if anyone is in queue\n"
                "`!cancel` - Leave the queue"
            ),
            inline=False,
        )

        # Challenge System
        embed.add_field(
            name="⚔️ Challenge System",
            value=(
                "`!challenge @user` - Challenge specific player\n"
                "Note: Must be used in the LFG channel to tag opponent"
            ),
            inline=False,
        )

        # Match Reporting
        embed.add_field(
            name="📝 Match Reporting",
            value=(
                "**Matched Games:** Both players get match report buttons in DMs\n"
                "**Solo Games:** Use `!record_game` to report any match played outside the bot\n"
                "• Report win/loss using the buttons\n"
                "• Optional: Add deck URL and match details"
            ),
            inline=False,
        )

        # Tips & Info
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Queue time can be 5-120 minutes\n"
                "• Direct challenges expire after 5 minutes\n"
                "• Use `!record_game` for matches played outside bot system\n"
                "• For tournaments, use `!match` instead (see `!tournament_help`)"
            ),
            inline=False,
        )

        embed.set_footer(text="Type !tournament_help for tournament commands")

        await ctx.send(embed=embed)

    @commands.command()
    async def record_game(self, ctx):
        """Submit a match report without being matched through LFG"""
        # Create view with both buttons
        view = ReportButtonsSolo(ctx.author.id, ctx.author.global_name, self.bot)

        try:
            await ctx.author.send("Please select match outcome:", view=view)
            await ctx.send("Check your DMs to submit the match report!", ephemeral=True)
        except discord.Forbidden:
            await ctx.send(
                "I couldn't send you a DM. Please enable DMs from server members.",
                ephemeral=True,
            )

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
            cur_matches.execute("DROP TABLE IF EXISTS solo_match_reports")
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

            # Recreate solo_match_reports table
            cur_matches.execute("""CREATE TABLE solo_match_reports
                                   (reporter_id INTEGER,
                                    reporter_name TEXT,
                                    opponent_name TEXT,
                                    is_winner BOOLEAN,
                                    first_player TEXT,
                                    match_time INTEGER,
                                    curiosa_link TEXT,
                                    match_comment TEXT,
                                    report_date DATETIME,
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
                description="All databases have been dropped and recreated:\n• ELO database reset\n• Match records cleared\n• Solo match reports cleared\n• Challenge matches cleared\n\nAll tables are ready to use.",
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


async def setup(bot):
    await bot.add_cog(LFGCog(bot))
