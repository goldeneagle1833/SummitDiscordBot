import discord
from discord.ext import commands
import datetime
import logging
from random import randrange

from utils.database import winner_report, losser_report, solo_match_report
from utils.constants import SORCERY_NICKNAMES

logger = logging.getLogger("discord_bot")

# In-memory LFG queue (user_id: {timestamp, timeframe})
lfg_queue = {}


class MatchReportModal(discord.ui.Modal, title="Match Report"):
    curiosa_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="Enter Your Curiosa Deck URL",
        required=False,
    )

    first_player = discord.ui.TextInput(
        label="Did you go first? (y/n)",
        placeholder="Enter YES or NO",
        required=False,
        max_length=3,
    )

    match_time = discord.ui.TextInput(
        label="Match time",
        placeholder="Estimate match time in minutes (eg. 30)",
        required=False,
        max_length=3,
        min_length=1,
    )

    match_comment = discord.ui.TextInput(
        label="Notes",
        placeholder="Anything else about the match?",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, winner_id, winner_global, loser_id, loser_global, is_winner):
        super().__init__()
        self.winner_id = winner_id
        self.winner_global = winner_global
        self.loser_id = loser_id
        self.loser_global = loser_global
        self.is_winner = is_winner

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        interaction_user_id = interaction.user.id
        interaction_global = interaction.user.global_name

        curiosa_link = (
            self.curiosa_url.value if self.curiosa_url.value else "No URL provided"
        )
        match_comment = self.match_comment.value if self.match_comment.value else ""
        first_player = self.first_player.value if self.first_player.value else "n"
        match_time = (
            int(self.match_time.value) if self.match_time.value.isdigit() else 0
        )

        if self.is_winner:
            winner_report(
                interaction_user_id,
                self.winner_id,
                self.winner_global,
                True,
                self.loser_id,
                self.loser_global,
                first_player,
                match_time,
                curiosa_link,
                match_comment,
                interaction_user_id,
                interaction_global,
            )
        else:
            losser_report(
                interaction_user_id,
                self.winner_id,
                self.winner_global,
                False,
                self.loser_id,
                self.loser_global,
                first_player,
                match_time,
                curiosa_link,
                match_comment,
                interaction_user_id,
                interaction_global,
            )

        await interaction.followup.send(
            f"✅ Match report submitted!\n**Winner:** {self.winner_global}\n**Loser:** {self.loser_global}",
            ephemeral=True,
        )


class LFGReportButtons(discord.ui.View):
    def __init__(
        self,
        match_id: int,
        player1_id: int,
        player1_global: str,
        player2_id: int,
        player2_global: str,
    ):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_global = player1_global
        self.player2_global = player2_global

    @discord.ui.button(
        label="I Won!", style=discord.ButtonStyle.success, custom_id="win_button"
    )
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        opponent_id = (
            self.player2_id
            if interaction.user.id == self.player1_id
            else self.player1_id
        )
        opponent_global = (
            self.player2_global
            if interaction.user.id == self.player1_id
            else self.player1_global
        )

        await interaction.response.send_modal(
            MatchReportModal(
                winner_id=interaction.user.id,
                winner_global=interaction.user.global_name,
                loser_id=opponent_id,
                loser_global=opponent_global,
                is_winner=True,
            )
        )
        await interaction.message.edit(view=None)

    @discord.ui.button(
        label="I Lost", style=discord.ButtonStyle.danger, custom_id="lose_button"
    )
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        opponent_id = (
            self.player2_id
            if interaction.user.id == self.player1_id
            else self.player1_id
        )
        opponent_global = (
            self.player2_global
            if interaction.user.id == self.player1_id
            else self.player1_global
        )

        await interaction.response.send_modal(
            MatchReportModal(
                winner_id=opponent_id,
                winner_global=opponent_global,
                loser_id=interaction.user.id,
                loser_global=interaction.user.global_name,
                is_winner=False,
            )
        )
        await interaction.message.edit(view=None)

    @discord.ui.button(
        label="We didn't play/cancel match",
        style=discord.ButtonStyle.blurple,
        custom_id="cancel_match",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            f"{interaction.user.mention} clicked **cancel match**", ephemeral=True
        )
        await interaction.message.edit(view=None)


class ChallengeButtons(discord.ui.View):
    def __init__(self, challenger_id: int, challenger_global: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.challenger_global = challenger_global

    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.success)
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        challenger = await interaction.client.fetch_user(self.challenger_id)

        # Send match report buttons to both players
        challenger_view = LFGReportButtons(
            0,  # match_id not needed for direct challenges
            self.challenger_id,
            self.challenger_global,
            interaction.user.id,
            interaction.user.global_name,
        )

        opponent_view = LFGReportButtons(
            0,  # match_id not needed for direct challenges
            interaction.user.id,
            interaction.user.global_name,
            self.challenger_id,
            self.challenger_global,
        )

        await challenger.send("Match report:", view=challenger_view)
        await interaction.response.send_message("Match report:", view=opponent_view)
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


class ReportButtonsSolo(discord.ui.View):
    def __init__(self, reporter_id: int, reporter_global: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global

    @discord.ui.button(label="I Won!", style=discord.ButtonStyle.success)
    async def won_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            SoloMatchReportModal(
                reporter_id=self.reporter_id,
                reporter_global=self.reporter_global,
                is_winner=True,
            )
        )
        await interaction.message.edit(view=None)

    @discord.ui.button(label="I Lost", style=discord.ButtonStyle.danger)
    async def lost_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            SoloMatchReportModal(
                reporter_id=self.reporter_id,
                reporter_global=self.reporter_global,
                is_winner=False,
            )
        )
        await interaction.message.edit(view=None)


class SoloMatchReportModal(discord.ui.Modal, title="Solo Match Report"):
    opponent_name = discord.ui.TextInput(
        label="Opponent's Name",
        placeholder="Enter your opponent's name",
        required=False,
    )

    curiosa_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="Enter Your Curiosa Deck URL",
        required=False,
    )

    first_player = discord.ui.TextInput(
        label="Did you go first? (y/n)",
        placeholder="Enter YES or NO",
        required=False,
        max_length=3,
    )

    match_time = discord.ui.TextInput(
        label="Match time",
        placeholder="Estimate match time in minutes (eg. 30)",
        required=False,
        max_length=3,
        min_length=1,
    )

    match_comment = discord.ui.TextInput(
        label="Notes",
        placeholder="Anything else about the match?",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, reporter_id: int, reporter_global: str, is_winner: bool):
        super().__init__()
        self.reporter_id = reporter_id
        self.reporter_global = reporter_global
        self.is_winner = is_winner

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        curiosa_link = (
            self.curiosa_url.value if self.curiosa_url.value else "No URL provided"
        )
        match_comment = self.match_comment.value if self.match_comment.value else ""
        first_player = self.first_player.value if self.first_player.value else "n"
        match_time = (
            int(self.match_time.value) if self.match_time.value.isdigit() else 0
        )

        solo_match_report(
            reporter_id=self.reporter_id,
            reporter_global=self.reporter_global,
            opponent_name=self.opponent_name.value,
            is_winner=self.is_winner,
            first_player=first_player,
            match_time=match_time,
            curiosa_link=curiosa_link,
            match_comment=match_comment,
        )

        result = "Won" if self.is_winner else "Lost"
        await interaction.followup.send(
            f"✅ Solo match report submitted!\n**Result:** {result}\n**Opponent:** {self.opponent_name.value}",
            ephemeral=True,
        )


class LFGCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def check_if_someone_is_lfg(self, ctx):
        now = datetime.datetime.now()
        for user_id, info in lfg_queue.items():
            timestamp = info["timestamp"]
            timeframe = info["timeframe"]
            if (now - timestamp).total_seconds() < timeframe * 60:
                return user_id
        return None

    def add_to_lfg_queue(self, ctx, timeframe):
        lfg_queue[ctx.author.id] = {
            "timestamp": datetime.datetime.now(),
            "timeframe": int(timeframe),
        }

    def pair_players(self, ctx):
        now = datetime.datetime.now()
        for user_id, info in lfg_queue.items():
            if (
                user_id != ctx.author.id
                and (now - info["timestamp"]).total_seconds() < info["timeframe"] * 60
            ):
                matched_user_id = user_id
                lfg_queue.pop(matched_user_id, None)
                lfg_queue.pop(ctx.author.id, None)
                logger.info(f"Pairing {matched_user_id} with {ctx.author.id}")
                return matched_user_id
        return None

    def clean_expired_lfg(self):
        now = datetime.datetime.now()
        expired = [
            user_id
            for user_id, info in lfg_queue.items()
            if (now - info["timestamp"]).total_seconds() > info["timeframe"] * 60
        ]
        for user_id in expired:
            lfg_queue.pop(user_id)

    @commands.command()
    async def lfg(self, ctx, timeframe: int = 30):
        """Usage: !lfg [minutes]"""
        self.clean_expired_lfg()
        owner_id = 296846802924208130
        channel_id = 1336912830867439676
        owner = await self.bot.fetch_user(owner_id)
        lfg_channel = self.bot.get_channel(channel_id)

        if owner:
            await owner.send(f"{ctx.author} used the !lfg command in #{ctx.channel}.")

        matched_user_id = self.check_if_someone_is_lfg(ctx)
        if matched_user_id and matched_user_id != ctx.author.id:
            matched_user = await self.bot.fetch_user(matched_user_id)
            view_ctx = LFGReportButtons(
                ctx.author.id,
                ctx.author.id,
                ctx.author.global_name,
                matched_user_id,
                matched_user.global_name,
            )
            await ctx.author.send("Match report:", view=view_ctx)
            await ctx.send(
                f"{ctx.author.mention}, matched with {matched_user.mention} who is also looking for a game!"
            )

            view_matched = LFGReportButtons(
                matched_user_id,
                matched_user_id,
                matched_user.global_name,
                ctx.author.id,
                ctx.author.global_name,
            )
            await matched_user.send(
                f"You've been matched with {ctx.author.mention} for a game!",
                view=view_matched,
            )
            self.pair_players(ctx)
            await lfg_channel.send(
                f"A match was found! {SORCERY_NICKNAMES[randrange(0, len(SORCERY_NICKNAMES))]} and "
                f"{SORCERY_NICKNAMES[randrange(0, len(SORCERY_NICKNAMES))]} have been paired for a game."
            )
        elif matched_user_id == ctx.author.id:
            await ctx.send(
                f"{ctx.author.mention}, you are already in the LFG queue. Please wait for someone to match with you."
            )
        else:
            self.add_to_lfg_queue(ctx, timeframe)
            await ctx.author.send(
                f"You have been added to the queue for looking for a game for "
                f"{timeframe} minutes. You can also use the `!lfg` command here to join the queue privately."
            )
            if lfg_channel:
                await lfg_channel.send(
                    f"A {SORCERY_NICKNAMES[randrange(0, len(SORCERY_NICKNAMES))]} is now looking for a game "
                    f"for {timeframe} minutes! Message me with the `!lfg` command to join them."
                )

        logger.info(f"LFG command invoked by {ctx.author}")

    @commands.command()
    async def checklfg(self, ctx):
        """Check if anyone is currently in the LFG queue."""
        self.clean_expired_lfg()
        if len(lfg_queue) > 0:
            await ctx.send(f"{ctx.author.mention}, yes, someone is in the queue!")
        else:
            await ctx.send(f"{ctx.author.mention}, no one is currently in the queue.")

    @commands.command()
    async def cancel(self, ctx):
        """Cancel your LFG queue status."""
        channel_id = 1336912830867439676
        lfg_channel = self.bot.get_channel(channel_id)
        if ctx.author.id in lfg_queue:
            lfg_queue.pop(ctx.author.id)
            await ctx.send(
                f"{ctx.author.mention}, you have been removed from the LFG queue."
            )
            if len(lfg_queue) == 0 and lfg_channel:
                await lfg_channel.send("No one is currently looking for a game.")
        else:
            await ctx.send(
                f"{ctx.author.mention}, you are not currently in the LFG queue."
            )

    @commands.command()
    async def challenge(self, ctx, opponent: discord.Member):
        """Challenge a specific player to a match"""
        # Delete the original command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass  # If bot doesn't have permission to delete messages

        if opponent.id == ctx.author.id:
            await ctx.send("You cannot challenge yourself!", ephemeral=True)
            return

        if opponent.bot:
            await ctx.send("You cannot challenge a bot!", ephemeral=True)
            return

        view = ChallengeButtons(ctx.author.id, ctx.author.global_name)

        try:
            await opponent.send(
                f"{ctx.author.global_name} has challenged you to a match!",
                view=view,
            )
            await ctx.author.send(
                f"Challenge sent to {opponent.global_name}! They have 5 minutes to accept.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await ctx.send(
                f"I couldn't send a DM to {opponent.global_name}. They might have DMs disabled.",
                ephemeral=True,
            )

    @commands.command()
    async def help_lfg(self, ctx):
        """Get detailed help for the Looking For Game (LFG) system."""
        embed = discord.Embed(
            title="🎮 Looking For Game (LFG) System",
            description="Find matches and challenge other players with these commands:",
            color=discord.Color.blue(),
        )

        # Queue Commands
        embed.add_field(
            name="🔍 Queue Commands",
            value=(
                "`!lfg [minutes]` - Join queue for X minutes (default 30)\n"
                "`!checklfg` - See if anyone is in queue\n"
                "`!cancel` - Leave the queue"
            ),
            inline=False,
        )

        # Challenge System
        embed.add_field(
            name="⚔️ Challenge System",
            value=(
                "`!challenge @user` - Challenge specific player\n"
                "Note: Must be used in the LFG channel to tag opponent"
            ),
            inline=False,
        )

        # Match Reporting
        embed.add_field(
            name="📝 Match Reporting",
            value=(
                "After matching or accepting a challenge:\n"
                "• Both players get match report buttons in DMs\n"
                "• Report win/loss using the buttons\n"
                "• Optional: Add deck URL and match details"
            ),
            inline=False,
        )

        # Tips & Info
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Queue time can be 5-120 minutes\n"
                "• Direct challenges expire after 5 minutes\n"
            ),
            inline=False,
        )

        embed.set_footer(text="Type !help for a list of all available commands")

        await ctx.send(embed=embed)

    @commands.command()
    async def record_game(self, ctx):
        """Submit a match report without being matched through LFG"""
        # Create view with both buttons
        view = ReportButtonsSolo(ctx.author.id, ctx.author.global_name)

        try:
            await ctx.author.send("Please select match outcome:", view=view)
            await ctx.send("Check your DMs to submit the match report!", ephemeral=True)
        except discord.Forbidden:
            await ctx.send(
                "I couldn't send you a DM. Please enable DMs from server members.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(LFGCog(bot))
