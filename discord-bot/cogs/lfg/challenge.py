import discord
import random
import datetime
import logging

import config
from cogs.lfg.state import lfg_queue
from cogs.lfg.helpers import scrub_urls
from cogs.lfg.match_reporting import MatchCardView
from utils.database import get_active_event, save_pairing
from utils.avatar_elo import avatar_input_error, canonicalize_avatar_name

logger = logging.getLogger("discord_bot")


class ChallengeInitView(discord.ui.View):
    """View with a button to open the challenge modal"""

    def __init__(self, modal, challenger_id: int = None):
        super().__init__(timeout=60)
        self.modal = modal
        self.challenger_id = challenger_id or modal.challenger.id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="\u2694\ufe0f Send Challenge", style=discord.ButtonStyle.primary)
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

    avatar = discord.ui.TextInput(
        label="Your Avatar for this match",
        placeholder="Enter the exact Avatar card name",
        required=True,
        max_length=100,
    )

    def __init__(self, challenger, opponent, lfg_channel, bot, guild_id=None):
        super().__init__()
        self.challenger = challenger
        self.opponent = opponent
        self.lfg_channel = lfg_channel
        self.bot = bot
        self.guild_id = guild_id
        self.event_snapshot = get_active_event()
        self.avatar_specific = bool(
            self.event_snapshot and self.event_snapshot.get("avatar_specific")
        )
        if not self.avatar_specific:
            self.remove_item(self.avatar)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        url = self.deck_url.value if self.deck_url.value else None
        challenger_avatar = None
        if self.avatar_specific:
            challenger_avatar = canonicalize_avatar_name(self.avatar.value)
            if not challenger_avatar:
                await interaction.followup.send(
                    avatar_input_error("your avatar", self.avatar.value),
                    ephemeral=True,
                )
                return
        challenger_global = self.challenger.global_name or self.challenger.display_name
        opponent_global = self.opponent.global_name or self.opponent.display_name

        view = ChallengeButtons(
            self.challenger.id,
            challenger_global,
            self.lfg_channel,
            challenger_deck_url=url,
            guild_id=self.guild_id,
            challenger_avatar=challenger_avatar,
            event_snapshot=self.event_snapshot,
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

    avatar = discord.ui.TextInput(
        label="Your Avatar for this match",
        placeholder="Enter the exact Avatar card name",
        required=True,
        max_length=100,
    )

    def __init__(
        self,
        challenger_id: int,
        challenger_global: str,
        channel=None,
        challenger_deck_url: str = None,
        guild_id: int = None,
        challenger_avatar: str = None,
        event_snapshot: dict = None,
    ):
        super().__init__()
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url
        self.guild_id = guild_id
        self.challenger_avatar = challenger_avatar
        self.event_snapshot = event_snapshot
        self.avatar_specific = bool(
            event_snapshot and event_snapshot.get("avatar_specific")
        )
        if not self.avatar_specific:
            self.remove_item(self.avatar)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        challenger = await interaction.client.fetch_user(self.challenger_id)
        accepter_global = interaction.user.global_name or interaction.user.display_name
        accepter_deck_url = self.deck_url.value if self.deck_url.value else None
        accepter_avatar = None
        if self.avatar_specific:
            current_event = get_active_event()
            if (
                not current_event
                or current_event.get("event_id") != self.event_snapshot.get("event_id")
            ):
                await interaction.followup.send(
                    "The event changed before this challenge was accepted. Please send a new challenge.",
                    ephemeral=True,
                )
                return
            accepter_avatar = canonicalize_avatar_name(self.avatar.value)
            if not accepter_avatar:
                await interaction.followup.send(
                    avatar_input_error("your avatar", self.avatar.value),
                    ephemeral=True,
                )
                return

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

        # Save pairing to database for validation during match reporting
        pairing_id = 0
        if not self.guild_id:
            logger.warning(
                f"guild_id is None for challenge between {self.challenger_id} and {interaction.user.id}, "
                f"attempting to recover from interaction"
            )
            if interaction.guild:
                self.guild_id = interaction.guild.id

        if self.guild_id:
            try:
                pairing_id = save_pairing(
                    guild_id=self.guild_id,
                    player1_id=self.challenger_id,
                    player2_id=interaction.user.id,
                    player1_deck_url=self.challenger_deck_url,
                    player2_deck_url=accepter_deck_url,
                    match_type="ranked",
                    player1_avatar=self.challenger_avatar,
                    player2_avatar=accepter_avatar,
                    event_snapshot=self.event_snapshot,
                )
                logger.info(
                    f"Saved challenge pairing {pairing_id} in guild {self.guild_id}: "
                    f"{self.challenger_id} vs {interaction.user.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to save challenge pairing for {self.challenger_id} vs {interaction.user.id}: {e}",
                    exc_info=True,
                )
        else:
            logger.error(
                f"Cannot save challenge pairing: guild_id is None for {self.challenger_id} vs {interaction.user.id}"
            )

        # Assign active player role to both players if they don't have it
        try:
            guild = interaction.client.get_guild(config.GUILD_ID)
            if guild:
                active_role = guild.get_role(config.ACTIVE_PLAYER_ROLE_ID)
                if active_role:
                    for player_id in (self.challenger_id, interaction.user.id):
                        member = guild.get_member(player_id)
                        if member and active_role not in member.roles:
                            await member.add_roles(active_role)
                            logger.info(f"Added active player role to {member.display_name} ({player_id})")
        except Exception as e:
            logger.error(f"Failed to assign active player role: {e}")

        # Randomly select which player gets the report buttons
        # Both challenger and accepter can have deck URLs
        players = [
            (
                self.challenger_id,
                self.challenger_global,
                challenger,
                self.challenger_deck_url,  # Challenger's deck URL (if provided)
                self.challenger_avatar,
                False,
            ),
            (
                interaction.user.id,
                accepter_global,
                interaction.user,
                accepter_deck_url,  # Accepter's deck URL
                accepter_avatar,
                True,
            ),
        ]
        reporter_player, other_player = random.sample(players, 2)
        (
            reporter_id,
            reporter_global,
            reporter_user,
            reporter_deck_url,
            reporter_avatar,
            reporter_is_accepter,
        ) = reporter_player
        other_id, other_global, other_user, other_deck_url, other_avatar, other_is_accepter = (
            other_player
        )

        # Build deck message
        reporter_deck_text = (
            f"\n**Your Deck:** {reporter_deck_url}" if reporter_deck_url else ""
        )
        other_deck_text = f"\n**Your Deck:** {other_deck_url}" if other_deck_url else ""
        reporter_avatar_text = ""
        other_avatar_text = ""
        if reporter_avatar and other_avatar:
            reporter_avatar_text = (
                f"\n**Your Avatar:** {reporter_avatar}"
                f"\n**Opponent Avatar:** {other_avatar}"
            )
            other_avatar_text = (
                f"\n**Your Avatar:** {other_avatar}"
                f"\n**Opponent Avatar:** {reporter_avatar}"
            )

        # Use pairing_id if we saved one, otherwise 0
        challenge_pairing_id = pairing_id if self.guild_id else 0

        # Create match card view for the reporter (same as normal LFG flow)
        match_card_view = MatchCardView(
            bot=interaction.client,
            pairing_id=challenge_pairing_id,
            player1_id=reporter_id,
            player1_global=reporter_global,
            player2_id=other_id,
            player2_global=other_global,
            player1_deck_url=reporter_deck_url,
            player2_deck_url=other_deck_url,
            match_start_time=match_start_time,
            guild_id=self.guild_id,
            match_type="ranked",
            player1_avatar=reporter_avatar,
            player2_avatar=other_avatar,
            event_snapshot=self.event_snapshot,
        )

        # Send match card to the selected reporter
        if reporter_is_accepter:
            # Reporter is the one who accepted - use followup since we deferred
            try:
                await interaction.followup.send(
                    f"⚔️ **Challenge Accepted!** You're playing against {other_user.mention} (**{other_global}**)!{reporter_deck_text}{reporter_avatar_text}\n\n"
                    f"Use the button below to report the result when your match is done.\n\n"
                    f"💡 **Tip:** If these buttons expire, click **'📋 Report Last Match'** in the LFG channel for fresh ones!",
                    view=match_card_view,
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to send match card to accepter: {e}")
        else:
            # Reporter is the challenger - send via DM
            try:
                await challenger.send(
                    f"⚔️ **Challenge Accepted!** **{accepter_global}** accepted your challenge!{reporter_deck_text}{reporter_avatar_text}\n\n"
                    f"Use the button below to report the result when your match is done.\n\n"
                    f"💡 **Tip:** If these buttons expire, click **'📋 Report Last Match'** in the LFG channel for fresh ones!",
                    view=match_card_view,
                )
            except discord.Forbidden:
                try:
                    dm_channel = interaction.client.get_channel(config.DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        guild = interaction.client.get_guild(config.GUILD_ID)
                        if guild:
                            member = guild.get_member(reporter_id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )
                                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                                if role and role not in member.roles:
                                    await member.add_roles(role)

                        await dm_channel.send(
                            scrub_urls(
                                f"{challenger.mention} ⚔️ **Challenge Accepted!** **{accepter_global}** accepted your challenge!\n\n"
                                f"Use the button below to report the result when your match is done.\n\n"
                                f"💡 **Tip:** If these buttons expire, click **'📋 Report Last Match'** for fresh ones!"
                            ),
                            view=match_card_view,
                        )
                except Exception as e:
                    logger.error(f"Failed to handle DM failure for challenger: {e}")

        # Send info to the other player (no buttons)
        if other_is_accepter:
            # Other is the accepter - send followup
            try:
                await interaction.followup.send(
                    f"⚔️ **Challenge Accepted!** You're playing against {reporter_user.mention} (**{reporter_global}**)!{other_deck_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome.\n\n"
                    f"💡 **Tip:** If you need fresh reporting buttons, click **'📋 Report Last Match'** in the LFG channel!",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to send info to accepter: {e}")
        else:
            # Other is the challenger - send via DM
            try:
                await challenger.send(
                    f"⚔️ **Challenge Accepted!** **{accepter_global}** accepted your challenge!{other_deck_text}{other_avatar_text}\n\n"
                    f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome.\n\n"
                    f"💡 **Tip:** If you need fresh reporting buttons, click **'📋 Report Last Match'** in the LFG channel!"
                )
            except discord.Forbidden:
                try:
                    dm_channel = interaction.client.get_channel(config.DM_DISABLED_CHANNEL_ID)
                    if dm_channel:
                        guild = interaction.client.get_guild(config.GUILD_ID)
                        if guild:
                            member = guild.get_member(other_id)
                            if member:
                                await dm_channel.set_permissions(
                                    member, read_messages=True, send_messages=True
                                )
                                role = guild.get_role(config.DM_DISABLED_ROLE_ID)
                                if role and role not in member.roles:
                                    await member.add_roles(role)

                        await dm_channel.send(
                            scrub_urls(
                                f"{challenger.mention} ⚔️ **Challenge Accepted!** **{accepter_global}** accepted your challenge!\n\n"
                                f"**{reporter_global}** has the match report buttons. When they report the result, you'll receive a confirmation to verify the outcome.\n\n"
                                f"💡 **Tip:** If you need fresh reporting buttons, click **'📋 Report Last Match'**!"
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
        guild_id: int = None,
        challenger_avatar: str = None,
        event_snapshot: dict = None,
    ):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url
        self.guild_id = guild_id
        self.challenger_avatar = challenger_avatar
        self.event_snapshot = event_snapshot

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
            guild_id=self.guild_id,
            challenger_avatar=self.challenger_avatar,
            event_snapshot=self.event_snapshot,
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
