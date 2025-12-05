import discord
from discord.ext import commands
import datetime
import sqlite3
import logging
import random
from openai import OpenAI

import config

logger = logging.getLogger("discord_bot")

openai = OpenAI(api_key=config.OPENAI_API_KEY)

# Track active syphons: {leader_id: [syphoner_id1, syphoner_id2, ...]}
active_syphons = {}


class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fart_channel_id = config.FART_CHANNEL_ID
        self.guild_id = config.GUILD_ID
        self.leader_role_id = config.LEADER_ROLE_ID
        self.giga_target_role_id = 1445222741686095994  # Role for double damage target
        self.item_costs = {
            "blue": 7,  # Blue Shell (was 14)
            "red": 5,  # Red Shell (was 10)
            "green": 5,  # Green Shell (was 10)
            "banana": 5,  # Banana (was 10)
            "star": 50,  # Star 
            "mushroom": 5,  # Mushroom (was 10)
            "bobomb": 25,  # Bob-omb (was 50)
            "bluestar": 38,  # Blue Star (was 75) 
            "fart_star": 200,  # Star Killer - removes star from random protected user
        }
        logger.info("ShopCog initialized")
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
            
            # Try to get SKU name (you'll need to map SKU IDs to names)
            sku_name = f"SKU_{sku_id}" if sku_id else "Unknown Product"

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
            await self.log_discord_purchase(
                user_id=user.id,
                username=str(user),
                purchase_type="renewal" if entitlement.subscription_id else "update",
                sku_id=str(entitlement.sku_id) if entitlement.sku_id else None,
                sku_name=f"SKU_{entitlement.sku_id}" if entitlement.sku_id else "Unknown Product",
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

    # Update the check_points method
    async def check_points(self, user_id: int, item_type: str = "red") -> bool:
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

    async def get_sorted_players(self):
        """Get players sorted by score"""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id, score FROM fart_scores ORDER BY score DESC")
        result = cur.fetchall()
        conn.close()
        return result

    async def find_target(self, user_id: int, direction: str) -> tuple:
        """Find target based on direction (front/back/random_front)"""
        players = await self.get_sorted_players()
        user_index = next(
            (i for i, (pid, _) in enumerate(players) if pid == user_id), None
        )

        if user_index is None:
            return None

        if direction == "front":
            target_index = user_index - 1
        elif direction == "back":
            target_index = user_index + 1
        elif direction == "random_front":
            if user_index == 0:
                return None
            target_index = random.randint(0, user_index - 1)
        else:
            return None

        return players[target_index] if 0 <= target_index < len(players) else None

    @commands.command(name="blue_shell")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def blue_shell(self, ctx):
        logger.debug(f"Blue shell command used by {ctx.author.id}")
        if ctx.channel.id != self.fart_channel_id:
            logger.debug(f"Wrong channel: {ctx.channel.id}")
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        try:
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

            damage = self.roll_damage(3)
            logger.debug(f"Blue shell damage rolled: {damage}")

            await self.deduct_points(ctx.author.id, "blue")
            actual_damage = await self.deduct_damage(leader_id, damage)
            await ctx.send(
                f"<@{ctx.author.id}> launched a Blue Shell at leader <@{leader_id}> for {actual_damage} damage!"
            )
        except Exception as e:
            logger.error(f"Error in blue shell command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="red_shell")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def red_shell(self, ctx):
        """Hit the player directly in front"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if not await self.check_points(ctx.author.id, "red"):
            return await ctx.send(
                f"You don't have enough points! Red Shell costs {self.item_costs['red']} points!"
            )

        target = await self.find_target(ctx.author.id, "front")
        if not target:
            return await ctx.send("No player in front of you!")

        if await self.is_protected(target[0]):
            return await ctx.send(f"<@{target[0]}> is protected by a Star!")

        damage = self.roll_damage(2)
        await self.deduct_points(ctx.author.id, "red")
        actual_damage = await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Red Shell for {actual_damage} damage!"
        )

    @commands.command(name="green_shell")
    async def green_shell(self, ctx):
        """Hit a random player in fronaaat"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

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

    @commands.command(name="banana")
    async def banana(self, ctx):
        """Hit a random player behind"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

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

    @commands.command(name="star")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def star(self, ctx):
        logger.debug(f"Star command used by {ctx.author.id}")
        try:
            if ctx.channel.id != self.fart_channel_id:
                logger.debug(f"Wrong channel: {ctx.channel.id}")
                await ctx.send(
                    f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
                )
                return

            if not await self.check_points(ctx.author.id, "star"):
                return await ctx.send(
                    f"You don't have enough points! Star protection costs {self.item_costs['star']} points!"
                )

            protection_end = datetime.datetime.now() + datetime.timedelta(hours=24)
            logger.debug(f"Setting protection until: {protection_end}")

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
                    "INSERT OR REPLACE INTO protection_status (user_id, protected_until) VALUES (?, ?)",
                    (ctx.author.id, protection_end),
                )
                conn.commit()
                logger.debug(f"Protection status updated for user {ctx.author.id}")

                await self.deduct_points(ctx.author.id, "star")
                await ctx.send(
                    f"<@{ctx.author.id}> is now protected by a Star for 24 hours!"
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
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

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

            if cooldown_result:
                last_used_date = datetime.datetime.fromisoformat(cooldown_result[0]).date()
                if last_used_date + datetime.timedelta(weeks=1) > datetime.datetime.now().date():
                    days_remaining = (last_used_date + datetime.timedelta(weeks=1) - datetime.datetime.now().date()).days
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

            # Update weekly usage cooldown
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

        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

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

        for player_id, _ in top_5:
            if await self.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                actual_damage = await self.deduct_damage(player_id, damage)
                hit_info.append((f"<@{player_id}>", actual_damage))

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
            response += "⭐ " + ", ".join(protected_players) + " were protected by Stars!"

        await ctx.send(response)

    @commands.command(name="fart_shop")
    async def fart_shop(self, ctx):
        """Display all available shop items"""
        embed = discord.Embed(
            title="Fart Shop",
            description="Use the commands below to purchase items:",
            color=discord.Color.gold(),
        )

        items = [
            ("Blue Shell (!blue_shell)", "Hits the leader with 3d20/2 damage", 14),
            (
                "Red Shell (!red_shell)",
                "Hits the player directly in front of you with 2d20/2 damage",
                10,
            ),
            (
                "Green Shell (!green_shell)",
                "Hits a random player in front of you with 2d20/2 damage",
                10,
            ),
            (
                "Banana (!banana)",
                "Hits a random player behind you with 2d20/2 damage",
                10,
            ),
            ("Star (!star)", "Protects you from all items for 24 hours", 50),
            (
                "Mushroom (!mushroom)",
                "Mushroom Boost - Next fart rolls twice, take higher! (Once per week)",
                10,
            ),
            (
                "Bob-omb (!bobomb)",
                "Hits the top 5 players with 3d20/2 damage",
                50,
            ),
            (
                "Blue Star (!blue_star)",
                "Hits the leader with 4d20/2 damage AND protects you for 12 hours",
                75,
            ),
        ]

        for name, description, cost in items:
            embed.add_field(
                name=f"{name} - {cost} points", value=description, inline=False
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
                        logger.info(f"User {user_id} has giga target role - damage doubled to {actual_damage}")
            
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

    @commands.command(name="giga_fart_cannon")
    @commands.cooldown(1, 86400, commands.BucketType.guild)  # Once per day for the entire server
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
                logger.error(f"Could not find giga target role {self.giga_target_role_id}")
                return await ctx.send("An error occurred - role not found.")
            
            target_member = guild.get_member(target_id)
            if not target_member:
                logger.error(f"Could not find member {target_id}")
                return await ctx.send("An error occurred - target player not found.")
            
            # Remove role from everyone else first
            for member in guild.members:
                if giga_role in member.roles and member.id != target_id:
                    await member.remove_roles(giga_role)
                    logger.info(f"Removed giga target role from {member.id}")
            
            # Add role to target
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

    @commands.command(name="blue_star")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def blue_star(self, ctx):
        """Damages the leader and gives protection to the user"""
        logger.debug(f"Blue Star command used by {ctx.author.id}")

        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        if not await self.check_points(ctx.author.id, "bluestar"):
            return await ctx.send(
                f"You don't have enough points! Blue Star costs {self.item_costs['bluestar']} points!"
            )

        # Find and hit the leader
        players = await self.get_sorted_players()
        if not players:
            return await ctx.send("No players found!")

        leader_id = players[0][0]
        if leader_id == ctx.author.id:
            return await ctx.send("You can't Blue Star yourself!")

        if await self.is_protected(leader_id):
            return await ctx.send(f"<@{leader_id}> is protected by a Star!")

        # Apply enhanced damage (4d20/2 instead of normal 3d20/2)
        damage = self.roll_damage(4)

        # Give protection for 12 hours
        protection_end = datetime.datetime.now() + datetime.timedelta(hours=12)

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            # Set protection status
            cur.execute(
                """
                INSERT OR REPLACE INTO protection_status (user_id, protected_until) 
                VALUES (?, ?)
                """,
                (ctx.author.id, protection_end),
            )
            conn.commit()

            # Apply effects
            await self.deduct_points(ctx.author.id, "bluestar")
            actual_damage = await self.deduct_damage(leader_id, damage)

            await ctx.send(
                f"<@{ctx.author.id}> used a Blue Star!\n"
                f"Hit leader <@{leader_id}> for {actual_damage} damage!\n"
                f"Gained Star protection for 12 hours!"
            )
        finally:
            conn.close()

    @commands.command(name="fart_star")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def fart_star(self, ctx):
        """
        Remove the star protection from a random protected user.
        Cost: 200 points
        """
        logger.debug(f"Fart Star command used by {ctx.author.id}")
        try:
            if ctx.channel.id != self.fart_channel_id:
                logger.debug(f"Wrong channel: {ctx.channel.id}")
                await ctx.send(
                    f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
                )
                return

            # Check if user has enough points
            if not await self.check_points(ctx.author.id, "fart_star"):
                return await ctx.send(
                    f"You don't have enough points! Fart Star costs {self.item_costs['fart_star']} points!"
                )

            # Get all currently protected users
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            try:
                # Get protected users whose protection hasn't expired
                cur.execute("""
                    SELECT user_id, protected_until
                    FROM protection_status
                    WHERE protected_until > ?
                """, (datetime.datetime.now(),))
                
                protected_users = cur.fetchall()
                
                if not protected_users:
                    await ctx.send(
                        f"{ctx.author.mention}, there are no users with active star protection right now!"
                    )
                    return
                
                # Select a random protected user
                target_user_id, protected_until = random.choice(protected_users)
                
                # Remove their protection
                cur.execute("""
                    DELETE FROM protection_status
                    WHERE user_id = ?
                """, (target_user_id,))
                conn.commit()
                
                # Deduct points from the user
                await self.deduct_points(ctx.author.id, "fart_star")
                
                # Send success message
                await ctx.send(
                    f"💥 {ctx.author.mention} used Fart Star! "
                    f"<@{target_user_id}>'s star protection has been destroyed! 💥"
                )
                
                logger.info(f"User {ctx.author.id} removed star protection from user {target_user_id}")
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error in fart_star command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="evil_star")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def evil_star(self, ctx):
        """
        Double your points... but only if you have exactly 666 points.
        The dark star only reveals itself to those who walk the cursed path.
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
                cur.execute("SELECT score FROM fart_scores WHERE user_id = ?", (ctx.author.id,))
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
                conn.commit()
                
                await ctx.send(
                    f"🔥😈 **THE DARK PACT IS SEALED!** 😈🔥\n"
                    f"{ctx.author.mention} has walked the cursed path with **666 points**...\n"
                    f"The Evil Star grants its sinister blessing!\n"
                    f"**666 ➜ 1332 points!**\n"
                    f"May the darkness guide your farts... 🔥💀"
                )
                
                logger.info(f"User {ctx.author.id} successfully used Evil Star at exactly 666 points")
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Error in evil_star command: {e}")
            await ctx.send("The dark powers have failed you... an error occurred.")
            raise


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
