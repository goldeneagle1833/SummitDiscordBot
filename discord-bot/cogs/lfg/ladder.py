import discord
from discord.ext import commands
import datetime
import logging
import asyncio
import random
import sqlite3

import config
from cogs.lfg.state import (
    active_ladder_challenges,
    ladder_challenge_lock,
    LADDER_CHALLENGE_MAX_JOINERS,
    LADDER_CHALLENGE_TIMEOUT_SECONDS,
    pending_match_reports,
    processed_matches,
)
from cogs.lfg.helpers import scrub_urls, send_milestone_announcement
from cogs.lfg.match_reporting import LFGReportButtons
from utils.database import (
    winner_report,
    losser_report,
    update_elo_db,
    update_elo_db_ladder,
    complete_ladder_challenge,
    delete_ladder_challenge,
    get_user_event_elo,
    create_ladder_challenge_table,
)

logger = logging.getLogger("discord_bot")


class LadderChallengeJoinButton(discord.ui.View):
    """Buttons for joining/leaving a ladder challenge queue and cancelling"""

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
                "You can't join your own challenge! Use the Cancel button to cancel it.",
                ephemeral=True,
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
                        # Queue full - disable all buttons
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

    @discord.ui.button(
        label="Leave Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="leave_ladder_challenge",
    )
    async def leave_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle a player leaving the ladder challenge queue"""
        user_id = interaction.user.id

        # Challenger can't use this button
        if user_id == self.challenger_id:
            await interaction.response.send_message(
                "Use the Cancel button to cancel your challenge.", ephemeral=True
            )
            return

        async with ladder_challenge_lock:
            challenge_data = active_ladder_challenges.get(self.challenger_id)
            if not challenge_data:
                await interaction.response.send_message(
                    "This ladder challenge is no longer active.", ephemeral=True
                )
                return

            # Check if they're actually in the queue
            joiner_idx = next(
                (i for i, j in enumerate(challenge_data["joiners"]) if j["user_id"] == user_id),
                None,
            )
            if joiner_idx is None:
                await interaction.response.send_message(
                    "You haven't joined this challenge.", ephemeral=True
                )
                return

            # Remove the joiner
            challenge_data["joiners"].pop(joiner_idx)
            joiner_count = len(challenge_data["joiners"])

            # Update the embed
            challenger_global = challenge_data["challenger_global"]
            embed = _build_ladder_challenge_embed(
                challenger_global, challenge_data["joiners"], self.challenger_id
            )

            try:
                msg = challenge_data.get("message")
                if msg:
                    # Re-enable buttons in case they were disabled at max
                    for item in self.children:
                        item.disabled = False
                    await msg.edit(embed=embed, view=self)
            except Exception as e:
                logger.error(f"Error updating ladder challenge message: {e}")

        await interaction.response.send_message(
            "You've left the ladder challenge queue.", ephemeral=True
        )

    @discord.ui.button(
        label="Cancel Challenge",
        style=discord.ButtonStyle.danger,
        custom_id="cancel_ladder_challenge",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handle the challenger cancelling their ladder challenge"""
        user_id = interaction.user.id

        # Only the challenger can cancel
        if user_id != self.challenger_id:
            await interaction.response.send_message(
                "Only the challenger can cancel this challenge.", ephemeral=True
            )
            return

        async with ladder_challenge_lock:
            challenge_data = active_ladder_challenges.pop(self.challenger_id, None)

        if not challenge_data:
            await interaction.response.send_message(
                "This ladder challenge is no longer active.", ephemeral=True
            )
            return

        # Cancel the timeout task
        task = challenge_data.get("task")
        if task and not task.done():
            task.cancel()

        # Delete the DB record so it doesn't count as daily use
        challenge_id = challenge_data.get("challenge_id")
        if challenge_id:
            delete_ladder_challenge(challenge_id)

        # Update the message
        challenger_global = challenge_data["challenger_global"]
        try:
            msg = challenge_data.get("message")
            if msg:
                embed = discord.Embed(
                    title="Ladder Challenge Cancelled",
                    description=f"**{challenger_global}** cancelled their ladder challenge.",
                    color=discord.Color.red(),
                )
                await msg.edit(embed=embed, view=None)
        except Exception as e:
            logger.error(f"Error updating cancelled ladder challenge message: {e}")

        await interaction.response.send_message(
            "Your ladder challenge has been cancelled. It does not count as your daily challenge.",
            ephemeral=True,
        )


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
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
                "SELECT winner_elo_change, winner_lifetime_elo_change FROM match_records WHERE match_id=?",
                (match_id,),
            )
            elo_row = cur_match.fetchone()
            conn_match.close()

            if elo_row:
                event_change = elo_row[0] or 0
                lifetime_change = elo_row[1] or 0
                extra_event_change = round(event_change * (winner_mult - 1.0))
                extra_lifetime_change = round(lifetime_change * (winner_mult - 1.0))
                conn_fix = _sqlite3.connect("elo.db")
                cur_fix = conn_fix.cursor()
                cur_fix.execute(
                    "UPDATE overall_standings SET online_elo = online_elo + ?, online_event_elo = online_event_elo + ?, "
                    "elo = elo + ?, event_elo = event_elo + ? WHERE user_id = ?",
                    (extra_lifetime_change, extra_event_change, extra_lifetime_change, extra_event_change, self.winner_id),
                )
                conn_fix.commit()
                conn_fix.close()
                logger.info(
                    f"Ladder bonus: Winner {self.winner_id} gets extra lifetime {extra_lifetime_change:+d}, "
                    f"event {extra_event_change:+d} ELO (mult={winner_mult})"
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
        joiner_names = [f"\u2022 {j['global_name']}" for j in joiners]
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

    embed.set_footer(text="Ladder Challenge \u2022 Top 16 vs The Field")
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
        # No one joined — delete the DB record so it doesn't count as daily use
        if challenge_id:
            delete_ladder_challenge(challenge_id)

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
                "Your ladder challenge expired with no challengers. It does not count as your daily challenge — you can try again!"
            )
        except Exception:
            pass
        return

    # Randomly select one opponent
    selected = random.choice(joiners)
    selected_id = selected["user_id"]
    selected_global = selected["global_name"]

    # Determine ELO multipliers based on event ELO
    challenger_elo = get_user_event_elo(challenger_id)
    opponent_elo = get_user_event_elo(selected_id)
    elo_diff = abs(challenger_elo - opponent_elo)

    if elo_diff < 100:
        # Normal stakes
        winner_mult = 1.0
        loser_mult = 1.0
        stakes_text = "ELO difference < 100 \u2014 **Normal ELO stakes** apply."
    else:
        # Special stakes
        winner_mult = 2.0  # Non-Top16 winner gets 2x
        loser_mult = 0.5  # Top16 loser gets 0.5x
        stakes_text = "**Special Stakes:** Challenger wins = 2x ELO. Top 16 loses = 0.5x ELO loss."

    # Update the challenge record with selected opponent
    create_ladder_challenge_table()
    conn = sqlite3.connect("match_records.db")
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
                    value="\n".join(f"\u2022 {j['global_name']}" for j in not_selected),
                    inline=False,
                )
            embed.set_footer(text="Ladder Challenge \u2022 May the best sorcerer win!")
            await msg.edit(embed=embed, view=None)
    except Exception as e:
        logger.error(f"Error updating ladder challenge result message: {e}")

    # Build ladder_info for the normal report flow with modified ELO
    guild_id = channel.guild.id if channel and channel.guild else None
    ladder_info = {
        "challenger_id": challenger_id,
        "challenge_id": challenge_id,
        "elo_multiplier_winner": winner_mult,
        "elo_multiplier_loser": loser_mult,
        "guild_id": guild_id,
    }

    # Assign active player role to both players if they don't have it
    try:
        guild = bot.get_guild(config.GUILD_ID)
        if guild:
            active_role = guild.get_role(config.ACTIVE_PLAYER_ROLE_ID)
            if active_role:
                for player_id in (challenger_id, selected_id):
                    member = guild.get_member(player_id)
                    if member and active_role not in member.roles:
                        await member.add_roles(active_role)
                        logger.info(f"Added active player role to {member.display_name} ({player_id})")
    except Exception as e:
        logger.error(f"Failed to assign active player role: {e}")

    # Send report buttons only to the Top 16 player (challenger)
    report_view = LFGReportButtons(
        match_id=0,
        player1_id=challenger_id,
        player1_global=challenger_global,
        player2_id=selected_id,
        player2_global=selected_global,
        bot=bot,
        channel=channel,
        ladder_info=ladder_info,
        guild_id=guild_id,
    )

    # DM the challenger with report buttons
    try:
        challenger_user = await bot.fetch_user(challenger_id)
        await challenger_user.send(
            f"**Ladder Challenge Match!** Your opponent is **{selected_global}**!\n\n"
            f"{stakes_text}\n\n"
            f"Report the match result below:",
            view=report_view,
        )
    except discord.Forbidden:
        dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if dm_channel:
            await dm_channel.send(
                scrub_urls(
                    f"<@{challenger_id}> **Ladder Challenge Match!** Your opponent is **{selected_global}**!\n\n"
                    f"{stakes_text}\n\nReport the match result below:"
                ),
                view=report_view,
            )
    except Exception as e:
        logger.error(f"Error DMing challenger for ladder match: {e}")

    # DM the selected opponent (notification only, no report buttons)
    try:
        opponent_user = await bot.fetch_user(selected_id)
        await opponent_user.send(
            f"**You've been selected for a Ladder Challenge!**\n\n"
            f"You're playing against **{challenger_global}** (Top 16)!\n\n"
            f"{stakes_text}\n\n"
            f"**{challenger_global}** will report the match result. You'll be asked to confirm.",
        )
    except discord.Forbidden:
        dm_channel = bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
        if dm_channel:
            await dm_channel.send(
                scrub_urls(
                    f"<@{selected_id}> **You've been selected for a Ladder Challenge!**\n\n"
                    f"You're playing against **{challenger_global}** (Top 16)!\n\n"
                    f"{stakes_text}\n\n**{challenger_global}** will report the match result. You'll be asked to confirm."
                ),
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
