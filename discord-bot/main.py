import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

from cogs.lfg import LFGCog
from cogs.elo import EloCog
from cogs.fun import FunCog
from cogs.utility import UtilityCog
from cogs.shop import ShopCog

load_dotenv()
TOKEN = os.getenv("TOKEN")

# Configure logging
logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)

handler = logging.FileHandler(filename="bot.log", encoding="utf-8", mode="a")
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(handler)
logger.addHandler(stream_handler)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # Remove default help command


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    logger.info(f"Bot started as {bot.user.name}")


@bot.event
async def on_member_join(member):
    welcome_channel_id = 1319120228650844202
    channel = bot.get_channel(welcome_channel_id)
    if channel:
        embed = discord.Embed(
            title="👋 Welcome to Summit Discord!",
            description="I'm the Summit Discord Bot, here to help you find games and connect with others.\nI'm still under development, so expect new features soon!",
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
                "`!lfghelp` - Learn how to use the Looking For Game system\n"
                "`!lfg [minutes]` - Add yourself to the queue for X minutes (default 30)\n"
                "`!checklfg` - Check if anyone is currently in the LFG queue\n"
                "`!challenge @user` - Challenge a specific player to a match\n"
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
                "`!replay` - Replay your last match\n"
                "`!mygames` - List your recent games"
                "`!report` - Report a match result this will not update your Elo only for record keeping"
            ),
            inline=False,
        )

        # DM Usage Note
        embed.add_field(
            name="📝 Note",
            value="Most commands can be used in DMs for privacy. The `!challenge` command must be used in lfg so you can tag other players.",
            inline=False,
        )

        embed.set_footer(text="Type !help or !lfghelp for more detailed information")

        await channel.send(f"Welcome {member.mention}!", embed=embed)


async def setup_cogs():
    await bot.add_cog(LFGCog(bot))
    await bot.add_cog(EloCog(bot))
    await bot.add_cog(FunCog(bot))
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(ShopCog(bot))


async def main():
    async with bot:
        await setup_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
