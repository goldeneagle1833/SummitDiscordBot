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
from cogs.tournament import TournamentCog
from cogs.slash_commands import SlashCommandsCog
from cogs.anti_spam import AntiSpamCog
from cogs.purchase_tracking import PurchaseTrackingCog

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

    # Sync slash commands
    try:
        # Sync to specific guild (instant) - this makes commands appear immediately in your server
        from config import GUILD_ID

        guild = discord.Object(id=GUILD_ID)
        synced_guild = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced_guild)} slash commands to guild {GUILD_ID}")
        print(f"✅ Synced {len(synced_guild)} slash commands to guild (instant)")

        # Also sync globally (takes up to 1 hour to propagate) for DMs and other servers
        synced_global = await bot.tree.sync()
        logger.info(f"Synced {len(synced_global)} slash commands globally")
        print(
            f"✅ Synced {len(synced_global)} slash commands globally (may take up to 1 hour)"
        )
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")
        print(f"Failed to sync slash commands: {e}")


@bot.event
async def on_member_join(member):
    welcome_channel_id = 1319120228650844202
    channel = bot.get_channel(welcome_channel_id)
    if channel:
        embed = discord.Embed(
            title="👋 Welcome to Summit Discord!",
            description=f"Welcome {member.mention}!",
            color=discord.Color.blue(),
        )

        # Key Channels
        embed.add_field(
            name="Key Channels",
            value=(
                "<#1336912830867439676> - Find games with `!lfg`\n"
                "<#1379476865089142844> - Event decks & decklists\n"
                "<#1402265039951368273> - Fun & games"
            ),
            inline=False,
        )

        # Bot Commands
        embed.add_field(
            name="Getting Started",
            value=(
                "Type `/` to see all commands\n"
                "`/help` - Full feature list\n"
                "📺 [Watch the Bot Tutorial](https://youtu.be/6eErwhPocL8) - Learn how to use the bot!"
            ),
            inline=False,
        )

        embed.set_footer(text="Ready to play? Head to the LFG channel!")

        await channel.send(embed=embed)


async def setup_cogs():
    await bot.add_cog(AntiSpamCog(bot))  # Load anti-spam first to monitor all messages
    await bot.add_cog(LFGCog(bot))
    await bot.add_cog(EloCog(bot))
    await bot.add_cog(FunCog(bot))
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(TournamentCog(bot))
    await bot.add_cog(SlashCommandsCog(bot))
    await bot.add_cog(PurchaseTrackingCog(bot))


async def main():
    async with bot:
        await setup_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
