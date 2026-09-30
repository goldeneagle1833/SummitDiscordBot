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
            await elo_cog.leaderboard(ctx)
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
    @app_commands.describe(
        voice="Play the challenge on voice chat or not (default: voice)",
        deck_url="Your deck link (required in Avatar-mode seasons: it sets your avatar)",
    )
    @app_commands.choices(voice=[
        app_commands.Choice(name="🔊 Voice", value="voice"),
        app_commands.Choice(name="🔇 No voice", value="no_voice"),
    ])
    async def issue_challenge_slash(
        self, interaction: discord.Interaction, voice: str = "voice", deck_url: str = None,
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

        await lfg_cog.issue_challenge(ctx, voice, *([deck_url] if deck_url else []))

    # ==================== ADMIN MATCH REPORTS ====================

    async def _admin_report_flow(self, interaction, winner, loser, top16_player=None):
        """Avatar mode asks for both avatars in a form; Player mode reports right away."""
        from cogs.lfg.admin_avatar_report import AdminAvatarReportModal
        from services.avatar_mode import is_avatar_mode
        from utils.checks import check_is_admin

        ctx = FakeContext(self.bot, interaction)
        if not isinstance(interaction.user, discord.Member) or not check_is_admin(ctx):
            await interaction.response.send_message(
                "You need administrator permissions to use this command.", ephemeral=True
            )
            return
        if winner.id == loser.id:
            await interaction.response.send_message(
                "Winner and loser cannot be the same player!", ephemeral=True
            )
            return

        if is_avatar_mode():
            await interaction.response.send_modal(
                AdminAvatarReportModal(self.bot, winner, loser, top16_player)
            )
            return

        await interaction.response.defer()
        lfg_cog = self.bot.get_cog("LFGCog")
        if not lfg_cog:
            await interaction.followup.send("LFG system is not available.", ephemeral=True)
            return
        if top16_player:
            await lfg_cog.report_challenge_as_admin(ctx, winner, loser, top16_player)
        else:
            await lfg_cog.report_match_as_admin(ctx, winner, loser)

    @app_commands.command(
        name="admin-report",
        description="(Admin) Report a match result; asks for both avatars in Avatar-mode seasons",
    )
    @app_commands.describe(winner="The player who won", loser="The player who lost")
    async def admin_report_slash(
        self, interaction: discord.Interaction, winner: discord.Member, loser: discord.Member,
    ):
        await self._admin_report_flow(interaction, winner, loser)

    @app_commands.command(
        name="admin-challenge-report",
        description="(Admin) Report a ladder challenge; asks for both avatars in Avatar-mode seasons",
    )
    @app_commands.describe(
        winner="The player who won",
        loser="The player who lost",
        top16_player="The Top 16 player who issued the challenge (winner or loser)",
    )
    async def admin_challenge_report_slash(
        self, interaction: discord.Interaction,
        winner: discord.Member, loser: discord.Member, top16_player: discord.Member,
    ):
        if top16_player.id not in (winner.id, loser.id):
            await interaction.response.send_message(
                "The Top 16 player must be either the winner or the loser!", ephemeral=True
            )
            return
        await self._admin_report_flow(interaction, winner, loser, top16_player)

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

    # ==================== PAIRING BANS (ADMIN ONLY) ====================

    @app_commands.command(
        name="ban",
        description="🔧 [ADMIN] Block a player from the pairing service (opens a form)",
    )
    @app_commands.describe(member="The player to block")
    @app_commands.default_permissions(administrator=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member):
        """Opens the ban modal directly (slash commands can respond with a modal)."""
        from cogs.pairing_bans import member_is_admin

        if not member_is_admin(interaction.user):
            await interaction.response.send_message(
                "You need administrator permissions to use this command.", ephemeral=True
            )
            return
        ban_cog = self.bot.get_cog("PairingBanCog")
        if not ban_cog:
            await interaction.response.send_message(
                "Pairing bans are not available.", ephemeral=True
            )
            return
        error = ban_cog.validate_target(interaction.user, member)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await interaction.response.send_modal(ban_cog.build_ban_modal(member, interaction.user))

    @app_commands.command(
        name="unban",
        description="🔧 [ADMIN] Lift a player's pairing service block",
    )
    @app_commands.describe(member="The player to unblock")
    @app_commands.default_permissions(administrator=True)
    async def unban_slash(self, interaction: discord.Interaction, member: discord.Member):
        from cogs.pairing_bans import member_is_admin

        await interaction.response.defer(ephemeral=True)
        if not member_is_admin(interaction.user):
            await interaction.followup.send(
                "You need administrator permissions to use this command.", ephemeral=True
            )
            return
        ban_cog = self.bot.get_cog("PairingBanCog")
        if not ban_cog:
            await interaction.followup.send("Pairing bans are not available.", ephemeral=True)
            return
        embed = await ban_cog.apply_unban(member, interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommandsCog(bot))
