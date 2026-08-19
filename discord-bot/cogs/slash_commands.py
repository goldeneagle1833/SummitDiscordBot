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
    Commands are organized with prefixes: lfg_, stats_, help_
    """

    def __init__(self, bot):
        self.bot = bot

    # ==================== LFG COMMANDS (Priority - shown first) ====================

    @app_commands.command(
        name="lfg", description="🎮 LFG System - Find games, check queue, and more"
    )
    @app_commands.describe(
        action="What do you want to do?",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="👀 Check who's in queue (/lfg check)", value="check"
            ),
            app_commands.Choice(
                name="❓ Help & instructions (/lfg help)", value="help"
            ),
        ]
    )
    async def lfg_slash(
        self, interaction: discord.Interaction, action: str
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

        if action == "check":
            await lfg_cog.check_lfg(ctx)
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
                name="🔎 Match Elo details (/stats match_elo)", value="match_elo"
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
            await elo_cog.event_leaderboard(ctx)
        elif action == "match_elo":
            await interaction.followup.send(
                "Use `!match_elo <match_id>` for now.",
                ephemeral=True,
            )

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

    # ==================== LADDER CHALLENGE ====================

    @app_commands.command(
        name="issue-challenge",
        description="Issue a ladder challenge (Top 16 event players only, once per day)",
    )
    @app_commands.describe(avatar="Avatar card name (required in avatar-specific events)")
    async def issue_challenge_slash(
        self,
        interaction: discord.Interaction,
        avatar: str | None = None,
    ):
        """Ladder challenge - Top 16 event players can challenge the field with special ELO stakes"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        lfg_cog = self.bot.get_cog("LFGCog")
        if not lfg_cog:
            await interaction.followup.send(
                "LFG system is not available.", ephemeral=True
            )
            return

        await lfg_cog.issue_challenge(ctx, avatar_name=avatar)

    # ==================== UTILITY COMMANDS ====================

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

    # ==================== COMMUNITY MANAGEMENT (ADMIN ONLY) ====================

    @app_commands.command(
        name="add_discord_server",
        description="🔧 [ADMIN] Add a Discord server to the community list",
    )
    @app_commands.describe(
        name="Server name",
        invite_url="Discord invite URL (e.g., https://discord.gg/abc123)",
        location="Location (e.g., CA, United States, Europe, etc.)",
        description="Optional description of the server",
    )
    @app_commands.default_permissions(administrator=True)
    async def add_discord_server_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        invite_url: str,
        location: str,
        description: str = "",
    ):
        """Add a Discord server to the community database"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        community_cog = self.bot.get_cog("CommunityCog")
        if not community_cog:
            await interaction.followup.send(
                "Community system is not available.", ephemeral=True
            )
            return

        await community_cog._add_discord_server(ctx, name, invite_url, location, description)

    @app_commands.command(
        name="add_youtube_channel",
        description="🔧 [ADMIN] Add a YouTube channel to the community list",
    )
    @app_commands.describe(
        name="Channel name",
        channel_id="YouTube channel ID (e.g., UCzWglR4ytbyq0aAfWrNaMHw)",
        channel_url="Full YouTube channel URL",
    )
    @app_commands.default_permissions(administrator=True)
    async def add_youtube_channel_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        channel_id: str,
        channel_url: str,
    ):
        """Add a YouTube channel to the community database"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        community_cog = self.bot.get_cog("CommunityCog")
        if not community_cog:
            await interaction.followup.send(
                "Community system is not available.", ephemeral=True
            )
            return

        await community_cog._add_youtube_channel(ctx, name, channel_id, channel_url)

    @app_commands.command(
        name="add_website",
        description="🔧 [ADMIN] Add a website to the community list",
    )
    @app_commands.describe(
        name="Website name",
        url="Website URL",
        description="Optional description of the website",
    )
    @app_commands.default_permissions(administrator=True)
    async def add_website_slash(
        self,
        interaction: discord.Interaction,
        name: str,
        url: str,
        description: str = "",
    ):
        """Add a website to the community database"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        community_cog = self.bot.get_cog("CommunityCog")
        if not community_cog:
            await interaction.followup.send(
                "Community system is not available.", ephemeral=True
            )
            return

        await community_cog._add_website(ctx, name, url, description)

    @app_commands.command(
        name="remove_community_entry",
        description="🔧 [ADMIN] Remove a community entry by ID",
    )
    @app_commands.describe(
        entry_type="Type of entry to remove",
        entry_id="ID of the entry (use /list_community to see IDs)",
    )
    @app_commands.choices(
        entry_type=[
            app_commands.Choice(name="Discord Server", value="discord"),
            app_commands.Choice(name="YouTube Channel", value="youtube"),
            app_commands.Choice(name="Website", value="website"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def remove_community_entry_slash(
        self, interaction: discord.Interaction, entry_type: str, entry_id: int
    ):
        """Remove a community entry from the database"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        community_cog = self.bot.get_cog("CommunityCog")
        if not community_cog:
            await interaction.followup.send(
                "Community system is not available.", ephemeral=True
            )
            return

        await community_cog._remove_community_entry(ctx, entry_type, entry_id)

    @app_commands.command(
        name="list_community",
        description="🔧 [ADMIN] List all community entries with IDs",
    )
    @app_commands.default_permissions(administrator=True)
    async def list_community_slash(self, interaction: discord.Interaction):
        """List all community entries"""
        await interaction.response.defer(ephemeral=True)
        ctx = FakeContext(self.bot, interaction)

        community_cog = self.bot.get_cog("CommunityCog")
        if not community_cog:
            await interaction.followup.send(
                "Community system is not available.", ephemeral=True
            )
            return

        await community_cog.list_community_cmd(ctx)


async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))
