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
            title="📖 Welcome to Summit Bot!",
            description="Here are the main systems and how to learn more about them:",
            color=discord.Color.blue(),
        )

        # Main Systems Overview
        embed.add_field(
            name="Looking For Game (LFG) System",
            value=(
                "Find matches and report results:\n"
                "`!lfg [minutes]` - Join queue for X minutes (default 30)\n"
                "`!checklfg` - See who's in queue\n"
                "`!challenge @user` - Challenge specific player\n"
                "`!cancel` - Leave the queue\n"
                "`!record_game` - Record a match result manually"
            ),
            inline=False,
        )

        embed.add_field(
            name="Tournament System",
            value=(
                "Tournament Player Commands:\n"
                "`!join <name>` - Join tournament during registration\n"
                "`!my_round` - View your match and report results\n"
                "`!bracket <name>` - View tournament bracket\n\n"
                "Tournament Admin Commands:\n"
                "`!create_tournament` - Create new tournament\n"
                "`!start_tournament <name>` - Start the tournament\n"
                "`!complete_tournament <name>` - End tournament\n"
                "`!remove <name> @user` - Remove player"
            ),
            inline=False,
        )

        embed.add_field(
            name="Rankings & Stats",
            value=(
                "`!rank` - Check your Elo ranking\n"
                "`!mystats` - Get your match history\n"
                "`!leaderboard` - View top 10 rankings\n"
                "`!mygames` - List your recent games\n"
                "`!replay` - View last match details"
            ),
            inline=False,
        )

        embed.add_field(
            name="Fun System",
            value=(
                "For fart game and item shop commands:\n"
                "Use `!helpfart` to see all fun commands"
            ),
            inline=False,
        )

        embed.add_field(
            name="Utility",
            value=(
                "`!help` - Show this help message\n"
                "`!commands` - View all available commands\n"
                "`!deckcheck` - Check if a Curiosa deck is legal"
            ),
            inline=False,
        )

        # Important Notes
        embed.add_field(
            name="Important Notes",
            value=(
                "• Most commands work in DMs for privacy\n"
                "• The `!challenge` command must be used in the LFG channel\n"
                "• Tournament commands require active tournament\n"
                "• For complete command list use `!commands`"
            ),
            inline=False,
        )

        embed.set_footer(
            text="Need more details? Use !commands to see everything available"
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
                "`!cancel` - Leave the queue\n"
                "`!record_game` - Record a match result manually"
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

        # Tournament Commands
        embed.add_field(
            name="🏆 Tournament System",
            value=(
                "Player Commands:\n"
                "`!tournament_help` - Show tournament command help\n"
                "`!join <name>` - Join a tournament during registration\n"
                "`!my_round` - View your current match and report results\n"
                "`!bracket <name>` - View the tournament bracket\n\n"
                "Admin Commands:\n"
                "`!create_tournament` - Create a new tournament\n"
                "`!start_tournament <name>` - Start a tournament\n"
                "`!complete_tournament <name>` - Finalize a tournament\n"
                "`!remove <name> @user` - Remove player from tournament"
            ),
            inline=False,
        )

        # Utility Commands
        embed.add_field(
            name="🛠️ Utility",
            value=(
                "`!help` - Show help message\n"
                "`!commands` - Show this command list\n"
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
                "`!attackfart` - Attack leader to reduce their score\n"
                "`!syphonfart` - Place syphon to steal leader's next points\n"
                "`!fartprediction` - Predict fart type for 2x points\n"
                "`!bullfart` - Get bonus points (weekly)\n\n"
                "Shop & Items:\n"
                "`!fartshop` - View available items\n"
                "`!blueshell` - Hit leader with damage\n"
                "`!redshell` - Hit player in front\n"
                "`!greenshell` - Hit random front player\n"
                "`!banana` - Hit random player behind\n"
                "`!star` - Get 24h protection\n\n"
                "Scores & Stats:\n"
                "`!fartrank` - Check your score and ranking\n"
                "`!fartleaderboard` - View top 5 farters\n"
                "`!syphonstatus` - Check active syphons\n"
                "`!helpfart` - View detailed fart commands"
            ),
            inline=False,
        )

        # Leader-Only Commands
        embed.add_field(
            name="👑 Leader Commands",
            value=(
                "`!fartlord` - Make grand proclamation\n"
                "`!taxes` - Take 5% from others (once per reign)\n"
                "`!wealth` - Redistribute from top 5 (once per reign)"
            ),
            inline=False,
        )

        # Command Usage Notes
        embed.add_field(
            name="📝 Notes",
            value=(
                "• Most commands work in DMs for privacy\n"
                "• Tournament commands require proper tournament context\n"
                "• `!challenge` must be used in #lfg channel\n"
                "• Fun system commands have daily/weekly limits\n"
                "• Use specific help commands (`!lfghelp`, `!tournament_help`, `!helpfart`) for details"
            ),
            inline=False,
        )

        embed.set_footer(text="For more details about any command, use !help [command]")

        await ctx.send(embed=embed)
        logger.info(f"Commands list requested by {ctx.author}")


async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
