import discord
from discord.ext import commands
import requests
import json
import logging

from utils.deck_checker import get_deck_id, find_card

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
            description="Here are all available commands:",
            color=discord.Color.blue(),
        )

        # General Commands
        embed.add_field(
            name="🎮 General Commands",
            value=(
                "`!help` - Show this help message\n"
                "`!commands` - List available commands\n"
                "`!deckcheck` - Check if a Curiosa deck is legal for Summit play"
            ),
            inline=False,
        )

        # LFG Commands
        embed.add_field(
            name="🔍 Looking For Game Commands",
            value=(
                "`!lfg [minutes]` - Add yourself to the queue for X minutes (default 30)\n"
                "`!checklfg` - Check if anyone is currently in the LFG queue\n"
                "`!challenge @user` - Challenge a specific player to a match (Must be in LFG channel to tag person)\n"
                "`!cancel` - Remove yourself from the LFG queue"
            ),
            inline=False,
        )

        # Rankings & Stats
        embed.add_field(
            name="📊 Rankings & Stats",
            value=(
                "`!rank` - Check your current Elo ranking\n"
                "`!mystats` - Get a summary of your match history\n"
                "`!leaderboard` - Show the top 10 Elo rankings\n"
                "`!replay` - Replay your last match"
            ),
            inline=False,
        )

        # DM Usage Note
        embed.add_field(
            name="📝 Note",
            value="Most commands can be used in DMs for privacy. The `!challenge` command must be used in lfg so you can challenge other players.",
            inline=False,
        )

        embed.set_footer(
            text="Bot is still under development - expect new features soon!"
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def commands(self, ctx):
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
                "`!lfghelp` - Learn how to use the LFG system\n"
                "`!lfg [minutes]` - Join queue for X minutes (default 30)\n"
                "`!checklfg` - Check who's in queue\n"
                "`!challenge @user` - Challenge specific player\n"
                "`!cancel` - Leave the queue"
            ),
            inline=False,
        )

        # Rankings & Stats Commands
        embed.add_field(
            name="📊 Rankings & Statistics",
            value=(
                "`!rank` - Check your Elo ranking\n"
                "`!leaderboard` - View top 10 Elo rankings\n"
                "`!mystats` - View your match statistics\n"
                "`!mygames` - List your recent games\n"
                "`!replay` - Replay your last match"
            ),
            inline=False,
        )

        # Utility Commands
        embed.add_field(
            name="🛠️ Utility",
            value=(
                "`!help` - Show help message\n"
                "`!commands` - Show this command list\n"
                "`!deckcheck` - Check Curiosa deck legality\n"
                "`!match_report @user` - Report match result"
            ),
            inline=False,
        )

        # Fun Commands
        embed.add_field(
            name="🎲 Fun System",
            value=(
                "`!fart` - Roll for daily fart points\n"
                "`!fartrank` - Check your fart ranking\n"
                "`!fartleaderboard` - View top 5 fart scores\n"
                "`!attackfart` - Attack fart leader (once per day)\n"
                "`!fartshop` - Buy fart items with points"
            ),
            inline=False,
        )

        # Command Usage Note
        embed.add_field(
            name="📝 Note",
            value=(
                "• Most commands work in DMs for privacy\n"
                "• `!challenge` must be used in #lfg channel\n"
                "• Use `!lfghelp` for detailed LFG guidance"
            ),
            inline=False,
        )

        embed.set_footer(text="For more details about any command, use !help [command]")

        await ctx.send(embed=embed)
        logger.info(f"Commands list requested by {ctx.author}")


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
