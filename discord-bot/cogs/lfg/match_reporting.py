import discord
from discord.ext import commands
import datetime
import logging

import config
from cogs.lfg.state import pending_match_reports, processed_matches
from cogs.lfg.helpers import scrub_urls, send_milestone_announcement, generate_ladder_challenge_announcement
from utils.database import (
    record_match,
    complete_ladder_challenge,
    delete_ladder_challenge,
    mark_pairing_reported,
    get_pairing_between_players,
    get_active_event,
)
from utils.avatar_elo import avatar_input_error, canonicalize_avatar_name
from repositories.limited_repo import (
    get_limited_pairing_between_players,
    mark_limited_pairing_reported,
)
from services.limited_service import limited_winner_report, get_run_summary
from cogs.lfg.persistent_confirm import create_confirmation_view

logger = logging.getLogger("discord_bot")

LADDER_WINNER_ROLE_ID = 1472382884550803658


def _avatar_specific_event_active(match_type: str = "ranked") -> bool:
    """Return whether this report contributes to an avatar-specific event ladder."""
    if match_type in ("testing", "rumble", "points", "limited"):
        return False
    active_event = get_active_event()
    return bool(active_event and active_event.get("avatar_specific"))


def _canonicalize_reported_avatars(reporter_avatar: str, opponent_avatar: str):
    reporter = canonicalize_avatar_name(reporter_avatar.strip()) if reporter_avatar else None
    opponent = canonicalize_avatar_name(opponent_avatar.strip()) if opponent_avatar else None
    if not reporter or not opponent:
        errors = []
        if not reporter:
            errors.append(avatar_input_error("your avatar", reporter_avatar))
        if not opponent:
            errors.append(
                avatar_input_error("your opponent's avatar", opponent_avatar)
            )
        raise ValueError(" ".join(errors))
    return reporter, opponent


def _confirmation_message(
    reporter_global: str,
    opponent_won: bool,
    winner_global: str,
    loser_global: str,
    winner_avatar: str = None,
    loser_avatar: str = None,
) -> str:
    message = (
        f"**Match Report Confirmation**\n\n"
        f"You **{'WON' if opponent_won else 'LOST'}** against {reporter_global}\n\n"
    )
    if winner_avatar and loser_avatar:
        message += (
            "**Reported avatars**\n"
            f"Winner — {winner_global}: **{winner_avatar}**\n"
            f"Loser — {loser_global}: **{loser_avatar}**\n\n"
            "Confirm only if both the result and avatars are correct. "
            "Otherwise, dispute this report:"
        )
    else:
        message += "Please confirm or dispute this result:"
    return message


async def _fallback_to_backup_channel(bot, user, message, view=None):
    """Send message to backup channel when DM fails."""
    try:
        backup_channel = bot.get_channel(config.DM_BACKUP_CHANNEL_ID)
        if backup_channel:
            await backup_channel.send(
                scrub_urls(f"{user.mention} {message}"),
                view=view,
            )
            logger.info(f"Sent fallback message to backup channel for {user.id}")
            return True
    except Exception as e:
        logger.error(f"Failed to send to backup channel: {e}")
    return False


async def _send_confirmation_to_opponent(
    bot, opponent_user, opponent_id, opponent_global,
    confirm_msg, confirmation_view, reply_interaction, guild_id,
):
    """Send a confirmation view to the opponent via DM, falling back to a channel."""
    logger.info(f"Attempting to send confirmation to opponent {opponent_id} ({opponent_global})")

    # Always try DM first - don't skip based on role
    # (User might have re-enabled DMs since role was added)
    guild = bot.get_guild(guild_id) if guild_id else None
    try:
        logger.info(f"Sending confirmation DM to opponent {opponent_id} ({opponent_global})")
        await opponent_user.send(confirm_msg, view=confirmation_view)
        logger.info(f"✅ Successfully sent confirmation DM to opponent {opponent_id} ({opponent_global})")

        # Remove DM_DISABLED_ROLE if they have it (DMs are working now)
        if guild:
            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
            member = guild.get_member(opponent_id)
            if role and member and role in member.roles:
                await member.remove_roles(role)
                logger.info(f"Removed DM_DISABLED_ROLE from {opponent_id} (DMs working)")

        await reply_interaction.followup.send(
            f"Match report sent to {opponent_global}. Waiting for confirmation...",
            ephemeral=True,
        )
    except discord.Forbidden:
            try:
                if guild:
                    role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                    member = guild.get_member(opponent_id)
                    if role and member:
                        await member.add_roles(role)

                dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    if guild:
                        member = guild.get_member(opponent_id)
                        if member:
                            await dm_channel.set_permissions(
                                member, read_messages=True, send_messages=True
                            )
                    logger.info(f"Sending confirmation to DM-disabled channel for opponent {opponent_id}")
                    await dm_channel.send(
                        scrub_urls(f"{opponent_user.mention} {confirm_msg}"),
                        view=confirmation_view,
                    )
                    logger.info(f"✅ Successfully sent confirmation to channel for opponent {opponent_id}")
                    await reply_interaction.followup.send(
                        "Match report sent. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    # Fallback to backup channel if DM_DISABLED_CHANNEL_ID doesn't exist
                    if await _fallback_to_backup_channel(bot, opponent_user, confirm_msg, confirmation_view):
                        await reply_interaction.followup.send(
                            "Match report sent. Waiting for confirmation...",
                            ephemeral=True,
                        )
                    else:
                        await reply_interaction.followup.send(
                            f"Could not send confirmation to {opponent_global}.",
                            ephemeral=True,
                        )
            except Exception as e:
                logger.error(f"Failed to handle DM failure for opponent: {e}")
                # Last resort: try backup channel
                if await _fallback_to_backup_channel(bot, opponent_user, confirm_msg, confirmation_view):
                    await reply_interaction.followup.send(
                        "Match report sent. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    await reply_interaction.followup.send(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )


async def _apply_ladder_elo(bot, ladder_info, winner_id, winner_global, loser_id, loser_global, match_id, event_active):
    """Complete a ladder challenge: record result, assign role if non-Top16 won, return stakes message.

    ELO has already been calculated and applied atomically by record_match().
    This function handles only the side-effects specific to ladder challenges.
    """
    challenger_id = ladder_info["challenger_id"]

    # Complete the ladder challenge record
    if ladder_info.get("challenge_id"):
        complete_ladder_challenge(
            ladder_info["challenge_id"],
            winner_id,
            match_id,
            ladder_info.get("elo_multiplier_winner", 1.0),
            ladder_info.get("elo_multiplier_loser", 1.0),
        )

    # If non-Top16 player won, assign role and compose stakes message
    stakes_msg = ""
    if winner_id != challenger_id:
        try:
            guild = bot.get_guild(ladder_info.get("guild_id"))
            if guild:
                member = guild.get_member(winner_id)
                role = guild.get_role(LADDER_WINNER_ROLE_ID)
                if member and role:
                    await member.add_roles(role)
                    logger.info(f"Assigned ladder winner role to {winner_id}")
        except Exception as e:
            logger.error(f"Failed to assign ladder winner role: {e}")

        winner_mult = ladder_info.get("elo_multiplier_winner", 1.0)
        if winner_mult != 1.0:
            stakes_msg = "\n**Ladder Bonus:** Winner gained 2x ELO! Top 16 player lost only 0.5x ELO."

    return stakes_msg


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
            winner_went_first = "y" if reporter_went_first else "n"
            loser_went_first = "n" if reporter_went_first else "y"
            winner_deck_url = curiosa_link
            loser_deck_url = None
        else:
            winner_went_first = "n" if reporter_went_first else "y"
            loser_went_first = "y" if reporter_went_first else "n"
            winner_deck_url = None
            loser_deck_url = curiosa_link

        match_id, _, _, _, _, event_active = await record_match(
            reporter_id=interaction_user_id,
            winner_id=self.winner_id,
            winner_global=self.winner_global,
            loser_id=self.loser_id,
            loser_global=self.loser_global,
            first_player=first_player,
            match_time=match_time,
            match_comment=match_comment,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
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


class ReporterDeckURLModal(discord.ui.Modal, title="Enter Your Deck"):
    """Modal for capturing deck URL when reporter didn't provide one at queue join"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/...",
        required=True,
    )

    match_comment = discord.ui.TextInput(
        label="Match Comments",
        placeholder="Any notes about the match? (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    reporter_avatar = discord.ui.TextInput(
        label="Your Avatar",
        placeholder="Enter the Avatar card name you played",
        required=True,
        max_length=100,
    )

    opponent_avatar = discord.ui.TextInput(
        label="Opponent's Avatar",
        placeholder="Enter the Avatar card name they played",
        required=True,
        max_length=100,
    )

    def __init__(
        self, view: "LFGReportButtons", interaction: discord.Interaction, is_win: bool
    ):
        super().__init__()
        self.view = view
        self.original_interaction = interaction
        self.is_win = is_win
        self.avatar_specific = _avatar_specific_event_active(view.match_type)
        if view.reporter_deck_url:
            self.remove_item(self.deck_url)
        if not self.avatar_specific:
            self.remove_item(self.reporter_avatar)
            self.remove_item(self.opponent_avatar)

    async def on_submit(self, interaction: discord.Interaction):
        # Update the reporter's deck URL
        if self.deck_url in self.children:
            self.view.reporter_deck_url = (
                self.deck_url.value.strip() if self.deck_url.value else None
            )
        if self.avatar_specific:
            try:
                reporter_avatar, opponent_avatar = _canonicalize_reported_avatars(
                    self.reporter_avatar.value,
                    self.opponent_avatar.value,
                )
            except ValueError as error:
                await interaction.response.send_message(str(error), ephemeral=True)
                return
            self.view.reporter_avatar = reporter_avatar
            self.view.opponent_avatar = opponent_avatar
        # Store the match comment on the view
        self.view.match_comment = (
            self.match_comment.value.strip() if self.match_comment.value else ""
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

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

        try:
            logger.info(f"Processing win report with deck URL for user {original_interaction.user.id}")

            # Disable buttons immediately to prevent double-clicks
            for item in view.children:
                item.disabled = True
            try:
                await original_interaction.message.edit(view=view)
            except Exception:
                pass

            # Get opponent from view player IDs
            opponent_id = (
                view.player2_id
                if original_interaction.user.id == view.player1_id
                else view.player1_id
            )
            logger.info(f"Opponent ID: {opponent_id}")

            # Soft-validate pairing exists in DB (warn but don't block the report)
            if not view.ladder_info:
                if not view.guild_id:
                    logger.warning(
                        f"guild_id is None during match report for user {original_interaction.user.id} — skipping pairing validation"
                    )
                else:
                    try:
                        if view.match_type == "limited":
                            pairing = get_limited_pairing_between_players(view.guild_id, original_interaction.user.id, opponent_id)
                        else:
                            pairing = get_pairing_between_players(view.guild_id, original_interaction.user.id, opponent_id)
                        if not pairing:
                            logger.warning(
                                f"No active pairing found in guild {view.guild_id} between "
                                f"user {original_interaction.user.id} and opponent {opponent_id} — proceeding anyway"
                            )
                        else:
                            logger.info(
                                f"Validated pairing {pairing['pairing_id']} for match report in guild {view.guild_id}: "
                                f"user {original_interaction.user.id} vs opponent {opponent_id}"
                            )
                    except Exception as pairing_error:
                        logger.error(f"Error checking pairing: {pairing_error}")

            # Fetch opponent to get their global name
            try:
                opponent = await view.bot.fetch_user(opponent_id)
                opponent_global = opponent.global_name or opponent.display_name
            except Exception as e:
                logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
                await interaction.followup.send(
                    "Failed to fetch opponent information.",
                    ephemeral=True,
                )
                return

            # Check if a report is already pending for this match
            if (original_interaction.user.id, opponent_id) in pending_match_reports or (
                opponent_id,
                original_interaction.user.id,
            ) in pending_match_reports:
                await interaction.followup.send(
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
                "guild_id": view.guild_id,
                "ladder_info": view.ladder_info,
                "match_type": view.match_type,
                "match_comment": view.match_comment,
                "winner_avatar": view.reporter_avatar,
                "loser_avatar": view.opponent_avatar,
            }
            logger.info(f"Stored pending report for match between {original_interaction.user.id} and {opponent_id}")

            # Send confirmation to opponent
            try:
                opponent = await view.bot.fetch_user(opponent_id)

                reporter_global_name = original_interaction.user.global_name or original_interaction.user.display_name
                confirmation_view = create_confirmation_view(
                    reporter_id=original_interaction.user.id,
                    reporter_global=reporter_global_name,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=original_interaction.user.id,
                    winner_global=reporter_global_name,
                    loser_id=opponent_id,
                    loser_global=opponent_global,
                    is_winner=False,
                    match_start_time=view.match_start_time,
                    first_player=view.first_player,
                    match_comment=view.match_comment,
                    winner_deck_url=view.reporter_deck_url,
                    loser_deck_url=view.opponent_deck_url,
                    ladder_info=view.ladder_info,
                    match_type=view.match_type,
                    guild_id=view.guild_id,
                    winner_run_id=view.reporter_run_id,  # Reporter won
                    loser_run_id=view.opponent_run_id,
                    winner_avatar=view.reporter_avatar,
                    loser_avatar=view.opponent_avatar,
                )

                confirm_msg = _confirmation_message(
                    reporter_global=reporter_global_name,
                    opponent_won=False,
                    winner_global=reporter_global_name,
                    loser_global=opponent_global,
                    winner_avatar=view.reporter_avatar,
                    loser_avatar=view.opponent_avatar,
                )
                await _send_confirmation_to_opponent(
                    view.bot, opponent, opponent_id, opponent_global,
                    confirm_msg, confirmation_view,
                    interaction, view.guild_id,
                )

                # Remove buttons from original message
                if original_interaction.message:
                    try:
                        await original_interaction.message.edit(view=None)
                    except Exception:
                        pass

            except discord.Forbidden:
                logger.warning(f"Discord.Forbidden when sending confirmation to {opponent_id}, attempted backup channel")
                await interaction.followup.send(
                    f"Attempted to send confirmation to {opponent_global} via backup channel.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Error sending confirmation to opponent: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while sending confirmation to your opponent.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Unexpected error in ReporterDeckURLModal loss report: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An unexpected error occurred while processing your match report. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                logger.error("Failed to send error followup message")

    async def _process_loss_report(self, interaction: discord.Interaction):
        """Process loss report after collecting deck URL"""
        view = self.view
        original_interaction = self.original_interaction

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

        try:
            logger.info(f"Processing loss report with deck URL for user {original_interaction.user.id}")

            # Disable buttons immediately to prevent double-clicks
            for item in view.children:
                item.disabled = True
            try:
                await original_interaction.message.edit(view=view)
            except Exception:
                pass

            # Get opponent from view player IDs
            opponent_id = (
                view.player2_id
                if original_interaction.user.id == view.player1_id
                else view.player1_id
            )
            logger.info(f"Opponent ID: {opponent_id}")

            # Soft-validate pairing exists in DB (warn but don't block the report)
            if not view.ladder_info:
                if not view.guild_id:
                    logger.warning(
                        f"guild_id is None during match report for user {original_interaction.user.id} — skipping pairing validation"
                    )
                else:
                    try:
                        if view.match_type == "limited":
                            pairing = get_limited_pairing_between_players(view.guild_id, original_interaction.user.id, opponent_id)
                        else:
                            pairing = get_pairing_between_players(view.guild_id, original_interaction.user.id, opponent_id)
                        if not pairing:
                            logger.warning(
                                f"No active pairing found in guild {view.guild_id} between "
                                f"user {original_interaction.user.id} and opponent {opponent_id} — proceeding anyway"
                            )
                        else:
                            logger.info(
                                f"Validated pairing {pairing['pairing_id']} for match report in guild {view.guild_id}: "
                                f"user {original_interaction.user.id} vs opponent {opponent_id}"
                            )
                    except Exception as pairing_error:
                        logger.error(f"Error checking pairing: {pairing_error}")

            # Fetch opponent to get their global name
            try:
                opponent = await view.bot.fetch_user(opponent_id)
                opponent_global = opponent.global_name or opponent.display_name
            except Exception as e:
                logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
                await interaction.followup.send(
                    "Failed to fetch opponent information.",
                    ephemeral=True,
                )
                return

            # Check if a report is already pending for this match
            if (original_interaction.user.id, opponent_id) in pending_match_reports or (
                opponent_id,
                original_interaction.user.id,
            ) in pending_match_reports:
                await interaction.followup.send(
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
                "guild_id": view.guild_id,
                "ladder_info": view.ladder_info,
                "match_type": view.match_type,
                "match_comment": view.match_comment,
                "winner_avatar": view.opponent_avatar,
                "loser_avatar": view.reporter_avatar,
            }
            logger.info(f"Stored pending report for match between {original_interaction.user.id} and {opponent_id}")

            # Send confirmation to opponent
            try:
                opponent = await view.bot.fetch_user(opponent_id)

                reporter_global_name = original_interaction.user.global_name or original_interaction.user.display_name
                confirmation_view = create_confirmation_view(
                    reporter_id=original_interaction.user.id,
                    reporter_global=reporter_global_name,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=opponent_id,
                    winner_global=opponent_global,
                    loser_id=original_interaction.user.id,
                    loser_global=reporter_global_name,
                    is_winner=True,
                    match_start_time=view.match_start_time,
                    first_player=view.first_player,
                    match_comment=view.match_comment,
                    winner_deck_url=view.opponent_deck_url,
                    loser_deck_url=view.reporter_deck_url,
                    ladder_info=view.ladder_info,
                    match_type=view.match_type,
                    guild_id=view.guild_id,
                    winner_run_id=view.opponent_run_id,  # Opponent won
                    loser_run_id=view.reporter_run_id,
                    winner_avatar=view.opponent_avatar,
                    loser_avatar=view.reporter_avatar,
                )

                confirm_msg = _confirmation_message(
                    reporter_global=reporter_global_name,
                    opponent_won=True,
                    winner_global=opponent_global,
                    loser_global=reporter_global_name,
                    winner_avatar=view.opponent_avatar,
                    loser_avatar=view.reporter_avatar,
                )
                await _send_confirmation_to_opponent(
                    view.bot, opponent, opponent_id, opponent_global,
                    confirm_msg, confirmation_view,
                    interaction, view.guild_id,
                )

                # Remove buttons from original message
                if original_interaction.message:
                    try:
                        await original_interaction.message.edit(view=None)
                    except Exception:
                        pass

            except discord.Forbidden:
                logger.warning(f"Discord.Forbidden when sending confirmation to {opponent_id}, attempted backup channel")
                await interaction.followup.send(
                    f"Attempted to send confirmation to {opponent_global} via backup channel.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Error sending confirmation to opponent: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while sending confirmation to your opponent.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Unexpected error in ReporterDeckURLModal loss report: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An unexpected error occurred while processing your match report. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                logger.error("Failed to send error followup message")


class MatchTypeSelectionView(discord.ui.View):
    """View that asks the reporter to choose Ranked or Casual before match reporting."""

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
        guild_id: int = None,
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
        self.guild_id = guild_id

    @discord.ui.button(
        label="⚔️ Ranked (ELO Tracked)",
        style=discord.ButtonStyle.success,
        custom_id="match_type_ranked",
    )
    async def ranked_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._continue_with_match_type(interaction, "ranked")

    @discord.ui.button(
        label="⭐ Casual (No ELO)",
        style=discord.ButtonStyle.primary,
        custom_id="match_type_casual",
    )
    async def casual_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._continue_with_match_type(interaction, "testing")

    async def _continue_with_match_type(
        self, interaction: discord.Interaction, match_type: str
    ):
        """Delete this message and show the 'Did you go first?' view."""
        # Defer FIRST to lock in the interaction before any message operations
        await interaction.response.defer()

        # Delete the match type selection message
        try:
            await interaction.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete match type selection message: {e}")

        # Create "Did you go first?" view with the selected match type
        went_first_view = WentFirstView(
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
            opponent_user=self.opponent_user,
            reporter_deck_text=self.reporter_deck_text,
            guild_id=self.guild_id,
            match_type=match_type,
        )

        # Build match type label for message
        match_type_emoji = "⚔️" if match_type == "ranked" else "⭐"
        match_type_label = "Ranked" if match_type == "ranked" else "Casual"

        # Send the "Did you go first?" question via followup (since we deferred)
        try:
            await interaction.followup.send(
                f"{match_type_emoji} **{match_type_label} Match** - You've been matched with {self.opponent_user.mention} (**{self.player2_global}**)!{self.reporter_deck_text}\n\n**Did you go first?**",
                view=went_first_view,
            )
        except discord.NotFound as e:
            # Interaction expired (10062) - fall back to DM-disabled channel
            logger.warning(f"Interaction expired when sending went first view: {e}")
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                try:
                    # Grant user permissions to see/use the channel
                    if self.guild_id:
                        guild = self.bot.get_guild(self.guild_id)
                        if guild:
                            member = guild.get_member(interaction.user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )

                    await dm_channel.send(
                        f"{interaction.user.mention} {match_type_emoji} **{match_type_label} Match** - You've been matched with {self.opponent_user.mention} (**{self.player2_global}**)!{self.reporter_deck_text}\n\n**Did you go first?**",
                        view=went_first_view,
                    )
                except Exception as channel_error:
                    logger.error(f"Failed to send went first view to DM-disabled channel: {channel_error}")
        except Exception as e:
            logger.error(f"Error sending went first view after match type selection: {e}")
            # Try to notify user via DM-disabled channel instead of followup
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                try:
                    await dm_channel.send(
                        f"{interaction.user.mention} An error occurred setting up your match. Please try again using `!lfg`.",
                    )
                except Exception:
                    pass


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
        guild_id: int = None,
        ladder_info: dict = None,
        match_type: str = "ranked",
        reporter_run_id: int = None,
        opponent_run_id: int = None,
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
        self.guild_id = guild_id
        self.ladder_info = ladder_info
        self.match_type = match_type
        self.reporter_run_id = reporter_run_id
        self.opponent_run_id = opponent_run_id

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
        # Defer FIRST to lock in the interaction before any message operations
        await interaction.response.defer()

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
            guild_id=self.guild_id,
            ladder_info=self.ladder_info,
            match_type=self.match_type,
            reporter_run_id=self.reporter_run_id,
            opponent_run_id=self.opponent_run_id,
        )

        # Build match type label for message
        if self.match_type == "limited":
            match_type_emoji = "🎲"
            match_type_label = "Limited"
        elif self.match_type == "ranked":
            match_type_emoji = "⚔️"
            match_type_label = "Ranked"
        else:
            match_type_emoji = "⭐"
            match_type_label = "Casual"

        # Send the report buttons via followup (since we deferred)
        try:
            await interaction.followup.send(
                f"{match_type_emoji} **{match_type_label} Match Found!** You've been matched with {self.opponent_user.mention} (**{self.player2_global}**)!{self.reporter_deck_text}\n\nReport the match result below:",
                view=view_reporter,
            )
        except discord.NotFound as e:
            # Interaction expired (10062) - fall back to DM-disabled channel
            logger.warning(f"Interaction expired when sending report buttons: {e}")
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                try:
                    # Grant user permissions to see/use the channel
                    if self.guild_id:
                        guild = self.bot.get_guild(self.guild_id)
                        if guild:
                            member = guild.get_member(interaction.user.id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )

                    await dm_channel.send(
                        f"{interaction.user.mention} {match_type_emoji} **{match_type_label} Match Found!** You've been matched with {self.opponent_user.mention} (**{self.player2_global}**)!{self.reporter_deck_text}\n\nReport the match result below:",
                        view=view_reporter,
                    )
                except Exception as channel_error:
                    logger.error(f"Failed to send report buttons to DM-disabled channel: {channel_error}")
        except Exception as e:
            logger.error(f"Error sending report buttons after went first: {e}")
            # Try to notify user via DM-disabled channel instead of followup
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                try:
                    await dm_channel.send(
                        f"{interaction.user.mention} An error occurred setting up your match. Please try again using `!lfg`.",
                    )
                except Exception:
                    pass


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
        guild_id: int = None,
        ladder_info: dict = None,
        match_type: str = "ranked",
        reporter_run_id: int = None,
        opponent_run_id: int = None,
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
        self.guild_id = guild_id
        self.ladder_info = ladder_info
        self.match_type = match_type
        self.reporter_run_id = reporter_run_id
        self.opponent_run_id = opponent_run_id
        # Track when the match started for automatic match time calculation
        self.match_start_time = match_start_time or datetime.datetime.now()
        self.match_comment = ""
        self.reporter_avatar = None
        self.opponent_avatar = None

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if reporter needs to provide a deck URL (skip for testing matches)
        if (
            not self.reporter_deck_url
            and self.match_type not in ("testing", "rumble")
        ) or _avatar_specific_event_active(self.match_type):
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=True)
            await interaction.response.send_modal(modal)
            return

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

        try:
            logger.info(f"Processing 'I Won' button for user {interaction.user.id}")

            # Disable buttons immediately to prevent double-clicks
            for item in self.children:
                item.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass

            # Get opponent from view player IDs
            opponent_id = (
                self.player2_id
                if interaction.user.id == self.player1_id
                else self.player1_id
            )
            logger.info(f"Opponent ID: {opponent_id}")

            # Soft-validate pairing exists in DB (warn but don't block the report)
            if not self.ladder_info:
                if not self.guild_id:
                    logger.warning(
                        f"guild_id is None during match report for user {interaction.user.id} — skipping pairing validation"
                    )
                else:
                    try:
                        if self.match_type == "limited":
                            pairing = get_limited_pairing_between_players(self.guild_id, interaction.user.id, opponent_id)
                        else:
                            pairing = get_pairing_between_players(self.guild_id, interaction.user.id, opponent_id)
                        if not pairing:
                            logger.warning(
                                f"No active pairing found in guild {self.guild_id} between "
                                f"user {interaction.user.id} and opponent {opponent_id} — proceeding anyway"
                            )
                        else:
                            logger.info(
                                f"Validated pairing {pairing['pairing_id']} for match report in guild {self.guild_id}: "
                                f"user {interaction.user.id} vs opponent {opponent_id}"
                            )
                    except Exception as pairing_error:
                        logger.error(f"Error checking pairing: {pairing_error}")

            # Fetch opponent to get their global name
            try:
                opponent = await self.bot.fetch_user(opponent_id)
                opponent_global = opponent.global_name or opponent.display_name
            except Exception as e:
                logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
                await interaction.followup.send(
                    "Failed to fetch opponent information.",
                    ephemeral=True,
                )
                return

            # Check if a report is already pending for this match
            if (interaction.user.id, opponent_id) in pending_match_reports or (
                opponent_id,
                interaction.user.id,
            ) in pending_match_reports:
                await interaction.followup.send(
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
                "opponent_message": None,
                "match_start_time": self.match_start_time,
                "reporter_deck_url": self.reporter_deck_url,
                "opponent_deck_url": self.opponent_deck_url,
                "first_player": self.first_player,
                "guild_id": self.guild_id,
                "ladder_info": self.ladder_info,
                "match_type": self.match_type,
                "match_comment": self.match_comment,
                "winner_avatar": self.reporter_avatar,
                "loser_avatar": self.opponent_avatar,
            }
            logger.info(f"Stored pending report for match between {interaction.user.id} and {opponent_id}")

            # Send confirmation to opponent
            try:
                opponent = await self.bot.fetch_user(opponent_id)

                # Reporter won, so reporter's deck is winner's deck, opponent's deck is loser's deck
                reporter_global_name = interaction.user.global_name or interaction.user.display_name
                confirmation_view = create_confirmation_view(
                    reporter_id=interaction.user.id,
                    reporter_global=reporter_global_name,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=interaction.user.id,
                    winner_global=reporter_global_name,
                    loser_id=opponent_id,
                    loser_global=opponent_global,
                    is_winner=False,  # For opponent, they lost
                    match_start_time=self.match_start_time,
                    first_player=self.first_player,
                    match_comment=self.match_comment,
                    winner_deck_url=self.reporter_deck_url,  # Reporter won, so their deck is winner's
                    loser_deck_url=self.opponent_deck_url,  # Opponent lost, so their deck is loser's
                    ladder_info=self.ladder_info,
                    match_type=self.match_type,
                    guild_id=self.guild_id,
                    winner_run_id=self.reporter_run_id,  # Reporter won
                    loser_run_id=self.opponent_run_id,
                    winner_avatar=self.reporter_avatar,
                    loser_avatar=self.opponent_avatar,
                )

                confirm_msg = _confirmation_message(
                    reporter_global=reporter_global_name,
                    opponent_won=False,
                    winner_global=reporter_global_name,
                    loser_global=opponent_global,
                    winner_avatar=self.reporter_avatar,
                    loser_avatar=self.opponent_avatar,
                )
                await _send_confirmation_to_opponent(
                    self.bot, opponent, opponent_id, opponent_global,
                    confirm_msg, confirmation_view,
                    interaction, self.guild_id,
                )

                # Remove buttons from this user's message
                if interaction.message:
                    try:
                        await interaction.message.edit(view=None)
                    except Exception:
                        pass

            except discord.Forbidden:
                logger.warning(f"Discord.Forbidden when sending confirmation to {opponent_id}, attempted backup channel")
                await interaction.followup.send(
                    f"Attempted to send confirmation to {opponent_global} via backup channel.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Error sending confirmation to opponent: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while sending confirmation to your opponent.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Unexpected error in won_button: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An unexpected error occurred while processing your match report. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                logger.error("Failed to send error followup message")

    @discord.ui.button(
        label="I Lost", style=discord.ButtonStyle.danger, custom_id="lose_button"
    )
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if reporter needs to provide a deck URL (skip for testing matches)
        if (
            not self.reporter_deck_url
            and self.match_type not in ("testing", "rumble")
        ) or _avatar_specific_event_active(self.match_type):
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=False)
            await interaction.response.send_modal(modal)
            return

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

        try:
            logger.info(f"Processing 'I Lost' button for user {interaction.user.id}")

            # Disable buttons immediately to prevent double-clicks
            for item in self.children:
                item.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass

            # Get opponent from view player IDs
            opponent_id = (
                self.player2_id
                if interaction.user.id == self.player1_id
                else self.player1_id
            )
            logger.info(f"Opponent ID: {opponent_id}")

            # Soft-validate pairing exists in DB (warn but don't block the report)
            if not self.ladder_info:
                if not self.guild_id:
                    logger.warning(
                        f"guild_id is None during match report for user {interaction.user.id} — skipping pairing validation"
                    )
                else:
                    try:
                        if self.match_type == "limited":
                            pairing = get_limited_pairing_between_players(self.guild_id, interaction.user.id, opponent_id)
                        else:
                            pairing = get_pairing_between_players(self.guild_id, interaction.user.id, opponent_id)
                        if not pairing:
                            logger.warning(
                                f"No active pairing found in guild {self.guild_id} between "
                                f"user {interaction.user.id} and opponent {opponent_id} — proceeding anyway"
                            )
                        else:
                            logger.info(
                                f"Validated pairing {pairing['pairing_id']} for match report in guild {self.guild_id}: "
                                f"user {interaction.user.id} vs opponent {opponent_id}"
                            )
                    except Exception as pairing_error:
                        logger.error(f"Error checking pairing: {pairing_error}")

            # Fetch opponent to get their global name
            try:
                opponent = await self.bot.fetch_user(opponent_id)
                opponent_global = opponent.global_name or opponent.display_name
            except Exception as e:
                logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
                await interaction.followup.send(
                    "Failed to fetch opponent information.",
                    ephemeral=True,
                )
                return

            # Check if a report is already pending for this match
            if (interaction.user.id, opponent_id) in pending_match_reports or (
                opponent_id,
                interaction.user.id,
            ) in pending_match_reports:
                await interaction.followup.send(
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
                "opponent_message": None,
                "match_start_time": self.match_start_time,
                "reporter_deck_url": self.reporter_deck_url,
                "opponent_deck_url": self.opponent_deck_url,
                "first_player": self.first_player,
                "guild_id": self.guild_id,
                "ladder_info": self.ladder_info,
                "match_type": self.match_type,
                "match_comment": self.match_comment,
                "winner_avatar": self.opponent_avatar,
                "loser_avatar": self.reporter_avatar,
            }
            logger.info(f"Stored pending report for match between {interaction.user.id} and {opponent_id}")

            # Send confirmation to opponent
            try:
                opponent = await self.bot.fetch_user(opponent_id)

                # Reporter lost, so opponent's deck is winner's deck, reporter's deck is loser's deck
                reporter_global_name = interaction.user.global_name or interaction.user.display_name
                confirmation_view = create_confirmation_view(
                    reporter_id=interaction.user.id,
                    reporter_global=reporter_global_name,
                    opponent_id=opponent_id,
                    opponent_global=opponent_global,
                    winner_id=opponent_id,
                    winner_global=opponent_global,
                    loser_id=interaction.user.id,
                    loser_global=reporter_global_name,
                    is_winner=True,  # For opponent, they won
                    match_start_time=self.match_start_time,
                    first_player=self.first_player,
                    match_comment=self.match_comment,
                    winner_deck_url=self.opponent_deck_url,  # Opponent won, so their deck is winner's
                    loser_deck_url=self.reporter_deck_url,  # Reporter lost, so their deck is loser's
                    ladder_info=self.ladder_info,
                    match_type=self.match_type,
                    guild_id=self.guild_id,
                    winner_run_id=self.opponent_run_id,  # Opponent won
                    loser_run_id=self.reporter_run_id,
                    winner_avatar=self.opponent_avatar,
                    loser_avatar=self.reporter_avatar,
                )

                confirm_msg = _confirmation_message(
                    reporter_global=reporter_global_name,
                    opponent_won=True,
                    winner_global=opponent_global,
                    loser_global=reporter_global_name,
                    winner_avatar=self.opponent_avatar,
                    loser_avatar=self.reporter_avatar,
                )
                await _send_confirmation_to_opponent(
                    self.bot, opponent, opponent_id, opponent_global,
                    confirm_msg, confirmation_view,
                    interaction, self.guild_id,
                )

                # Remove buttons from this user's message
                if interaction.message:
                    try:
                        await interaction.message.edit(view=None)
                    except Exception:
                        pass

            except discord.Forbidden:
                logger.warning(f"Discord.Forbidden when sending confirmation to {opponent_id}, attempted backup channel")
                await interaction.followup.send(
                    f"Attempted to send confirmation to {opponent_global} via backup channel.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Error sending confirmation to opponent: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while sending confirmation to your opponent.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Unexpected error in lost_button: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "An unexpected error occurred while processing your match report. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                logger.error("Failed to send error followup message")

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

        # If this was a ladder challenge, delete the DB record so it doesn't count as daily use
        if self.ladder_info and self.ladder_info.get("challenge_id"):
            try:
                delete_ladder_challenge(self.ladder_info["challenge_id"])
                logger.info(
                    f"Deleted ladder challenge {self.ladder_info['challenge_id']} due to match cancellation"
                )
            except Exception as e:
                logger.error(f"Failed to delete ladder challenge on cancel: {e}")

        try:
            await interaction.message.edit(view=None)
        except discord.Forbidden:
            # Can't edit messages in DM channels - silently ignore
            pass
        except discord.NotFound:
            pass


# ──────────────────────────────────────────────
#  New DM Dropdown Report Flow
# ──────────────────────────────────────────────

class MatchCardView(discord.ui.View):
    """Match card view sent via DM when a match is found.
    Uses pairing_id in custom_ids so multiple active matches don't conflict.
    Reporter clicks 'Report Result' to get ephemeral select-menu dropdowns.
    """

    def __init__(
        self,
        bot,
        pairing_id: int,
        player1_id: int,
        player1_global: str,
        player2_id: int,
        player2_global: str,
        player1_deck_url: str = None,
        player2_deck_url: str = None,
        match_start_time=None,
        guild_id: int = None,
        ladder_info: dict = None,
        match_type: str = "ranked",
        player1_run_id: int = 0,
        player2_run_id: int = 0,
        player1_avatar: str = None,
        player2_avatar: str = None,
        event_snapshot: dict = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.pairing_id = pairing_id
        self.player1_id = player1_id
        self.player1_global = player1_global
        self.player2_id = player2_id
        self.player2_global = player2_global
        self.player1_deck_url = player1_deck_url
        self.player2_deck_url = player2_deck_url
        self.match_start_time = match_start_time or datetime.datetime.now()
        self.guild_id = guild_id
        self.ladder_info = ladder_info or {}
        self.match_type = match_type
        self.player1_run_id = player1_run_id
        self.player2_run_id = player2_run_id
        self.player1_avatar = player1_avatar
        self.player2_avatar = player2_avatar
        self.event_snapshot = event_snapshot
        self.avatar_specific = bool(
            event_snapshot and event_snapshot.get("avatar_specific")
        ) or _avatar_specific_event_active(match_type)

        report_btn = discord.ui.Button(
            label="Report Result",
            style=discord.ButtonStyle.primary,
            custom_id=f"match_card_report:{pairing_id}",
        )
        report_btn.callback = self.report_result
        self.add_item(report_btn)

        cancel_btn = discord.ui.Button(
            label="Cancel Match",
            style=discord.ButtonStyle.danger,
            custom_id=f"match_card_cancel:{pairing_id}",
        )
        cancel_btn.callback = self.cancel_match
        self.add_item(cancel_btn)

    async def report_result(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        reporter_id = interaction.user.id
        if reporter_id not in (self.player1_id, self.player2_id):
            await interaction.followup.send("You're not part of this match.", ephemeral=True)
            return

        opponent_id = self.player2_id if reporter_id == self.player1_id else self.player1_id
        if (reporter_id, opponent_id) in pending_match_reports or (opponent_id, reporter_id) in pending_match_reports:
            await interaction.followup.send(
                "A report for this match is already pending confirmation.", ephemeral=True
            )
            return

        reporter_global = interaction.user.global_name or interaction.user.display_name
        opponent_global = self.player2_global if reporter_id == self.player1_id else self.player1_global
        reporter_deck_url = self.player1_deck_url if reporter_id == self.player1_id else self.player2_deck_url
        opponent_deck_url = self.player2_deck_url if reporter_id == self.player1_id else self.player1_deck_url
        reporter_run_id = self.player1_run_id if reporter_id == self.player1_id else self.player2_run_id
        opponent_run_id = self.player2_run_id if reporter_id == self.player1_id else self.player1_run_id
        reporter_avatar = self.player1_avatar if reporter_id == self.player1_id else self.player2_avatar
        opponent_avatar = self.player2_avatar if reporter_id == self.player1_id else self.player1_avatar

        # Disable buttons while reporter fills in the dropdowns
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        # Notify opponent that reporting has started
        try:
            opponent_user = await self.bot.fetch_user(opponent_id)
            try:
                await opponent_user.send(
                    f"**{reporter_global}** is reporting the result for your match. "
                    f"You'll receive a confirmation request shortly."
                )
            except discord.Forbidden:
                pass
        except Exception:
            pass

        view = ReportResultSelectView(
            bot=self.bot,
            reporter_id=reporter_id,
            reporter_global=reporter_global,
            reporter_deck_url=reporter_deck_url,
            opponent_id=opponent_id,
            opponent_global=opponent_global,
            opponent_deck_url=opponent_deck_url,
            player1_id=self.player1_id,
            player1_global=self.player1_global,
            player2_id=self.player2_id,
            player2_global=self.player2_global,
            match_start_time=self.match_start_time,
            guild_id=self.guild_id,
            ladder_info=self.ladder_info,
            match_type=self.match_type,
            reporter_run_id=reporter_run_id,
            opponent_run_id=opponent_run_id,
            reporter_avatar=reporter_avatar,
            opponent_avatar=opponent_avatar,
            event_snapshot=self.event_snapshot,
        )

        msg = "**Report Match Result:**\nSelect who went first, then who won, then click **Submit Report**."
        if not reporter_deck_url and self.match_type not in ("testing", "rumble"):
            msg += "\nYou'll be asked for your deck URL after selecting."

        await interaction.followup.send(msg, view=view, ephemeral=True)

    async def cancel_match(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id not in (self.player1_id, self.player2_id):
            await interaction.followup.send("You're not part of this match.", ephemeral=True)
            return

        canceler_global = interaction.user.global_name or interaction.user.display_name
        other_id = self.player2_id if interaction.user.id == self.player1_id else self.player1_id

        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(content="**Match Cancelled**", view=self)
        except Exception:
            pass

        # If this was a ladder challenge, delete the DB record so it doesn't count as daily use
        if self.ladder_info and self.ladder_info.get("challenge_id"):
            try:
                delete_ladder_challenge(self.ladder_info["challenge_id"])
                logger.info(
                    f"Deleted ladder challenge {self.ladder_info['challenge_id']} due to match cancellation"
                )
            except Exception as e:
                logger.error(f"Failed to delete ladder challenge on cancel: {e}")

        try:
            other_user = await self.bot.fetch_user(other_id)
            try:
                await other_user.send(
                    f"Your match against **{canceler_global}** has been cancelled.\n"
                    f"If this was a mistake, use the **📋 Report Last Match** button in the LFG channel."
                )
            except discord.Forbidden:
                pass
        except Exception:
            pass

        await interaction.followup.send(
            "Match cancelled. If this was a mistake, use **📋 Report Last Match** in the LFG channel.",
            ephemeral=True,
        )


class ReportResultSelectView(discord.ui.View):
    """Ephemeral view with turn-order and winner selects plus submit button."""

    def __init__(
        self,
        bot,
        reporter_id: int,
        reporter_global: str,
        reporter_deck_url: str,
        opponent_id: int,
        opponent_global: str,
        opponent_deck_url: str,
        player1_id: int,
        player1_global: str,
        player2_id: int,
        player2_global: str,
        match_start_time,
        guild_id: int,
        ladder_info: dict = None,
        match_type: str = "ranked",
        reporter_run_id: int = 0,
        opponent_run_id: int = 0,
        reporter_avatar: str = None,
        opponent_avatar: str = None,
        event_snapshot: dict = None,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.reporter_deck_url = reporter_deck_url
        self.opponent_id = opponent_id
        self.opponent_global = opponent_global
        self.opponent_deck_url = opponent_deck_url
        self.player1_id = player1_id
        self.player1_global = player1_global
        self.player2_id = player2_id
        self.player2_global = player2_global
        self.match_start_time = match_start_time
        self.guild_id = guild_id
        self.ladder_info = ladder_info or {}
        self.match_type = match_type
        self.reporter_run_id = reporter_run_id
        self.opponent_run_id = opponent_run_id
        self.selected_winner_id = None
        self.selected_first_id = None
        self._submit_interaction = None
        self.match_comment = ""
        self.reporter_avatar = reporter_avatar
        self.opponent_avatar = opponent_avatar
        self.event_snapshot = event_snapshot
        self.avatar_specific = bool(
            event_snapshot and event_snapshot.get("avatar_specific")
        ) or _avatar_specific_event_active(match_type)

        self.first_select = discord.ui.Select(
            placeholder="Who went first?",
            options=[
                discord.SelectOption(label=player1_global, value=str(player1_id)),
                discord.SelectOption(label=player2_global, value=str(player2_id)),
            ],
        )
        self.first_select.callback = self._on_first_select
        self.add_item(self.first_select)

        self.winner_select = discord.ui.Select(
            placeholder="Who won?",
            options=[
                discord.SelectOption(label=player1_global, value=str(player1_id)),
                discord.SelectOption(label=player2_global, value=str(player2_id)),
            ],
        )
        self.winner_select.callback = self._on_winner_select
        self.add_item(self.winner_select)

        self.submit_button = discord.ui.Button(
            label="Submit Report",
            style=discord.ButtonStyle.success,
            disabled=True,
        )
        self.submit_button.callback = self._on_submit
        self.add_item(self.submit_button)

    def _get_player_label(self, player_id: int | None) -> str | None:
        if player_id == self.player1_id:
            return self.player1_global
        if player_id == self.player2_id:
            return self.player2_global
        return None

    def _sync_controls(self):
        first_label = self._get_player_label(self.selected_first_id)
        winner_label = self._get_player_label(self.selected_winner_id)

        self.first_select.placeholder = (
            f"Went first: {first_label}" if first_label else "Who went first?"
        )
        self.winner_select.placeholder = (
            f"Winner: {winner_label}" if winner_label else "Who won?"
        )
        self.submit_button.disabled = not (
            self.selected_first_id is not None and self.selected_winner_id is not None
        )

    async def _on_winner_select(self, interaction: discord.Interaction):
        self.selected_winner_id = int(self.winner_select.values[0])
        self._sync_controls()
        await interaction.response.edit_message(view=self)

    async def _on_first_select(self, interaction: discord.Interaction):
        self.selected_first_id = int(self.first_select.values[0])
        self._sync_controls()
        await interaction.response.edit_message(view=self)

    async def _on_submit(self, interaction: discord.Interaction):
        if self.selected_winner_id is None or self.selected_first_id is None:
            await interaction.response.send_message(
                "Please select who went first and who won before submitting.",
                ephemeral=True,
            )
            return

        self._submit_interaction = interaction
        if (
            not self.reporter_deck_url
            and self.match_type not in ("testing", "rumble")
        ) or (
            self.avatar_specific
            and (not self.reporter_avatar or not self.opponent_avatar)
        ):
            modal = MatchReportDeckModal(self)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer()
            await self._submit(interaction)

    async def _submit(
        self,
        interaction: discord.Interaction,
        deck_url: str = None,
        match_comment: str = "",
        reporter_avatar: str = None,
        opponent_avatar: str = None,
    ):
        if deck_url:
            self.reporter_deck_url = deck_url
        if match_comment:
            self.match_comment = match_comment
        if self.avatar_specific:
            try:
                self.reporter_avatar, self.opponent_avatar = _canonicalize_reported_avatars(
                    reporter_avatar or self.reporter_avatar,
                    opponent_avatar or self.opponent_avatar,
                )
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return

        winner_id = self.selected_winner_id
        loser_id = self.player2_id if winner_id == self.player1_id else self.player1_id
        winner_global = self.player1_global if winner_id == self.player1_id else self.player2_global
        loser_global = self.player2_global if winner_id == self.player1_id else self.player1_global

        # Slot deck URLs into player1/player2 slots
        if self.reporter_id == self.player1_id:
            p1_deck = self.reporter_deck_url
            p2_deck = self.opponent_deck_url
        else:
            p1_deck = self.opponent_deck_url
            p2_deck = self.reporter_deck_url

        winner_deck_url = p1_deck if winner_id == self.player1_id else p2_deck
        loser_deck_url = p2_deck if winner_id == self.player1_id else p1_deck

        if self.reporter_id == self.player1_id:
            p1_avatar = self.reporter_avatar
            p2_avatar = self.opponent_avatar
        else:
            p1_avatar = self.opponent_avatar
            p2_avatar = self.reporter_avatar

        winner_avatar = p1_avatar if winner_id == self.player1_id else p2_avatar
        loser_avatar = p2_avatar if winner_id == self.player1_id else p1_avatar

        # "y" means the reporter went first (consistent with existing convention)
        first_player = "y" if self.selected_first_id == self.reporter_id else "n"
        is_reporter_winner = (winner_id == self.reporter_id)

        # Duplicate guard
        if (self.reporter_id, self.opponent_id) in pending_match_reports or \
                (self.opponent_id, self.reporter_id) in pending_match_reports:
            await interaction.followup.send(
                "A report for this match is already pending confirmation.", ephemeral=True
            )
            return

        pending_match_reports[(self.reporter_id, self.opponent_id)] = {
            "winner_id": winner_id,
            "winner_global": winner_global,
            "loser_id": loser_id,
            "loser_global": loser_global,
            "reporter_id": self.reporter_id,
            "reporter_global": self.reporter_global,
            "is_winner": is_reporter_winner,
            "opponent_message": None,
            "match_start_time": self.match_start_time,
            "reporter_deck_url": self.reporter_deck_url,
            "opponent_deck_url": self.opponent_deck_url,
            "first_player": first_player,
            "guild_id": self.guild_id,
            "ladder_info": self.ladder_info,
            "match_type": self.match_type,
            "match_comment": self.match_comment,
            "winner_avatar": winner_avatar,
            "loser_avatar": loser_avatar,
            "event_snapshot": self.event_snapshot,
        }

        winner_run_id = self.reporter_run_id if is_reporter_winner else self.opponent_run_id
        loser_run_id = self.opponent_run_id if is_reporter_winner else self.reporter_run_id

        try:
            opponent_user = await self.bot.fetch_user(self.opponent_id)
        except Exception as e:
            logger.error(f"Failed to fetch opponent {self.opponent_id}: {e}")
            pending_match_reports.pop((self.reporter_id, self.opponent_id), None)
            await interaction.followup.send("Failed to fetch opponent information.", ephemeral=True)
            return

        confirmation_view = create_confirmation_view(
            reporter_id=self.reporter_id,
            reporter_global=self.reporter_global,
            opponent_id=self.opponent_id,
            opponent_global=self.opponent_global,
            winner_id=winner_id,
            winner_global=winner_global,
            loser_id=loser_id,
            loser_global=loser_global,
            is_winner=(winner_id == self.opponent_id),
            match_start_time=self.match_start_time,
            first_player=first_player,
            match_comment=self.match_comment,
            winner_deck_url=winner_deck_url,
            loser_deck_url=loser_deck_url,
            ladder_info=self.ladder_info,
            match_type=self.match_type,
            guild_id=self.guild_id,
            winner_run_id=winner_run_id,
            loser_run_id=loser_run_id,
            winner_avatar=winner_avatar,
            loser_avatar=loser_avatar,
            event_snapshot=self.event_snapshot,
        )

        opponent_won = (winner_id == self.opponent_id)
        confirm_msg = _confirmation_message(
            reporter_global=self.reporter_global,
            opponent_won=opponent_won,
            winner_global=winner_global,
            loser_global=loser_global,
            winner_avatar=winner_avatar,
            loser_avatar=loser_avatar,
        )

        await _send_confirmation_to_opponent(
            self.bot, opponent_user, self.opponent_id, self.opponent_global,
            confirm_msg, confirmation_view, interaction, self.guild_id,
        )

        # Replace the ephemeral select form with a confirmation message
        target_interaction = self._submit_interaction or interaction
        try:
            await target_interaction.edit_original_response(
                content="**Result reported!** Waiting for your opponent to confirm.",
                view=None,
            )
        except Exception:
            pass

        self.stop()


class MatchReportDeckModal(discord.ui.Modal, title="Enter Your Deck"):
    """Collects the reporter's deck URL before submitting the match report."""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/...",
        required=True,
    )

    match_comment = discord.ui.TextInput(
        label="Match Comments",
        placeholder="Any notes about the match? (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    reporter_avatar = discord.ui.TextInput(
        label="Your Avatar",
        placeholder="Enter the Avatar card name you played",
        required=True,
        max_length=100,
    )

    opponent_avatar = discord.ui.TextInput(
        label="Opponent's Avatar",
        placeholder="Enter the Avatar card name they played",
        required=True,
        max_length=100,
    )

    def __init__(self, report_view: "ReportResultSelectView"):
        super().__init__()
        self.report_view = report_view
        self.avatar_specific = report_view.avatar_specific
        if report_view.reporter_deck_url:
            self.remove_item(self.deck_url)
        if not self.avatar_specific or (
            report_view.reporter_avatar and report_view.opponent_avatar
        ):
            self.remove_item(self.reporter_avatar)
            self.remove_item(self.opponent_avatar)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        url = None
        if self.deck_url in self.children:
            url = self.deck_url.value.strip() if self.deck_url.value else None
        comment = self.match_comment.value.strip() if self.match_comment.value else ""
        reporter_avatar = None
        opponent_avatar = None
        if self.reporter_avatar in self.children:
            reporter_avatar = self.reporter_avatar.value
            opponent_avatar = self.opponent_avatar.value
        await self.report_view._submit(
            interaction,
            deck_url=url or None,
            match_comment=comment,
            reporter_avatar=reporter_avatar,
            opponent_avatar=opponent_avatar,
        )


# ──────────────────────────────────────────────
#  Limited Report Flow (!limited_report @opponent)
# ──────────────────────────────────────────────

class LimitedReportView(discord.ui.View):
    """DM view sent to the reporter for !limited_report.

    Contains two dropdowns (who went first, who won) and a submit button.
    On submit, sends a confirmation to the opponent.
    """

    def __init__(
        self,
        bot,
        reporter_id: int,
        reporter_global: str,
        opponent_id: int,
        opponent_global: str,
        opponent_user: discord.User,
        guild_id: int,
    ):
        super().__init__(timeout=300)  # 5 minute timeout
        self.bot = bot
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.opponent_id = opponent_id
        self.opponent_global = opponent_global
        self.opponent_user = opponent_user
        self.guild_id = guild_id
        self.match_start_time = datetime.datetime.now()

        # Track selected values across interactions
        self.selected_went_first = None
        self.selected_winner = None

        # Add the select menus with callbacks
        self.went_first_select = discord.ui.Select(
            placeholder="Who went first?",
            options=[
                discord.SelectOption(label=reporter_global, value=str(reporter_id)),
                discord.SelectOption(label=opponent_global, value=str(opponent_id)),
            ],
            row=0,
        )
        self.went_first_select.callback = self._went_first_callback

        self.who_won_select = discord.ui.Select(
            placeholder="Who won?",
            options=[
                discord.SelectOption(label=reporter_global, value=str(reporter_id)),
                discord.SelectOption(label=opponent_global, value=str(opponent_id)),
            ],
            row=1,
        )
        self.who_won_select.callback = self._who_won_callback

        self.add_item(self.went_first_select)
        self.add_item(self.who_won_select)

    async def _went_first_callback(self, interaction: discord.Interaction):
        self.selected_went_first = int(self.went_first_select.values[0])
        await interaction.response.defer()

    async def _who_won_callback(self, interaction: discord.Interaction):
        self.selected_winner = int(self.who_won_select.values[0])
        await interaction.response.defer()

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success, row=2)
    async def submit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Validate selections
        if self.selected_went_first is None:
            await interaction.response.send_message(
                "Please select who went first.", ephemeral=True
            )
            return
        if self.selected_winner is None:
            await interaction.response.send_message(
                "Please select who won.", ephemeral=True
            )
            return

        await interaction.response.defer()

        # Disable all controls
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        went_first_id = self.selected_went_first
        winner_id = self.selected_winner
        loser_id = self.opponent_id if winner_id == self.reporter_id else self.reporter_id
        winner_global = self.reporter_global if winner_id == self.reporter_id else self.opponent_global
        loser_global = self.opponent_global if loser_id == self.opponent_id else self.reporter_global

        # Determine first_player from the reporter's perspective
        first_player = "y" if went_first_id == self.reporter_id else "n"

        # Check for existing pending report
        if (self.reporter_id, self.opponent_id) in pending_match_reports or (
            self.opponent_id, self.reporter_id
        ) in pending_match_reports:
            await interaction.followup.send(
                "A report for this match is already pending confirmation."
            )
            return

        # Store pending report
        pending_match_reports[(self.reporter_id, self.opponent_id)] = {
            "winner_id": winner_id,
            "winner_global": winner_global,
            "loser_id": loser_id,
            "loser_global": loser_global,
            "reporter_id": self.reporter_id,
            "reporter_global": self.reporter_global,
            "is_winner": winner_id == self.reporter_id,
            "opponent_message": None,
            "match_start_time": self.match_start_time,
            "reporter_deck_url": None,
            "opponent_deck_url": None,
            "first_player": first_player,
            "guild_id": self.guild_id,
            "ladder_info": None,
            "match_type": "limited",
        }

        # Determine what the opponent sees
        opponent_is_winner = winner_id == self.opponent_id
        if opponent_is_winner:
            confirm_msg = f"**Limited Match Report Confirmation**\n\nYou **WON** against {self.reporter_global}\n\nPlease confirm or dispute this result:"
        else:
            confirm_msg = f"**Limited Match Report Confirmation**\n\nYou **LOST** against {self.reporter_global}\n\nPlease confirm or dispute this result:"

        confirmation_view = create_confirmation_view(
            reporter_id=self.reporter_id,
            reporter_global=self.reporter_global,
            opponent_id=self.opponent_id,
            opponent_global=self.opponent_global,
            winner_id=winner_id,
            winner_global=winner_global,
            loser_id=loser_id,
            loser_global=loser_global,
            is_winner=opponent_is_winner,
            match_start_time=self.match_start_time,
            first_player=first_player,
            winner_deck_url=None,
            loser_deck_url=None,
            ladder_info=None,
            match_type="limited",
            guild_id=self.guild_id,
            winner_run_id=None,
            loser_run_id=None,
        )

        try:
            await _send_confirmation_to_opponent(
                self.bot, self.opponent_user, self.opponent_id, self.opponent_global,
                confirm_msg, confirmation_view,
                interaction, self.guild_id,
            )
        except Exception as e:
            logger.error(f"Error sending limited confirmation to opponent: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while sending confirmation to your opponent."
            )
            return

        # Update reporter's message
        try:
            await interaction.message.edit(
                content=f"Limited match report sent to **{self.opponent_global}**. Waiting for confirmation...",
                view=None,
            )
        except Exception:
            pass

        self.stop()


