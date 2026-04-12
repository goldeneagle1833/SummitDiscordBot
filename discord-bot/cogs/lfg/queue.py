import discord
import random
import datetime
import logging
import sqlite3

import config
from cogs.lfg.state import lfg_queue, lfg_queue_lock
from cogs.lfg.helpers import scrub_urls
from utils.constants import SORCERY_NICKNAMES
from utils.database import save_pairing
from repositories.limited_repo import save_limited_pairing, get_active_arena_run
from services.pilots_service import is_pilot_active

logger = logging.getLogger("discord_bot")


def get_last_unreported_pairing(user_id: int, guild_id: int):
    """Get the most recent unreported pairing for a user.

    Returns:
        dict with keys: pairing_id, player1_id, player2_id, player1_deck_url, player2_deck_url, match_type
        or None if no unreported pairing found
    """
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check regular pairings first
    cursor.execute(
        """
        SELECT * FROM pairings
        WHERE guild_id = ?
          AND (player1_id = ? OR player2_id = ?)
          AND reported = 0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id, user_id, user_id)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)

    # Check limited pairings if no regular pairing found
    conn = sqlite3.connect("match_records.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM limited_pairings
        WHERE guild_id = ?
          AND (player1_id = ? OR player2_id = ?)
          AND reported = 0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (guild_id, user_id, user_id)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        pairing_dict = dict(row)
        pairing_dict['match_type'] = 'limited'
        return pairing_dict

    return None


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

        # Limited queue requires a deck URL
        if self.queue_type == "limited" and not deck_url:
            await interaction.followup.send(
                "A Curiosa deck URL is **required** for Limited queue. Please provide your draft deck URL.",
                ephemeral=True,
            )
            return

        # For limited queue, player must have an active arena run (created via Draft Sorcery)
        run_id = None
        if self.queue_type == "limited":
            active_run = get_active_arena_run(interaction.user.id)
            if active_run and active_run["status"] == "active" and active_run["wins"] < 5 and active_run["losses"] < 3:
                run_id = active_run["run_id"]
                deck_url = active_run["deck_url"]
            else:
                if active_run and active_run["status"] != "active":
                    msg = "Your current Limited run is over. Start a new run at https://draftsorcery.com/ to continue playing Limited."
                else:
                    msg = "You need an active arena run to join the Limited queue. Start one at https://draftsorcery.com/ first."
                await interaction.followup.send(msg, ephemeral=True)
                return

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

        # Use lock to prevent race conditions - check, match, OR add must be atomic
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
                matched_ladder_info = matched_user_info.get("ladder_info")
                matched_run_id = matched_user_info.get("run_id")

                # Determine match type based on both players' queue types
                match_type = lfg_cog.resolve_match_type(
                    self.queue_type, matched_queue_type
                )

                # If matched user has ladder_info, adjust multipliers based on ELO difference
                if matched_ladder_info:
                    from utils.database import get_user_event_elo

                    challenger_elo = get_user_event_elo(
                        matched_ladder_info["challenger_id"]
                    )
                    opponent_elo = get_user_event_elo(interaction.user.id)
                    elo_diff = abs(challenger_elo - opponent_elo)

                    if elo_diff < 100:
                        # Normal stakes - set multipliers to 1.0
                        matched_ladder_info["elo_multiplier_winner"] = 1.0
                        matched_ladder_info["elo_multiplier_loser"] = 1.0
                        logger.info(
                            f"Ladder challenge match: ELO diff {elo_diff} < 100 - using normal stakes"
                        )
                    else:
                        # Keep special stakes (2.0 for winner, 0.5 for loser)
                        logger.info(
                            f"Ladder challenge match: ELO diff {elo_diff} >= 100 - using special stakes (2x/0.5x)"
                        )

                # Remove matched user from queue
                lfg_queue.pop(matched_user_id, None)
                logger.info(
                    f"Lock acquired: Matching {interaction.user.id} with {matched_user_id} (match_type={match_type})"
                )
            else:
                # No match found - add to queue while still holding the lock
                matched_user_id = None
                matched_user_deck_url = None
                matched_ladder_info = None
                matched_run_id = None
                match_type = None
                lfg_cog.add_to_lfg_queue(
                    ctx,
                    timeframe_value,
                    deck_url,
                    self.queue_type,
                    run_id=run_id,
                )

        # Handle the result outside the lock
        if matched_user_id:
            if match_type == "limited":
                match_type_emoji = "🎲"
                match_type_label = "Limited"
            elif match_type == "ranked":
                match_type_emoji = "⚔️"
                match_type_label = "Ranked"
            else:
                match_type_emoji = "⭐"
                match_type_label = "Casual"
            # Match found!
            matched_user = await self.bot.fetch_user(matched_user_id)
            lfg_channel = self.bot.get_channel(lfg_cog.lfg_channel_id)
            joiner_global = (
                interaction.user.global_name or interaction.user.display_name
            )
            matched_global = matched_user.global_name or matched_user.display_name

            # Record match start time
            match_start_time = datetime.datetime.now()

            # Validate guild_id before saving pairing
            if not interaction.guild or not interaction.guild.id:
                logger.error(
                    f"Cannot save pairing: guild_id is None for users {interaction.user.id} and {matched_user_id}"
                )
                await interaction.followup.send(
                    "Error: Could not save match pairing. Please try using !lfg command instead.",
                    ephemeral=True,
                )
                return

            # Save pairing to database for validation during match reporting
            try:
                if match_type == "limited":
                    pairing_id = save_limited_pairing(
                        guild_id=interaction.guild.id,
                        player1_id=interaction.user.id,
                        player2_id=matched_user_id,
                        player1_deck_url=deck_url,
                        player2_deck_url=matched_user_deck_url,
                        player1_run_id=run_id,
                        player2_run_id=matched_run_id,
                    )
                else:
                    pairing_id = save_pairing(
                        guild_id=interaction.guild.id,
                        player1_id=interaction.user.id,
                        player2_id=matched_user_id,
                        player1_deck_url=deck_url,
                        player2_deck_url=matched_user_deck_url,
                    )
                logger.info(
                    f"Saved {'limited ' if match_type == 'limited' else ''}pairing {pairing_id} in guild {interaction.guild.id}: "
                    f"{interaction.user.id} ({joiner_global}) vs {matched_user_id} ({matched_global})"
                )
            except Exception as e:
                logger.error(
                    f"Failed to save pairing for users {interaction.user.id} and {matched_user_id}: {e}",
                    exc_info=True,
                )
                await interaction.followup.send(
                    "Error: Could not save match pairing to database. Please contact an admin.",
                    ephemeral=True,
                )
                return

            # Assign active player role to both players if they don't have it
            try:
                guild = self.bot.get_guild(config.GUILD_ID)
                if guild:
                    active_role = guild.get_role(config.ACTIVE_PLAYER_ROLE_ID)
                    if active_role:
                        for player_id in (interaction.user.id, matched_user_id):
                            member = guild.get_member(player_id)
                            if member and active_role not in member.roles:
                                await member.add_roles(active_role)
                                logger.info(f"Added active player role to {member.display_name} ({player_id})")
            except Exception as e:
                logger.error(f"Failed to assign active player role: {e}")

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

            # Create "Did you go first?" view with the pre-determined match type
            # (Skip match type selection since we already know it from queue types)
            from cogs.lfg.match_reporting import WentFirstView

            # Determine run_ids for reporter and other player
            if match_type == "limited":
                if reporter_is_joiner:
                    reporter_run_id = run_id
                    other_run_id = matched_run_id
                else:
                    reporter_run_id = matched_run_id
                    other_run_id = run_id
            else:
                reporter_run_id = None
                other_run_id = None

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
                ladder_info=matched_ladder_info,
                match_type=match_type,
                reporter_run_id=reporter_run_id,
                opponent_run_id=other_run_id,
            )

            # Build match type label for message
            if match_type == "limited":
                match_type_emoji = "🎲"
                match_type_label = "Limited"
            elif match_type == "ranked":
                match_type_emoji = "⚔️"
                match_type_label = "Ranked"
            else:
                match_type_emoji = "⭐"
                match_type_label = "Casual"

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
                    f"🎮 **Match Found!** You've been matched with {reporter_user.mention} (**{reporter_global}**)!{other_own_deck_text}\n\n"
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
                                f"{other_user.mention} 🎮 **Match Found!**\n\nYou've been matched with {reporter_user.mention} (**{reporter_global}**)!\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation button to verify the outcome."
                            )
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for other player: {e}")

            # Announce match in LFG channel
            if lfg_channel:
                # Add ladder challenge info if applicable
                ladder_note = ""
                if matched_ladder_info:
                    from utils.database import get_user_event_elo

                    elo_diff = abs(
                        get_user_event_elo(matched_ladder_info["challenger_id"])
                        - get_user_event_elo(interaction.user.id)
                    )
                    if elo_diff >= 100:
                        ladder_note = " 🏆 **Ladder Challenge!** Top 16 player - Special stakes (2x/0.5x ELO)!"
                    else:
                        ladder_note = " 🏆 **Ladder Challenge!** Top 16 player (normal stakes - ELO diff < 100)"

                await lfg_channel.send(
                    f"{match_type_emoji} **{match_type_label} Match Found!** {interaction.user.mention} matched with {matched_user.mention}!{ladder_note}"
                )

            await lfg_cog.update_lfg_status()

            await interaction.followup.send(
                f"{match_type_emoji} {match_type_label} match found! You've been paired with {matched_global}. Check your DMs!",
                ephemeral=True,
            )
        else:
            # Already added to queue inside the lock above
            queue_label = self.queue_type.capitalize()
            deck_msg = f"\n**Deck:** {deck_url}" if deck_url else ""
            try:
                await interaction.user.send(
                    f"You have been added to the **{queue_label}** queue for {timeframe_value} minutes.{deck_msg}"
                )
            except Exception:
                pass

            try:
                await lfg_cog.update_lfg_status()
            except Exception as e:
                logger.error(f"Failed to update LFG status after queue join: {e}")

            await interaction.followup.send(
                f"You've joined the **{queue_label}** queue for {timeframe_value} minutes!{deck_msg}",
                ephemeral=True,
            )


class JoinQueueButtons(discord.ui.View):
    """Buttons for joining the LFG queue (Ranked, Testing, or Both) - for empty queue"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        if not is_pilot_active("GrewWolves"):
            self.remove_item(self.join_limited_button)

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
        label="Join Limited",
        style=discord.ButtonStyle.primary,
        custom_id="join_lfg_limited",
    )
    async def join_limited_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not is_pilot_active("GrewWolves"):
            await interaction.response.send_message(
                "Limited queue is not currently available.", ephemeral=True
            )
            return
        await self._handle_join(interaction, "limited")

    @discord.ui.button(
        label="📬 Resend Last Match",
        style=discord.ButtonStyle.secondary,
        custom_id="resend_last_match",
        row=1,
    )
    async def resend_last_match_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Resend the match reporting flow for the user's most recent unreported pairing"""
        await interaction.response.defer(ephemeral=True)

        # Debug message for specific user
        if interaction.user.id == 296846802924208130:
            try:
                await interaction.user.send("🔧 **Debug**: Resend Last Match button is working!")
            except Exception:
                pass

        # Get guild ID from interaction
        if not interaction.guild:
            await interaction.followup.send(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id

        # Get the last unreported pairing
        pairing = get_last_unreported_pairing(interaction.user.id, guild_id)

        if not pairing:
            await interaction.followup.send(
                "No unreported matches found. Play a match first!",
                ephemeral=True,
            )
            return

        # Determine opponent
        if pairing['player1_id'] == interaction.user.id:
            opponent_id = pairing['player2_id']
            reporter_deck_url = pairing.get('player1_deck_url')
            opponent_deck_url = pairing.get('player2_deck_url')
        else:
            opponent_id = pairing['player1_id']
            reporter_deck_url = pairing.get('player2_deck_url')
            opponent_deck_url = pairing.get('player1_deck_url')

        # Fetch opponent user
        try:
            opponent_user = await self.bot.fetch_user(opponent_id)
        except Exception as e:
            logger.error(f"Failed to fetch opponent user {opponent_id}: {e}")
            await interaction.followup.send(
                "Failed to fetch opponent information. Please try again.",
                ephemeral=True,
            )
            return

        # Import WentFirstView here to avoid circular import
        from cogs.lfg.match_reporting import WentFirstView

        # Determine match type
        match_type = pairing.get('match_type', 'ranked')

        # Get run IDs for limited matches
        reporter_run_id = None
        opponent_run_id = None
        if match_type == 'limited':
            reporter_run = get_active_arena_run(interaction.user.id)
            opponent_run = get_active_arena_run(opponent_id)
            reporter_run_id = reporter_run['run_id'] if reporter_run else None
            opponent_run_id = opponent_run['run_id'] if opponent_run else None

        # Build deck text
        reporter_deck_text = ""
        if reporter_deck_url:
            reporter_deck_text = f"\n**Your Deck:** {reporter_deck_url}"

        # Create the WentFirstView
        went_first_view = WentFirstView(
            match_id=0,  # Not needed for existing pairings
            player1_id=interaction.user.id,
            player1_global=interaction.user.global_name or interaction.user.display_name,
            player2_id=opponent_id,
            player2_global=opponent_user.global_name or opponent_user.display_name,
            bot=self.bot,
            channel=None,  # Will use DM fallback
            match_start_time=datetime.datetime.now(),
            reporter_deck_url=reporter_deck_url,
            opponent_deck_url=opponent_deck_url,
            opponent_user=opponent_user,
            reporter_deck_text=reporter_deck_text,
            guild_id=guild_id,
            match_type=match_type,
            reporter_run_id=reporter_run_id,
            opponent_run_id=opponent_run_id,
        )

        # Determine match type emoji and label
        if match_type == "limited":
            match_type_emoji = "🎲"
            match_type_label = "Limited"
        elif match_type == "ranked":
            match_type_emoji = "⚔️"
            match_type_label = "Ranked"
        else:
            match_type_emoji = "⭐"
            match_type_label = "Casual"

        # Try to send to DM first
        try:
            await interaction.user.send(
                f"{match_type_emoji} **{match_type_label} Match** - You've been matched with {opponent_user.mention} (**{opponent_user.global_name or opponent_user.display_name}**)!{reporter_deck_text}\n\n**Did you go first?**",
                view=went_first_view,
            )
            await interaction.followup.send(
                f"Match reporting flow resent! Check your DMs.",
                ephemeral=True,
            )
        except discord.Forbidden:
            # DM failed, fall back to DM-disabled channel
            dm_channel = self.bot.get_channel(config.DM_DISABLED_CHANNEL_ID)
            if dm_channel:
                try:
                    # Grant permissions
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        member = guild.get_member(interaction.user.id)
                        if member:
                            await dm_channel.set_permissions(
                                member, read_messages=True, send_messages=True
                            )

                    await dm_channel.send(
                        f"{interaction.user.mention} {match_type_emoji} **{match_type_label} Match** - You've been matched with {opponent_user.mention} (**{opponent_user.global_name or opponent_user.display_name}**)!{reporter_deck_text}\n\n**Did you go first?**",
                        view=went_first_view,
                    )
                    await interaction.followup.send(
                        f"Match reporting flow sent to <#{config.DM_DISABLED_CHANNEL_ID}>!",
                        ephemeral=True,
                    )
                except Exception as e:
                    logger.error(f"Failed to send to DM-disabled channel: {e}")
                    await interaction.followup.send(
                        "Failed to send match reporting flow. Please try again.",
                        ephemeral=True,
                    )
            else:
                await interaction.followup.send(
                    "Could not send DM and fallback channel not found. Please contact an admin.",
                    ephemeral=True,
                )


class ActiveQueueButtons(JoinQueueButtons):
    """Buttons for active queue (includes Leave Queue button)"""

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

            # Update status message after leaving queue (same as !cancel)
            cog = self.bot.get_cog("LFGCog")
            if cog:
                await cog.update_lfg_status()
        else:
            # User not in queue
            await interaction.response.send_message(
                "You are not currently in the LFG queue.", ephemeral=True
            )
