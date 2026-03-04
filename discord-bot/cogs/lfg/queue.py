import discord
import random
import datetime
import logging

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock
from cogs.lfg.helpers import scrub_urls
from cogs.lfg.match_reporting import WentFirstView
from utils.constants import SORCERY_NICKNAMES
from utils.database import save_pairing

logger = logging.getLogger("discord_bot")


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

    def __init__(self, bot, is_button_join=True, queue_type="ranked"):
        super().__init__()
        self.bot = bot
        self.is_button_join = (
            is_button_join  # True if from button, False if from !lfg command
        )
        self.queue_type = queue_type

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
            matched_user_id = lfg_cog.check_if_someone_is_lfg(ctx, self.queue_type)

            if matched_user_id and matched_user_id != interaction.user.id:
                # Get matched user's info before removing from queue
                matched_user_info = lfg_queue.get(matched_user_id, {})
                matched_user_deck_url = matched_user_info.get("deck_url")
                matched_queue_type = matched_user_info.get("queue_type", "ranked")
                # Determine match type based on both players' queue types
                match_type = lfg_cog.resolve_match_type(
                    self.queue_type, matched_queue_type
                )
                # Remove matched user from queue
                lfg_queue.pop(matched_user_id, None)
                logger.info(
                    f"Lock acquired: Matching {interaction.user.id} with {matched_user_id} (match_type={match_type})"
                )
            else:
                matched_user_id = None
                matched_user_deck_url = None
                match_type = None

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

            # Save pairing to database for validation during match reporting
            save_pairing(
                guild_id=interaction.guild.id,
                player1_id=interaction.user.id,
                player2_id=matched_user_id,
                player1_deck_url=deck_url,
                player2_deck_url=matched_user_deck_url,
            )

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

            # Determine match type label for messages
            match_type_label = "Ranked" if match_type == "ranked" else "Casual"
            match_type_emoji = "\u2694\ufe0f" if match_type == "ranked" else "\u2b50"

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
                guild_id=interaction.guild.id,
                match_type=match_type,
            )

            # Send "Did you go first?" question to the selected reporter
            try:
                await reporter_user.send(
                    f"{match_type_emoji} **{match_type_label} Match Found!** You've been matched with {other_user.mention} (**{other_global}**)!{reporter_deck_text}\n\n**Did you go first?**",
                    view=went_first_view,
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
                                f"{reporter_user.mention} {match_type_emoji} **{match_type_label} Match Found!**\n\nYou've been matched with {other_user.mention} (**{other_global}**)!\n\n**Did you go first?**"
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
                    f"{match_type_emoji} **{match_type_label} Match Found!** You've been matched with {reporter_user.mention} (**{reporter_global}**)!{other_own_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                )
            except discord.Forbidden:
                try:
                    dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
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
                                f"{other_user.mention} {match_type_emoji} **{match_type_label} Match Found!**\n\nYou've been matched with {reporter_user.mention} (**{reporter_global}**)!\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                            )
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for other player: {e}")

            # Announce match in LFG channel
            if lfg_channel:
                await lfg_channel.send(
                    f"{match_type_emoji} **{match_type_label} Match Found!** {interaction.user.mention} matched with {matched_user.mention}!"
                )

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"{match_type_emoji} {match_type_label} match found! You've been paired with {matched_global}. Check your DMs!",
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

                lfg_cog.add_to_lfg_queue(
                    ctx, timeframe_value, deck_url, self.queue_type
                )

            queue_label = self.queue_type.capitalize()
            deck_msg = f"\n**Deck:** {deck_url}" if deck_url else ""
            try:
                await interaction.user.send(
                    f"You have been added to the **{queue_label}** queue for {timeframe_value} minutes.{deck_msg}"
                )
            except discord.Forbidden:
                pass

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"You've joined the **{queue_label}** queue for {timeframe_value} minutes!{deck_msg}",
                ephemeral=True,
            )


class JoinQueueButtons(discord.ui.View):
    """Buttons for joining the LFG queue (Ranked, Testing, or Both)"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def _handle_join(self, interaction: discord.Interaction, queue_type: str):
        """Shared handler for all join buttons"""
        if interaction.user.id in lfg_queue:
            await interaction.response.send_message(
                "You're already in the queue!", ephemeral=True
            )
            return
        modal = DeckURLModal(self.bot, is_button_join=True, queue_type=queue_type)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Join Ranked",
        style=discord.ButtonStyle.green,
        custom_id="join_lfg_ranked",
    )
    async def join_ranked_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_join(interaction, "ranked")

    @discord.ui.button(
        label="Join Casual",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_testing",
    )
    async def join_testing_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_join(interaction, "testing")

    @discord.ui.button(
        label="Join Both",
        style=discord.ButtonStyle.secondary,
        custom_id="join_lfg_both",
    )
    async def join_both_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self._handle_join(interaction, "both")

    @discord.ui.button(
        label="Leave Queue",
        style=discord.ButtonStyle.danger,
        custom_id="leave_lfg_queue",
    )
    async def leave_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Remove user from the LFG queue (reuses !cancel logic)"""
        async with lfg_queue_lock:
            was_in_queue = interaction.user.id in lfg_queue
            if was_in_queue:
                lfg_queue.pop(interaction.user.id)

        if was_in_queue:
            # Send ephemeral confirmation
            await interaction.response.send_message(
                "You have been removed from the LFG queue.", ephemeral=True
            )

            # Update status message after leaving queue
            cog = self.bot.get_cog("LFG")
            if cog:
                await cog.update_lfg_status()
        else:
            # User not in queue
            await interaction.response.send_message(
                "You are not currently in the LFG queue.", ephemeral=True
            )
