import discord
from discord.ext import commands
import datetime
import math
import sqlite3
import logging
import random
import time
from openai import OpenAI

import config
from utils.text import find_best_command_match
from cogs.fun import (
    parse_to_est_date,
    get_est_date,
    get_est_now,
    get_est_midnight,
    safe_parse_datetime,
)

logger = logging.getLogger("discord_bot")

openai = OpenAI(api_key=config.OPENAI_API_KEY)


class ShopCog(commands.Cog):
    # Sliding-window rate limit for shop item spam (banana peel-out)
    SHOP_RATE_LIMIT_MAX = 5
    SHOP_RATE_LIMIT_WINDOW_SECONDS = 30 * 60  # 30 minutes
    # Browse catalog freely; gas_gamble is intentionally unrestricted
    RATE_LIMIT_EXEMPT = frozenset({"fart_shop", "gas_gamble"})
    # Point transfers / wagers / pacts are not "loot the floor" shop toys
    YOURT_LOOT_EXEMPT = frozenset(
        {"fart_shop", "gas_gamble", "fart_donation", "fart_court", "evil_star"}
    )

    def __init__(self, bot):
        self.bot = bot
        self.fart_channel_id = config.FART_CHANNEL_ID
        self.guild_id = config.GUILD_ID
        self.leader_role_id = config.LEADER_ROLE_ID
        self.giga_target_role_id = config.DM_DISABLED_ROLE_ID  # Role for double damage target
        self.item_costs = {
            "blue": 20,  # Blue Shell - 6d20/2, once/day (Gothic S6)
            "red": 10,  # Red Shell - 3d20/2
            "green": 5,  # Green Shell
            "banana": 5,  # Banana
            "star": 50,  # Star (actual cost is 10% of points)
            "mushroom": 5,  # Mushroom
            "bobomb": 25,  # Bob-omb
            "fart_star": 200,  # Star Killer (actual cost is 10% of points)
            "thunder_fart": 10,  # Thunder Fart - 10 damage to all, once/week
            "gas_shield": 8,  # Gas Shield - reflect 50% damage back at next attacker
            "stink_bomb": 12,  # Stink Bomb - hit random player (anyone)
            "fart_rocket": 100,  # Fart Rocket - swap scores, once/week
            "fart_trap": 20,  # Fart Trap - target's next attack hits themselves
            "stink_cloud": 5,  # Stink Cloud (actual cost is 5% of points)
            "gas_gamble": 3,  # Gas Gamble - custom bet amount
            "fart_leech": 5,  # Fart Leech - once/day
            "fart_twister": 50,  # Fart Twister - uses daily fart, once/week
            "fart_lance": 15,  # Fart Lance - diminishing damage to 3 players ahead
            "big_banana": 20,  # Big Banana - 4d10, once/day
        }
        # user_id -> list of unix timestamps for recent shop item uses
        self._shop_usage: dict[int, list[float]] = {}
        logger.info("ShopCog initialized")
        self.setup_purchase_database()

    ATTACK_COMMANDS = {
        'blue_shell', 'red_shell', 'green_shell', 'banana', 'bobomb',
        'stink_bomb', 'thunder_fart', 'fart_rocket',
        'fart_leech', 'stink_cloud', 'fart_star', 'fart_twister',
        'fart_lance', 'big_banana',
    }

    @staticmethod
    def format_rate_limit_remaining(seconds: float) -> str:
        """Pretty-print remaining peel-out wait time."""
        total = max(0, math.ceil(seconds))
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

    def prune_shop_usage(self, user_id: int, now: float | None = None) -> list[float]:
        """Drop uses outside the rate-limit window; return remaining timestamps."""
        now = time.time() if now is None else now
        window = self.SHOP_RATE_LIMIT_WINDOW_SECONDS
        usages = [t for t in self._shop_usage.get(user_id, []) if now - t < window]
        if usages:
            self._shop_usage[user_id] = usages
        else:
            self._shop_usage.pop(user_id, None)
        return usages

    def check_shop_rate_limit(
        self, user_id: int, now: float | None = None
    ) -> tuple[bool, float | None]:
        """
        Sliding window: max SHOP_RATE_LIMIT_MAX uses per SHOP_RATE_LIMIT_WINDOW_SECONDS.
        Returns (allowed, seconds_remaining_until_next_slot).
        """
        now = time.time() if now is None else now
        usages = self.prune_shop_usage(user_id, now)
        if len(usages) >= self.SHOP_RATE_LIMIT_MAX:
            oldest = min(usages)
            remaining = self.SHOP_RATE_LIMIT_WINDOW_SECONDS - (now - oldest)
            return False, max(remaining, 0.0)
        return True, None

    def record_shop_usage(self, user_id: int, now: float | None = None):
        """Record a shop item use for the peel-out rate limit."""
        now = time.time() if now is None else now
        self.prune_shop_usage(user_id, now)
        self._shop_usage.setdefault(user_id, []).append(now)

    def peel_out_message(self, mention: str, remaining_seconds: float) -> str:
        wait = self.format_rate_limit_remaining(remaining_seconds)
        return (
            f"🍌 **PEEL OUT!!!!** {mention}, looks like you've used too many shop items "
            f"too quickly — wait **{wait}** before using more!"
        )

    def yourt_waives_shop_limits(self) -> bool:
        """True during Yourt's 1-hour free-shop crash (costs, CDs, peel-out off)."""
        fun = self.bot.get_cog("FunCog")
        if fun is None:
            return False
        check = getattr(fun, "is_yourt_rampage_active", None)
        if not callable(check):
            return False
        try:
            return check() is True
        except Exception:
            return False

    def yourt_loot_message(self, mention: str, command_name: str) -> str:
        from cogs.fun import YOURT_EMOJI_FALLBACK, drunken_case

        emoji = YOURT_EMOJI_FALLBACK
        fun = self.bot.get_cog("FunCog")
        markup = getattr(fun, "yourt_emoji_markup", None) if fun is not None else None
        if callable(markup):
            rendered = markup()
            if isinstance(rendered, str):
                emoji = rendered
        item = drunken_case(command_name.replace("_", " "))
        looted = drunken_case("LOOTED")
        cleanup = drunken_case("while the shopkeeper was cleaning up Yourt's mess")
        return (
            f"{emoji}{emoji} {mention} **{looted}** a **{item}** {cleanup}! "
            f"{emoji}{emoji}{emoji}"
        )

    async def cog_check(self, ctx):
        """Block shop commands if user is stink clouded, rate-limited, or fart-trapped."""
        if ctx.command.name in ('fart_shop',):
            return True

        # Check stink cloud block
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS frost_shart_freeze (
                    user_id INTEGER PRIMARY KEY,
                    frozen_until TEXT NOT NULL
                )
            """)
            cur.execute(
                """
                SELECT frozen_until FROM frost_shart_freeze
                WHERE user_id = ? AND frozen_until > datetime('now')
                """,
                (ctx.author.id,),
            )
            if cur.fetchone():
                await ctx.send(
                    f"{ctx.author.mention}, you're frozen solid by a Frostshart! "
                    f"No shop items until midnight EST!"
                )
                return False

            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_blocks (
                    user_id INTEGER PRIMARY KEY,
                    blocked_until TIMESTAMP
                )
            """)
            cur.execute(
                "SELECT blocked_until FROM shop_blocks WHERE user_id = ? AND blocked_until > datetime('now')",
                (ctx.author.id,),
            )
            result = cur.fetchone()
            if result:
                await ctx.send(
                    f"{ctx.author.mention}, you're blinded by a Stink Cloud! Wait for it to clear before using shop items!"
                )
                return False
        finally:
            conn.close()

        # Peel-out rate limit: 5 shop items / 30 minutes (!gas_gamble exempt)
        # Yourt rampage dumps the tent on the floor — peel-out is off.
        if ctx.command.name not in self.RATE_LIMIT_EXEMPT:
            if self.yourt_waives_shop_limits():
                if hasattr(ctx.command, "reset_cooldown"):
                    ctx.command.reset_cooldown(ctx)
            else:
                allowed, remaining = self.check_shop_rate_limit(ctx.author.id)
                if not allowed:
                    await ctx.send(self.peel_out_message(ctx.author.mention, remaining))
                    return False
                self.record_shop_usage(ctx.author.id)

        # Check fart trap on attack commands
        if ctx.command.name in self.ATTACK_COMMANDS:
            trapped = await self.check_fart_trap(ctx, ctx.author.id)
            if trapped:
                return False

        return True

    async def cog_after_invoke(self, ctx):
        """During Yourt chaos, announce that the item was looted off the tent floor."""
        if not ctx.command or ctx.command.name in self.YOURT_LOOT_EXEMPT:
            return
        if not self.yourt_waives_shop_limits():
            return
        try:
            await ctx.send(
                self.yourt_loot_message(ctx.author.mention, ctx.command.name)
            )
        except Exception as e:
            logger.error(f"Error sending Yourt loot message: {e}")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle shop command errors and suggest corrections for typos"""
        # Unwrap CommandInvokeError to the original exception when present
        error = getattr(error, "original", error)

        # Short cooldowns were previously silent because this listener
        # swallows non-CommandNotFound errors before the default handler.
        if isinstance(error, commands.CommandOnCooldown):
            if ctx.command and ctx.command.cog is self:
                if self.yourt_waives_shop_limits() and not getattr(
                    ctx, "_yourt_cooldown_retry", False
                ):
                    ctx._yourt_cooldown_retry = True
                    ctx.command.reset_cooldown(ctx)
                    await ctx.reinvoke()
                    return
                await ctx.send(
                    f"{ctx.author.mention}, slow down! Try again in {error.retry_after:.0f}s."
                )
            return

        if isinstance(error, commands.BadArgument):
            if ctx.command and ctx.command.name == "fart_court":
                await ctx.send(
                    f"{ctx.author.mention}, usage: `!fart_court @user <amount>`"
                )
            return

        # Only handle CommandNotFound typos below
        if not isinstance(error, commands.CommandNotFound):
            return

        # Extract the failed command from the message
        message_content = ctx.message.content.lower()
        if not message_content.startswith("!"):
            return

        failed_command = message_content.split()[0][1:]  # Remove the !

        # Common shop-related commands and suggestions
        command_suggestions = {
            # Blue Shell variations
            "blue": "!blue_shell",
            "blueshell": "!blue_shell",
            "blue_shell": "!blue_shell",
            "blushell": "!blue_shell",
            "blueshel": "!blue_shell",
            "bloo": "!blue_shell",
            # Red Shell variations
            "red": "!red_shell",
            "redshell": "!red_shell",
            "red_shell": "!red_shell",
            "redshel": "!red_shell",
            # Green Shell variations
            "green": "!green_shell",
            "greenshell": "!green_shell",
            "green_shell": "!green_shell",
            "greenshel": "!green_shell",
            "gren": "!green_shell",
            # Banana variations
            "banana": "!banana",
            "bananna": "!banana",
            "banan": "!banana",
            "nana": "!banana",
            # Star variations
            "star": "!star",
            "str": "!star",
            "protect": "!star",
            "protection": "!star",
            "shield": "!star",
            # Mushroom variations
            "mushroom": "!mushroom",
            "mushrrom": "!mushroom",
            "mushrom": "!mushroom",
            "shroom": "!mushroom",
            "mush": "!mushroom",
            "boost": "!mushroom",
            # Bob-omb variations
            "bobomb": "!bobomb",
            "bob-omb": "!bobomb",
            "bomb": "!bobomb",
            "bom": "!bobomb",
            "boomb": "!bobomb",
            "bobom": "!bobomb",
            # Shop variations
            "shop": "!fart_shop",
            "fartshop": "!fart_shop",
            "fart_shop": "!fart_shop",
            "shopfart": "!fart_shop",
            "shop_fart": "!fart_shop",
            "store": "!fart_shop",
            "buy": "!fart_shop",
            "items": "!fart_shop",
            "purchase": "!fart_shop",
            # Giga Fart Cannon variations
            "giga": "!giga_fart_cannon",
            "gigafart": "!giga_fart_cannon",
            "giga_fart": "!giga_fart_cannon",
            "gigafartcannon": "!giga_fart_cannon",
            "giga_fart_cannon": "!giga_fart_cannon",
            "cannon": "!giga_fart_cannon",
            "gigacannon": "!giga_fart_cannon",
            # Fart Star variations
            "fartstar": "!fart_star",
            "fart_star": "!fart_star",
            "fartstr": "!fart_star",
            "starkiller": "!fart_star",
            "killer": "!fart_star",
            "remove_star": "!fart_star",
            "removestar": "!fart_star",
            # Evil Star variations
            "evilstar": "!evil_star",
            "evil_star": "!evil_star",
            "evil": "!evil_star",
            "evilstr": "!evil_star",
            "devil": "!evil_star",
            "devilstar": "!evil_star",
            "666": "!evil_star",
            "satan": "!evil_star",
            "dark": "!evil_star",
            "darkstar": "!evil_star",
            # Thunder Fart variations
            "thunderfart": "!thunder_fart",
            "thunder_fart": "!thunder_fart",
            "thunder": "!thunder_fart",
            "lightning": "!thunder_fart",
            "thunderf": "!thunder_fart",
            # Gas Shield variations
            "gasshield": "!gas_shield",
            "gas_shield": "!gas_shield",
            "shield": "!gas_shield",
            "gshield": "!gas_shield",
            "reflect": "!gas_shield",
            # Stink Bomb variations
            "stinkbomb": "!stink_bomb",
            "stink_bomb": "!stink_bomb",
            "stink": "!stink_bomb",
            "stinkb": "!stink_bomb",
            # Fart Rocket variations
            "fartrocket": "!fart_rocket",
            "fart_rocket": "!fart_rocket",
            "rocket": "!fart_rocket",
            "frocket": "!fart_rocket",
            # Fart Trap variations
            "farttrap": "!fart_trap",
            "fart_trap": "!fart_trap",
            "trap": "!fart_trap",
            "ftrap": "!fart_trap",
            # Stink Cloud variations
            "stinkcloud": "!stink_cloud",
            "stink_cloud": "!stink_cloud",
            "cloud": "!stink_cloud",
            "scloud": "!stink_cloud",
            "blooper": "!stink_cloud",
            # Gas Gamble variations
            "gasgamble": "!gas_gamble",
            "gas_gamble": "!gas_gamble",
            "gamble": "!gas_gamble",
            "ggamble": "!gas_gamble",
            "coinblock": "!gas_gamble",
            # Fart Leech variations
            "fartleech": "!fart_leech",
            "fart_leech": "!fart_leech",
            "leech": "!fart_leech",
            "fleech": "!fart_leech",
            "steal": "!fart_leech",
            # Fart Twister variations
            "farttwister": "!fart_twister",
            "fart_twister": "!fart_twister",
            "twister": "!fart_twister",
            "tornado": "!fart_twister",
            # Fart Lance variations
            "fartlance": "!fart_lance",
            "fart_lance": "!fart_lance",
            "lance": "!fart_lance",
            "icelance": "!fart_lance",
            "ice_lance": "!fart_lance",
            # Big Banana variations
            "bigbanana": "!big_banana",
            "big_banana": "!big_banana",
            "bignana": "!big_banana",
            "bigban": "!big_banana",
            # Fart Court variations
            "fartcourt": "!fart_court",
            "fart_court": "!fart_court",
            "court": "!fart_court",
            # Fart Donation variations
            "fartdonation": "!fart_donation",
            "fart_donation": "!fart_donation",
            "donation": "!fart_donation",
            "donate": "!fart_donation",
            "give": "!fart_donation",
        }

        actual_commands = {
            "blue_shell": "!blue_shell",
            "blueshell": "!blue_shell",
            "red_shell": "!red_shell",
            "redshell": "!red_shell",
            "green_shell": "!green_shell",
            "greenshell": "!green_shell",
            "banana": "!banana",
            "star": "!star",
            "mushroom": "!mushroom",
            "bobomb": "!bobomb",
            "fart_shop": "!fart_shop",
            "fartshop": "!fart_shop",
            "shop_fart": "!fart_shop",
            "shopfart": "!fart_shop",
            "shop": "!fart_shop",
            "giga_fart_cannon": "!giga_fart_cannon",
            "gigafartcannon": "!giga_fart_cannon",
            "fart_star": "!fart_star",
            "fartstar": "!fart_star",
            "star_fart": "!fart_star",
            "starfart": "!fart_star",
            "evil_star": "!evil_star",
            "evilstar": "!evil_star",
            "thunder_fart": "!thunder_fart",
            "thunderfart": "!thunder_fart",
            "fart_thunder": "!thunder_fart",
            "fartthunder": "!thunder_fart",
            "gas_shield": "!gas_shield",
            "gasshield": "!gas_shield",
            "fart_shield": "!gas_shield",
            "fartshield": "!gas_shield",
            "stink_bomb": "!stink_bomb",
            "stinkbomb": "!stink_bomb",
            "fart_rocket": "!fart_rocket",
            "fartrocket": "!fart_rocket",
            "rocket_fart": "!fart_rocket",
            "rocketfart": "!fart_rocket",
            "fart_trap": "!fart_trap",
            "farttrap": "!fart_trap",
            "trap_fart": "!fart_trap",
            "trapfart": "!fart_trap",
            "stink_cloud": "!stink_cloud",
            "stinkcloud": "!stink_cloud",
            "gas_gamble": "!gas_gamble",
            "gasgamble": "!gas_gamble",
            "fart_gamble": "!gas_gamble",
            "fartgamble": "!gas_gamble",
            "fart_leech": "!fart_leech",
            "fartleech": "!fart_leech",
            "leech_fart": "!fart_leech",
            "leechfart": "!fart_leech",
            "fart_twister": "!fart_twister",
            "farttwister": "!fart_twister",
            "twister_fart": "!fart_twister",
            "twisterfart": "!fart_twister",
            "fart_lance": "!fart_lance",
            "fartlance": "!fart_lance",
            "lance_fart": "!fart_lance",
            "lancefart": "!fart_lance",
            "big_banana": "!big_banana",
            "bigbanana": "!big_banana",
            "fart_court": "!fart_court",
            "fartcourt": "!fart_court",
            "court_fart": "!fart_court",
            "courtfart": "!fart_court",
            "fart_donation": "!fart_donation",
            "fartdonation": "!fart_donation",
            "donation_fart": "!fart_donation",
            "donationfart": "!fart_donation",
            "fart_donate": "!fart_donation",
            "fartdonate": "!fart_donation",
        }

        suggestion = find_best_command_match(failed_command, command_suggestions, actual_commands)
        if suggestion:
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!fart_shop` to see all available items."
            )
            return

    def setup_purchase_database(self):
        """Create table to track Discord monetization purchases"""
        try:
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS purchase_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    user_discriminator TEXT,
                    purchase_type TEXT NOT NULL,
                    sku_id TEXT,
                    sku_name TEXT,
                    entitlement_id TEXT,
                    subscription_id TEXT,
                    guild_id INTEGER,
                    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    notes TEXT
                )
            """)
            conn.commit()
            conn.close()
            logger.info("Discord purchase tracking database initialized")
        except Exception as e:
            logger.error(f"Error setting up purchase database: {e}")

    async def log_discord_purchase(
        self,
        user_id: int,
        username: str,
        purchase_type: str,
        sku_id: str = None,
        sku_name: str = None,
        entitlement_id: str = None,
        subscription_id: str = None,
        guild_id: int = None,
        expires_at: datetime.datetime = None,
        notes: str = None,
    ):
        """Log a Discord monetization purchase to the database"""
        try:
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO purchase_records 
                (user_id, username, user_discriminator, purchase_type, sku_id, sku_name, 
                 entitlement_id, subscription_id, guild_id, expires_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    user_id,
                    username,
                    "",  # discriminator (legacy, but keeping for compatibility)
                    purchase_type,
                    sku_id,
                    sku_name,
                    entitlement_id,
                    subscription_id,
                    guild_id,
                    expires_at,
                    notes,
                ),
            )
            conn.commit()
            conn.close()
            logger.info(
                f"Logged Discord purchase: {username} ({user_id}) - {purchase_type} - {sku_name}"
            )
        except Exception as e:
            logger.error(f"Error logging Discord purchase: {e}")

    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement):
        """Called when a user purchases a subscription or one-time product"""
        try:
            user = entitlement.user
            if not user:
                logger.warning(
                    f"Entitlement created but no user found: {entitlement.id}"
                )
                return

            # Determine purchase type
            if entitlement.subscription_id:
                purchase_type = "subscription"
            else:
                purchase_type = "one_time_purchase"

            # Get SKU information
            sku_id = str(entitlement.sku_id) if entitlement.sku_id else None

            # Try to get SKU name (you'll need to map SKU IDs to names)
            sku_name = f"SKU_{sku_id}" if sku_id else "Unknown Product"

            await self.log_discord_purchase(
                user_id=user.id,
                username=str(user),
                purchase_type=purchase_type,
                sku_id=sku_id,
                sku_name=sku_name,
                entitlement_id=str(entitlement.id),
                subscription_id=str(entitlement.subscription_id)
                if entitlement.subscription_id
                else None,
                guild_id=entitlement.guild_id,
                expires_at=entitlement.ends_at,
                notes=f"Entitlement created",
            )

            logger.info(f"Purchase recorded: {user} bought {sku_name}")

        except Exception as e:
            logger.error(f"Error in on_entitlement_create: {e}")

    @commands.Cog.listener()
    async def on_entitlement_update(self, entitlement: discord.Entitlement):
        """Called when an entitlement is updated (e.g., subscription renewed)"""
        try:
            user = entitlement.user
            if not user:
                return

            # Mark previous entitlement as inactive and log the update
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE purchase_records 
                SET is_active = 0 
                WHERE entitlement_id = ?
            """,
                (str(entitlement.id),),
            )
            conn.commit()
            conn.close()

            # Log the update as a new record
            await self.log_discord_purchase(
                user_id=user.id,
                username=str(user),
                purchase_type="renewal" if entitlement.subscription_id else "update",
                sku_id=str(entitlement.sku_id) if entitlement.sku_id else None,
                sku_name=f"SKU_{entitlement.sku_id}"
                if entitlement.sku_id
                else "Unknown Product",
                entitlement_id=str(entitlement.id),
                subscription_id=str(entitlement.subscription_id)
                if entitlement.subscription_id
                else None,
                guild_id=entitlement.guild_id,
                expires_at=entitlement.ends_at,
                notes="Entitlement updated/renewed",
            )

            logger.info(f"Purchase updated: {user} - {entitlement.id}")

        except Exception as e:
            logger.error(f"Error in on_entitlement_update: {e}")

    @commands.Cog.listener()
    async def on_entitlement_delete(self, entitlement: discord.Entitlement):
        """Called when an entitlement is deleted (subscription cancelled, refund, etc.)"""
        try:
            # Mark the entitlement as inactive in the database
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE purchase_records 
                SET is_active = 0, notes = notes || ' | Entitlement deleted'
                WHERE entitlement_id = ?
            """,
                (str(entitlement.id),),
            )
            conn.commit()
            conn.close()

            logger.info(f"Entitlement deleted: {entitlement.id}")

        except Exception as e:
            logger.error(f"Error in on_entitlement_delete: {e}")

    async def setup_protection_table(self):
        """Create protection table if it doesn't exist"""
        async with self.bot.db.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS protection_status (
                    user_id INTEGER PRIMARY KEY,
                    protected_until TIMESTAMP
                )
            """)
            await self.bot.db.commit()

    def _ensure_evil_star_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evil_star_usage (
                user_id INTEGER PRIMARY KEY,
                used_at TEXT NOT NULL
            )
        """)

    def _ensure_donation_usage_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fart_donation_usage (
                donor_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                donated_at TEXT NOT NULL,
                PRIMARY KEY (donor_id, recipient_id)
            )
        """)

    async def has_used_evil_star(self, user_id: int) -> bool:
        """True if the user sealed the Evil Star pact this season."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            self._ensure_evil_star_table(cur)
            cur.execute(
                "SELECT 1 FROM evil_star_usage WHERE user_id = ?",
                (user_id,),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    async def deny_if_evil_star_corrupted(self, ctx) -> bool:
        """
        Block mortal star mechanics after Evil Star use.
        Returns True if the user was blocked (message already sent).
        """
        if not await self.has_used_evil_star(ctx.author.id):
            return False
        await ctx.send(
            f"😈 {ctx.author.mention}, those who have walked the cursed path cannot return to mortal stars...\n"
            f"The Evil Star has corrupted your soul. All other star powers are forbidden until the season resets. 💀"
        )
        return True

    async def has_donated_to_this_season(self, donor_id: int, recipient_id: int) -> bool:
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            self._ensure_donation_usage_table(cur)
            cur.execute(
                "SELECT 1 FROM fart_donation_usage WHERE donor_id = ? AND recipient_id = ?",
                (donor_id, recipient_id),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    async def mark_donated_this_season(self, donor_id: int, recipient_id: int):
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            self._ensure_donation_usage_table(cur)
            cur.execute(
                "INSERT OR REPLACE INTO fart_donation_usage (donor_id, recipient_id, donated_at) VALUES (?, ?, ?)",
                (donor_id, recipient_id, datetime.datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    async def check_usage_cooldown(self, user_id: int, command_name: str, period: str):
        """
        Check daily/weekly command_usage cooldown.
        Returns (allowed: bool, message: str | None).
        """
        if self.yourt_waives_shop_limits():
            return True, None
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS command_usage
                (user_id INTEGER,
                 command_name TEXT,
                 last_used TEXT,
                 PRIMARY KEY (user_id, command_name))
            """)
            cur.execute(
                "SELECT last_used FROM command_usage WHERE user_id=? AND command_name=?",
                (user_id, command_name),
            )
            row = cur.fetchone()
            if not row:
                return True, None

            parsed = safe_parse_datetime(row[0])
            if not parsed:
                return True, None

            if period == "daily":
                last_date = parse_to_est_date(row[0])
                if last_date == get_est_date():
                    est_now = get_est_now()
                    midnight = get_est_midnight()
                    time_until_next = midnight - est_now
                    hours = int(time_until_next.total_seconds() // 3600)
                    minutes = int((time_until_next.total_seconds() % 3600) // 60)
                    pretty = command_name.replace("_", " ").title()
                    return False, (
                        f"You can only use {pretty} once per day! "
                        f"Try again in **{hours}h {minutes}m** (resets at midnight EST)."
                    )
                return True, None

            # weekly
            last_used_date = parsed.date()
            next_available = last_used_date + datetime.timedelta(weeks=1)
            today = datetime.datetime.now().date()
            if next_available > today:
                days_remaining = (next_available - today).days
                if days_remaining < 1:
                    days_remaining = 1
                pretty = command_name.replace("_", " ").title()
                return False, (
                    f"You can only use {pretty} once per week! "
                    f"Try again in {days_remaining} day{'s' if days_remaining != 1 else ''}."
                )
            return True, None
        finally:
            conn.close()

    async def mark_usage_cooldown(self, user_id: int, command_name: str):
        """Record successful use for daily/weekly cooldowns."""
        if self.yourt_waives_shop_limits():
            return
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS command_usage
                (user_id INTEGER,
                 command_name TEXT,
                 last_used TEXT,
                 PRIMARY KEY (user_id, command_name))
            """)
            cur.execute(
                "INSERT OR REPLACE INTO command_usage (user_id, command_name, last_used) VALUES (?, ?, ?)",
                (user_id, command_name, datetime.datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_percent_cost(self, user_id: int, percent: float) -> tuple[int, int]:
        """Return (cost, current_score) for a percent-of-score item. Cost is at least 1."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("SELECT score FROM fart_scores WHERE user_id = ?", (user_id,))
            result = cur.fetchone()
            current_points = result[0] if result else 0
            if self.yourt_waives_shop_limits():
                return 0, current_points
            cost = max(1, int(current_points * percent))
            return cost, current_points
        finally:
            conn.close()

    async def deduct_amount(self, user_id: int, amount: int):
        """Deduct an explicit point amount from a user."""
        if amount <= 0 or self.yourt_waives_shop_limits():
            return
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                (amount, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    # Update the check_points method
    async def check_points(self, user_id: int, item_type: str = "red") -> bool:
        if self.yourt_waives_shop_limits():
            return True
        cost = self.item_costs.get(
            item_type, 10
        )  # Default to 10 if item type not found
        logger.debug(f"Checking points for user {user_id} - needs {cost} points")
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute("SELECT score FROM fart_scores WHERE user_id = ?", (user_id,))
            result = cur.fetchone()
            has_points = result and result[0] >= cost
            logger.debug(f"User {user_id} has enough points: {has_points}")
            conn.close()
            return has_points
        except Exception as e:
            logger.error(f"Error checking points: {e}")
            raise

    # Update the deduct_points method
    async def deduct_points(self, user_id: int, item_type: str = "red"):
        if self.yourt_waives_shop_limits():
            return
        cost = self.item_costs.get(
            item_type, 10
        )  # Default to 10 if item type not found
        logger.debug(f"Deducting {cost} points from user {user_id}")
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                (cost, user_id),
            )
            conn.commit()
            conn.close()
            logger.debug(f"Successfully deducted points from user {user_id}")
        except Exception as e:
            logger.error(f"Error deducting points: {e}")
            raise

    async def is_protected(self, user_id: int) -> bool:
        """Check if user has active protection"""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS protection_status (
                    user_id INTEGER PRIMARY KEY,
                    protected_until TIMESTAMP
                )
            """)
            cur.execute(
                """
                SELECT protected_until FROM protection_status 
                WHERE user_id = ? AND protected_until > datetime('now')
                """,
                (user_id,),
            )
            result = bool(cur.fetchone())
            conn.close()
            return result
        except Exception as e:
            conn.close()
            raise e

    def roll_damage(self, num_dice: int) -> int:
        """Roll specified number of D20 dice and return average"""
        total = sum(random.randint(1, 20) for _ in range(num_dice))
        return total // 2

    def roll_d10_damage(self, num_dice: int) -> int:
        """Roll specified number of D10 dice (no halving)"""
        return sum(random.randint(1, 10) for _ in range(num_dice))

    async def get_sorted_players(self):
        """Get players sorted by score"""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id, score FROM fart_scores ORDER BY score DESC")
        result = cur.fetchall()
        conn.close()
        return result

    async def add_points(self, user_id: int, amount: int):
        """Add points to a user's score"""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE fart_scores SET score = score + ? WHERE user_id = ?",
                (amount, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_user_score(self, user_id: int) -> int:
        """Get a user's current score"""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("SELECT score FROM fart_scores WHERE user_id = ?", (user_id,))
            result = cur.fetchone()
            return result[0] if result else 0
        finally:
            conn.close()

    async def check_gas_shield(self, ctx, target_id, attacker_id, damage_dealt):
        """Check if target has a gas shield. If so, reflect 50% damage back to attacker and consume shield."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gas_shields (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            cur.execute("SELECT 1 FROM gas_shields WHERE user_id = ?", (target_id,))
            if cur.fetchone():
                cur.execute("DELETE FROM gas_shields WHERE user_id = ?", (target_id,))
                conn.commit()
                reflected = damage_dealt // 2
                if reflected > 0:
                    await self.deduct_damage(attacker_id, reflected)
                    await ctx.send(
                        f"<@{target_id}>'s Gas Shield reflected {reflected} damage back at <@{attacker_id}>!"
                    )
        finally:
            conn.close()

    async def check_fart_trap(self, ctx, attacker_id):
        """Check if attacker has a fart trap set on them. Returns True if trapped (attack should be cancelled)."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fart_traps (
                    user_id INTEGER PRIMARY KEY,
                    set_by INTEGER NOT NULL
                )
            """)
            cur.execute(
                "SELECT set_by FROM fart_traps WHERE user_id = ?", (attacker_id,)
            )
            result = cur.fetchone()
            if result:
                set_by = result[0]
                cur.execute("DELETE FROM fart_traps WHERE user_id = ?", (attacker_id,))
                conn.commit()
                damage = self.roll_damage(3)  # 3d20/2
                actual_damage = await self.deduct_damage(attacker_id, damage)
                await ctx.send(
                    f"<@{attacker_id}> triggered a Fart Trap set by <@{set_by}>!\n"
                    f"The attack backfired for {actual_damage} damage to themselves!"
                )
                return True
            return False
        finally:
            conn.close()

    async def find_target(self, user_id: int, direction: str) -> tuple:
        """Find target based on direction (front/back/random_front). back and random_front pick randomly."""
        players = await self.get_sorted_players()
        user_index = next(
            (i for i, (pid, _) in enumerate(players) if pid == user_id), None
        )

        if user_index is None:
            return None

        if direction == "front":
            target_index = user_index - 1
        elif direction == "back":
            if user_index >= len(players) - 1:
                return None
            target_index = random.randint(user_index + 1, len(players) - 1)
        elif direction == "random_front":
            if user_index == 0:
                return None
            target_index = random.randint(0, user_index - 1)
        else:
            return None

        return players[target_index] if 0 <= target_index < len(players) else None

    @commands.command(name="blue_shell", aliases=["blueshell", "shell_blue", "shellblue"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def blue_shell(self, ctx):
        """Hit the leader with 6d20/2 damage. Costs 20 points. Once per day."""
        logger.debug(f"Blue shell command used by {ctx.author.id}")
        try:
            allowed, cooldown_msg = await self.check_usage_cooldown(
                ctx.author.id, "blue_shell", "daily"
            )
            if not allowed:
                return await ctx.send(cooldown_msg)

            if not await self.check_points(ctx.author.id, "blue"):
                return await ctx.send(
                    f"You don't have enough points! Blue Shell costs {self.item_costs['blue']} points!"
                )

            players = await self.get_sorted_players()
            if not players:
                logger.warning("No players found for blue shell")
                return await ctx.send("No players found!")

            leader_id = players[0][0]
            logger.debug(f"Target leader: {leader_id}")

            if await self.is_protected(leader_id):
                logger.debug(f"Leader {leader_id} is protected")
                return await ctx.send(f"<@{leader_id}> is protected by a Star!")

            damage = self.roll_damage(6)
            logger.debug(f"Blue shell damage rolled: {damage}")

            await self.deduct_points(ctx.author.id, "blue")
            await self.mark_usage_cooldown(ctx.author.id, "blue_shell")
            actual_damage = await self.deduct_damage(leader_id, damage)
            await ctx.send(
                f"<@{ctx.author.id}> launched a Blue Shell at leader <@{leader_id}> for {actual_damage} damage!"
            )
            await self.check_gas_shield(ctx, leader_id, ctx.author.id, actual_damage)
        except Exception as e:
            logger.error(f"Error in blue shell command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="red_shell", aliases=["redshell", "shell_red", "shellred"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def red_shell(self, ctx):
        """Hit the player directly in front with 3d20/2 damage. Costs 10 points."""
        if not await self.check_points(ctx.author.id, "red"):
            return await ctx.send(
                f"You don't have enough points! Red Shell costs {self.item_costs['red']} points!"
            )

        target = await self.find_target(ctx.author.id, "front")
        if not target:
            return await ctx.send("No player in front of you!")

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        damage = self.roll_damage(3)
        await self.deduct_points(ctx.author.id, "red")
        actual_damage = await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Red Shell for {actual_damage} damage!"
        )
        await self.check_gas_shield(ctx, target[0], ctx.author.id, actual_damage)

    @commands.command(name="green_shell", aliases=["greenshell", "shell_green", "shellgreen"])
    async def green_shell(self, ctx):
        """Hit a random player in front"""
        if not await self.check_points(ctx.author.id, "green"):
            return await ctx.send(
                f"You don't have enough points! Green Shell costs {self.item_costs['green']} points!"
            )

        target = await self.find_target(ctx.author.id, "random_front")
        if not target:
            return await ctx.send("No players in front of you!")

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        damage = self.roll_damage(2)
        await self.deduct_points(ctx.author.id, "green")
        actual_damage = await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Green Shell for {actual_damage} damage!"
        )
        await self.check_gas_shield(ctx, target[0], ctx.author.id, actual_damage)

    @commands.command(name="banana")
    async def banana(self, ctx):
        """Hit a random player behind"""
        if not await self.check_points(ctx.author.id, "banana"):
            return await ctx.send(
                f"You don't have enough points! Banana costs {self.item_costs['banana']} points!"
            )

        target = await self.find_target(ctx.author.id, "back")
        if not target:
            return await ctx.send("No players behind you!")

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        damage = self.roll_damage(2)
        await self.deduct_points(ctx.author.id, "banana")
        actual_damage = await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Banana for {actual_damage} damage!"
        )
        await self.check_gas_shield(ctx, target[0], ctx.author.id, actual_damage)

    @commands.command(name="star")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def star(self, ctx):
        """Protect yourself from all items for 72 hours. Costs 10% of points. Once per week."""
        logger.debug(f"Star command used by {ctx.author.id}")
        try:
            if await self.deny_if_evil_star_corrupted(ctx):
                return

            allowed, cooldown_msg = await self.check_usage_cooldown(
                ctx.author.id, "star", "weekly"
            )
            if not allowed:
                return await ctx.send(cooldown_msg)

            # Get user's current points
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT score FROM fart_scores WHERE user_id = ?", (ctx.author.id,)
                )
                result = cur.fetchone()

                if not result:
                    await ctx.send(f"{ctx.author.mention}, you have no points!")
                    return

                current_points = result[0]
                # Calculate 10% cost (minimum 1 point); Yourt crash = free
                if self.yourt_waives_shop_limits():
                    star_cost = 0
                else:
                    star_cost = max(1, int(current_points * 0.10))
                    if current_points < star_cost:
                        return await ctx.send(
                            f"You don't have enough points! Star protection costs {star_cost} points (10% of your total)!"
                        )

                protection_end = datetime.datetime.now() + datetime.timedelta(hours=72)
                logger.debug(f"Setting protection until: {protection_end}")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS protection_status (
                        user_id INTEGER PRIMARY KEY,
                        protected_until TIMESTAMP
                    )
                """)
                cur.execute(
                    "INSERT OR REPLACE INTO protection_status (user_id, protected_until) VALUES (?, ?)",
                    (ctx.author.id, protection_end),
                )

                # Deduct the calculated cost
                cur.execute(
                    "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                    (star_cost, ctx.author.id),
                )
                conn.commit()
                logger.debug(
                    f"Protection status updated for user {ctx.author.id}, deducted {star_cost} points"
                )

                await self.mark_usage_cooldown(ctx.author.id, "star")
                await ctx.send(
                    f"<@{ctx.author.id}> is now protected by a Star for 72 hours! (Cost: {star_cost} points)"
                )
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error in star command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="mushroom")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def mushroom(self, ctx):
        """Mushroom Boost - Your next fart gets rolled twice, take the higher result! (Once per week)"""
        try:
            # Check if user has enough points
            if not await self.check_points(ctx.author.id, "mushroom"):
                return await ctx.send(
                    f"You don't have enough points! Mushroom Boost costs {self.item_costs['mushroom']} points!"
                )

            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()

            # Create lucky charms table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lucky_charms (
                    user_id INTEGER PRIMARY KEY,
                    activated_at TEXT
                )
            """)

            # Create weekly usage tracking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lucky_charm_usage (
                    user_id INTEGER,
                    command_name TEXT,
                    last_used TEXT,
                    PRIMARY KEY (user_id, command_name)
                )
            """)

            # Check weekly cooldown
            cur.execute(
                "SELECT last_used FROM lucky_charm_usage WHERE user_id = ? AND command_name = 'mushroom'",
                (ctx.author.id,),
            )
            cooldown_result = cur.fetchone()

            if cooldown_result and not self.yourt_waives_shop_limits():
                last_used_date = datetime.datetime.fromisoformat(
                    cooldown_result[0]
                ).date()
                if (
                    last_used_date + datetime.timedelta(weeks=1)
                    > datetime.datetime.now().date()
                ):
                    days_remaining = (
                        last_used_date
                        + datetime.timedelta(weeks=1)
                        - datetime.datetime.now().date()
                    ).days
                    conn.close()
                    return await ctx.send(
                        f"You can only use Mushroom Boost once per week! Try again in {days_remaining} day{'s' if days_remaining != 1 else ''}."
                    )

            # Check if user already has an active lucky charm
            cur.execute(
                "SELECT activated_at FROM lucky_charms WHERE user_id = ?",
                (ctx.author.id,),
            )
            result = cur.fetchone()

            if result:
                conn.close()
                return await ctx.send(
                    f"You already have a Mushroom Boost active! Use `!fart` to consume it first."
                )

            # Deduct the cost
            await self.deduct_points(ctx.author.id, "mushroom")

            # Activate the lucky charm
            now = datetime.datetime.now()
            cur.execute(
                "INSERT INTO lucky_charms (user_id, activated_at) VALUES (?, ?)",
                (ctx.author.id, now.isoformat()),
            )

            # Update weekly usage cooldown (skipped during Yourt — floor loot is free)
            if not self.yourt_waives_shop_limits():
                cur.execute(
                    """
                INSERT INTO lucky_charm_usage (user_id, command_name, last_used)
                VALUES (?, 'mushroom', ?)
                ON CONFLICT(user_id, command_name) 
                DO UPDATE SET last_used = ?
                """,
                    (ctx.author.id, now.isoformat(), now.isoformat()),
                )

            conn.commit()
            conn.close()

            await ctx.send(
                f" **Mushroom Boost Activated!** \n"
                f"<@{ctx.author.id}> Your next `!fart` will be rolled twice, and you'll get the higher result!"
            )

        except Exception as e:
            logger.error(f"Error in mushroom command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="bobomb")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def bobomb(self, ctx):
        """Hit the top 5 players with explosion damage"""
        logger.debug(f"Bob-omb command used by {ctx.author.id}")

        if not await self.check_points(ctx.author.id, "bobomb"):
            return await ctx.send(
                f"You don't have enough points! Bob-omb costs {self.item_costs['bobomb']} points!"
            )

        players = await self.get_sorted_players()
        if not players:
            return await ctx.send("No players found!")

        # Get top 5 players
        top_5 = players[:5]
        damage = self.roll_damage(3)  # 3d20/2 damage

        # Track who got hit and their damage
        hit_info = []  # List of (mention, actual_damage) tuples
        protected_players = []

        hit_player_ids = []
        for player_id, _ in top_5:
            if await self.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                actual_damage = await self.deduct_damage(player_id, damage)
                hit_info.append((f"<@{player_id}>", actual_damage))
                hit_player_ids.append((player_id, actual_damage))

        await self.deduct_points(ctx.author.id, "bobomb")

        # Construct response message
        response = f"<@{ctx.author.id}> threw a Bob-omb!\n"

        if hit_info:
            # Group by damage amount for cleaner display
            damage_groups = {}
            for mention, dmg in hit_info:
                if dmg not in damage_groups:
                    damage_groups[dmg] = []
                damage_groups[dmg].append(mention)

            for dmg, mentions in damage_groups.items():
                response += f"💥 {', '.join(mentions)} took {dmg} damage!\n"

        if protected_players:
            response += (
                "⭐ " + ", ".join(protected_players) + " were protected by Stars!"
            )

        await ctx.send(response)

        # Check gas shields for each hit player
        for player_id, actual_damage in hit_player_ids:
            await self.check_gas_shield(ctx, player_id, ctx.author.id, actual_damage)

    @commands.command(name="thunder_fart", aliases=["thunderfart", "fart_thunder", "fartthunder"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def thunder_fart(self, ctx):
        """Hit ALL players for 10 damage each. Costs 10 points. Once per week."""
        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "thunder_fart", "weekly"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        if not await self.check_points(ctx.author.id, "thunder_fart"):
            return await ctx.send(
                f"You don't have enough points! Thunder Fart costs {self.item_costs['thunder_fart']} points!"
            )

        players = await self.get_sorted_players()
        if not players:
            return await ctx.send("No players found!")

        await self.deduct_points(ctx.author.id, "thunder_fart")
        await self.mark_usage_cooldown(ctx.author.id, "thunder_fart")

        damage = 10
        hit_players = []
        hit_player_ids = []
        protected_players = []

        for player_id, _ in players:
            if player_id == ctx.author.id:
                continue
            if await self.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                actual_damage = await self.deduct_damage(player_id, damage)
                hit_players.append((f"<@{player_id}>", actual_damage))
                hit_player_ids.append((player_id, actual_damage))

        response = f"<@{ctx.author.id}> unleashed a Thunder Fart!\n"
        if hit_players:
            response += f"Everyone took {damage} damage!\n"
            response += f"Hit {len(hit_players)} players!\n"
        if protected_players:
            response += "⭐ " + ", ".join(protected_players) + " were protected by Stars!"

        await ctx.send(response)

        # Check gas shields for each hit player
        for player_id, actual_damage in hit_player_ids:
            await self.check_gas_shield(ctx, player_id, ctx.author.id, actual_damage)

    @commands.command(name="gas_shield", aliases=["gasshield", "shield_gas", "shieldgas", "fart_shield", "fartshield"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def gas_shield(self, ctx):
        """Activate a shield that reflects 50% damage back at the next attacker"""
        if not await self.check_points(ctx.author.id, "gas_shield"):
            return await ctx.send(
                f"You don't have enough points! Gas Shield costs {self.item_costs['gas_shield']} points!"
            )

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gas_shields (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            cur.execute(
                "SELECT 1 FROM gas_shields WHERE user_id = ?", (ctx.author.id,)
            )
            if cur.fetchone():
                return await ctx.send(
                    f"{ctx.author.mention}, you already have a Gas Shield active!"
                )

            await self.deduct_points(ctx.author.id, "gas_shield")
            cur.execute(
                "INSERT INTO gas_shields (user_id) VALUES (?)", (ctx.author.id,)
            )
            conn.commit()
        finally:
            conn.close()

        await ctx.send(
            f"<@{ctx.author.id}> activated a Gas Shield! The next attack against them will reflect 50% damage back!"
        )

    @commands.command(name="stink_bomb", aliases=["stinkbomb", "bomb_stink", "bombstink"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def stink_bomb(self, ctx):
        """Hit a random player (anyone) for heavy damage"""
        if not await self.check_points(ctx.author.id, "stink_bomb"):
            return await ctx.send(
                f"You don't have enough points! Stink Bomb costs {self.item_costs['stink_bomb']} points!"
            )

        players = await self.get_sorted_players()
        # Filter out self
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if not targets:
            return await ctx.send("No other players found!")

        target_id, _ = random.choice(targets)

        if await self.is_protected(target_id):
            return await ctx.send(f"<@{target_id}> is protected by a Star!")

        damage = self.roll_damage(3)  # 3d20/2
        await self.deduct_points(ctx.author.id, "stink_bomb")
        actual_damage = await self.deduct_damage(target_id, damage)
        await ctx.send(
            f"<@{ctx.author.id}> threw a Stink Bomb at <@{target_id}> for {actual_damage} damage!"
        )
        await self.check_gas_shield(ctx, target_id, ctx.author.id, actual_damage)

    @commands.command(name="fart_rocket", aliases=["fartrocket", "rocket_fart", "rocketfart"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_rocket(self, ctx):
        """Swap scores with a random player. Costs 100 points. Once per week."""
        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "fart_rocket", "weekly"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        if not await self.check_points(ctx.author.id, "fart_rocket"):
            return await ctx.send(
                f"You don't have enough points! Fart Rocket costs {self.item_costs['fart_rocket']} points!"
            )

        players = await self.get_sorted_players()
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if not targets:
            return await ctx.send("No other players found!")

        target = random.choice(targets)

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        # Get both scores and swap them
        my_score = await self.get_user_score(ctx.author.id)
        target_score = await self.get_user_score(target[0])

        cost = (
            0
            if self.yourt_waives_shop_limits()
            else self.item_costs["fart_rocket"]
        )
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            # Swap scores, then deduct cost from the user's new score
            new_user_score = max(0, target_score - cost)
            cur.execute(
                "UPDATE fart_scores SET score = ? WHERE user_id = ?",
                (new_user_score, ctx.author.id),
            )
            cur.execute(
                "UPDATE fart_scores SET score = ? WHERE user_id = ?",
                (my_score, target[0]),
            )
            conn.commit()
        finally:
            conn.close()

        await self.mark_usage_cooldown(ctx.author.id, "fart_rocket")
        await ctx.send(
            f"<@{ctx.author.id}> launched a Fart Rocket and swapped scores with <@{target[0]}>!\n"
            f"<@{ctx.author.id}>: {my_score} -> {target_score} -> {new_user_score} (-{cost} cost)\n"
            f"<@{target[0]}>: {target_score} -> {my_score}"
        )

    @commands.command(name="fart_trap", aliases=["farttrap", "trap_fart", "trapfart"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_trap(self, ctx):
        """Set a trap on a random player - their next attack backfires on them!"""
        if not await self.check_points(ctx.author.id, "fart_trap"):
            return await ctx.send(
                f"You don't have enough points! Fart Trap costs {self.item_costs['fart_trap']} points!"
            )

        players = await self.get_sorted_players()
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if not targets:
            return await ctx.send("No other players found!")

        target_id, _ = random.choice(targets)

        if await self.is_protected(target_id):
            return await ctx.send(f"<@{target_id}> is protected by a Star!")

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fart_traps (
                    user_id INTEGER PRIMARY KEY,
                    set_by INTEGER NOT NULL
                )
            """)
            cur.execute(
                "SELECT 1 FROM fart_traps WHERE user_id = ?", (target_id,)
            )
            if cur.fetchone():
                return await ctx.send(
                    f"<@{target_id}> already has a trap set on them!"
                )

            await self.deduct_points(ctx.author.id, "fart_trap")
            cur.execute(
                "INSERT INTO fart_traps (user_id, set_by) VALUES (?, ?)",
                (target_id, ctx.author.id),
            )
            conn.commit()
        finally:
            conn.close()

        await ctx.send(
            f"<@{ctx.author.id}> set a fart trap! "
            f"Someone's next attack will backfire on them..."
        )

    @commands.command(name="stink_cloud", aliases=["stinkcloud", "cloud_stink", "cloudstink"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def stink_cloud(self, ctx):
        """Blind a random player, blocking shop items for 24 hours. Costs 5% of points. Once per day."""
        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "stink_cloud", "daily"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        cost, current_points = await self.get_percent_cost(ctx.author.id, 0.05)
        if current_points < cost:
            return await ctx.send(
                f"You don't have enough points! Stink Cloud costs {cost} points (5% of your total)!"
            )

        players = await self.get_sorted_players()
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if not targets:
            return await ctx.send("No other players found!")

        target_id, _ = random.choice(targets)

        if await self.is_protected(target_id):
            return await ctx.send(f"<@{target_id}> is protected by a Star!")

        await self.deduct_amount(ctx.author.id, cost)
        await self.mark_usage_cooldown(ctx.author.id, "stink_cloud")

        block_until = datetime.datetime.now() + datetime.timedelta(hours=24)
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_blocks (
                    user_id INTEGER PRIMARY KEY,
                    blocked_until TIMESTAMP
                )
            """)
            cur.execute(
                "INSERT OR REPLACE INTO shop_blocks (user_id, blocked_until) VALUES (?, ?)",
                (target_id, block_until),
            )
            conn.commit()
        finally:
            conn.close()

        await ctx.send(
            f"<@{ctx.author.id}> released a Stink Cloud on <@{target_id}>! (-{cost} points)\n"
            f"<@{target_id}> is blinded and can't use shop items for 24 hours!"
        )

    @commands.command(name="gas_gamble", aliases=["gasgamble", "gamble_gas", "gamblegas", "fart_gamble", "fartgamble"])
    async def gas_gamble(self, ctx, amount: int = None):
        """Gamble any amount of points! 40% chance to double, 60% chance to lose. Usage: !gas_gamble <amount>"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if amount is None or amount <= 0:
            return await ctx.send(
                f"{ctx.author.mention}, specify an amount to gamble! Usage: `!gas_gamble <amount>`"
            )

        user_score = await self.get_user_score(ctx.author.id)
        if user_score < amount:
            return await ctx.send(
                f"You don't have enough points! You have {user_score} but tried to gamble {amount}."
            )

        # Deduct the bet
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                (amount, ctx.author.id),
            )
            conn.commit()
        finally:
            conn.close()

        if random.random() < 0.4:
            # Win - get double back (net gain = amount)
            winnings = amount * 2
            await self.add_points(ctx.author.id, winnings)
            await ctx.send(
                f"<@{ctx.author.id}> gambled {amount} points and **WON**! +{winnings} points!"
            )
        else:
            # Lose - already deducted
            await ctx.send(
                f"<@{ctx.author.id}> gambled {amount} points and **LOST**! -{amount} points down the drain!"
            )

    @commands.command(name="fart_donation", aliases=["fartdonation", "donation_fart", "donationfart", "fart_donate", "fartdonate"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_donation(self, ctx, target: discord.Member = None, amount: int = None):
        """Donate points to another player (max 100; once per recipient per season). Usage: !fart_donation @user <amount>"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if target is None or amount is None:
            return await ctx.send(
                f"{ctx.author.mention}, usage: `!fart_donation @user <amount>` "
                f"(max 100 points)"
            )

        if amount <= 0:
            return await ctx.send("You must donate at least 1 point!")

        if amount > 100:
            return await ctx.send(
                f"{ctx.author.mention}, you can only be so generous — donations are capped at **100** points. "
                f"Perhaps try `!fart_gift` next time?"
            )

        if target.id == ctx.author.id:
            return await ctx.send("You can't donate to yourself!")

        if target.bot:
            return await ctx.send("You can't donate to a bot!")

        if await self.has_donated_to_this_season(ctx.author.id, target.id):
            return await ctx.send(
                f"{ctx.author.mention}, you've already donated to <@{target.id}> this season! "
                f"One gift of points per player — try `!fart_gift` if you still want to share the gas."
            )

        user_score = await self.get_user_score(ctx.author.id)
        if user_score < amount:
            return await ctx.send(
                f"You don't have enough points! You have {user_score} but tried to donate {amount}."
            )

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                (amount, ctx.author.id),
            )
            conn.commit()
        finally:
            conn.close()

        await self.add_points(target.id, amount)
        await self.mark_donated_this_season(ctx.author.id, target.id)

        await ctx.send(
            f"<@{ctx.author.id}> donated {amount} points to <@{target.id}>! "
            f"(Max 100 • once per player per season — feeling bigger-hearted? Try `!fart_gift`!)"
        )

    @commands.command(name="fart_court", aliases=["fartcourt", "court_fart", "courtfart"])
    async def fart_court(self, ctx, target: discord.Member = None, amount: int = None):
        """Take another specific player to court! 50% chance they pay you the specified amount, 50% chance you pay them. Once per week. Usage: !fart_court @user <amount>"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if target is None or amount is None:
            return await ctx.send(
                f"{ctx.author.mention}, usage: `!fart_court @user <amount>`"
            )

        if amount <= 0:
            return await ctx.send("You must stake at least 1 point!")

        if target.id == ctx.author.id:
            return await ctx.send("You can't take yourself to court!")

        if target.bot:
            return await ctx.send("You can't take a bot to court!")

        # Weekly cooldown — same command_usage table as !big_banana.
        # Only blocks if already used successfully; failed attempts never write here.
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS command_usage
                (user_id INTEGER,
                 command_name TEXT,
                 last_used TEXT,
                 PRIMARY KEY (user_id, command_name))
            """)
            cur.execute(
                "SELECT last_used FROM command_usage WHERE user_id=? AND command_name='fart_court'",
                (ctx.author.id,),
            )
            row = cur.fetchone()
            if row:
                parsed = safe_parse_datetime(row[0])
                if parsed:
                    last_used_date = parsed.date()
                    next_available = last_used_date + datetime.timedelta(weeks=1)
                    if next_available > datetime.datetime.now().date():
                        days_remaining = (next_available - datetime.datetime.now().date()).days
                        if days_remaining < 1:
                            days_remaining = 1
                        return await ctx.send(
                            f"{ctx.author.mention}, you've already used Fart Court this week! "
                            f"Try again in {days_remaining} day{'s' if days_remaining != 1 else ''}."
                        )
        finally:
            conn.close()

        # Star protects the defendant — failed attempts do not consume weekly usage
        if await self.is_protected(target.id):
            return await ctx.send(f"<@{target.id}> is protected by a Star!")

        author_score = await self.get_user_score(ctx.author.id)
        target_score = await self.get_user_score(target.id)

        if author_score < amount:
            return await ctx.send(
                f"You don't have enough points! You have {author_score} but tried to stake {amount}."
            )
        if target_score < amount:
            return await ctx.send(
                f"<@{target.id}> doesn't have enough points! They have {target_score} but need {amount}."
            )

        if random.random() < 0.5:
            # Target pays author
            payer_id, payee_id = target.id, ctx.author.id
            result_msg = (
                f"<@{ctx.author.id}> took <@{target.id}> to court and **WON**! "
                f"<@{target.id}> pays {amount} points!"
            )
        else:
            # Author pays target
            payer_id, payee_id = ctx.author.id, target.id
            result_msg = (
                f"<@{ctx.author.id}> took <@{target.id}> to court and **LOST**! "
                f"<@{ctx.author.id}> pays {amount} points!"
            )

        # Only a successful court case records weekly usage (same transaction as transfer)
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                (amount, payer_id),
            )
            if cur.rowcount != 1:
                return await ctx.send(
                    f"{ctx.author.mention}, court fell through — couldn't update the payer's score. Weekly usage not spent."
                )
            cur.execute(
                "UPDATE fart_scores SET score = score + ? WHERE user_id = ?",
                (amount, payee_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return await ctx.send(
                    f"{ctx.author.mention}, court fell through — couldn't update the payee's score. Weekly usage not spent."
                )
            cur.execute(
                "INSERT OR REPLACE INTO command_usage (user_id, command_name, last_used) VALUES (?, 'fart_court', ?)",
                (ctx.author.id, datetime.datetime.now().isoformat()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("fart_court failed during score transfer")
            return await ctx.send(
                f"{ctx.author.mention}, court fell through due to an error. Weekly usage not spent."
            )
        finally:
            conn.close()

        await ctx.send(result_msg)

    @commands.command(name="fart_leech", aliases=["fartleech", "leech_fart", "leechfart"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_leech(self, ctx):
        """Steal 2d20/2 points from a random player. Costs 5 points. Once per day."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "fart_leech", "daily"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        if not await self.check_points(ctx.author.id, "fart_leech"):
            return await ctx.send(
                f"You don't have enough points! Fart Leech costs {self.item_costs['fart_leech']} points!"
            )

        players = await self.get_sorted_players()
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if not targets:
            return await ctx.send("No other players found!")

        target_id, target_score = random.choice(targets)

        if await self.is_protected(target_id):
            return await ctx.send(f"<@{target_id}> is protected by a Star!")

        await self.deduct_points(ctx.author.id, "fart_leech")
        await self.mark_usage_cooldown(ctx.author.id, "fart_leech")

        steal_amount = self.roll_damage(2)  # 2d20/2
        # Can't steal more than the target has
        actual_steal = min(steal_amount, target_score)

        if actual_steal <= 0:
            await self.add_points(ctx.author.id, 0)
            return await ctx.send(
                f"<@{ctx.author.id}> tried to leech <@{target_id}> but they have no points to steal!"
            )

        await self.deduct_damage(target_id, actual_steal)
        await self.add_points(ctx.author.id, actual_steal)

        await ctx.send(
            f"<@{ctx.author.id}> leeched {actual_steal} points from <@{target_id}>!"
        )
        await self.check_gas_shield(ctx, target_id, ctx.author.id, actual_steal)

    @commands.command(name="fart_twister", aliases=["farttwister", "twister_fart", "twisterfart"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_twister(self, ctx):
        """Launch a random player into another! Costs 50 points, uses daily fart, once per week."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "fart_twister", "weekly"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        # Check daily action cooldown (Yourt crash waives the daily fart cost)
        if not self.yourt_waives_shop_limits():
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                    (ctx.author.id,),
                )
                row = cur.fetchone()
                if row:
                    parsed = safe_parse_datetime(row[0])
                    if parsed:
                        last_date = parse_to_est_date(row[0])
                        if last_date == get_est_date():
                            await ctx.send(
                                f"{ctx.author.mention}, you've already used your daily action today! "
                                f"Fart Twister uses your daily fart."
                            )
                            return
            finally:
                conn.close()

        if not await self.check_points(ctx.author.id, "fart_twister"):
            return await ctx.send(
                f"You don't have enough points! Fart Twister costs {self.item_costs['fart_twister']} points!"
            )

        players = await self.get_sorted_players()
        targets = [(pid, score) for pid, score in players if pid != ctx.author.id]
        if len(targets) < 2:
            return await ctx.send("Not enough players for a Fart Twister! Need at least 2 other players.")

        # Pick two different random targets
        player_a, player_b = random.sample(targets, 2)
        player_a_id, player_a_score = player_a
        player_b_id, _ = player_b

        # All-or-nothing: if either is protected, fizzle
        if await self.is_protected(player_a_id) or await self.is_protected(player_b_id):
            return await ctx.send(
                f"The Fart Twister fizzles! One of the targets has Star protection. "
                f"Your points are safe."
            )

        damage = player_a_score // 2

        # Deduct cost and update daily action
        await self.deduct_points(ctx.author.id, "fart_twister")
        await self.mark_usage_cooldown(ctx.author.id, "fart_twister")
        if not self.yourt_waives_shop_limits():
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE fart_scores SET date_last_updated=? WHERE user_id=?",
                    (datetime.datetime.now().isoformat(), ctx.author.id),
                )
                conn.commit()
            finally:
                conn.close()

        # Apply damage to both targets
        actual_damage_a = await self.deduct_damage(player_a_id, damage)
        actual_damage_b = await self.deduct_damage(player_b_id, damage)

        await ctx.send(
            f"🌪️ **FART TWISTER!** <@{ctx.author.id}> unleashed a massive twister!\n"
            f"<@{player_a_id}> was launched into the air and crashed into <@{player_b_id}>!\n"
            f"💥 <@{player_a_id}> took {actual_damage_a} damage!\n"
            f"💥 <@{player_b_id}> took {actual_damage_b} damage!\n"
            f"*(Damage based on half of <@{player_a_id}>'s {player_a_score} points)*"
        )

        await self.check_gas_shield(ctx, player_a_id, ctx.author.id, actual_damage_a)
        await self.check_gas_shield(ctx, player_b_id, ctx.author.id, actual_damage_b)

    @commands.command(name="fart_lance", aliases=["fartlance", "lance_fart", "lancefart"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fart_lance(self, ctx):
        """Ice Lance - hit up to 3 players ahead with diminishing damage!"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if not await self.check_points(ctx.author.id, "fart_lance"):
            return await ctx.send(
                f"You don't have enough points! Fart Lance costs {self.item_costs['fart_lance']} points!"
            )

        players = await self.get_sorted_players()
        user_index = next(
            (i for i, (pid, _) in enumerate(players) if pid == ctx.author.id), None
        )

        if user_index is None or user_index == 0:
            return await ctx.send("No players in front of you to lance!")

        await self.deduct_points(ctx.author.id, "fart_lance")

        # Hit up to 3 players ahead with diminishing damage: 3d20/2, 2d20/2, 1d20/2
        dice_counts = [3, 2, 1]
        hit_results = []
        protected_players = []
        hit_player_ids = []

        for i, num_dice in enumerate(dice_counts):
            target_index = user_index - 1 - i
            if target_index < 0:
                break

            target_id, _ = players[target_index]

            if await self.is_protected(target_id):
                protected_players.append(f"<@{target_id}>")
                continue

            damage = self.roll_damage(num_dice)
            actual_damage = await self.deduct_damage(target_id, damage)
            hit_results.append((f"<@{target_id}>", actual_damage, num_dice))
            hit_player_ids.append((target_id, actual_damage))

        response = f"🧊 **FART LANCE!** <@{ctx.author.id}> fired a triple-burst of gas!\n"

        if hit_results:
            for mention, dmg, dice in hit_results:
                response += f"💥 {mention} took {dmg} damage! ({dice}d20/2)\n"

        if protected_players:
            response += "⭐ " + ", ".join(protected_players) + " blocked by Star protection!"

        if not hit_results and not protected_players:
            response += "The lance hit nothing but air!"

        await ctx.send(response)

        for player_id, actual_damage in hit_player_ids:
            await self.check_gas_shield(ctx, player_id, ctx.author.id, actual_damage)

    @commands.command(name="big_banana", aliases=["bigbanana", "banana_big", "bananabig"])
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def big_banana(self, ctx):
        """Hit a random player behind you with 4d10 damage! Costs 20 points. Once per day."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        allowed, cooldown_msg = await self.check_usage_cooldown(
            ctx.author.id, "big_banana", "daily"
        )
        if not allowed:
            return await ctx.send(cooldown_msg)

        if not await self.check_points(ctx.author.id, "big_banana"):
            return await ctx.send(
                f"You don't have enough points! Big Banana costs {self.item_costs['big_banana']} points!"
            )

        target = await self.find_target(ctx.author.id, "back")
        if not target:
            return await ctx.send("No players behind you!")

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        damage = self.roll_d10_damage(4)  # 4d10
        await self.deduct_points(ctx.author.id, "big_banana")
        await self.mark_usage_cooldown(ctx.author.id, "big_banana")
        actual_damage = await self.deduct_damage(target[0], damage)

        await ctx.send(
            f"🍌 **BIG BANANA!** <@{ctx.author.id}> hurled a massive banana at <@{target[0]}> "
            f"for {actual_damage} damage! (4d10)"
        )
        await self.check_gas_shield(ctx, target[0], ctx.author.id, actual_damage)

    @commands.command(name="fart_shop", aliases=["fartshop", "shop_fart", "shopfart", "shop"])
    async def fart_shop(self, ctx):
        """Display all available shop items"""
        yourt_free = self.yourt_waives_shop_limits()
        shop_title = "💨 Fart Shop"
        shop_description = (
            "Use the commands below to purchase items:\n"
            "Aliases: `!fart_shop` `!fartshop` `!shop_fart` `!shopfart` `!shop`"
        )
        shop_color = discord.Color.gold()
        if yourt_free:
            from cogs.fun import drunken_case

            shop_title = ":yourt: " + drunken_case("Fart Shop YOURT MESS")
            shop_description = (
                ":yourt: "
                + drunken_case("items everywhere grab them they are FREE for one hour")
                + " :yourt:\n"
                + shop_description
            )
            shop_color = discord.Color.green()

        embed = discord.Embed(
            title=shop_title,
            description=shop_description,
            color=shop_color,
        )

        items = [
            (
                "Blue Shell (!blue_shell / !blueshell)",
                "Hits the leader with 6d20/2 damage (once/day)\n*Seeks the strongest stench...*",
                self.item_costs["blue"],
            ),
            (
                "Red Shell (!red_shell / !redshell)",
                "Hits the player directly in front of you with 3d20/2 damage\n*Locked on and loaded.*",
                self.item_costs["red"],
            ),
            (
                "Green Shell (!green_shell / !greenshell)",
                "Hits a random player in front of you with 2d20/2 damage\n*Bouncing off the walls.*",
                self.item_costs["green"],
            ),
            (
                "Banana (!banana)",
                "Hits a random player behind you with 2d20/2 damage\n*Slippery. Normal banana, normal odds.*",
                self.item_costs["banana"],
            ),
            (
                "Big Banana (!big_banana / !bigbanana)",
                "Hits a random player behind you with 4d10 damage (once/day)\n*Big slippery. More banana-y.*",
                self.item_costs["big_banana"],
            ),
            (
                "Star (!star)",
                "Protects you from all items for 72 hours (10% of points, once/week)\n*Forbidden if you've used Evil Star this season.*",
                "10%",
            ),
            (
                "Mushroom (!mushroom)",
                "Mushroom Boost - Next fart rolls twice, take higher! (Once per week)\n*Eat this. Trust me.*",
                self.item_costs["mushroom"],
            ),
            (
                "Bob-omb (!bobomb)",
                "Hits the top 5 players with 3d20/2 damage\n*Nobody is safe from this blast.*",
                self.item_costs["bobomb"],
            ),
            (
                "Fart Star (!fart_star / !fartstar)",
                "Removes star protection from a random protected user (10% of points, once/week)\n*Forbidden if you've used Evil Star this season.*",
                "10% of pts",
            ),
            (
                "Evil Star (!evil_star / !evilstar)",
                "😈 Doubles your points... but ONLY if you have exactly 666 points! (FREE, once/season)\n*Sealing the pact locks you out of all other stars until reset.*",
                "FREE",
            ),
            (
                "Thunder Fart (!thunder_fart / !thunderfart)",
                "Hits ALL players for 10 damage each (once/week)\n*The whole room trembles.*",
                self.item_costs["thunder_fart"],
            ),
            (
                "Gas Shield (!gas_shield / !gasshield)",
                "Reflects 50% damage back at the next attacker\n*Touch me and find out.*",
                self.item_costs["gas_shield"],
            ),
            (
                "Stink Bomb (!stink_bomb / !stinkbomb)",
                "Hits a random player (anyone!) for 3d20/2 damage\n*Nowhere to hide.*",
                self.item_costs["stink_bomb"],
            ),
            (
                "Fart Rocket (!fart_rocket / !fartrocket)",
                "Swap scores with a random player (once/week)\n*Identity theft is flattery.*",
                self.item_costs["fart_rocket"],
            ),
            (
                "Fart Lance (!fart_lance / !fartlance)",
                "Hits up to 3 players ahead with diminishing damage (3/2/1 d20/2)\n*A triple-burst of gaseous fury.*",
                self.item_costs["fart_lance"],
            ),
            (
                "Fart Trap (!fart_trap / !farttrap)",
                "Set a hidden trap - a player's next attack backfires on them!\n*You'll never see it coming...*",
                self.item_costs["fart_trap"],
            ),
            (
                "Fart Twister (!fart_twister / !farttwister)",
                "Launch a player into another! Damage = half the launched player's score. Uses daily fart. (once/week)\n*What goes up must come crashing down.*",
                self.item_costs["fart_twister"],
            ),
            (
                "Stink Cloud (!stink_cloud / !stinkcloud)",
                "Blinds a random player, blocking them from shop items for 24 hours (5% of points, once/day)\n*Can't buy what you can't see.*",
                "5%",
            ),
            (
                "Gas Gamble (!gas_gamble / !gasgamble <amount>)",
                "Gamble any amount! 40% chance to double, 60% to lose it all.\n*Feeling lucky, punk?*",
                "Custom",
            ),
            (
                "Fart Leech (!fart_leech / !fartleech)",
                "Steal 2d20/2 points from a random player and add to your score (once/day)\n*What's yours is mine.*",
                self.item_costs["fart_leech"],
            ),
            (
                "Fart Donation (!fart_donation / !fartdonation @user <amount>)",
                "Donate your points to another player. **Maximum 100 points. Once per player per season.**\n*You can only be so generous — try !fart_gift for more.*",
                "Max 100",
            ),
            (
                "Fart Court (!fart_court / !fartcourt @user <amount>)",
                "Take another player to court! 50% they pay you, 50% you pay them. Blocked by Star. (Once per week)\n*Justice is blind... and gaseous.*",
                "Custom",
            ),
        ]

        for name, description, cost in items:
            if yourt_free and cost not in ("Custom", "Max 100", "FREE"):
                cost_display = "FREE"
            elif isinstance(cost, str):
                cost_display = cost
            else:
                cost_display = f"{cost} points"
            embed.add_field(
                name=f"{name} - {cost_display}", value=description, inline=False
            )

        await ctx.send(embed=embed)

    # Add this method to the ShopCog class
    async def deduct_damage(self, user_id: int, damage: int) -> int:
        print("Deducting damage...")
        """Deduct damage amount from user's points. Double damage if user has giga target role. Returns actual damage dealt."""
        try:
            actual_damage = damage
            # Check if user has the giga target role
            guild = self.bot.get_guild(self.guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    giga_role = guild.get_role(self.giga_target_role_id)
                    if giga_role and giga_role in member.roles:
                        actual_damage = damage * 2
                        logger.info(
                            f"User {user_id} has giga target role - damage doubled to {actual_damage}"
                        )

            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE fart_scores SET score = CASE WHEN score - ? < 0 THEN 0 ELSE score - ? END WHERE user_id = ?",
                (actual_damage, actual_damage, user_id),
            )
            conn.commit()
            conn.close()
            logger.debug(f"Deducted {actual_damage} damage points from user {user_id}")
            return actual_damage
        except Exception as e:
            logger.error(f"Error deducting damage: {e}")
            raise

    @commands.command(name="giga_fart_cannon", aliases=["gigafartcannon", "giga_cannon", "gigacannon", "fart_cannon", "fartcannon"])
    @commands.cooldown(
        1, 86400, commands.BucketType.guild
    )  # Once per day for the entire server
    async def giga_fart_cannon(self, ctx):
        """Fire the Giga Fart Cannon! Assigns double damage debuff to a random top 5 player. (Once per day for entire server)"""
        logger.debug(f"Giga Fart Cannon command used by {ctx.author.id}")

        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        try:
            # Get top 5 players
            players = await self.get_sorted_players()
            if not players or len(players) < 1:
                return await ctx.send("Not enough players in the fart ranks!")

            top_5 = players[:5]

            # Select a random player from top 5
            target = random.choice(top_5)
            target_id = target[0]

            # Get guild and role
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                logger.error(f"Could not find guild {self.guild_id}")
                return await ctx.send("An error occurred - guild not found.")

            giga_role = guild.get_role(self.giga_target_role_id)
            if not giga_role:
                logger.error(
                    f"Could not find giga target role {self.giga_target_role_id}"
                )
                return await ctx.send("An error occurred - role not found.")

            target_member = guild.get_member(target_id)
            if not target_member:
                logger.error(f"Could not find member {target_id}")
                return await ctx.send("An error occurred - target player not found.")

            # Remove role from everyone first
            for member in guild.members:
                if giga_role in member.roles:
                    await member.remove_roles(giga_role)
                    logger.info(f"Removed giga target role from {member.id}")

            # Add role to new target
            await target_member.add_roles(giga_role)
            logger.info(f"Added giga target role to {target_id}")

            await ctx.send(
                f"💨 **GIGA FART CANNON FIRED!**\n"
                f"<@{target_id}> has been marked! They will take **DOUBLE DAMAGE** from all shop items!\n"
                f" This command is now on cooldown for the entire server for 24 hours!"
            )

        except Exception as e:
            logger.error(f"Error in giga_fart_cannon command: {e}", exc_info=True)
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="fart_star", aliases=["fartstar", "star_fart", "starfart", "star_killer", "starkiller"])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def fart_star(self, ctx):
        """
        Remove the star protection from a random protected user.
        Cost: 10% of user's current points (minimum 1 point). Once per week.
        """
        logger.debug(f"Fart Star command used by {ctx.author.id}")
        try:
            if ctx.channel.id != self.fart_channel_id:
                logger.debug(f"Wrong channel: {ctx.channel.id}")
                await ctx.send(
                    f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
                )
                return

            if await self.deny_if_evil_star_corrupted(ctx):
                return

            allowed, cooldown_msg = await self.check_usage_cooldown(
                ctx.author.id, "fart_star", "weekly"
            )
            if not allowed:
                return await ctx.send(cooldown_msg)

            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                # Calculate cost: 10% of user's current points (minimum 1)
                cur.execute(
                    "SELECT score FROM fart_scores WHERE user_id = ?",
                    (ctx.author.id,),
                )
                result = cur.fetchone()
                user_score = result[0] if result else 0
                if self.yourt_waives_shop_limits():
                    cost = 0
                else:
                    cost = max(1, int(user_score * 0.10))
                    if user_score < 1:
                        return await ctx.send(
                            f"You don't have enough points! Fart Star costs 10% of your points (minimum 1)."
                        )

                # Get protected users whose protection hasn't expired
                cur.execute(
                    """
                    SELECT user_id, protected_until
                    FROM protection_status
                    WHERE protected_until > ?
                """,
                    (datetime.datetime.now(),),
                )

                protected_users = cur.fetchall()

                if not protected_users:
                    await ctx.send(
                        f"{ctx.author.mention}, there are no users with active star protection right now!"
                    )
                    return

                # Select a random protected user
                target_user_id, protected_until = random.choice(protected_users)

                # Remove their protection
                cur.execute(
                    """
                    DELETE FROM protection_status
                    WHERE user_id = ?
                """,
                    (target_user_id,),
                )

                # Deduct 10% of points
                cur.execute(
                    "UPDATE fart_scores SET score = score - ? WHERE user_id = ?",
                    (cost, ctx.author.id),
                )
                conn.commit()

                await self.mark_usage_cooldown(ctx.author.id, "fart_star")

                # Send success message
                await ctx.send(
                    f"💥 {ctx.author.mention} used Fart Star (-{cost} points)! "
                    f"<@{target_user_id}>'s star protection has been destroyed! 💥"
                )

                logger.info(
                    f"User {ctx.author.id} removed star protection from user {target_user_id}"
                )

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Error in fart_star command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="evil_star", aliases=["evilstar", "star_evil", "starevil"])
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def evil_star(self, ctx):
        """
        Double your points... but only if you have exactly 666 points.
        The dark star only reveals itself to those who walk the cursed path.
        Once per season — also locks you out of all other star commands until reset.
        """
        logger.debug(f"Evil Star command used by {ctx.author.id}")
        try:
            if ctx.channel.id != self.fart_channel_id:
                logger.debug(f"Wrong channel: {ctx.channel.id}")
                await ctx.send(
                    f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
                )
                return

            # Check user's current points
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                self._ensure_evil_star_table(cur)

                # Check if user has already used evil_star this season
                cur.execute(
                    "SELECT used_at FROM evil_star_usage WHERE user_id = ?",
                    (ctx.author.id,),
                )
                already_used = cur.fetchone()

                if already_used:
                    await ctx.send(
                        f"😈 The Evil Star has already granted you its power, {ctx.author.mention}...\n"
                        f"The dark pact can only be sealed **once per season**.\n"
                        f"The beast does not offer second chances until the season resets... 💀"
                    )
                    return

                cur.execute(
                    "SELECT score FROM fart_scores WHERE user_id = ?", (ctx.author.id,)
                )
                result = cur.fetchone()

                if not result:
                    await ctx.send(
                        f"{ctx.author.mention}, you have no points... the darkness has no use for you."
                    )
                    return

                current_points = result[0]

                if current_points != 666:
                    await ctx.send(
                        f"😈 The Evil Star rejects you, {ctx.author.mention}...\n"
                        f"You have {current_points} points, but the dark pact requires **exactly 666 points**.\n"
                        f"Return when you've embraced the number of the beast... 😈"
                    )
                    return

                # User has exactly 666 points - double them!
                new_points = current_points * 2
                cur.execute(
                    "UPDATE fart_scores SET score = ? WHERE user_id = ?",
                    (new_points, ctx.author.id),
                )

                # Mark that user has used evil_star this season
                cur.execute(
                    "INSERT INTO evil_star_usage (user_id, used_at) VALUES (?, ?)",
                    (ctx.author.id, datetime.datetime.now().isoformat()),
                )

                conn.commit()

                await ctx.send(
                    f"🔥😈 **THE DARK PACT IS SEALED!** 😈🔥\n"
                    f"{ctx.author.mention} has walked the cursed path with **666 points**...\n"
                    f"The Evil Star grants its sinister blessing!\n"
                    f"**666 ➜ 1332 points!**\n"
                    f"May the darkness guide your farts... 🔥💀\n\n"
                    f"*All other stars (`!star`, `!fart_star`, …) are forbidden until the season resets.*"
                )

                logger.info(
                    f"User {ctx.author.id} successfully used Evil Star at exactly 666 points"
                )

            finally:
                conn.close()

        except Exception as e:
            logger.error(f"Error in evil_star command: {e}")
            await ctx.send("The dark powers have failed you... an error occurred.")
            raise


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
