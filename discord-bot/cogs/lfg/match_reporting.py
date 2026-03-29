import discord
from discord.ext import commands
import datetime
import logging

import config
from cogs.lfg.state import pending_match_reports, processed_matches
from cogs.lfg.helpers import scrub_urls, send_milestone_announcement, generate_ladder_challenge_announcement
from utils.database import (
    winner_report,
    losser_report,
    update_elo_db,
    update_elo_db_ladder,
    complete_ladder_challenge,
    mark_pairing_reported,
    get_pairing_between_players,
)
from repositories.limited_repo import (
    get_limited_pairing_between_players,
    mark_limited_pairing_reported,
)
from services.limited_service import limited_winner_report, get_run_summary, forfeit_arena_run

logger = logging.getLogger("discord_bot")

LADDER_WINNER_ROLE_ID = 1472382884550803658


async def _apply_ladder_elo(bot, ladder_info, winner_id, winner_global, loser_id, loser_global, match_id, event_active):
    """Apply ladder challenge ELO modifications, complete challenge, and assign role if non-top-16 won."""
    import sqlite3 as _sqlite3

    challenger_id = ladder_info["challenger_id"]

    # Determine multipliers based on who won
    if winner_id == challenger_id:
        # Top 16 player won - normal ELO for both
        winner_mult = 1.0
        loser_mult = 1.0
    else:
        # Non-Top16 player won - they get boosted, Top16 gets reduced loss
        winner_mult = ladder_info["elo_multiplier_winner"]
        loser_mult = ladder_info["elo_multiplier_loser"]

    # Adjust winner ELO if multiplier != 1.0
    # winner_report already applied a normal ELO update for the winner
    if winner_mult != 1.0 and event_active:
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
                (extra_change, extra_change, winner_id),
            )
            cur_fix.commit()
            conn_fix.close()
            logger.info(
                f"Ladder bonus: Winner {winner_id} gets extra {extra_change:+d} ELO (mult={winner_mult})"
            )

    # Update loser ELO with multiplier
    if loser_mult != 1.0:
        update_elo_db_ladder(
            loser_id, loser_global, False, winner_id, elo_multiplier=loser_mult
        )
    else:
        update_elo_db(loser_id, loser_global, False, winner_id)

    # Complete the ladder challenge record
    if ladder_info.get("challenge_id"):
        complete_ladder_challenge(ladder_info["challenge_id"], winner_id, match_id)

    # If non-top-16 player won, assign role
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
        ladder_info: dict = None,
        match_type: str = "ranked",
        winner_run_id: int = None,
        loser_run_id: int = None,
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
        self.ladder_info = ladder_info
        self.match_type = match_type
        self.winner_run_id = winner_run_id
        self.loser_run_id = loser_run_id

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
        if not confirmer_deck_url and self.match_type != "testing":
            # Show modal to collect deck URL before proceeding (skip for testing matches)
            modal = ConfirmerDeckURLModal(self, interaction)
            await interaction.response.send_modal(modal)
            return

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer()

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
                await interaction.followup.send(
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

        # Submit match report - branch based on match type
        winner_run_complete = False
        loser_run_complete = False
        stakes_msg = ""
        elo_msg = ""

        if self.match_type == "limited":
            # Limited match: use separate limited tables and ELO
            match_id, winner_run_complete, loser_run_complete = limited_winner_report(
                reporter_id=self.reporter_id,
                winner_id=self.winner_id,
                winner_display_name=self.winner_global,
                loser_id=self.loser_id,
                loser_display_name=self.loser_global,
                first_player=self.first_player,
                match_time=match_time,
                curiosa_url_winner=winner_deck,
                curiosa_url_loser=loser_deck,
                match_comment=combined_comment,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
                winner_run_id=self.winner_run_id,
                loser_run_id=self.loser_run_id,
            )
            elo_msg = " *(🎲 Limited match - Limited ELO updated)*"
        else:
            # Standard match: use existing report flow
            match_id, _, _, event_active = await winner_report(
                self.reporter_id,
                self.winner_id,
                self.winner_global,
                True,
                self.loser_id,
                self.loser_global,
                self.first_player,
                match_time,
                winner_deck,
                combined_comment,
                self.winner_id,
                self.winner_global,
                winner_deck_url=self.winner_deck_url,
                loser_deck_url=self.loser_deck_url,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
                match_type=self.match_type,
            )

            # Update ELO for the loser (with ladder multipliers if applicable)
            if self.match_type == "testing":
                pass  # No ELO updates for testing matches
            elif self.ladder_info:
                stakes_msg = await _apply_ladder_elo(
                    self.bot, self.ladder_info,
                    self.winner_id, self.winner_global,
                    self.loser_id, self.loser_global,
                    match_id, event_active,
                )
            else:
                update_elo_db(self.loser_id, self.loser_global, False, self.winner_id)

            if self.match_type == "testing":
                elo_msg = " *(⭐ Casual match - ELO not affected)*"
            elif not event_active:
                elo_msg = " *(No active event - ELO not affected)*"

        # Remove the confirmation message
        await interaction.message.edit(
            content=f"Match confirmed! **Match ID: #{match_id}** - {self.winner_global} won against {self.loser_global}.{elo_msg}{stakes_msg}",
            view=None,
        )

        # Send confirmation to confirming user
        await interaction.followup.send(
            f"Match report confirmed and submitted! **Match ID: #{match_id}**\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}{elo_msg}{stakes_msg}",
            ephemeral=True,
        )

        # Notify the reporter
        try:
            reporter = await self.bot.fetch_user(self.reporter_id)
            await reporter.send(
                f"{self.opponent_global} has confirmed your match report! Match has been recorded.{stakes_msg}"
            )
        except discord.Forbidden:
            # If DM fails, send to match-report channel
            match_report_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    scrub_urls(
                        f"{reporter.mention} {self.opponent_global} has confirmed your match report! Match has been recorded.{stakes_msg}"
                    )
                )
        except Exception:
            pass

        # Get guild_id from pending report before removing
        pending_report = pending_match_reports.get((self.reporter_id, self.opponent_id), {})
        guild_id = pending_report.get("guild_id")

        # Remove from pending
        pending_match_reports.pop((self.reporter_id, self.opponent_id), None)

        # Mark pairing as reported in database
        if self.match_type == "limited":
            if guild_id:
                mark_limited_pairing_reported(guild_id, self.winner_id, self.loser_id)
        elif guild_id and not self.ladder_info:
            mark_pairing_reported(guild_id, self.winner_id, self.loser_id)

        # T022: Send run completion DMs for limited matches
        if self.match_type == "limited":
            await self._send_limited_run_status(winner_run_complete, loser_run_complete)

        # Update leaderboard in designated channel
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

        # Announce ladder challenge result in LFG channel
        if self.ladder_info and lfg_cog:
            lfg_channel = self.bot.get_channel(lfg_cog.lfg_channel_id)
            if lfg_channel:
                # Determine if the underdog won and get stakes info
                challenger_id = self.ladder_info.get("challenger_id")
                underdog_won = self.winner_id != challenger_id
                winner_mult = self.ladder_info.get("elo_multiplier_winner", 1.0)
                loser_mult = self.ladder_info.get("elo_multiplier_loser", 1.0)
                stakes_text = f"{winner_mult}x/{loser_mult}x" if winner_mult != 1.0 or loser_mult != 1.0 else "Normal"

                # Generate stylized announcement using ChatGPT
                announcement = generate_ladder_challenge_announcement(
                    underdog_won=underdog_won,
                    winner_name=self.winner_global,
                    loser_name=self.loser_global,
                    stakes_multiplier=stakes_text
                )

                # Replace placeholders with actual mentions
                announcement = announcement.replace("WINNER", f"<@{self.winner_id}>")
                announcement = announcement.replace("LOSER", f"<@{self.loser_id}>")

                await lfg_channel.send(announcement + f" Top 16: use `!issue_challenge` for special stakes!")

        # Check for milestone and send announcement if needed
        await send_milestone_announcement(
            self.bot, self.winner_id, self.loser_id, match_id
        )

    async def _send_limited_run_status(self, winner_run_complete: bool, loser_run_complete: bool):
        """Send run status DMs to both players after a limited match."""
        for player_id, run_id, run_complete in [
            (self.winner_id, self.winner_run_id, winner_run_complete),
            (self.loser_id, self.loser_run_id, loser_run_complete),
        ]:
            if not run_id:
                continue
            try:
                user = await self.bot.fetch_user(player_id)
                summary = get_run_summary(run_id)
                if run_complete:
                    await user.send(f"🏁 **Arena Run Complete!**\n\n{summary}")
                else:
                    # Active run - show Continue/Forfeit buttons
                    view = RunStatusView(player_id, run_id, self.bot)
                    await user.send(
                        f"🎲 **Limited Match Recorded**\n\n{summary}\n\nWhat would you like to do?",
                        view=view,
                    )
            except discord.Forbidden:
                logger.warning("Could not DM limited run status to user %s", player_id)
            except Exception as e:
                logger.error("Error sending limited run status to %s: %s", player_id, e)

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
            match_report_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/...",
        required=True,
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

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

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

        # Soft-validate pairing exists in DB (warn but don't block the report)
        if not view.ladder_info:
            if not view.guild_id:
                logger.warning(
                    f"guild_id is None during match report for user {original_interaction.user.id} — skipping pairing validation"
                )
            else:
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
                ladder_info=view.ladder_info,
                match_type=view.match_type,
                winner_run_id=view.reporter_run_id,  # Reporter won
                loser_run_id=view.opponent_run_id,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = view.bot.get_guild(view.guild_id) if view.guild_id else None
            if guild:
                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            if opponent_has_dm_issue:
                dm_channel = view.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **LOST** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
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

                        dm_channel = view.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
                            await interaction.followup.send(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        await interaction.followup.send(
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
            await interaction.followup.send(
                f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in ReporterDeckURLModal win report: {e}")
            await interaction.followup.send(
                "An error occurred while processing your match report.",
                ephemeral=True,
            )

    async def _process_loss_report(self, interaction: discord.Interaction):
        """Process loss report after collecting deck URL"""
        view = self.view
        original_interaction = self.original_interaction

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

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

        # Soft-validate pairing exists in DB (warn but don't block the report)
        if not view.ladder_info:
            if not view.guild_id:
                logger.warning(
                    f"guild_id is None during match report for user {original_interaction.user.id} — skipping pairing validation"
                )
            else:
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
                ladder_info=view.ladder_info,
                match_type=view.match_type,
                winner_run_id=view.opponent_run_id,  # Opponent won
                loser_run_id=view.reporter_run_id,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = view.bot.get_guild(view.guild_id) if view.guild_id else None
            if guild:
                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            if opponent_has_dm_issue:
                dm_channel = view.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
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

                        dm_channel = view.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
                        if dm_channel:
                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {original_interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.followup.send(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
                        await interaction.followup.send(
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
            await interaction.followup.send(
                f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in ReporterDeckURLModal loss report: {e}")
            await interaction.followup.send(
                "An error occurred while processing your match report.",
                ephemeral=True,
            )


class ConfirmerDeckURLModal(discord.ui.Modal, title="Enter Your Deck"):
    """Modal for capturing deck URL when confirmer didn't provide one at queue join"""

    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="https://curiosa.io/decks/...",
        required=True,
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

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer()

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
                await interaction.followup.send(
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

        # Submit match report - branch based on match type
        winner_run_complete = False
        loser_run_complete = False
        stakes_msg = ""
        elo_msg = ""

        if view.match_type == "limited":
            match_id, winner_run_complete, loser_run_complete = limited_winner_report(
                reporter_id=view.reporter_id,
                winner_id=view.winner_id,
                winner_display_name=view.winner_global,
                loser_id=view.loser_id,
                loser_display_name=view.loser_global,
                first_player=view.first_player,
                match_time=match_time,
                curiosa_url_winner=winner_deck,
                curiosa_url_loser=loser_deck,
                match_comment=combined_comment,
                winner_went_first=winner_went_first,
                loser_went_first=loser_went_first,
                winner_run_id=view.winner_run_id,
                loser_run_id=view.loser_run_id,
            )
            elo_msg = " *(🎲 Limited match - Limited ELO updated)*"
        else:
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
                match_type=view.match_type,
            )

            if view.match_type == "testing":
                pass
            elif view.ladder_info:
                stakes_msg = await _apply_ladder_elo(
                    view.bot, view.ladder_info,
                    view.winner_id, view.winner_global,
                    view.loser_id, view.loser_global,
                    match_id, event_active,
                )
            else:
                update_elo_db(view.loser_id, view.loser_global, False, view.winner_id)

            if view.match_type == "testing":
                elo_msg = " *(⭐ Casual match - ELO not affected)*"
            elif not event_active:
                elo_msg = " *(No active event - ELO not affected)*"

        # Update the confirmation message
        await original_interaction.message.edit(
            content=f"Match confirmed! **Match ID: #{match_id}** - {view.winner_global} won against {view.loser_global}.{elo_msg}{stakes_msg}",
            view=None,
        )

        # Send confirmation to confirming user
        await interaction.followup.send(
            f"Match report confirmed and submitted! **Match ID: #{match_id}**\n**Winner:** {view.winner_global}\n**Loser:** {view.loser_global}{elo_msg}{stakes_msg}",
            ephemeral=True,
        )

        # Notify the reporter
        try:
            reporter = await view.bot.fetch_user(view.reporter_id)
            await reporter.send(
                f"{view.opponent_global} has confirmed your match report! Match has been recorded.{stakes_msg}"
            )
        except discord.Forbidden:
            match_report_channel = view.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if match_report_channel:
                await match_report_channel.send(
                    scrub_urls(
                        f"<@{view.reporter_id}> {view.opponent_global} has confirmed your match report! Match has been recorded.{stakes_msg}"
                    )
                )
        except Exception:
            pass

        # Get guild_id from pending report before removing
        pending_report = pending_match_reports.get((view.reporter_id, view.opponent_id), {})
        guild_id = pending_report.get("guild_id")

        # Remove from pending
        pending_match_reports.pop((view.reporter_id, view.opponent_id), None)

        # Mark pairing as reported
        if view.match_type == "limited":
            if guild_id:
                mark_limited_pairing_reported(guild_id, view.winner_id, view.loser_id)
        elif guild_id and not view.ladder_info:
            mark_pairing_reported(guild_id, view.winner_id, view.loser_id)

        # Send run status DMs for limited matches
        if view.match_type == "limited":
            await view._send_limited_run_status(winner_run_complete, loser_run_complete)

        # Update leaderboard
        lfg_cog = view.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.update_leaderboard()

        # Announce ladder challenge result in LFG channel
        if view.ladder_info and lfg_cog:
            lfg_channel = view.bot.get_channel(lfg_cog.lfg_channel_id)
            if lfg_channel:
                # Determine if the underdog won and get stakes info
                challenger_id = view.ladder_info.get("challenger_id")
                underdog_won = view.winner_id != challenger_id
                winner_mult = view.ladder_info.get("elo_multiplier_winner", 1.0)
                loser_mult = view.ladder_info.get("elo_multiplier_loser", 1.0)
                stakes_text = f"{winner_mult}x/{loser_mult}x" if winner_mult != 1.0 or loser_mult != 1.0 else "Normal"

                # Generate stylized announcement using ChatGPT
                announcement = generate_ladder_challenge_announcement(
                    underdog_won=underdog_won,
                    winner_name=view.winner_global,
                    loser_name=view.loser_global,
                    stakes_multiplier=stakes_text
                )

                # Replace placeholders with actual mentions
                announcement = announcement.replace("WINNER", f"<@{view.winner_id}>")
                announcement = announcement.replace("LOSER", f"<@{view.loser_id}>")

                await lfg_channel.send(announcement + f" Top 16: use `!issue_challenge` for special stakes!")

        # Check for milestone
        await send_milestone_announcement(
            view.bot, view.winner_id, view.loser_id, match_id
        )


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
        except Exception as e:
            logger.error(f"Error sending went first view after match type selection: {e}")
            try:
                await interaction.followup.send(
                    "An error occurred. Please try again.",
                    ephemeral=True,
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
        except Exception as e:
            logger.error(f"Error sending report buttons after went first: {e}")
            try:
                await interaction.followup.send(
                    "An error occurred. Please try again.",
                    ephemeral=True,
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

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if reporter needs to provide a deck URL (skip for testing matches)
        if not self.reporter_deck_url and self.match_type != "testing":
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=True)
            await interaction.response.send_modal(modal)
            return

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

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

        # Soft-validate pairing exists in DB (warn but don't block the report)
        if not self.ladder_info:
            if not self.guild_id:
                logger.warning(
                    f"guild_id is None during match report for user {interaction.user.id} — skipping pairing validation"
                )
            else:
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
                ladder_info=self.ladder_info,
                match_type=self.match_type,
                winner_run_id=self.reporter_run_id,  # Reporter won
                loser_run_id=self.opponent_run_id,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = interaction.guild
            if guild:
                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            # Try to send via DM first (unless they have the DM-disabled role)
            if opponent_has_dm_issue:
                # Send to designated channel instead
                dm_channel = interaction.client.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **LOST** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                    logger.info(
                        f"Posted confirmation in DM-disabled channel for {opponent_global}"
                    )
                else:
                    await interaction.followup.send(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **LOST** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )

                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    # DM failed - add role, grant channel access, and post in designated channel
                    try:
                        if guild:
                            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)
                                logger.info(
                                    f"Added DM-disabled role to {opponent_global}"
                                )

                        dm_channel = interaction.client.get_channel(
                            config.DM_DISABLED_CHANNEL_ID
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
                            await interaction.followup.send(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
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
            await interaction.followup.send(
                f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in won_button: {e}")
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
        # Check if reporter needs to provide a deck URL (skip for testing matches)
        if not self.reporter_deck_url and self.match_type != "testing":
            # Show modal to collect deck URL before proceeding
            modal = ReporterDeckURLModal(self, interaction, is_win=False)
            await interaction.response.send_modal(modal)
            return

        # Acknowledge interaction immediately to prevent 3-second timeout
        await interaction.response.defer(ephemeral=True)

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

        # Soft-validate pairing exists in DB (warn but don't block the report)
        if not self.ladder_info:
            if not self.guild_id:
                logger.warning(
                    f"guild_id is None during match report for user {interaction.user.id} — skipping pairing validation"
                )
            else:
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
                ladder_info=self.ladder_info,
                match_type=self.match_type,
                winner_run_id=self.opponent_run_id,  # Opponent won
                loser_run_id=self.reporter_run_id,
            )

            # Check if opponent has DM-disabled role
            opponent_has_dm_issue = False
            guild = interaction.guild
            if guild:
                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                member = guild.get_member(opponent_id)
                if role and member and role in member.roles:
                    opponent_has_dm_issue = True

            # Try to send via DM first (unless they have the DM-disabled role)
            if opponent_has_dm_issue:
                # Send to designated channel instead
                dm_channel = interaction.client.get_channel(config.DM_DISABLED_CHANNEL_ID)
                if dm_channel:
                    await dm_channel.send(
                        scrub_urls(
                            f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                        ),
                        view=confirmation_view,
                    )
                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                    logger.info(
                        f"Posted confirmation in DM-disabled channel for {opponent_global}"
                    )
                else:
                    await interaction.followup.send(
                        f"Could not send confirmation to {opponent_global}.",
                        ephemeral=True,
                    )
            else:
                try:
                    await opponent.send(
                        f"**Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:",
                        view=confirmation_view,
                    )

                    await interaction.followup.send(
                        f"Match report sent to {opponent_global}. Waiting for confirmation...",
                        ephemeral=True,
                    )
                except discord.Forbidden:
                    # DM failed - add role and post in designated channel
                    try:
                        if guild:
                            role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                            member = guild.get_member(opponent_id)
                            if role and member:
                                await member.add_roles(role)
                                logger.info(
                                    f"Added DM-disabled role to {opponent_global}"
                                )

                        dm_channel = interaction.client.get_channel(
                            config.DM_DISABLED_CHANNEL_ID
                        )
                        if dm_channel:
                            await dm_channel.send(
                                scrub_urls(
                                    f"{opponent.mention} **Match Report Confirmation**\n\nYou **WON** against {interaction.user.global_name}\n\nPlease confirm or dispute this result:"
                                ),
                                view=confirmation_view,
                            )
                            await interaction.followup.send(
                                "Match report sent. Waiting for confirmation...",
                                ephemeral=True,
                            )
                            logger.info(
                                f"Posted confirmation in DM-disabled channel for {opponent_global}"
                            )
                        else:
                            await interaction.followup.send(
                                f"Could not send confirmation to {opponent_global}.",
                                ephemeral=True,
                            )
                    except Exception as e:
                        logger.error(f"Failed to handle DM failure for opponent: {e}")
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
            await interaction.followup.send(
                f"Could not send confirmation to {opponent_global}. They might have DMs disabled.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Error in lost_button: {e}")
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
        try:
            await interaction.message.edit(view=None)
        except discord.Forbidden:
            # Can't edit messages in DM channels - silently ignore
            pass
        except discord.NotFound:
            pass


class RunStatusView(discord.ui.View):
    """Post-match DM view with Continue/Forfeit buttons for active limited arena runs."""

    def __init__(self, user_id: int, run_id: int, bot):
        super().__init__(timeout=3600)  # 60 minute timeout
        self.user_id = user_id
        self.run_id = run_id
        self.bot = bot

    @discord.ui.button(
        label="Continue Run",
        style=discord.ButtonStyle.success,
        custom_id="limited_continue_run",
    )
    async def continue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your run.", ephemeral=True)
            return

        # Disable buttons
        for item in self.children:
            item.disabled = True

        summary = get_run_summary(self.run_id)
        await interaction.response.edit_message(
            content=f"🎲 **Current Run Status**\n\n{summary}",
            view=self,
        )

    @discord.ui.button(
        label="Forfeit Run",
        style=discord.ButtonStyle.danger,
        custom_id="limited_forfeit_run",
    )
    async def forfeit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your run.", ephemeral=True)
            return

        # Disable buttons
        for item in self.children:
            item.disabled = True

        try:
            forfeit_summary = forfeit_arena_run(self.user_id)
            await interaction.response.edit_message(
                content=f"💀 **Arena Run Forfeited**\n\n{forfeit_summary}",
                view=self,
            )
        except ValueError as e:
            await interaction.response.edit_message(
                content=f"Could not forfeit: {e}",
                view=self,
            )
