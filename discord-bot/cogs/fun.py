import discord
from discord.ext import commands
import datetime
import sqlite3
import logging
from random import randrange
from openai import OpenAI

import config

logger = logging.getLogger("discord_bot")

openai = OpenAI(api_key=config.OPENAI_API_KEY)

# Track active syphons: {leader_id: [syphoner_id1, syphoner_id2, ...]}
active_syphons = {}

daily_usage_message = "You have already used your daily action today. The actions are `!fart`, `!attackfart`, `!syphonfart`, `!fartprediction`. \n Use `!fartrank` to check your score."


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fart_channel_id = config.FART_CHANNEL_ID
        self.guild_id = config.GUILD_ID
        self.leader_role_id = config.LEADER_ROLE_ID

    def openai_response(self, prompt, name_of_user):
        response = openai.responses.create(
            model="gpt-4.1-nano",
            instructions=f"in less than 10 words. Respond to the following prompt as if you were "
            f"around {name_of_user} farting with a little bit of sarcasm and humor.",
            input=prompt,
        )
        print(response)
        return response.output_text

    def openai_response_to_attack(self, prompt, name_of_user, damage):
        response = openai.responses.create(
            model="gpt-4.1-nano",
            instructions=f"in less than 10 words. Respond to the following prompt as if you were "
            f"around {name_of_user} farting to attack another users score with sarcasm and humor. "
            f"The fart did {damage} damage to the opponent's score. keep the damage number in the response.",
            input=prompt,
        )
        print(response)
        return response.output_text

    def save_fart_score(self, last_updated, user_id, user_display_name, level):
        logger.info(f"Saving fart score {level} for user {user_id}")
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                       (user_id INTEGER PRIMARY KEY, 
                        user_display_name TEXT,
                        date_last_updated TEXT, 
                        score INTEGER
                       )""")
        cur.execute("SELECT * FROM fart_scores WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row:
            new_score = row[3] + level
            cur.execute(
                "UPDATE fart_scores SET score=?, date_last_updated=?, user_display_name=? WHERE user_id=?",
                (new_score, last_updated.isoformat(), user_display_name, user_id),
            )
        else:
            cur.execute(
                "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) VALUES (?, ?, ?, ?)",
                (user_id, user_display_name, last_updated.isoformat(), level),
            )
        conn.commit()
        conn.close()

    async def update_fart_leader_role(self, ctx):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            print("Guild not found.")
            return

        leader_role = guild.get_role(self.leader_role_id)
        if not leader_role:
            print("Leader role not found.")
            return

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM fart_scores ORDER BY score DESC LIMIT 1")
        leader_row = cur.fetchone()
        conn.close()

        if not leader_row:
            print("No fart scores found.")
            return

        leader_id = leader_row[0]
        new_leader = guild.get_member(leader_id)
        if not new_leader:
            print("New leader not found in the guild.")
            return

        # Remove the role from all members
        for member in guild.members:
            if leader_role in member.roles:
                try:
                    await member.remove_roles(leader_role)
                    print(f"Removed leader role from {member.display_name}.")
                except discord.errors.Forbidden:
                    print(
                        f"Missing permissions to remove role from {member.display_name}."
                    )
                except Exception as e:
                    print(
                        f"An error occurred removing role from {member.display_name}: {e}"
                    )

        # Assign the role to the new leader
        try:
            await new_leader.add_roles(leader_role)
            print(f"Assigned leader role to {new_leader.display_name}.")
        except discord.errors.Forbidden:
            print(f"Missing permissions to assign role to {new_leader.display_name}.")
        except Exception as e:
            print(f"An error occurred assigning role to {new_leader.display_name}: {e}")

    def save_fart_type(self, user_id, username, fart_type, roll, timestamp):
        """Save the fart type to the database for tracking"""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()

            # Create table if it doesn't exist with correct schema
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fart_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    fart_type TEXT NOT NULL,
                    roll INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)

            # Ensure username is not None
            safe_username = username or "Unknown User"

            # Insert the fart record
            cur.execute(
                """INSERT INTO fart_history 
                   (user_id, username, fart_type, roll, timestamp) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, safe_username, fart_type, roll, timestamp.isoformat()),
            )

            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error in save_fart_type: {e}")
            raise
        finally:
            if "conn" in locals():
                conn.close()

    @commands.command()
    async def helpfart(self, ctx):
        """Get detailed help on all fart commands."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        embed = discord.Embed(
            title="🌟 Summit Fart Command Guide",
            description="Master the art of magical flatulence!",
            color=discord.Color.green(),
        )

        # Daily Actions Section
        embed.add_field(
            name="📅 Daily Actions (Choose One)",
            value=(
                "`!fart` - Roll for random fart points\n"
                "`!attackfart` - Attack leader to reduce their score\n"
                "`!syphonfart` - Place syphon to steal leader's next points\n"
                "`!fartprediction` - Predict fart type for 2x points"
            ),
            inline=False,
        )

        # Score Commands Section
        embed.add_field(
            name="📊 Score Commands",
            value=(
                "`!fartrank` - Check your score and ranking\n"
                "`!fartleaderboard` - View top 5 farters\n"
                "`!syphonstatus` - Check active syphons"
            ),
            inline=False,
        )

        # Special Commands Section
        embed.add_field(
            name="✨ Special Commands",
            value=("`!bullfart` - Get bonus points based on last fart (weekly)\n"),
            inline=False,
        )

        # Leader Commands Section
        embed.add_field(
            name="👑 Leader-Only Commands",
            value=(
                "`!fartlord` - Make grand proclamation\n"
                "`!taxes` - Take 5% from working class (once per reign)\n"
                "`!wealth` - Redistribute from top 5 (once per reign)"
            ),
            inline=False,
        )

        # Fart Types Section
        embed.add_field(
            name="💨 Fart Types (Roll Ranges)",
            value=(
                "💨 Ordinary (66-100) - Common\n"
                "💨💨 Exceptional (36-65) - Uncommon\n"
                "💨💨💨 Elite (16-35) - Rare\n"
                "💨💨💨💨 Unique (6-15) - Very Rare\n"
                "💩💨💨💨💨 Curio Shart (1-5) - Legendary"
            ),
            inline=False,
        )

        embed.set_footer(text="Remember: You can only use one daily action per day!")

        await ctx.send(embed=embed)

        """Let out a magical fart once per day for points!"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        did_user_fart_today = False
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
            (ctx.author.id,),
        )
        row = cur.fetchone()
        if row:
            last_fart_date = datetime.datetime.fromisoformat(row[0]).date()
            if last_fart_date == datetime.datetime.now().date():
                did_user_fart_today = True
        conn.close()

        if did_user_fart_today:
            await ctx.send(f"{ctx.author.mention} {daily_usage_message}")
            return

        roll = randrange(1, 101)
        if roll < 5:
            fart_message = "Curio Shart! 💩💨💨💨💨"
            fart_type = "curio_shart"
        elif roll <= 15:
            fart_message = "Unique Fart! 💨💨💨💨"
            fart_type = "unique"
        elif roll <= 35:
            fart_message = "Elite Fart! 💨💨💨"
            fart_type = "elite"
        elif roll <= 65:
            fart_message = "Exceptional Fart! 💨💨"
            fart_type = "exceptional"
        else:
            fart_message = "Ordinary Fart! 💨"
            fart_type = "ordinary"

        now = datetime.datetime.now()
        points_earned = 100 - roll

        # Track the fart type in the database
        self.save_fart_type(ctx.author.id, ctx.author.global_name, fart_type, roll, now)

        # Check if this user is being syphoned
        if ctx.author.id in active_syphons:
            syphoners = active_syphons[ctx.author.id]
            num_syphoners = len(syphoners)
            stolen_points = points_earned // 2
            points_per_syphoner = stolen_points // num_syphoners
            remaining_points = points_earned - (points_per_syphoner * num_syphoners)

            # Award points to each syphoner WITHOUT updating their last_used date
            syphoner_names = []
            for syphoner_id in syphoners:
                syphoner = await self.bot.fetch_user(syphoner_id)

                # Update score without changing date_last_updated
                conn = sqlite3.connect("fart_scores.db")
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO fart_scores (user_id, user_display_name, score) 
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                       score = score + ?
                       WHERE user_id = ?""",
                    (
                        syphoner_id,
                        syphoner.global_name,
                        points_per_syphoner,
                        points_per_syphoner,
                        syphoner_id,
                    ),
                )
                conn.commit()
                conn.close()

                syphoner_names.append(f"{syphoner.mention} (+{points_per_syphoner})")

            # Award remaining points to farter
            self.save_fart_score(
                now, ctx.author.id, ctx.author.global_name, remaining_points
            )

            # Remove the syphons
            del active_syphons[ctx.author.id]

            fart_message_add = self.openai_response(fart_message, ctx.author.name)
            syphoners_text = ", ".join(syphoner_names)
            await ctx.send(
                f"{fart_message} {fart_message_add}\n\n"
                f"💀 **SYPHONED BY {num_syphoners} SORCERER{'S' if num_syphoners > 1 else ''}!** "
                f"{syphoners_text} stole points! "
                f"You earned {remaining_points} points."
            )
        else:
            # Normal fart - no syphon active
            fart_message_add = self.openai_response(fart_message, ctx.author.name)
            self.save_fart_score(
                now, ctx.author.id, ctx.author.global_name, points_earned
            )
            await ctx.send(
                f"{fart_message} {fart_message_add} You earned {points_earned} points."
            )

        await self.update_fart_leader_role(ctx)

    @commands.command()
    async def fart(self, ctx):
        """Let out a magical fart once per day for points!"""
        try:
            # Channel check
            if ctx.channel.id != self.fart_channel_id:
                await ctx.send(
                    f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
                )
                return

            # Database operations in try-except block
            try:
                conn = sqlite3.connect("fart_scores.db")
                cur = conn.cursor()

                # Create tables if they don't exist
                cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                           (user_id INTEGER PRIMARY KEY, 
                            user_display_name TEXT,
                            date_last_updated TEXT, 
                            score INTEGER
                           )""")

                cur.execute("""CREATE TABLE IF NOT EXISTS fart_history
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            username TEXT NOT NULL,
                            fart_type TEXT NOT NULL,
                            roll INTEGER NOT NULL,
                            timestamp TEXT NOT NULL
                           )""")

                did_user_fart_today = False
                cur.execute(
                    "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                    (ctx.author.id,),
                )
                row = cur.fetchone()
                if row:
                    last_fart_date = datetime.datetime.fromisoformat(row[0]).date()
                    if last_fart_date == datetime.datetime.now().date():
                        did_user_fart_today = True
            except sqlite3.Error as e:
                logger.error(f"Database error while checking fart status: {e}")
                await ctx.send(
                    "⚠️ There was an error checking your fart status. Please try again later."
                )
                return
            finally:
                if "conn" in locals():
                    conn.close()

            if did_user_fart_today:
                await ctx.send(f"{ctx.author.mention} {daily_usage_message}")
                return

            # Roll and point calculation
            roll = randrange(1, 101)
            if roll < 5:
                fart_message = "Curio Shart! 💩💨💨💨💨"
                fart_type = "curio_shart"
            elif roll <= 15:
                fart_message = "Unique Fart! 💨💨💨💨"
                fart_type = "unique"
            elif roll <= 35:
                fart_message = "Elite Fart! 💨💨💨"
                fart_type = "elite"
            elif roll <= 65:
                fart_message = "Exceptional Fart! 💨💨"
                fart_type = "exceptional"
            else:
                fart_message = "Ordinary Fart! 💨"
                fart_type = "ordinary"

            now = datetime.datetime.now()
            points_earned = 100 - roll

            # Save fart type with error handling
            try:
                self.save_fart_type(
                    ctx.author.id, ctx.author.global_name, fart_type, roll, now
                )
            except sqlite3.Error as e:
                logger.error(f"Error saving fart type: {e}")
                await ctx.send(
                    "⚠️ There was an error saving your fart type, but continuing..."
                )

            # Handle syphon mechanics
            try:
                if ctx.author.id in active_syphons:
                    syphoners = active_syphons[ctx.author.id]
                    num_syphoners = len(syphoners)
                    stolen_points = points_earned // 2
                    points_per_syphoner = stolen_points // num_syphoners
                    remaining_points = points_earned - (
                        points_per_syphoner * num_syphoners
                    )

                    # Award points to each syphoner
                    syphoner_names = []
                    conn = sqlite3.connect("fart_scores.db")
                    cur = conn.cursor()

                    for syphoner_id in syphoners:
                        try:
                            syphoner = await self.bot.fetch_user(syphoner_id)
                            if not syphoner:
                                logger.error(f"Could not fetch user {syphoner_id}")
                                continue

                            cur.execute(
                                """INSERT INTO fart_scores (user_id, user_display_name, score) 
                                   VALUES (?, ?, ?)
                                   ON CONFLICT(user_id) DO UPDATE SET
                                   score = score + ?
                                   WHERE user_id = ?""",
                                (
                                    syphoner_id,
                                    syphoner.global_name,
                                    points_per_syphoner,
                                    points_per_syphoner,
                                    syphoner_id,
                                ),
                            )
                            syphoner_names.append(
                                f"{syphoner.mention} (+{points_per_syphoner})"
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing syphoner {syphoner_id}: {e}"
                            )
                            continue

                    conn.commit()
                    conn.close()

                    # Award remaining points to farter
                    self.save_fart_score(
                        now, ctx.author.id, ctx.author.global_name, remaining_points
                    )

                    # Remove the syphons
                    del active_syphons[ctx.author.id]

                    try:
                        fart_message_add = self.openai_response(
                            fart_message, ctx.author.name
                        )
                    except Exception as e:
                        logger.error(f"OpenAI API error: {e}")
                        fart_message_add = "... *cough cough*"

                    syphoners_text = ", ".join(syphoner_names)
                    await ctx.send(
                        f"{fart_message} {fart_message_add}\n\n"
                        f"💀 **SYPHONED BY {num_syphoners} SORCERER{'S' if num_syphoners > 1 else ''}!** "
                        f"{syphoners_text} stole points! "
                        f"You earned {remaining_points} points."
                    )
                else:
                    # Normal fart - no syphon active
                    try:
                        fart_message_add = self.openai_response(
                            fart_message, ctx.author.name
                        )
                    except Exception as e:
                        logger.error(f"OpenAI API error: {e}")
                        fart_message_add = "... *cough cough*"

                    self.save_fart_score(
                        now, ctx.author.id, ctx.author.global_name, points_earned
                    )
                    await ctx.send(
                        f"{fart_message} {fart_message_add} You earned {points_earned} points."
                    )

            except Exception as e:
                logger.error(f"Error processing fart mechanics: {e}")
                await ctx.send(
                    "⚠️ There was an error processing your fart. Please try again later."
                )
                return

            # Update leader role
            try:
                await self.update_fart_leader_role(ctx)
            except Exception as e:
                logger.error(f"Error updating leader role: {e}")
                await ctx.send(
                    "⚠️ There was an error updating the leader role, but your fart was counted!"
                )

        except Exception as e:
            logger.error(f"Unexpected error in fart command: {e}")
            await ctx.send(
                "💨 Oops! Something went wrong with your fart. Please try again later."
            )

    @commands.command()
    async def fartrank(self, ctx):
        """Check your fart score and rank."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        logger.info(f"Checking fart rank for user {ctx.author.id}")
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT score FROM fart_scores WHERE user_id=?", (ctx.author.id,))
        row = cur.fetchone()
        if row:
            user_score = row[0]
            cur.execute(
                "SELECT COUNT(*) FROM fart_scores WHERE score > ?", (user_score,)
            )
            rank = cur.fetchone()[0] + 1
            await ctx.send(
                f"{ctx.author.mention}, your fart score is {user_score} and your rank is #{rank}."
            )
        else:
            await ctx.send(
                f"{ctx.author.mention}, you don't have a fart score yet. "
                "Use the `!fart` command to start earning points!"
            )
        conn.close()
        await self.update_fart_leader_role(ctx)

    @commands.command()
    async def fartleaderboard(self, ctx):
        """Check the top 5 farting sorcerers."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        logger.info("Checking fart leaderboard")
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT user_display_name, score FROM fart_scores ORDER BY score DESC LIMIT 5"
        )
        rows = cur.fetchall()
        if rows:
            leaderboard = "🏆 **Fart Leaderboard** 🏆\n"
            for i, (user_display_name, score) in enumerate(rows, start=1):
                leaderboard += f"#{i}: {user_display_name} - {score} points\n"
            await ctx.send(leaderboard)
        else:
            await ctx.send(
                "No fart scores found. Use the `!fart` command to start earning points!"
            )
        conn.close()
        await self.update_fart_leader_role(ctx)

    @commands.command()
    async def attackfart(self, ctx):
        """Attack the fart leader with a fart! Only one attack OR fart per day."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        did_user_fart_today = False
        print(f"User {ctx.author.id} is attempting to attack the fart leader.")
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                (ctx.author.id,),
            )
            row = cur.fetchone()
            if row:
                last_fart_date = datetime.datetime.fromisoformat(row[0]).date()
                if last_fart_date == datetime.datetime.now().date():
                    did_user_fart_today = True

            if did_user_fart_today:
                await ctx.send(f"{ctx.author.mention} {daily_usage_message}")
                return

            roll = randrange(1, 101)
            if roll < 5:
                fart_message = "Curio Shart Attack! 💩💨💨💨💨"
            elif roll <= 15:
                fart_message = "Unique Fart Bomb! 💨💨💨💨"
            elif roll <= 35:
                fart_message = "Elite Fart Barrage! 💨💨💨"
                fart_type = "elite"
            elif roll <= 65:
                fart_message = "Exceptional Fart Strike! 💨💨"
                fart_type = "exceptional"
            else:
                fart_message = "Ordinary Fart Puff! 💨"
                fart_type = "ordinary"

            roll = 100 - roll

            # Get the leaderboard
            cur.execute(
                "SELECT user_id, user_display_name, score FROM fart_scores "
                "ORDER BY score DESC LIMIT 1"
            )
            leader_row = cur.fetchone()

            leader_id, leader_name, leader_score = leader_row

            if ctx.author.id == leader_id:
                await ctx.send("You are the leader! You cannot attack yourself.")
                return

            # Update the leader's score
            new_leader_score = max(0, leader_score - roll)
            cur.execute(
                "UPDATE fart_scores SET score=? WHERE user_id=?",
                (new_leader_score, leader_id),
            )

            # Update the user's last attack time
            now = datetime.datetime.now()
            cur.execute(
                "UPDATE fart_scores SET date_last_updated=? WHERE user_id=?",
                (now.isoformat(), ctx.author.id),
            )

            conn.commit()

            chatgpt = self.openai_response_to_attack(
                fart_message, ctx.author.name, roll
            )

            await ctx.send(
                f"{ctx.author.mention} attacked {leader_name} {chatgpt} \n\n"
                f"<@{leader_id}>'s new score is {new_leader_score}."
            )
        finally:
            conn.close()

        await self.update_fart_leader_role(ctx)

    @commands.command()
    async def syphonfart(self, ctx):
        """Place a syphon on the fart leader! Steal half their next fart roll. Once per day."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        # Check if user already used their daily action
        did_user_fart_today = False
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                (ctx.author.id,),
            )
            row = cur.fetchone()
            if row:
                last_fart_date = datetime.datetime.fromisoformat(row[0]).date()
                if last_fart_date == datetime.datetime.now().date():
                    did_user_fart_today = True

            if did_user_fart_today:
                await ctx.send(f"{ctx.author.mention} {daily_usage_message}")
                return

            # Get the current leader
            cur.execute(
                "SELECT user_id, user_display_name FROM fart_scores ORDER BY score DESC LIMIT 1"
            )
            leader_row = cur.fetchone()

            if not leader_row:
                await ctx.send("No fart leader found yet! Someone needs to fart first.")
                return

            leader_id, leader_name = leader_row

            # Can't syphon yourself
            if ctx.author.id == leader_id:
                await ctx.send(
                    "You can't syphon yourself! You're already the leader! 👑"
                )
                return

            # Check if user already has a syphon on this leader
            if (
                leader_id in active_syphons
                and ctx.author.id in active_syphons[leader_id]
            ):
                await ctx.send(
                    f"⚠️ You already have a syphon placed on {leader_name}! "
                    f"Wait for them to fart!"
                )
                return

            # Add user to the list of syphoners for this leader
            if leader_id not in active_syphons:
                active_syphons[leader_id] = []

            active_syphons[leader_id].append(ctx.author.id)
            num_syphoners = len(active_syphons[leader_id])

            # Mark user's daily action as used
            now = datetime.datetime.now()
            cur.execute(
                "UPDATE fart_scores SET date_last_updated=? WHERE user_id=?",
                (now.isoformat(), ctx.author.id),
            )
            conn.commit()

            if num_syphoners == 1:
                await ctx.send(
                    f"🌀 **SYPHON PLACED!** {ctx.author.mention} has placed a mystical syphon on \n"
                    f"<@{leader_id}>! When they fart, you'll steal half their points!"
                )
            else:
                await ctx.send(
                    f"🌀 **SYPHON #{num_syphoners} PLACED!** {ctx.author.mention} joins the syphon group! \n"
                    f"<@{leader_id}> now has **{num_syphoners} syphons** draining them! \n"
                    f"Points will be split evenly among all syphoners!"
                )

        finally:
            conn.close()

    @commands.command()
    async def syphonstatus(self, ctx):
        """Check active syphons on the current leader."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            # Get the current leader
            cur.execute(
                "SELECT user_id, user_display_name, score FROM fart_scores ORDER BY score DESC LIMIT 1"
            )
            leader_row = cur.fetchone()

            if not leader_row:
                await ctx.send("No fart leader found yet!")
                return

            leader_id, leader_name, leader_score = leader_row

            if leader_id not in active_syphons or len(active_syphons[leader_id]) == 0:
                await ctx.send(
                    f"👑 **Current Leader:** {leader_name} ({leader_score} points)\n"
                    f"✅ No active syphons! The leader is safe... for now. 😈"
                )
            else:
                syphoners = active_syphons[leader_id]
                num_syphoners = len(syphoners)
                syphoner_names = []

                for syphoner_id in syphoners:
                    syphoner = await self.bot.fetch_user(syphoner_id)
                    syphoner_names.append(syphoner.mention)

                syphoners_text = ", ".join(syphoner_names)
                await ctx.send(
                    f"👑 **Current Leader:** {leader_name} ({leader_score} points)\n"
                    f"💀 **Active Syphons:** {num_syphoners}\n"
                    f"🌀 **Syphoning:** {syphoners_text}\n\n"
                    f"When {leader_name} farts next, each syphoner will steal an equal share of 50% of the points!"
                )

        finally:
            conn.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if message.channel.id == self.fart_channel_id and self.bot.user.mentioned_in(
            message
        ):
            prompt = message.content.replace(
                f"<@{self.bot.user.id}>",
                "",
            ).strip()
            if prompt:
                try:
                    conn = sqlite3.connect("fart_scores.db")
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT score FROM fart_scores WHERE user_id=?",
                        (message.author.id,),
                    )
                    row = cur.fetchone()
                    if row:
                        user_score = row[0]
                        cur.execute(
                            "SELECT COUNT(*) FROM fart_scores WHERE score > ?",
                            (user_score,),
                        )
                        rank = cur.fetchone()[0] + 1
                        db_info = (
                            f"Your fart score is {user_score} and your rank is #{rank}."
                        )
                    else:
                        db_info = "You don't have a fart score yet. Use the `!fart` command to start earning points!"
                    conn.close()

                    response_text = self.openai_response(
                        f"{prompt}. Also, {db_info}", message.author.name
                    )
                    await message.channel.send(
                        f"{message.author.mention} {response_text}"
                    )
                except Exception as e:
                    logger.error(f"Error during OpenAI interaction: {e}")
                    await message.channel.send(
                        f"Sorry, I'm having trouble responding right now."
                    )

    @commands.command()
    async def fartprediction(self, ctx):
        """Predict your fart for double points or lose half!"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        view = FartPredictionView(self, ctx.author.id)
        await ctx.send("Predict your fart!", view=view)

    @commands.command()
    async def bullfart(self, ctx):
        """Use this command only once a week!"""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        # Update the last used date in the database
        now = datetime.datetime.now()
        user_id = ctx.author.id
        command_name = "bullfart"

        # Connect to the database
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()

        # Create a table to track command usage if it doesn't exist
        cur.execute(
            """CREATE TABLE IF NOT EXISTS command_usage
                       (user_id INTEGER,
                        command_name TEXT,
                        last_used TEXT,
                        PRIMARY KEY (user_id, command_name))"""
        )

        # Check if the user has used the command before
        cur.execute(
            "SELECT last_used FROM command_usage WHERE user_id=? AND command_name=?",
            (user_id, command_name),
        )
        row = cur.fetchone()

        if row:
            last_used_date = datetime.datetime.fromisoformat(row[0]).date()
            # Check if a week has passed since the last use
            if (
                last_used_date + datetime.timedelta(weeks=1)
                > datetime.datetime.now().date()
            ):
                await ctx.send(
                    f"{ctx.author.mention}, you can only use this command once a week!"
                )
                conn.close()
                return

        # Get the user's most recent fart from fart_history
        cur.execute(
            """SELECT fart_type FROM fart_history 
               WHERE user_id=? 
               ORDER BY timestamp DESC 
               LIMIT 1""",
            (user_id,),
        )
        roll_row = cur.fetchone()
        print(f"Last roll row: {roll_row}")

        if roll_row:
            last_roll_type = roll_row[0]
            print(f"User's last roll type: {last_roll_type}")

            # Map fart_type to points and display name
            fart_type_mapping = {
                "curio_shart": (50, "Curio Shart"),
                "unique": (35, "Unique Fart"),
                "elite": (25, "Elite Fart"),
                "exceptional": (15, "Exceptional Fart"),
                "ordinary": (10, "Ordinary Fart"),
            }

            if last_roll_type in fart_type_mapping:
                points_earned, display_name = fart_type_mapping[last_roll_type]
            else:
                # Fallback for unexpected values
                points_earned = 10
                display_name = last_roll_type

            self.save_fart_score(
                now, ctx.author.id, ctx.author.global_name, points_earned
            )
            await ctx.send(
                f"You earned a bonus {points_earned} points from using bullfart based on your last fart roll of {display_name}!"
            )
        else:
            # User hasn't rolled yet
            await ctx.send(
                f"{ctx.author.mention}, you need to roll a fart first before using bullfart!"
            )
            conn.close()
            return

        # Update cooldown AFTER successful execution
        cur.execute(
            "INSERT OR REPLACE INTO command_usage (user_id, command_name, last_used) VALUES (?, ?, ?)",
            (user_id, command_name, now.isoformat()),
        )

        conn.commit()
        conn.close()

        await self.update_fart_leader_role(ctx)

    @commands.command()
    @commands.has_role(config.LEADER_ROLE_ID)
    async def fartlord(self, ctx):
        """Declare yourself the Fart Lord (Leader role only)."""
        response_text = self.openai_response(
            "as the new fart lord, make a grand proclamation in less than 20 words. about being the fart lord and how great it is to be the fart lord.",
            ctx.author.name,
        )

        await ctx.send(
            f"Hear ye, hear ye! {ctx.author.mention} proclaims: {response_text}"
        )

    @commands.command()
    @commands.has_role(config.LEADER_ROLE_ID)
    async def taxes(self, ctx):
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_leader_only_once
                           (user_id INTEGER PRIMARY KEY, 
                            user_display_name TEXT
                           )""")

            # Check the CORRECT table - fart_leader_only_once, not fart_scores
            cur.execute(
                "SELECT * FROM fart_leader_only_once WHERE user_id=?", (ctx.author.id,)
            )
            row = cur.fetchone()

            if row:
                await ctx.send(
                    "You have already stolen from the working class during your reign."
                )
                conn.close()
                return
            else:
                cur.execute(
                    "INSERT OR REPLACE INTO fart_leader_only_once (user_id, user_display_name) VALUES (?, ?)",
                    (ctx.author.id, ctx.author.global_name),
                )
                # Fixed: Changed 'username' to 'user_display_name'
                cur.execute(
                    """SELECT user_id, user_display_name, score 
                   FROM fart_scores 
                   ORDER BY score DESC"""
                )
                all_users = cur.fetchall()

                if len(all_users) < 6:
                    await ctx.send(
                        "Not enough users to redistribute! Need at least 6 players."
                    )
                    conn.close()
                    return

                # Split into top 5 and everyone else
                top_5 = all_users[:5]
                others = all_users[5:]

                # Calculate total points to take from non-top-5
                total_taken = 0
                redistribution_details = []

                for user_id, user_display_name, score in others:
                    points_to_take = int(score * 0.05)
                    new_score = score - points_to_take
                    total_taken += points_to_take

                    # Update the user's score
                    cur.execute(
                        "UPDATE fart_scores SET score=? WHERE user_id=?",
                        (new_score, user_id),
                    )
                    redistribution_details.append(
                        f"{user_display_name}: -{points_to_take} points"
                    )

                # Distribute evenly to top 5
                points_per_top_user = total_taken // 5
                remainder = total_taken % 5

                top_5_details = []
                for i, (user_id, user_display_name, score) in enumerate(top_5):
                    # Give remainder to first user
                    bonus = points_per_top_user + (remainder if i == 0 else 0)
                    new_score = score + bonus

                    cur.execute(
                        "UPDATE fart_scores SET score=? WHERE user_id=?",
                        (new_score, user_id),
                    )
                    top_5_details.append(f"{user_display_name}: +{bonus} points")

                conn.commit()
                conn.close()

                # Create response message
                response = (
                    f"💰 **WEALTH REDISTRIBUTION COMPLETE!** 💰\n\n"
                    f"**Total redistributed:** {total_taken} points\n\n"
                    f"**TOP 5 GAINERS:**\n" + "\n".join(top_5_details) + "\n\n"
                    f"**Points taken from {len(others)} users** (5% each)"
                )

                await ctx.send(response)
                await self.update_fart_leader_role(ctx)
        except Exception as e:
            print(f"Error in wealth command: {e}")
            import traceback

            traceback.print_exc()
            await ctx.send(f"An error occurred: {e}")

    @commands.command()
    @commands.has_role(config.LEADER_ROLE_ID)
    async def wealth(self, ctx):
        """Robin Hood - Take 10% from top 5 and give to everyone else (Leader only, once per reign)"""
        try:
            print(f"User {ctx.author.id} is attempting to use wealth redistribution.")
            if ctx.channel.id != self.fart_channel_id:
                await ctx.send(
                    f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
                )
                return

            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_leader_only_once
                           (user_id INTEGER PRIMARY KEY, 
                            user_display_name TEXT
                           )""")

            # Check if user has already used robin command
            cur.execute(
                "SELECT * FROM fart_leader_only_once WHERE user_id=?", (ctx.author.id,)
            )
            row = cur.fetchone()

            if row:
                await ctx.send(
                    "You have already used wealth distribution during your reign!"
                )
                conn.close()
                return
            else:
                cur.execute(
                    "INSERT OR REPLACE INTO fart_leader_only_once (user_id, user_display_name) VALUES (?, ?)",
                    (ctx.author.id, ctx.author.global_name),
                )
                # Fixed: Changed 'username' to 'user_display_name'
                cur.execute(
                    """SELECT user_id, user_display_name, score 
                   FROM fart_scores 
                   ORDER BY score DESC"""
                )
                all_users = cur.fetchall()

                if len(all_users) < 6:
                    await ctx.send(
                        "Not enough users to redistribute! Need at least 6 players."
                    )
                    conn.close()
                    return

                # Split into top 5 and everyone else
                top_5 = all_users[:5]
                others = all_users[5:]

                # Calculate total points to take from top 5
                total_taken = 0
                top_5_details = []

                for user_id, user_display_name, score in top_5:
                    points_to_take = int(score * 0.10)
                    new_score = score - points_to_take
                    total_taken += points_to_take

                    # Update the user's score
                    cur.execute(
                        "UPDATE fart_scores SET score=? WHERE user_id=?",
                        (new_score, user_id),
                    )
                    top_5_details.append(
                        f"{user_display_name}: -{points_to_take} points"
                    )

                # Distribute evenly to everyone else
                points_per_user = total_taken // len(others)
                remainder = total_taken % len(others)

                others_details = []
                for i, (user_id, user_display_name, score) in enumerate(others):
                    # Give remainder to first user
                    bonus = points_per_user + (remainder if i == 0 else 0)
                    new_score = score + bonus

                    cur.execute(
                        "UPDATE fart_scores SET score=? WHERE user_id=?",
                        (new_score, user_id),
                    )
                    others_details.append(f"{user_display_name}: +{bonus} points")

                conn.commit()
                conn.close()

                # Create response message
                response = (
                    f"🏹 **ROBIN HOOD REDISTRIBUTION!** 🏹\n\n"
                    f"**Total redistributed:** {total_taken} points\n\n"
                    f"**TOP 5 TAXED (10% each):**\n" + "\n".join(top_5_details) + "\n\n"
                    f"**{len(others)} WORKERS REWARDED:**\n"
                    + "\n".join(others_details[:10])
                )

                if len(others_details) > 10:
                    response += f"\n...and {len(others_details) - 10} more!"

                await ctx.send(response)
                await self.update_fart_leader_role(ctx)
        except Exception as e:
            print(f"Error in wealth command: {e}")
            import traceback

            traceback.print_exc()
            await ctx.send(f"An error occurred: {e}")


class FartPredictionView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.chosen_prediction = None
        self.ctx = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This button is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Curio Shart", style=discord.ButtonStyle.primary)
    async def curio_shart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Curio Shart! 💩💨💨💨💨")

    @discord.ui.button(label="Unique Fart", style=discord.ButtonStyle.primary)
    async def unique_fart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Unique Fart! 💨💨💨💨")

    @discord.ui.button(label="Elite Fart", style=discord.ButtonStyle.primary)
    async def elite_fart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Elite Fart! 💨💨💨")

    @discord.ui.button(label="Exceptional Fart", style=discord.ButtonStyle.primary)
    async def exceptional_fart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Exceptional Fart! 💨💨")

    @discord.ui.button(label="Ordinary Fart", style=discord.ButtonStyle.primary)
    async def ordinary_fart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Ordinary Fart! 💨")

    async def handle_prediction(self, interaction: discord.Interaction, prediction):
        self.chosen_prediction = prediction
        self.ctx = interaction
        self.stop()

        await self.process_fart()
        await interaction.message.delete()

    async def process_fart(self):
        ctx = self.ctx
        cog = self.cog

        did_user_fart_today = False
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
            (self.user_id,),
        )
        row = cur.fetchone()
        if row:
            last_fart_date = datetime.datetime.fromisoformat(row[0]).date()
            if last_fart_date == datetime.datetime.now().date():
                did_user_fart_today = True
        conn.close()

        if did_user_fart_today:
            await ctx.response.send_message(f"<@{self.user_id}>, {daily_usage_message}")
            return

        roll = randrange(1, 101)
        if roll < 5:
            fart_message = "Curio Shart! 💩💨💨💨💨"
        elif roll <= 15:
            fart_message = "Unique Fart! 💨💨💨💨"
            fart_type = "unique"
        elif roll <= 35:
            fart_message = "Elite Fart! 💨💨💨"
            fart_type = "elite"
        elif roll <= 65:
            fart_message = "Exceptional Fart! 💨💨"
            fart_type = "exceptional"
        else:
            fart_message = "Ordinary Fart! 💨"
            fart_type = "ordinary"

        now = datetime.datetime.now()
        points_earned = 100 - roll

        if self.chosen_prediction == fart_message:
            points_earned *= 2
            result_message = "\n🎉 You predicted correctly! Your points are doubled!"
        else:
            points_earned //= 2
            result_message = "\n😢 Wrong prediction! Your points are halved."

        cog.save_fart_score(now, self.user_id, ctx.user.global_name, points_earned)
        fart_message_add = cog.openai_response(fart_message, ctx.user.name)

        await ctx.response.send_message(
            f"{fart_message} {fart_message_add} {result_message} You earned {points_earned} points."
        )

        await cog.update_fart_leader_role(ctx)


async def setup(bot):
    await bot.add_cog(FunCog(bot))
