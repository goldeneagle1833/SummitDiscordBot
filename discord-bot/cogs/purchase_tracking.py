import discord
from discord.ext import commands
import datetime
import sqlite3
import logging

logger = logging.getLogger("discord_bot")


class PurchaseTrackingCog(commands.Cog):
    """Tracks Discord monetization purchases (subscriptions, server products, etc.)"""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("PurchaseTrackingCog initialized")
        self.setup_purchase_database()

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
        notes: str = None
    ):
        """Log a Discord monetization purchase to the database"""
        try:
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO purchase_records 
                (user_id, username, user_discriminator, purchase_type, sku_id, sku_name, 
                 entitlement_id, subscription_id, guild_id, expires_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                notes
            ))
            conn.commit()
            conn.close()
            logger.info(f"Logged Discord purchase: {username} ({user_id}) - {purchase_type} - {sku_name}")
        except Exception as e:
            logger.error(f"Error logging Discord purchase: {e}")

    def get_sku_name(self, sku_id: str) -> str:
        """
        Map SKU IDs to friendly product names.
        Add your product mappings here when you create them in Discord.
        """
        # Example mappings - replace with your actual SKU IDs from Discord
        sku_names = {
            # "1234567890": "Premium Member",
            # "0987654321": "Supporter Pack",
            # "1111111111": "VIP Access",
        }
        return sku_names.get(sku_id, f"SKU_{sku_id}")

    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement):
        """Called when a user purchases a subscription or one-time product"""
        try:
            user = entitlement.user
            if not user:
                logger.warning(f"Entitlement created but no user found: {entitlement.id}")
                return

            # Determine purchase type
            if entitlement.subscription_id:
                purchase_type = "subscription"
            else:
                purchase_type = "one_time_purchase"

            # Get SKU information
            sku_id = str(entitlement.sku_id) if entitlement.sku_id else None
            sku_name = self.get_sku_name(sku_id) if sku_id else "Unknown Product"

            await self.log_discord_purchase(
                user_id=user.id,
                username=str(user),
                purchase_type=purchase_type,
                sku_id=sku_id,
                sku_name=sku_name,
                entitlement_id=str(entitlement.id),
                subscription_id=str(entitlement.subscription_id) if entitlement.subscription_id else None,
                guild_id=entitlement.guild_id,
                expires_at=entitlement.ends_at,
                notes=f"Entitlement created"
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
            cur.execute("""
                UPDATE purchase_records 
                SET is_active = 0 
                WHERE entitlement_id = ?
            """, (str(entitlement.id),))
            conn.commit()
            conn.close()

            # Log the update as a new record
            sku_id = str(entitlement.sku_id) if entitlement.sku_id else None
            sku_name = self.get_sku_name(sku_id) if sku_id else "Unknown Product"

            await self.log_discord_purchase(
                user_id=user.id,
                username=str(user),
                purchase_type="renewal" if entitlement.subscription_id else "update",
                sku_id=sku_id,
                sku_name=sku_name,
                entitlement_id=str(entitlement.id),
                subscription_id=str(entitlement.subscription_id) if entitlement.subscription_id else None,
                guild_id=entitlement.guild_id,
                expires_at=entitlement.ends_at,
                notes="Entitlement updated/renewed"
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
            cur.execute("""
                UPDATE purchase_records 
                SET is_active = 0, notes = notes || ' | Entitlement deleted'
                WHERE entitlement_id = ?
            """, (str(entitlement.id),))
            conn.commit()
            conn.close()

            logger.info(f"Entitlement deleted: {entitlement.id}")

        except Exception as e:
            logger.error(f"Error in on_entitlement_delete: {e}")

    @commands.command(name="purchase_history")
    @commands.has_permissions(administrator=True)
    async def purchase_history(self, ctx, user: discord.User = None, limit: int = 20):
        """
        [ADMIN ONLY] View purchase history from Discord's shop
        Usage: !purchase_history [@user] [limit]
        Examples:
          !purchase_history - Shows last 20 purchases from all users
          !purchase_history @User - Shows last 20 purchases from specific user
          !purchase_history @User 50 - Shows last 50 purchases from specific user
          !purchase_history 50 - Shows last 50 purchases from all users
        """
        try:
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()

            # Build query based on whether a user was specified
            if user:
                cur.execute("""
                    SELECT user_id, username, purchase_type, sku_name, purchase_date, 
                           expires_at, is_active, entitlement_id, subscription_id, notes
                    FROM purchase_records
                    WHERE user_id = ?
                    ORDER BY purchase_date DESC
                    LIMIT ?
                """, (user.id, limit))
                title = f"Purchase History for {user}"
            else:
                cur.execute("""
                    SELECT user_id, username, purchase_type, sku_name, purchase_date, 
                           expires_at, is_active, entitlement_id, subscription_id, notes
                    FROM purchase_records
                    ORDER BY purchase_date DESC
                    LIMIT ?
                """, (limit,))
                title = f"Recent Purchase History (Last {limit})"

            records = cur.fetchall()
            conn.close()

            if not records:
                await ctx.send("No purchase records found.")
                return

            # Create embed with purchase information
            embed = discord.Embed(
                title=title,
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )

            for record in records:
                user_id, username, purchase_type, sku_name, purchase_date, expires_at, is_active, entitlement_id, subscription_id, notes = record
                
                # Format the field value
                status = "✅ Active" if is_active else "❌ Inactive"
                field_value = f"**Type:** {purchase_type}\n**Product:** {sku_name}\n**Status:** {status}\n**Date:** {purchase_date}"
                
                if expires_at:
                    field_value += f"\n**Expires:** {expires_at}"
                if subscription_id:
                    field_value += f"\n**Sub ID:** {subscription_id[:16]}..."
                if notes:
                    field_value += f"\n**Notes:** {notes}"

                embed.add_field(
                    name=f"{username} (<@{user_id}>)",
                    value=field_value,
                    inline=False
                )

            # Add summary
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM purchase_records WHERE is_active = 1")
            active_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM purchase_records")
            unique_users = cur.fetchone()[0]
            conn.close()

            embed.set_footer(text=f"Active Purchases: {active_count} | Total Unique Buyers: {unique_users}")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in purchase_history command: {e}")
            await ctx.send(f"An error occurred: {e}")

    @commands.command(name="purchase_stats")
    @commands.has_permissions(administrator=True)
    async def purchase_stats(self, ctx):
        """
        [ADMIN ONLY] View statistics about Discord shop purchases
        """
        try:
            conn = sqlite3.connect("discord_purchases.db")
            cur = conn.cursor()

            # Get various statistics
            cur.execute("SELECT COUNT(*) FROM purchase_records")
            total_purchases = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM purchase_records WHERE is_active = 1")
            active_purchases = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT user_id) FROM purchase_records")
            unique_buyers = cur.fetchone()[0]

            cur.execute("SELECT purchase_type, COUNT(*) FROM purchase_records GROUP BY purchase_type")
            type_breakdown = cur.fetchall()

            cur.execute("SELECT sku_name, COUNT(*) FROM purchase_records GROUP BY sku_name ORDER BY COUNT(*) DESC LIMIT 5")
            top_products = cur.fetchall()

            cur.execute("SELECT username, COUNT(*) as purchase_count FROM purchase_records GROUP BY user_id ORDER BY purchase_count DESC LIMIT 5")
            top_buyers = cur.fetchall()

            conn.close()

            # Create embed
            embed = discord.Embed(
                title="📊 Discord Shop Purchase Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )

            embed.add_field(
                name="Overall Stats",
                value=f"**Total Purchases:** {total_purchases}\n**Active:** {active_purchases}\n**Unique Buyers:** {unique_buyers}",
                inline=False
            )

            if type_breakdown:
                type_str = "\n".join([f"**{ptype}:** {count}" for ptype, count in type_breakdown])
                embed.add_field(name="Purchase Types", value=type_str, inline=True)

            if top_products:
                products_str = "\n".join([f"**{name}:** {count}" for name, count in top_products])
                embed.add_field(name="Top Products", value=products_str, inline=True)

            if top_buyers:
                buyers_str = "\n".join([f"**{name}:** {count}" for name, count in top_buyers])
                embed.add_field(name="Top Buyers", value=buyers_str, inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in purchase_stats command: {e}")
            await ctx.send(f"An error occurred: {e}")

    @commands.command(name="test_purchase_log")
    @commands.has_permissions(administrator=True)
    async def test_purchase_log(self, ctx, user: discord.User = None):
        """
        [ADMIN ONLY] Manually log a test purchase to verify the system is working
        Usage: !test_purchase_log [@user]
        If no user is specified, logs a purchase for the command user
        """
        target_user = user if user else ctx.author
        
        try:
            await self.log_discord_purchase(
                user_id=target_user.id,
                username=str(target_user),
                purchase_type="test_purchase",
                sku_id="TEST_SKU_001",
                sku_name="Test Product",
                entitlement_id=f"TEST_ENT_{target_user.id}_{datetime.datetime.now().timestamp()}",
                guild_id=ctx.guild.id if ctx.guild else None,
                notes="Manual test purchase created by admin"
            )
            
            await ctx.send(
                f"✅ Test purchase logged successfully for {target_user.mention}!\n"
                f"Use `!purchase_history {target_user.mention}` to view it."
            )
            
        except Exception as e:
            await ctx.send(f"❌ Error logging test purchase: {e}")
            logger.error(f"Error in test_purchase_log: {e}")


async def setup(bot):
    await bot.add_cog(PurchaseTrackingCog(bot))
