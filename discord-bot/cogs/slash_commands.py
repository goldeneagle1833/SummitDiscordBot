import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("discord_bot")


class FakeContext:
    """Fake context object to simulate command context from interaction"""

    def __init__(self, bot, interaction):
        self.bot = bot
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.interaction = interaction

    async def send(self, *args, **kwargs):
        """Send message using interaction followup"""
        return await self.interaction.followup.send(*args, **kwargs)


class SlashCommandsCog(commands.Cog):
    """
    Slash command versions of bot commands for better UX with auto-complete.
    Users can type / and see all available commands with descriptions.
    Commands are organized with prefixes: lfg_, stats_, tournament_, help_
    """

    def __init__(self, bot):
        self.bot = bot

    # ==================== LFG COMMANDS (Priority - shown first) ====================

    @app_commands.command(
        name="lfg", description="🎮 LFG System - Find games, check queue, and more"
    )
    @app_commands.describe(
        action="What do you want to do?",
        timeframe="Minutes you're available (for 'join' action, default: 30)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="🎮 Join queue to find a game (/lfg join)", value="join"
            ),
            app_commands.Choice(
                name="👀 Check who's in queue (/lfg check)", value="check"
            ),
            app_commands.Choice(
                name="❌ Cancel your request (/lfg cancel)", value="cancel"
            ),
            app_commands.Choice(
                name="📝 Record a game manually (/lfg record)", value="record"
            ),
            app_commands.Choice(name="🎬 Submit replay (/lfg replay)", value="replay"),
            app_commands.Choice(
                name="❓ Help & instructions (/lfg help)", value="help"
            ),
        ]
    )
    async def lfg_slash(
        self, interaction: discord.Interaction, action: str, timeframe: int = 30
    ):
        """Unified LFG system command"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        lfg_cog = self.bot.get_cog("LFGCog")
        if not lfg_cog:
            await interaction.followup.send(
                "LFG system is not available.", ephemeral=True
            )
            return

        if action == "join":
            await lfg_cog.lfg(ctx, timeframe)
        elif action == "check":
            await lfg_cog.check_lfg(ctx)
        elif action == "cancel":
            await lfg_cog.cancel(ctx)
        elif action == "record":
            await lfg_cog.record_game(ctx)
        elif action == "replay":
            elo_cog = self.bot.get_cog("EloCog")
            if elo_cog:
                await elo_cog.replay(ctx)
            else:
                await interaction.followup.send(
                    "Replay system is not available.", ephemeral=True
                )
        elif action == "help":
            await lfg_cog.lfg_help(ctx)

    # ==================== STATS/ELO COMMANDS ====================

    @app_commands.command(
        name="stats", description="📊 View stats, rankings, and game information"
    )
    @app_commands.describe(action="What stats do you want to see?")
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="🏅 My Elo rating & rank (/stats rank)", value="rank"
            ),
            app_commands.Choice(
                name="🏆 Leaderboard (top 16) (/stats leaderboard)", value="leaderboard"
            ),
            app_commands.Choice(
                name="📈 My detailed statistics (/stats mystats)", value="mystats"
            ),
            app_commands.Choice(
                name="🎮 My recent games (/stats mygames)", value="mygames"
            ),
        ]
    )
    async def stats_slash(self, interaction: discord.Interaction, action: str):
        """Unified stats command"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        elo_cog = self.bot.get_cog("EloCog")
        if not elo_cog:
            await interaction.followup.send(
                "Elo system is not available.", ephemeral=True
            )
            return

        if action == "rank":
            await elo_cog.rank(ctx)
        elif action == "leaderboard":
            await elo_cog.leaderboard(ctx)
        elif action == "mystats":
            await elo_cog.mystats(ctx)
        elif action == "mygames":
            await elo_cog.mygames(ctx)

    @app_commands.command(
        name="masters_bracket",
        description="🏆 View the Elo leaderboard for masters bracket members only",
    )
    async def masters_bracket_slash(self, interaction: discord.Interaction):
        """Masters bracket leaderboard"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        elo_cog = self.bot.get_cog("EloCog")
        if not elo_cog:
            await interaction.followup.send(
                "Elo system is not available.", ephemeral=True
            )
            return

        await elo_cog.masters_bracket(ctx)

    # ==================== TOURNAMENT COMMANDS ====================

    @app_commands.command(
        name="tournament",
        description="🏆 Tournament system - Join, view brackets, and more",
    )
    @app_commands.describe(
        action="What do you want to do?",
        tournament_name="Tournament name (for 'join', 'bracket', and 'create' actions)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="📝 Join a tournament (/tournament join)", value="join"
            ),
            app_commands.Choice(
                name="📊 View bracket (/tournament bracket)", value="bracket"
            ),
            app_commands.Choice(
                name="⚔️ Report match result (/tournament match_report)",
                value="match_report",
            ),
            app_commands.Choice(
                name="➕ Create tournament (Admin) (/tournament create)", value="create"
            ),
            app_commands.Choice(
                name="❓ Help & instructions (/tournament help)", value="help"
            ),
        ]
    )
    async def tournament_slash(
        self, interaction: discord.Interaction, action: str, tournament_name: str = None
    ):
        """Unified tournament command"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        tournament_cog = self.bot.get_cog("TournamentCog")
        if not tournament_cog:
            await interaction.followup.send(
                "Tournament system is not available.", ephemeral=True
            )
            return

        if action == "join":
            if not tournament_name:
                await interaction.followup.send(
                    "❌ You must specify a tournament name to join!", ephemeral=True
                )
                return
            await tournament_cog.join(ctx, tournament_name=tournament_name)
        elif action == "bracket":
            if not tournament_name:
                await interaction.followup.send(
                    "❌ You must specify a tournament name to view bracket!",
                    ephemeral=True,
                )
                return
            await tournament_cog.bracket(ctx, tournament_name=tournament_name)
        elif action == "match_report":
            await tournament_cog.my_round(ctx)
        elif action == "create":
            await tournament_cog.create_tournament(ctx)
        elif action == "help":
            await tournament_cog.tournament_help(ctx)

    # ==================== UTILITY COMMANDS ====================

    @app_commands.command(
        name="util_deckcheck",
        description="⚙️ Check if your deck is legal for tournaments",
    )
    async def deckcheck_slash(self, interaction: discord.Interaction):
        """Deck check - slash command version"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.deckcheck(ctx)
        else:
            await interaction.followup.send(
                "Utility commands are not available.", ephemeral=True
            )

    @app_commands.command(
        name="util_help", description="⚙️ Get help with bot commands and features"
    )
    async def help_slash(self, interaction: discord.Interaction):
        """Help - slash command version"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.show_help(ctx)
        else:
            await interaction.followup.send("Help is not available.", ephemeral=True)

    @app_commands.command(
        name="util_commands", description="⚙️ View all available bot commands"
    )
    async def commands_slash(self, interaction: discord.Interaction):
        """Commands list - slash command version"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.commands(ctx)
        else:
            await interaction.followup.send(
                "Commands list is not available.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))
