import discord
from discord.ext import commands
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from cogs.lfg import LFGCog
from cogs.elo import EloCog
from cogs.fun import FunCog
from cogs.utility import UtilityCog
from cogs.shop import ShopCog
from cogs.slash_commands import SlashCommandsCog
from cogs.anti_spam import AntiSpamCog
from cogs.purchase_tracking import PurchaseTrackingCog
from cogs.streaming import StreamingCog
from cogs.community import CommunityCog
from cogs.chat import ChatCog
from cogs.reaction_roles import ReactionRolesCog
from cogs.match_confirmation_jobs import MatchConfirmationJobs
from cogs.pilots import PilotsCog
from cogs.daily_summary import DailySummaryCog
from cogs.dust import DustCog
from cogs.reddit_bridge import RedditBridgeCog
from cogs.magoo_monitor import MagooMonitorCog
from cogs.store_notifications import StoreNotificationsCog
from cogs.card_catalog_sync import CardCatalogSyncCog, ensure_card_catalog_table
from cogs.dynamic_voice import DynamicVoiceCog
from cogs.content_monitor import ContentMonitorCog
from cogs.lfg.persistent_confirm import (
    PersistentConfirmButton,
    PersistentDisputeButton,
    PersistentCorrectionConfirmButton,
    PersistentCorrectionDenyButton,
    PersistentMatchCardReportButton,
    PersistentMatchCardCancelButton,
    ensure_pending_confirmations_table,
    ensure_pending_corrections_table,
    ensure_match_cards_table,
)
from repositories.elo_repo import migrate_to_dual_elo_system
from services.elo_service import backfill_deck_data
from services.matchmaking_api import start_matchmaking_api

import config

load_dotenv(Path(__file__).resolve().parent / ".env")
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
intents.presences = True  # Required for streaming detection

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # Remove default help command


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    logger.info(f"Bot started as {bot.user.name}")

    # Backfill any missing deck JSON in the background (non-blocking)
    import asyncio
    asyncio.create_task(backfill_deck_data())

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
    channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="👋 Welcome to Summit Discord!",
            description=f"Welcome {member.mention}!",
            color=discord.Color.blue(),
        )

        # Website
        embed.add_field(
            name="🌐 Summit Website",
            value=(
                "**[sorcererssummit.com](https://sorcererssummit.com)**\n"
                "View leaderboards, match history, player stats, and more!"
            ),
            inline=False,
        )

        # Key Channels
        embed.add_field(
            name="Key Channels",
            value=(
                "<#1336912830867439676> - Find games with the **Join Queue** button\n"
                "<#1319404888039489607> - Get your roles via emoji reactions\n"
                "<#1402265039951368273> - Fun & games / bot spam"
            ),
            inline=False,
        )

        # Bot Commands
        embed.add_field(
            name="How to Find a Game",
            value=(
                "Head to <#1336912830867439676> and:\n"
                "1️⃣ Click the **Join Queue** button\n"
                "2️⃣ Enter your deck URL (optional)\n"
                "3️⃣ Get matched with another player!\n\n"
                "**Alternative:** Challenge someone directly with `!challenge @user`\n\n"
                "Type `!lfg_help` for all commands"
            ),
            inline=False,
        )

        # TTS Setup Guide
        embed.add_field(
            name="New to TTS?",
            value=(
                "**[Watch the TTS Setup Guide](https://youtu.be/cr8PVGmrnNQ?si=X6rlciFILEG9_HDM)**\n"
                "Learn how to set up Tabletop Simulator to play Sorcery!"
            ),
            inline=False,
        )

        embed.set_footer(text="Questions? Ask in the server or check /help!")

        await channel.send(embed=embed)


async def setup_cogs():
    await bot.add_cog(AntiSpamCog(bot))  # Load anti-spam first to monitor all messages
    await bot.add_cog(LFGCog(bot))
    await bot.add_cog(EloCog(bot))
    await bot.add_cog(FunCog(bot))
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(SlashCommandsCog(bot))
    await bot.add_cog(PurchaseTrackingCog(bot))
    await bot.add_cog(StoreNotificationsCog(bot))  # Store order DMs + admin pings
    await bot.add_cog(StreamingCog(bot))  # Streaming detection for website banner
    await bot.add_cog(CommunityCog(bot))  # Community page management
    await bot.add_cog(ReactionRolesCog(bot))  # Reaction-based role assignment
    await bot.add_cog(MatchConfirmationJobs(bot))  # Background jobs for match confirmation reminders & expiration
    await bot.add_cog(PilotsCog(bot))  # Feature flag management
    await bot.add_cog(DailySummaryCog(bot))  # Daily summary at 11:30 PM EST
    await bot.add_cog(ChatCog(bot))  # AI chat responses to mentions/replies
    await bot.add_cog(DustCog(bot))  # Dust code reward system
    await bot.add_cog(RedditBridgeCog(bot))  # Reddit subreddit -> Discord bridge
    await bot.add_cog(MagooMonitorCog(bot))  # Archimago complaint vibe monitor
    await bot.add_cog(CardCatalogSyncCog(bot))  # Daily card catalog sync from Sorcery TCG API
    await bot.add_cog(DynamicVoiceCog(bot))  # Auto-create temporary voice rooms
    await bot.add_cog(ContentMonitorCog(bot))  # Auto-create promo banners from sorcery-content links


async def main():
    async with bot:
        # Run DB schema migrations before handling any interactions
        migrate_to_dual_elo_system()
        ensure_pending_confirmations_table()
        ensure_pending_corrections_table()
        ensure_match_cards_table()
        ensure_card_catalog_table()
        # Register DynamicItem buttons so Confirm/Dispute survive bot restarts
        bot.add_dynamic_items(
            PersistentConfirmButton, PersistentDisputeButton,
            PersistentCorrectionConfirmButton, PersistentCorrectionDenyButton,
            PersistentMatchCardReportButton, PersistentMatchCardCancelButton,
        )
        await setup_cogs()
        matchmaking_runner = await start_matchmaking_api(bot)
        try:
            await bot.start(TOKEN)
        finally:
            if matchmaking_runner:
                await matchmaking_runner.cleanup()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
