import datetime
import discord
from discord.ext import commands
import requests
import json
import logging
import random

from utils.deck_checker import get_deck_id, find_card
from utils.checks import is_bot_admin

logger = logging.getLogger("discord_bot")


class DeckCheckModal(discord.ui.Modal, title="Deck Check"):
    deck_url = discord.ui.TextInput(
        label="Curiosa Deck URL",
        placeholder="Enter Your Curiosa Deck URL",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        deck_url = self.deck_url.value

        try:
            deck_id = get_deck_id(deck_url)
            response = requests.get("https://curiosa.io/api/decks?ids=" + deck_id)

            if response.status_code != 200:
                await interaction.followup.send(
                    f"Failed to retrieve deck data. Status code: {response.status_code}",
                    ephemeral=True,
                )
                return

            json_data = json.loads(response.text)

            invalid_cards = find_card(json_data, "Ring of Morrigan")

            if invalid_cards:
                await interaction.followup.send(
                    "Your deck is NOT legal! ❌ It contains the xxx cards.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "Your deck is legal! ✅",
                    ephemeral=True,
                )

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


class DeckCheckButton(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(
        label="Check Deck", style=discord.ButtonStyle.primary, custom_id="deck_check"
    )
    async def deck_check_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = DeckCheckModal()
        await interaction.response.send_modal(modal)


class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def deckcheck(self, ctx):
        """Opens a modal to check if a Curiosa deck is legal."""
        view = DeckCheckButton()
        await ctx.send("Click the button to check your deck:", view=view)

    @commands.command(name="help")
    async def show_help(self, ctx):
        """Show all available commands and their descriptions"""
        embed = discord.Embed(
            title="📖 Summit Bot Commands",
            description="Quick reference for all available commands:",
            color=discord.Color.blue(),
        )

        # LFG System
        embed.add_field(
            name="🎮 Looking For Game",
            value=(
                "`!lfg` - Join matchmaking queue\n"
                "`!cancel` - Leave the queue\n"
                "`!challenge @user` - Challenge a player\n"
                "`!record_game` - Report external match\n"
                "`!game_activity` - View recent activity\n"
                "➡️ Use `!lfg_help` for details"
            ),
            inline=False,
        )

        # Rankings & Stats
        embed.add_field(
            name="📊 Rankings & Stats",
            value=(
                "`!rank` - Check your Elo ranking\n"
                "`!leaderboard` - View top 10 rankings\n"
                "`!mystats` - Your match history summary\n"
                "`!mygames` - List recent games\n"
                "`!replay` - View last match details"
            ),
            inline=False,
        )

        # Fun System
        embed.add_field(
            name="💨 Fart Game",
            value=(
                "`!fart` `!fart_gift` `!fartrank`\n"
                "`!fartprediction` `!fart_shop`\n"
                "➡️ Use `!helpfart` for details"
            ),
            inline=False,
        )

        # Shop
        embed.add_field(
            name="🛒 Item Shop",
            value=(
                "`!fart_shop` `!blue_shell` `!red_shell`\n"
                "`!green_shell` `!banana` `!star`"
            ),
            inline=False,
        )

        # Dust Codes
        embed.add_field(
            name="Dust Codes",
            value=(
                "`!donatedust` - Donate a dust code (DM only)\n"
                "Codes drop randomly after matches!"
            ),
            inline=False,
        )

        # Utility
        embed.add_field(
            name="🛠️ Utility",
            value=(
                "`!help` - This message\n"
                "`!list_commands` - Full command list\n"
                "`!deckcheck` - Check Curiosa deck legality"
            ),
            inline=False,
        )

        # Admin Commands
        embed.add_field(
            name="🔧 Admin Commands",
            value="`!admin_help` - View admin commands (requires administrator, Bot Admin, or Judge role)",
            inline=False,
        )

        embed.set_footer(text="Use !list_commands for the complete detailed list")

        await ctx.send(embed=embed)

    @commands.command()
    async def list_commands(self, ctx):
        """List all available bot commands."""
        embed = discord.Embed(
            title="📋 Summit Discord Bot Commands",
            description="Here's a complete list of all available commands:",
            color=discord.Color.blurple(),
        )

        # LFG System Commands
        embed.add_field(
            name="🎮 Looking For Game (LFG)",
            value=(
                "`!lfg_help` - Learn how to use the LFG system\n"
                "`!lfg [minutes]` - Join queue for X minutes (default 30)\n"
                "`!check_lfg` - Check who's in queue\n"
                "`!challenge @user` - Challenge specific player\n"
                "`!cancel` - Leave the queue\n"
                "`!record_game` - Record a match result manually\n"
                "`!game_activity [hours]` - View games reported recently"
            ),
            inline=False,
        )

        # Rankings & Stats Commands
        embed.add_field(
            name="📊 Rankings & Statistics",
            value=(
                "`!rank` - Check your Elo ranking\n"
                "`!leaderboard` - View top 10 Elo rankings\n"
                "`!mystats` - Get a summary of your match history\n"
                "`!mygames` - List your recent games\n"
                "`!replay` - Replay your last match"
            ),
            inline=False,
        )

        # Dust Code System
        embed.add_field(
            name="Dust Codes",
            value=(
                "`!donatedust 11111 22222 33333 44444` - Donate a dust code (DM only)\n"
                "`!dustcodes` - Check remaining codes (admin only)\n"
                "Dust codes drop randomly after confirmed matches. One per player per season."
            ),
            inline=False,
        )

        # Utility Commands
        embed.add_field(
            name="🛠️ Utility",
            value=(
                "`!help` - Show help message\n"
                "`!list_commands` - Show this command list\n"
                "`!deckcheck` - Check Curiosa deck legality"
            ),
            inline=False,
        )

        # Fun & Fart System Commands
        embed.add_field(
            name="🎲 Fun System",
            value=(
                "Daily Actions:\n"
                "`!fart` - Roll for daily fart points\n"
                "`!fart_gift @user` - Roll your daily fart for someone else (once/season per player)\n"
                "`!fartprediction` - Predict fart type for 2x points\n"
                "`!bullfart` - Get bonus points (weekly)\n\n"
                "Shop & Items:\n"
                "`!fart_shop` - View available items\n"
                "`!blue_shell` - Hit leader with 6d20/2 (20 pts, once/day)\n"
                "`!red_shell` - Hit player in front with 3d20/2 (10 pts)\n"
                "`!green_shell` - Hit random front player\n"
                "`!banana` - Hit random player behind\n"
                "`!star` - Get 72h protection (10% pts, once/week)\n\n"
                "Scores & Stats:\n"
                "`!fartrank` - Check your score and ranking\n"
                "`!fartleaderboard` - View top 5 farters\n"
                "`!helpfart` - View detailed fart commands"
            ),
            inline=False,
        )

        # Leader-Only Commands
        embed.add_field(
            name="👑 Leader Commands",
            value=(
                "`!fartlord` - Make grand proclamation\n"
                "`!taxes` - Take 20% from everyone (once per reign)\n"
                "`!wealth` - Redistribute 50% from top 5 (once per reign)"
            ),
            inline=False,
        )

        # Admin Commands
        embed.add_field(
            name="🔧 Admin Commands",
            value=(
                "`!admin_help` - View all admin commands with details\n"
                "`!admin_report @winner @loser` - Manually report match\n"
                "`!spot_elo_reset @user [elo]` - Set user's ELO\n"
                "`!correct_match <id>` - Flip outcome & recalculate ELO\n"
                "`!remove_match <id>` - Remove match & revert ELO\n"
                "`!remove_player @user` - Remove player from rankings\n"
                "`!reset_elo` - ⚠️ Reset all ELO & match history"
            ),
            inline=False,
        )

        # Command Usage Notes
        embed.add_field(
            name="📝 Notes",
            value=(
                "• Most commands work in DMs for privacy\n"
                "• `!challenge` must be used in #lfg channel\n"
                "• Fun system commands have daily/weekly limits\n"
                "• Admin commands require administrator, Bot Admin, or Judge role\n"
                "• Use specific help commands (`!lfg_help`, `!helpfart`, `!admin_help`) for details"
            ),
            inline=False,
        )

        embed.set_footer(text="For more details about any command, use !help [command]")

        await ctx.send(embed=embed)
        logger.info(f"Commands list requested by {ctx.author}")

    @commands.command()
    @is_bot_admin()
    async def giveaway(self, ctx, hours: float = 24):
        """
        Admin-only: Pick a random winner from users who posted in this channel.
        Usage: !giveaway [hours] - hours to look back (default 24)
        """
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        await ctx.send(f"🎉 Searching for participants from the last {hours} hour(s)... This may take a moment.")

        # Dictionary to store unique users with their display names
        participants = {}

        try:
            # Search through channel history within the time window
            async for message in ctx.channel.history(after=cutoff, limit=None):
                # Skip bots
                if message.author.bot:
                    continue
                if message.author.id not in participants:
                    participants[message.author.id] = message.author.display_name

            if not participants:
                await ctx.send(
                    f"❌ No participants found! No one posted in this channel in the last {hours} hour(s)."
                )
                logger.info(f"Giveaway by {ctx.author} found no participants")
                return

            # Convert to list format
            participant_list = [
                {"user_id": user_id, "display_name": display_name}
                for user_id, display_name in participants.items()
            ]

            total_participants = len(participant_list)

            # Randomly pick a winner
            winner = random.choice(participant_list)
            winner_id = winner["user_id"]
            winner_name = winner["display_name"]

            # Create announcement embed
            embed = discord.Embed(
                title="🎉 GIVEAWAY WINNER! 🎉",
                description=f"Congratulations to our winner!",
                color=discord.Color.gold(),
            )

            embed.add_field(name="Winner", value=f"<@{winner_id}>", inline=False)

            embed.add_field(
                name="Total Participants",
                value=f"{total_participants} users",
                inline=False,
            )

            embed.add_field(
                name="Time Window",
                value=f"Last {hours} hour(s)",
                inline=False,
            )

            embed.add_field(
                name="Next Steps",
                value=f"<@{winner_id}>, please message <@{ctx.author.id}> to claim your prize!",
                inline=False,
            )

            embed.set_footer(text=f"Giveaway conducted by {ctx.author.display_name}")

            await ctx.send(embed=embed)
            logger.info(
                f"Giveaway by {ctx.author}: Winner {winner_name} ({winner_id}) "
                f"from {total_participants} participants (last {hours}h)"
            )

        except discord.Forbidden:
            await ctx.send(
                "❌ I don't have permission to read message history in this channel."
            )
            logger.error(f"Giveaway by {ctx.author} failed: Missing permissions")
        except Exception as e:
            await ctx.send(f"❌ An error occurred while running the giveaway: {e}")
            logger.error(f"Giveaway error: {e}")


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
