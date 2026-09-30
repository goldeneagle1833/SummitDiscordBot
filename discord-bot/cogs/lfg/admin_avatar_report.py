"""Admin match reports for Avatar-mode seasons.

The admin picks both players in the slash command (Discord's member picker,
so a player can't be mistyped), then a form asks for each player's avatar as
free text. Names are checked against the official avatar list; a near miss is
rejected with a "did you mean …?" instead of being corrected silently.
"""

import logging

import discord

from utils.avatars import validate_avatar_name

logger = logging.getLogger("discord_bot")


class InteractionContext:
    """Just enough of a commands.Context for the LFG cog's admin report code."""

    def __init__(self, bot, interaction: discord.Interaction):
        self.bot = bot
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.interaction = interaction

    async def send(self, *args, **kwargs):
        return await self.interaction.followup.send(*args, **kwargs)


class AdminAvatarReportModal(discord.ui.Modal):
    """Asks for the winner's and loser's avatars, then records the report."""

    def __init__(self, bot, winner: discord.Member, loser: discord.Member, top16_player=None):
        title = "Admin Challenge Report" if top16_player else "Admin Match Report"
        super().__init__(title=title)
        self.bot = bot
        self.winner = winner
        self.loser = loser
        self.top16_player = top16_player
        self.winner_avatar = discord.ui.TextInput(
            label=f"Winner's avatar ({winner.display_name})"[:45],
            placeholder="e.g. Imposter",
            max_length=40,
        )
        self.loser_avatar = discord.ui.TextInput(
            label=f"Loser's avatar ({loser.display_name})"[:45],
            placeholder="e.g. Persecutor",
            max_length=40,
        )
        self.add_item(self.winner_avatar)
        self.add_item(self.loser_avatar)

    async def on_submit(self, interaction: discord.Interaction):
        winner_avatar, winner_error = validate_avatar_name(self.winner_avatar.value)
        loser_avatar, loser_error = validate_avatar_name(self.loser_avatar.value)
        errors = [
            f"Winner: {winner_error}" if winner_error else None,
            f"Loser: {loser_error}" if loser_error else None,
        ]
        errors = [e for e in errors if e]
        if errors:
            await interaction.response.send_message(
                "Nothing was recorded.\n" + "\n".join(errors) + "\nRun the command again with the fixed name.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        lfg_cog = self.bot.get_cog("LFGCog")
        if not lfg_cog:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)
            return
        ctx = InteractionContext(self.bot, interaction)
        if self.top16_player:
            await lfg_cog.report_challenge_as_admin(
                ctx, self.winner, self.loser, self.top16_player, winner_avatar, loser_avatar,
            )
        else:
            await lfg_cog.report_match_as_admin(ctx, self.winner, self.loser, winner_avatar, loser_avatar)
