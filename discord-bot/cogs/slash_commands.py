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

    @app_commands.command(name="lfg", description="🎮 Find a game! Join the LFG queue to be matched with other players")
    @app_commands.describe(timeframe="How many minutes you're available to play (default: 30)")
    async def lfg_slash(self, interaction: discord.Interaction, timeframe: int = 30):
        """Find a game - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.lfg(ctx, timeframe)
        else:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)

    @app_commands.command(name="lfg_check", description="🎮 Check who's currently in the LFG queue")
    async def check_lfg_slash(self, interaction: discord.Interaction):
        """Check LFG queue - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.check_lfg(ctx)
        else:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)

    @app_commands.command(name="lfg_cancel", description="🎮 Cancel your LFG request")
    async def cancel_slash(self, interaction: discord.Interaction):
        """Cancel LFG - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.cancel(ctx)
        else:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)

    @app_commands.command(name="lfg_challenge", description="🎮 Challenge a specific player to a match")
    @app_commands.describe(opponent="The player you want to challenge")
    async def challenge_slash(self, interaction: discord.Interaction, opponent: discord.Member):
        """Challenge player - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.challenge(ctx, opponent)
        else:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)

    @app_commands.command(name="lfg_record", description="🎮 Manually record a game that was played")
    async def record_game_slash(self, interaction: discord.Interaction):
        """Record game - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.record_game(ctx)
        else:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)

    @app_commands.command(name="lfg_help", description="🎮 Learn how to use the LFG system")
    async def lfg_help_slash(self, interaction: discord.Interaction):
        """LFG help - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        lfg_cog = self.bot.get_cog("LFGCog")
        if lfg_cog:
            await lfg_cog.lfg_help(ctx)
        else:
            await interaction.followup.send("LFG help is not available.", ephemeral=True)

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

    # ==================== ACHIEVEMENT COMMANDS ====================

    @app_commands.command(name="achievement_profile", description="🏆 View your achievement progress")
    @app_commands.describe(user="User to view profile for (optional)")
    async def achievement_profile_slash(self, interaction: discord.Interaction, user: discord.User = None):
        """View achievement profile - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        # If no user specified, use the command author
        target_user = user if user else interaction.user
        
        achievements_cog = self.bot.get_cog("AchievementsCog")
        if achievements_cog:
            await achievements_cog.profile(ctx, target_user)
        else:
            await interaction.followup.send("Achievement system is not available.", ephemeral=True)

    @app_commands.command(name="achievement_list", description="🏆 View all available achievements")
    async def achievement_list_slash(self, interaction: discord.Interaction):
        """View all achievements - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        achievements_cog = self.bot.get_cog("AchievementsCog")
        if achievements_cog:
            await achievements_cog.achievements_list(ctx)
        else:
            await interaction.followup.send("Achievement system is not available.", ephemeral=True)

    @app_commands.command(name="achievement_earned", description="🏆 View earned achievements")
    @app_commands.describe(user="User to check earned achievements for (optional)")
    async def achievement_earned_slash(self, interaction: discord.Interaction, user: discord.User = None):
        """View earned achievements - slash command version"""
        await interaction.response.defer()
        ctx = FakeContext(self.bot, interaction)
        
        # If no user specified, use the command author
        target_user = user if user else interaction.user
        
        achievements_cog = self.bot.get_cog("AchievementsCog")
        if achievements_cog:
            await achievements_cog.achievements_earned(ctx, target_user)
        else:
            await interaction.followup.send("Achievement system is not available.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))
