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
from cogs.achievements import AchievementsCog

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
    
    # Initialize achievement database
    try:
        from utils.achievements import create_profiles_db
        create_profiles_db()
        logger.info("Achievement system initialized")
        print("✅ Achievement system initialized")
    except Exception as e:
        logger.error(f"Failed to initialize achievement system: {e}")
        print(f"⚠️ Achievement system initialization failed: {e}")
    
    # Sync slash commands
    try:
        # Sync to specific guild (instant)
        from config import GUILD_ID
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced_guild = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced_guild)} slash commands to guild {GUILD_ID}")
        print(f"✅ Synced {len(synced_guild)} slash commands to guild (instant)")
        
        # Also sync globally (takes up to 1 hour to propagate)
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands globally")
        print(f"✅ Synced {len(synced)} slash commands globally (may take up to 1 hour)")
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
            description=(
                f"Welcome {member.mention}! Here's your guide to our server:"
            ),
            color=discord.Color.blue(),
        )

        # Key Channels
        embed.add_field(
            name="Important Channels",
            value=(
                " <#1336912830867439676> - Use `!lfg` here to find games\n"
                " <#1379476865089142844> - Check out event decks and decklists\n"
                " <#1424374255721775175> - Latest Spoilers   \n"
                " <#1402265039951368273> - Silly fun and games"
            ),
            inline=False,
        )

        # Bot Help
        embed.add_field(
            name="Bot Commands",
            value=(
                "• Type `/` to see all slash commands (recommended!)\n"
                "• `!help` or `/help` - See all features\n"
                "• `!commands` or `/commands` - Full command list\n"
                "• `!lfg_help` or `/lfg_help` - Learn LFG system"
            ),
            inline=False,
        )

        embed.set_footer(text="Ready to play? Head to the LFG channel!")
        
        await channel.send(embed=embed)


async def setup_cogs():
    await bot.add_cog(LFGCog(bot))
    await bot.add_cog(EloCog(bot))
    await bot.add_cog(FunCog(bot))
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(TournamentCog(bot))
    await bot.add_cog(SlashCommandsCog(bot))
    await bot.add_cog(AchievementsCog(bot))


async def main():
    async with bot:
        await setup_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
