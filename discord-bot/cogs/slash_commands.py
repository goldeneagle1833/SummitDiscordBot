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

    @app_commands.command(name="lfg", description="🎮 LFG System - Find games, check queue, and more")
    @app_commands.describe(
        action="What do you want to do?",
        timeframe="Minutes you're available (for 'join' action, default: 30)",
        opponent="Player to challenge (for 'challenge' action)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="🎮 Join queue to find a game", value="join"),
        app_commands.Choice(name="👀 Check who's in queue", value="check"),
        app_commands.Choice(name="❌ Cancel your request", value="cancel"),
        app_commands.Choice(name="⚔️ Challenge specific player", value="challenge"),
        app_commands.Choice(name="📝 Record a game manually", value="record"),
        app_commands.Choice(name="❓ Help & instructions", value="help")
    ])
    async def lfg_slash(
        self, 
        interaction: discord.Interaction, 
        action: str,
        timeframe: int = 30,
        opponent: discord.Member = None
    ):
        """Unified LFG system command"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if not lfg_cog:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)
            return
        
        if action == "join":
            await lfg_cog.lfg(ctx, timeframe)
        elif action == "check":
            await lfg_cog.check_lfg(ctx)
        elif action == "cancel":
            await lfg_cog.cancel(ctx)
        elif action == "challenge":
            if not opponent:
                await interaction.followup.send("❌ You must specify an opponent to challenge!", ephemeral=True)
                return
            await lfg_cog.challenge(ctx, opponent)
        elif action == "record":
            await lfg_cog.record_game(ctx)
        elif action == "help":
            await lfg_cog.lfg_help(ctx)

    # ==================== STATS/ELO COMMANDS ====================

    @app_commands.command(name="stats_rank", description="📊 Check your current Elo rating and rank")
    async def rank_slash(self, interaction: discord.Interaction):
        """Check rank - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.rank(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    # ==================== STATS/ELO COMMANDS ====================

    @app_commands.command(name="stats_rank", description="📊 Check your current Elo rating and rank")
    async def rank_slash(self, interaction: discord.Interaction):
        """Check rank - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.rank(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    @app_commands.command(name="stats_leaderboard", description="📊 View the top 10 Elo rankings")
    async def leaderboard_slash(self, interaction: discord.Interaction):
        """Check leaderboard - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.leaderboard(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    @app_commands.command(name="stats_mystats", description="📊 View your detailed match statistics and performance")
    async def mystats_slash(self, interaction: discord.Interaction):
        """Check stats - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.mystats(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    @app_commands.command(name="stats_mygames", description="📊 View your recent game history")
    async def mygames_slash(self, interaction: discord.Interaction):
        """Check games - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.mygames(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    @app_commands.command(name="stats_replay", description="📊 Submit a replay of your game")
    async def replay_slash(self, interaction: discord.Interaction):
        """Submit replay - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        elo_cog = self.bot.get_cog("EloCog")
        if elo_cog:
            await elo_cog.replay(ctx)
        else:
            await interaction.followup.send("Elo system is not available.", ephemeral=True)

    # ==================== TOURNAMENT COMMANDS ====================

    @app_commands.command(name="tournament_create", description="🏆 Create a new tournament (Admin)")
    async def create_tournament_slash(self, interaction: discord.Interaction):
        """Create tournament - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        tournament_cog = self.bot.get_cog("TournamentCog")
        if tournament_cog:
            await tournament_cog.create_tournament(ctx)
        else:
            await interaction.followup.send("Tournament system is not available.", ephemeral=True)

    @app_commands.command(name="tournament_join", description="🏆 Join a tournament")
    @app_commands.describe(tournament_name="Name of the tournament to join")
    async def join_tournament_slash(self, interaction: discord.Interaction, tournament_name: str):
        """Join tournament - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        tournament_cog = self.bot.get_cog("TournamentCog")
        if tournament_cog:
            await tournament_cog.join(ctx, tournament_name=tournament_name)
        else:
            await interaction.followup.send("Tournament system is not available.", ephemeral=True)

    @app_commands.command(name="tournament_match", description="🏆 Check your current tournament match")
    async def my_match_slash(self, interaction: discord.Interaction):
        """Check match - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        tournament_cog = self.bot.get_cog("TournamentCog")
        if tournament_cog:
            await tournament_cog.my_round(ctx)
        else:
            await interaction.followup.send("Tournament system is not available.", ephemeral=True)

    @app_commands.command(name="tournament_bracket", description="🏆 View tournament bracket")
    @app_commands.describe(tournament_name="Name of the tournament")
    async def bracket_slash(self, interaction: discord.Interaction, tournament_name: str):
        """View bracket - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        tournament_cog = self.bot.get_cog("TournamentCog")
        if tournament_cog:
            await tournament_cog.bracket(ctx, tournament_name=tournament_name)
        else:
            await interaction.followup.send("Tournament system is not available.", ephemeral=True)

    @app_commands.command(name="tournament_help", description="🏆 Learn about tournament features")
    async def tournament_help_slash(self, interaction: discord.Interaction):
        """Tournament help - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        tournament_cog = self.bot.get_cog("TournamentCog")
        if tournament_cog:
            await tournament_cog.tournament_help(ctx)
        else:
            await interaction.followup.send("Tournament help is not available.", ephemeral=True)

    # ==================== UTILITY COMMANDS ====================

    @app_commands.command(name="util_deckcheck", description="⚙️ Check if your deck is legal for tournaments")
    async def deckcheck_slash(self, interaction: discord.Interaction):
        """Deck check - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.deckcheck(ctx)
        else:
            await interaction.followup.send("Utility commands are not available.", ephemeral=True)

    @app_commands.command(name="util_help", description="⚙️ Get help with bot commands and features")
    async def help_slash(self, interaction: discord.Interaction):
        """Help - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.show_help(ctx)
        else:
            await interaction.followup.send("Help is not available.", ephemeral=True)

    @app_commands.command(name="util_commands", description="⚙️ View all available bot commands")
    async def commands_slash(self, interaction: discord.Interaction):
        """Commands list - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        utility_cog = self.bot.get_cog("UtilityCog")
        if utility_cog:
            await utility_cog.commands(ctx)
        else:
            await interaction.followup.send("Commands list is not available.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))
