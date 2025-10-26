import discord
from discord.ext import commands
import datetime
import sqlite3
import logging
from random import randrange
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
        self.item_costs = {
            "blue": 14,  # Blue Shell
            "red": 10,  # Red Shell
            "green": 10,  # Green Shell
            "banana": 10,  # Banana
            "star": 200,  # Star
            "mushroom": 10,  # Mushroom
            "bobomb": 50,  # Bob-omb
            "bluestar": 250,  # Blue Star - new item
        }
        logger.info("ShopCog initialized")

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

    @commands.command(name="blueshell")
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
            await self.deduct_damage(leader_id, damage)
            await ctx.send(
                f"<@{ctx.author.id}> launched a Blue Shell at leader <@{leader_id}> for {damage} damage!"
            )
        except Exception as e:
            logger.error(f"Error in blue shell command: {e}")
            await ctx.send("An error occurred while processing the command.")
            raise

    @commands.command(name="redshell")
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
        await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Red Shell for {damage} damage!"
        )

    @commands.command(name="greenshell")
    async def green_shell(self, ctx):
        """Hit a random player in front"""
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
        await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Green Shell for {damage} damage!"
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
        await self.deduct_damage(target[0], damage)
        await ctx.send(
            f"<@{ctx.author.id}> hit <@{target[0]}> with a Banana for {damage} damage!"
        )

    @commands.command(name="star")
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
    async def mushroom(self, ctx):
        """Placeholder for mushroom item"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use this command in <#{self.fart_channel_id}>."
            )
            return

        await ctx.send("Mushroom feature coming soon!")

    @commands.command(name="bobomb")
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

        # Track who got hit
        hit_players = []
        protected_players = []

        for player_id, _ in top_5:
            if await self.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                hit_players.append(f"<@{player_id}>")
                await self.deduct_damage(player_id, damage)

        await self.deduct_points(ctx.author.id, "bobomb")

        # Construct response message
        response = f"<@{ctx.author.id}> threw a Bob-omb dealing {damage} damage to "

        if hit_players:
            response += ", ".join(hit_players)

        if protected_players:
            response += (
                "\n" + ", ".join(protected_players) + " were protected by Stars!"
            )

        await ctx.send(response)

    @commands.command(name="fartshop")
    async def fart_shop(self, ctx):
        """Display all available shop items"""
        embed = discord.Embed(
            title="Fart Shop",
            description="Use the commands below to purchase items:",
            color=discord.Color.gold(),
        )

        items = [
            ("Blue Shell (!blueshell)", "Hits the leader with 3d20/2 damage", 14),
            (
                "Red Shell (!redshell)",
                "Hits the player directly in front of you with 2d20/2 damage",
                10,
            ),
            (
                "Green Shell (!greenshell)",
                "Hits a random player in front of you with 2d20/2 damage",
                10,
            ),
            (
                "Banana (!banana)",
                "Hits a random player behind you with 2d20/2 damage",
                10,
            ),
            ("Star (!star)", "Protects you from all items for 24 hours", 200),
            ("Mushroom (!mushroom)", "Coming soon!", 10),
            (
                "Bob-omb (!bobomb)",
                "Hits the top 5 players with 3d20/2 damage",
                50,
            ),
            (
                "Blue Star (!bluestar)",
                "Hits the leader with 4d20/2 damage AND protects you for 12 hours",
                300,
            ),
        ]

        for name, description, cost in items:
            embed.add_field(
                name=f"{name} - {cost} points", value=description, inline=False
            )

        await ctx.send(embed=embed)

    # Add this method to the ShopCog class
    async def deduct_damage(self, user_id: int, damage: int):
        print("Deducting damage...")
        """Deduct damage amount from user's points"""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute(
                "UPDATE fart_scores SET score = CASE WHEN score - ? < 0 THEN 0 ELSE score - ? END WHERE user_id = ?",
                (damage, damage, user_id),
            )
            conn.commit()
            conn.close()
            logger.debug(f"Deducted {damage} damage points from user {user_id}")
        except Exception as e:
            logger.error(f"Error deducting damage: {e}")
            raise

    @commands.command(name="bluestar")
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
            await self.deduct_damage(leader_id, damage)

            await ctx.send(
                f"<@{ctx.author.id}> used a Blue Star!\n"
                f"Hit leader <@{leader_id}> for {damage} damage!\n"
                f"Gained Star protection for 12 hours!"
            )
        finally:
            conn.close()


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
