import discord
import random
import datetime
import logging

import config
from cogs.lfg.state import lfg_queue
from cogs.lfg.persistent_confirm import create_match_card_view
from cogs.lfg.pairing_messages import (
    PairingPlayer,
    announce_pairing,
    send_pairing_messages,
)
from utils.database import save_pairing
from utils.deck_checker import clean_deck_url

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
        label="Your Deck URL (optional)",
        placeholder="https://sorcerytcg.com/decks/...",
        required=False,
        max_length=200,
    )

    def __init__(self, challenger, opponent, lfg_channel, bot, guild_id=None):
        super().__init__()
        self.challenger = challenger
        self.opponent = opponent
        self.lfg_channel = lfg_channel
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        url = clean_deck_url(self.deck_url.value.strip()) if self.deck_url.value else None
        challenger_global = self.challenger.global_name or self.challenger.display_name
        opponent_global = self.opponent.global_name or self.opponent.display_name

        view = ChallengeButtons(
            self.challenger.id,
            challenger_global,
            self.lfg_channel,
            challenger_deck_url=url,
            guild_id=self.guild_id,
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
        label="Your Deck URL (optional)",
        placeholder="https://sorcerytcg.com/decks/...",
        required=False,
        max_length=200,
    )

    def __init__(
        self,
        challenger_id: int,
        challenger_global: str,
        channel=None,
        challenger_deck_url: str = None,
        guild_id: int = None,
    ):
        super().__init__()
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        challenger = await interaction.client.fetch_user(self.challenger_id)
        accepter_global = interaction.user.global_name or interaction.user.display_name
        accepter_deck_url = clean_deck_url(self.deck_url.value.strip()) if self.deck_url.value else None

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

        # Use pairing_id if we saved one, otherwise 0
        challenge_pairing_id = pairing_id if self.guild_id else 0

        # Create match card view for the reporter (same as normal LFG flow)
        match_card_view = create_match_card_view(
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
        )

        # Whichever player accepted is mid-interaction, so they get an
        # ephemeral reply; the other player is reached by DM.
        await send_pairing_messages(
            interaction.client,
            reporter=PairingPlayer(
                reporter_id,
                reporter_global,
                reporter_user,
                reporter_deck_url,
                interaction=interaction if reporter_is_accepter else None,
            ),
            other=PairingPlayer(
                other_id,
                other_global,
                other_user,
                other_deck_url,
                interaction=interaction if other_is_accepter else None,
            ),
            match_card_view=match_card_view,
            match_type="ranked",
            headline="Challenge Accepted!",
        )

        # Announce in LFG channel
        await announce_pairing(
            self.channel,
            player_a=challenger,
            player_b=interaction.user,
            match_type="ranked",
            headline="Challenge Accepted!",
        )


class ChallengeButtons(discord.ui.View):
    def __init__(
        self,
        challenger_id: int,
        challenger_global: str,
        channel=None,
        challenger_deck_url: str = None,
        guild_id: int = None,
    ):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global
        self.channel = channel
        self.challenger_deck_url = challenger_deck_url
        self.guild_id = guild_id

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
