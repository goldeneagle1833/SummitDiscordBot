import discord
from discord.ext import commands
import datetime
from zoneinfo import ZoneInfo
import sqlite3
import logging
from random import randrange
from openai import OpenAI

import config
from utils.text import find_best_command_match
from utils.checks import is_bot_admin

# EST timezone for daily action resets
EST = ZoneInfo("America/New_York")


def get_est_now():
    """Get the current datetime in EST timezone."""
    return datetime.datetime.now(EST)


def get_est_date():
    """Get the current date in EST timezone."""
    return get_est_now().date()


def get_est_midnight():
    """Get the next midnight in EST timezone."""
    now = get_est_now()
    tomorrow = now + datetime.timedelta(days=1)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_to_est_date(date_string):
    """Parse a datetime string and return its date in EST."""
    parsed = safe_parse_datetime(date_string)
    if parsed:
        # If the datetime is naive, assume it was stored in EST
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=EST)
        return parsed.astimezone(EST).date()
    return None


def safe_parse_datetime(date_string):
    """
    Safely parse datetime strings that might have malformed ISO format.
    Handles cases where day/month are not zero-padded.
    """
    if not date_string:
        return None

    try:
        # Try normal fromisoformat first
        return datetime.datetime.fromisoformat(date_string)
    except ValueError:
        try:
            # If it fails, try to fix common formatting issues
            # Handle single-digit day/month (e.g., '2025-11-9' -> '2025-11-09')
            import re

            # Pattern to match ISO-like datetime with potentially single-digit day/month
            pattern = (
                r"^(\d{4})-(\d{1,2})-(\d{1,2})T(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$"
            )
            match = re.match(pattern, date_string)

            if match:
                year, month, day, hour, minute, second, microsecond = match.groups()

                # Zero-pad single digits
                month = month.zfill(2)
                day = day.zfill(2)
                hour = hour.zfill(2)

                # Reconstruct the datetime string
                fixed_string = f"{year}-{month}-{day}T{hour}:{minute}:{second}"
                if microsecond:
                    fixed_string += f".{microsecond}"

                return datetime.datetime.fromisoformat(fixed_string)
            else:
                # If regex doesn't match, log the issue and return None
                logger.error(f"Could not parse datetime string: {date_string}")
                return None
        except Exception as e:
            logger.error(f"Error parsing datetime string '{date_string}': {e}")
            return None


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
        self.fun_channel_id = config.FART_CHANNEL_ID

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Monitor for invalid commands in fun channel and suggest corrections"""
        # Only handle CommandNotFound errors
        if not isinstance(error, commands.CommandNotFound):
            return

        # Only respond in the fun channel
        if ctx.channel.id != self.fun_channel_id:
            return

        # Extract the failed command from the message
        message_content = ctx.message.content.lower()
        if not message_content.startswith("!"):
            return

        failed_command = message_content.split()[0][1:]  # Remove the !

        # Common fart-related commands and suggestions
        command_suggestions = {
            # Fart command variations
            "fart": "!fart",
            "poot": "!fart",
            "toot": "!fart",
            "gas": "!fart",
            "flatulence": "!fart",
            "wind": "!fart",
            "pass": "!fart",
            "passgas": "!fart",
            "letone": "!fart",
            "rip": "!fart",
            "ripone": "!fart",
            "break": "!fart",
            "breakwind": "!fart",
            "cut": "!fart",
            "cutone": "!fart",
            "cut1": "!fart",
            # Help variations
            "help": "!helpfart",
            "helpfart": "!helpfart",
            "farthelp": "!helpfart",
            "commands": "!helpfart",
            "info": "!helpfart",
            "?": "!helpfart",
            "howto": "!helpfart",
            "guide": "!helpfart",
            # Rank variations
            "rank": "!fartrank",
            "fartrank": "!fartrank",
            "score": "!fartrank",
            "fartscore": "!fartrank",
            "myscore": "!fartrank",
            "myrank": "!fartrank",
            "check": "!fartrank",
            "checkrank": "!fartrank",
            "checkscore": "!fartrank",
            "stats": "!fartrank",
            "fartstats": "!fartrank",
            "status": "!fartrank",
            # Leaderboard variations
            "leaderboard": "!fartleaderboard",
            "fartleaderboard": "!fartleaderboard",
            "lb": "!fartleaderboard",
            "leaders": "!fartleaderboard",
            "top": "!fartleaderboard",
            "topfarts": "!fartleaderboard",
            "rankings": "!fartleaderboard",
            "fartrankings": "!fartleaderboard",
            "scoreboard": "!fartleaderboard",
            "board": "!fartleaderboard",
            # Attack variations
            "attack": "!attackfart",
            "attackfart": "!attackfart",
            "fartattack": "!attackfart",
            "attackwithfart": "!attackfart",
            "fart_attack": "!attackfart",
            "fight": "!attackfart",
            "battle": "!attackfart",
            "assaultfart": "!attackfart",
            "strikefarrt": "!attackfart",
            # Syphon variations
            "syphon": "!syphonfart",
            "syphonfart": "!syphonfart",
            "siphon": "!syphonfart",
            "siphonfart": "!syphonfart",
            "syfon": "!syphonfart",
            "syfonfart": "!syphonfart",
            "steal": "!syphonfart",
            "stealfarts": "!syphonfart",
            "drain": "!syphonfart",
            "drainfarts": "!syphonfart",
            "absorb": "!syphonfart",
            "absorbfarts": "!syphonfart",
            # Syphon status variations
            "syphonstatus": "!syphonstatus",
            "siphonstatus": "!syphonstatus",
            "syfonstatus": "!syphonstatus",
            "checksyphon": "!syphonstatus",
            "checksiphon": "!syphonstatus",
            "syphoncheck": "!syphonstatus",
            # Prediction variations
            "prediction": "!fartprediction",
            "fartprediction": "!fartprediction",
            "predict": "!fartprediction",
            "predictfart": "!fartprediction",
            "fortune": "!fartprediction",
            "fartfortune": "!fartprediction",
            "forecast": "!fartprediction",
            "fartforecast": "!fartprediction",
            # Bull fart variations
            "bull": "!bullfart",
            "bullfart": "!bullfart",
            "bullshit": "!bullfart",
            "challenge": "!bullfart",
            "challengefart": "!bullfart",
            "callfart": "!bullfart",
            "callout": "!bullfart",
            # Fart lord variations
            "lord": "!fartlord",
            "fartlord": "!fartlord",
            "king": "!fartlord",
            "fartking": "!fartlord",
            "leader": "!fartlord",
            "fartleader": "!fartlord",
            "champion": "!fartlord",
            "fartchampion": "!fartlord",
            # Taxes variations
            "tax": "!taxes",
            "taxes": "!taxes",
            "farttax": "!taxes",
            "farttaxes": "!taxes",
            "tribute": "!taxes",
            "farttribute": "!taxes",
            "pay": "!taxes",
            "paytax": "!taxes",
            # Wealth variations
            "wealth": "!wealth",
            "balance": "!wealth",
            "money": "!wealth",
            "gold": "!wealth",
            "cash": "!wealth",
            "bank": "!wealth",
            "bankroll": "!wealth",
            "funds": "!wealth",
            "riches": "!wealth",
        }

        actual_commands = {
            "fart": "!fart",
            "helpfart": "!helpfart",
            "fartrank": "!fartrank",
            "fartleaderboard": "!fartleaderboard",
            "attackfart": "!attackfart",
            "syphonfart": "!syphonfart",
            "syphonstatus": "!syphonstatus",
            "fartprediction": "!fartprediction",
            "bullfart": "!bullfart",
            "fartlord": "!fartlord",
            "taxes": "!taxes",
            "wealth": "!wealth",
        }

        suggestion = find_best_command_match(failed_command, command_suggestions, actual_commands)
        if suggestion:
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!helpfart` to see all available commands."
            )
            return

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
            title="💨 Fart Command Guide",
            description="Master the art of magical flatulence!",
            color=discord.Color.green(),
        )

        # Daily Actions Section
        embed.add_field(
            name="📅 Daily Actions (Choose One)",
            value=(
                "`!fart` - Roll for random fart points\n"
                "`!fartprediction` - Predict fart type for 2x (or half!)\n"
                "`!attackfart` - Attack leader to reduce their score\n"
                "`!syphonfart` - Steal half of leader's next fart"
            ),
            inline=False,
        )

        # Weekly Actions
        embed.add_field(
            name="📆 Weekly Actions",
            value="`!bullfart` - Bonus points based on last fart (once/week)",
            inline=False,
        )

        # Score Commands Section
        embed.add_field(
            name="📊 Stats & Leaderboard",
            value=(
                "`!fartrank` - Check your score and rank\n"
                "`!fartrank @user` - Check another user's rank\n"
                "`!fartleaderboard` - View top 5 farters\n"
                "`!syphonstatus` - Check active syphons on leader"
            ),
            inline=False,
        )

        # Leader Commands Section
        embed.add_field(
            name="👑 Leader-Only Commands",
            value=(
                "`!fartlord` - Make a grand proclamation\n"
                "`!taxes` - Take 5% from everyone (once/reign)\n"
                "`!wealth` - Robin Hood: redistribute from top 5 (once/reign)"
            ),
            inline=False,
        )

        # Admin Commands Section
        embed.add_field(
            name="🔧 Admin Commands",
            value="`!reset_fart_cooldown @user` - Reset a user's fart cooldown",
            inline=False,
        )

        # Fart Types Section
        embed.add_field(
            name="💨 Fart Types & Points",
            value=(
                "💨 **Ordinary** (1-35 pts) - 36% chance\n"
                "💨💨 **Exceptional** (36-65 pts) - 30% chance\n"
                "💨💨💨 **Elite** (66-85 pts) - 20% chance\n"
                "💨💨💨💨 **Unique** (86-95 pts) - 10% chance\n"
                "💩 **Curio Shart** (96-100 pts) - 4% chance"
            ),
            inline=False,
        )

        embed.set_footer(text="One daily action per day! | Alias: !farthelp")

        await ctx.send(embed=embed)

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
                    parsed_datetime = safe_parse_datetime(row[0])
                    if parsed_datetime:
                        last_fart_date = parse_to_est_date(row[0])
                        if last_fart_date == get_est_date():
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
                # Calculate time until next fart (midnight EST)
                now = get_est_now()
                midnight = get_est_midnight()
                time_until_next = midnight - now

                hours = int(time_until_next.total_seconds() // 3600)
                minutes = int((time_until_next.total_seconds() % 3600) // 60)

                time_msg = f"You can fart again in **{hours}h {minutes}m** (resets at midnight EST)"
                await ctx.send(
                    f"{ctx.author.mention} {daily_usage_message}\n{time_msg}"
                )
                return

            # Roll and point calculation
            roll = randrange(1, 101)

            # Check for Lucky Charm
            lucky_charm_active = False
            try:
                conn = sqlite3.connect("fart_scores.db")
                cur = conn.cursor()
                cur.execute(
                    "SELECT activated_at FROM lucky_charms WHERE user_id = ?",
                    (ctx.author.id,),
                )
                charm_result = cur.fetchone()

                if charm_result:
                    # Lucky charm is active - roll twice and take higher
                    lucky_charm_active = True
                    roll2 = randrange(1, 101)
                    original_roll = roll
                    roll = max(roll, roll2)

                    # Remove the lucky charm after use
                    cur.execute(
                        "DELETE FROM lucky_charms WHERE user_id = ?",
                        (ctx.author.id,),
                    )
                    conn.commit()

                conn.close()
            except sqlite3.Error as e:
                logger.error(f"Error checking lucky charm: {e}")
                if "conn" in locals():
                    conn.close()

            # Determine fart type based on roll (higher is better now)
            if roll >= 96:
                fart_message = "Curio Shart! 💩💨💨💨💨"
                fart_type = "curio_shart"
            elif roll >= 86:
                fart_message = "Unique Fart! 💨💨💨💨"
                fart_type = "unique"
            elif roll >= 66:
                fart_message = "Elite Fart! 💨💨💨"
                fart_type = "elite"
            elif roll >= 36:
                fart_message = "Exceptional Fart! 💨💨"
                fart_type = "exceptional"
            else:
                fart_message = "Ordinary Fart! 💨"
                fart_type = "ordinary"

            now = datetime.datetime.now()
            points_earned = roll  # Points equal to roll value

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
                    mushroom_boost_msg = (
                        " **MUSHROOM BOOST ACTIVATED!** \n"
                        if lucky_charm_active
                        else ""
                    )
                    await ctx.send(
                        f"{mushroom_boost_msg}{fart_message} {fart_message_add}\n\n"
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
                    mushroom_boost_msg = (
                        "**MUSHROOM BOOST ACTIVATED!** \n" if lucky_charm_active else ""
                    )
                    await ctx.send(
                        f"{mushroom_boost_msg}{fart_message} {fart_message_add} You earned {points_earned} points."
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
    async def fartrank(self, ctx, user: discord.Member = None):
        """Check your fart score and rank, or check another user's rank by tagging them."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        # Determine which user to check
        target_user = user if user else ctx.author
        is_self = target_user == ctx.author

        logger.info(f"Checking fart rank for user {target_user.id}")
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        cur.execute("SELECT score FROM fart_scores WHERE user_id=?", (target_user.id,))
        row = cur.fetchone()
        if row:
            user_score = row[0]
            cur.execute(
                "SELECT COUNT(*) FROM fart_scores WHERE score > ?", (user_score,)
            )
            rank = cur.fetchone()[0] + 1

            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, your fart score is {user_score} and your rank is #{rank}."
                )
            else:
                await ctx.send(
                    f"{target_user.display_name}'s fart score is {user_score} and their rank is #{rank}."
                )
        else:
            if is_self:
                await ctx.send(
                    f"{ctx.author.mention}, you don't have a fart score yet. "
                    "Use the `!fart` command to start earning points!"
                )
            else:
                await ctx.send(
                    f"{target_user.display_name} doesn't have a fart score yet. "
                    "They need to use the `!fart` command to start earning points!"
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
                parsed_datetime = safe_parse_datetime(row[0])
                if parsed_datetime:
                    last_fart_date = parse_to_est_date(row[0])
                    if last_fart_date == get_est_date():
                        did_user_fart_today = True

            if did_user_fart_today:
                # Calculate time until next fart (midnight EST)
                now = get_est_now()
                midnight = get_est_midnight()
                time_until_next = midnight - now

                hours = int(time_until_next.total_seconds() // 3600)
                minutes = int((time_until_next.total_seconds() % 3600) // 60)

                time_msg = f"You can use your daily action again in **{hours}h {minutes}m** (resets at midnight EST)"
                await ctx.send(
                    f"{ctx.author.mention} {daily_usage_message}\n{time_msg}"
                )
                return

            roll = randrange(1, 101)
            if roll >= 96:
                fart_message = "Curio Shart Attack! 💩💨💨💨💨"
                fart_type = "curio_shart"
            elif roll >= 86:
                fart_message = "Unique Fart Bomb! 💨💨💨💨"
                fart_type = "unique"
            elif roll >= 66:
                fart_message = "Elite Fart Barrage! 💨💨💨"
                fart_type = "elite"
            elif roll >= 36:
                fart_message = "Exceptional Fart Strike! 💨💨"
                fart_type = "exceptional"
            else:
                fart_message = "Ordinary Fart Puff! 💨"
                fart_type = "ordinary"

            damage = roll  # Damage equals roll value

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
            new_leader_score = max(0, leader_score - damage)
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
                fart_message, ctx.author.name, damage
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
                parsed_datetime = safe_parse_datetime(row[0])
                if parsed_datetime:
                    last_fart_date = parse_to_est_date(row[0])
                    if last_fart_date == get_est_date():
                        did_user_fart_today = True

            if did_user_fart_today:
                # Calculate time until next fart (midnight EST)
                now = get_est_now()
                midnight = get_est_midnight()
                time_until_next = midnight - now

                hours = int(time_until_next.total_seconds() // 3600)
                minutes = int((time_until_next.total_seconds() % 3600) // 60)

                time_msg = f"You can use your daily action again in **{hours}h {minutes}m** (resets at midnight EST)"
                await ctx.send(
                    f"{ctx.author.mention} {daily_usage_message}\n{time_msg}"
                )
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

        embed = discord.Embed(
            title="🔮 Fart Prediction Challenge",
            description="Choose your prediction wisely! \n✅ **Correct = 2x points** \n❌ **Wrong = half points**",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="💨 Fart Types & Odds",
            value=(
                "💩💨💨💨💨 **Curio Shart** (4% chance) - 96-100 points\n"
                "💨💨💨💨 **Unique Fart** (10% chance) - 86-95 points\n"
                "💨💨💨 **Elite Fart** (20% chance) - 66-85 points\n"
                "💨💨 **Exceptional Fart** (30% chance) - 36-65 points\n"
                "💨 **Ordinary Fart** (36% chance) - 1-35 points"
            ),
            inline=False,
        )
        embed.set_footer(text="Use the dropdown menu below to make your prediction!")

        view = FartPredictionView(self, ctx.author.id)
        await ctx.send(embed=embed, view=view)

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
            parsed_datetime = safe_parse_datetime(row[0])
            if parsed_datetime:
                last_used_date = parsed_datetime.date()
                next_available_date = last_used_date + datetime.timedelta(weeks=1)
                # Check if a week has passed since the last use
                if next_available_date > get_est_date():
                    days_remaining = (next_available_date - get_est_date()).days
                    await ctx.send(
                        f"{ctx.author.mention}, you can only use this command once a week! You can use it again in **{days_remaining} day{'s' if days_remaining != 1 else ''}**."
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

    @commands.command()
    @is_bot_admin()
    async def reset_fart_cooldown(self, ctx, user: discord.Member = None):
        """Admin command to reset a user's fart cooldown (set last fart to 48 hours ago).
        Usage: !reset_fart_cooldown @user
        """
        if user is None:
            await ctx.send("Please mention a user. Usage: `!reset_fart_cooldown @user`")
            return

        if user.bot:
            await ctx.send("Cannot reset fart cooldown for bots!")
            return

        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()

            # Check if user exists in database
            cur.execute(
                "SELECT date_last_updated FROM fart_scores WHERE user_id = ?",
                (user.id,),
            )
            row = cur.fetchone()

            if row:
                # Parse the current time from database and subtract 48 hours
                current_time = safe_parse_datetime(row[0])
                if current_time:
                    time_48_hours_ago = current_time - datetime.timedelta(hours=48)
                else:
                    # If parsing fails, use current time minus 48 hours
                    time_48_hours_ago = datetime.datetime.now() - datetime.timedelta(
                        hours=48
                    )

                time_string = time_48_hours_ago.isoformat()

                # Update the last fart time
                cur.execute(
                    "UPDATE fart_scores SET date_last_updated = ? WHERE user_id = ?",
                    (time_string, user.id),
                )
                conn.commit()
                conn.close()

                embed = discord.Embed(
                    title="💨 Fart Cooldown Reset",
                    description=(
                        f"**User:** {user.mention}\n"
                        f"**New last fart time:** {time_string}\n\n"
                        f"They can now use `!fart` again!"
                    ),
                    color=discord.Color.green(),
                )
                embed.set_footer(text=f"Reset by {ctx.author.display_name}")
                await ctx.send(embed=embed)
                logger.info(
                    f"Admin {ctx.author} reset fart cooldown for {user.display_name}"
                )
            else:
                conn.close()
                await ctx.send(
                    f"{user.mention} has never farted! They don't have a cooldown to reset."
                )

        except Exception as e:
            error_embed = discord.Embed(
                title="Fart Cooldown Reset Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=error_embed)
            logger.error(f"Fart cooldown reset failed: {e}")

    @reset_fart_cooldown.error
    async def reset_fart_cooldown_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need administrator permissions to use this command.")


class FartPredictionView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.user_id = user_id
        self.prediction_made = False  # Track if prediction has already been processed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This prediction is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.select(
        placeholder="🔮 Choose your fart prediction...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Curio Shart",
                value="curio_shart",
                emoji="💩",
                description="96-100 points • 4% chance • LEGENDARY",
            ),
            discord.SelectOption(
                label="Unique Fart",
                value="unique_fart",
                emoji="🌟",
                description="86-95 points • 10% chance • VERY RARE",
            ),
            discord.SelectOption(
                label="Elite Fart",
                value="elite_fart",
                emoji="⚡",
                description="66-85 points • 20% chance • RARE",
            ),
            discord.SelectOption(
                label="Exceptional Fart",
                value="exceptional_fart",
                emoji="✨",
                description="36-65 points • 30% chance • UNCOMMON",
            ),
            discord.SelectOption(
                label="Ordinary Fart",
                value="ordinary_fart",
                emoji="💨",
                description="1-35 points • 36% chance • COMMON",
            ),
        ],
    )
    async def prediction_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        selected_value = select.values[0]

        # Map select values to fart messages
        prediction_mapping = {
            "curio_shart": "Curio Shart! 💩💨💨💨💨",
            "unique_fart": "Unique Fart! 💨💨💨💨",
            "elite_fart": "Elite Fart! 💨💨💨",
            "exceptional_fart": "Exceptional Fart! 💨💨",
            "ordinary_fart": "Ordinary Fart! 💨",
        }

        chosen_prediction = prediction_mapping[selected_value]
        await self.handle_prediction(interaction, chosen_prediction)

    @discord.ui.button(label="💨", style=discord.ButtonStyle.secondary)
    async def ordinary_fart(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_prediction(interaction, "Ordinary Fart! 💨")

    async def handle_prediction(self, interaction: discord.Interaction, prediction):
        # Prevent duplicate predictions from double-clicks or multiple selections
        if self.prediction_made:
            await interaction.response.send_message(
                "You've already made your prediction!", ephemeral=True
            )
            return

        self.prediction_made = True
        await interaction.response.defer()
        await self.process_fart(interaction, prediction)

        # Disable the select menu and edit the message
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

    async def process_fart(
        self, interaction: discord.Interaction, chosen_prediction: str
    ):
        cog = self.cog

        # Check if user already used daily action
        did_user_fart_today = False
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                (self.user_id,),
            )
            row = cur.fetchone()
            if row:
                parsed_datetime = safe_parse_datetime(row[0])
                if parsed_datetime:
                    last_fart_date = parse_to_est_date(row[0])
                    if last_fart_date == get_est_date():
                        did_user_fart_today = True
        except sqlite3.Error as e:
            logger.error(f"Error checking daily action: {e}")
        finally:
            conn.close()

        if did_user_fart_today:
            await interaction.followup.send(f"<@{self.user_id}>, {daily_usage_message}")
            return

        roll = randrange(1, 101)

        # Check for Mushroom Boost
        mushroom_boost_active = False
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT activated_at FROM lucky_charms WHERE user_id = ?",
                (self.user_id,),
            )
            charm_result = cur.fetchone()

            if charm_result:
                # Mushroom boost is active - roll twice and take higher
                mushroom_boost_active = True
                roll2 = randrange(1, 101)
                original_roll = roll
                roll = max(roll, roll2)

                # Remove the mushroom boost after use
                cur.execute(
                    "DELETE FROM lucky_charms WHERE user_id = ?",
                    (self.user_id,),
                )
                conn.commit()

            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error checking mushroom boost in prediction: {e}")
            if "conn" in locals():
                conn.close()

        # Determine actual fart result
        if roll >= 96:
            fart_message = "Curio Shart! 💩💨💨💨💨"
            fart_type = "curio_shart"
        elif roll >= 86:
            fart_message = "Unique Fart! 💨💨💨💨"
            fart_type = "unique"
        elif roll >= 66:
            fart_message = "Elite Fart! 💨💨💨"
            fart_type = "elite"
        elif roll >= 36:
            fart_message = "Exceptional Fart! 💨💨"
            fart_type = "exceptional"
        else:
            fart_message = "Ordinary Fart! 💨"
            fart_type = "ordinary"

        now = datetime.datetime.now()
        points_earned = roll  # Points equal to roll value

        # Check if prediction was correct
        if chosen_prediction == fart_message:
            points_earned *= 2
            result_message = "\n🎉 You predicted correctly! Your points are doubled!"
        else:
            points_earned //= 2
            result_message = "\n😢 Wrong prediction! Your points are halved."

        # Save the fart type to history
        try:
            cog.save_fart_type(
                self.user_id, interaction.user.global_name, fart_type, roll, now
            )
        except Exception as e:
            logger.error(f"Error saving fart type: {e}")

        cog.save_fart_score(
            now, self.user_id, interaction.user.global_name, points_earned
        )

        try:
            fart_message_add = cog.openai_response(fart_message, interaction.user.name)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            fart_message_add = "... *magical silence*"

        mushroom_boost_msg = (
            "**MUSHROOM BOOST ACTIVATED!** \n" if mushroom_boost_active else ""
        )

        await interaction.followup.send(
            f"🔮 **Your Prediction:** {chosen_prediction}\n"
            f"💨 **Actual Result:** {mushroom_boost_msg}{fart_message} {fart_message_add}\n"
            f"{result_message} You earned **{points_earned}** points!"
        )

        try:
            await cog.update_fart_leader_role(interaction)
        except Exception as e:
            logger.error(f"Error updating leader role: {e}")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
