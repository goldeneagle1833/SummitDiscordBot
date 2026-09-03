import discord
from discord.ext import commands, tasks
import datetime
from zoneinfo import ZoneInfo
import sqlite3
import logging
import random
from random import randrange
# Fart flavor/proclamations are hardcoded (cogs.fart_flavor). Unused OpenAI
# helpers are kept commented below if we ever want attack-line generation back.
# from openai import OpenAI

# Uber-rare Curio Shart variants: the first Curio Shart ever (post-deploy) is
# always special — 40% lavashart / 40% frostshart / 20% Yourt. After that,
# 10% of Curio Sharts are lava/frost forever and 5% are Yourt. The global
# claimed flag survives FART GAME RESET (100% never comes back). Each player
# may receive each lava/frost variant at most once per season; those flags
# reset with the red Reset Fart Game button.
UBER_RARE_CURIO_CHANCE = 10  # lavashart / frostshart (combined, after first)
YOURT_CURIO_CHANCE = 5
# First-ever Curio d100: 1-40 lava, 41-80 frost, 81-100 Yourt (40/40/20)
FIRST_CURIO_LAVA_MAX = 40
FIRST_CURIO_FROST_MAX = 80
YOURT_RAMPAGE_SECONDS = 60 * 60
YOURT_ATTACK_EVERY_SECONDS = 10 * 60
YOURT_ATTACKS_TOTAL = 6
YOURT_EMOJI_NAME = "yourt"
YOURT_EMOJI_FALLBACK = ":yourt:"

UBER_RARE_CURIO_VARIANTS = {
    "lavashart": {
        "name": "LAVASHART",
        "emoji": "🌋💥",
        "color": 0x8B4513,  # reddish brown
        "flavor": "Molten essence — an UBER-RARE CURIO forged in impossible heat!",
    },
    "frostshart": {
        "name": "FROSTSHART",
        "emoji": "❄🥶",
        "color": 0x6B8A9E,  # blueish gray
        "flavor": "Absolute zero — an UBER-RARE CURIO crystallized from entropy!",
    },
    "yourt": {
        "name": "YOURTSHART",
        "emoji": YOURT_EMOJI_FALLBACK,
        "color": 0x2ECC71,  # green, matching the curio announcement vibe
        "flavor": "YoUrT fElL oUt — aN UBER-RARE CURIO soaked in tavern stank!",
    },
}

# Frostshart duration matches !stink_cloud (naive local now + 24h).
FROSTSHART_DURATION = datetime.timedelta(hours=24)
# Frozen players keep lookups, daily rolls, leader specials, and admin commands.
# Only the shop catalog and listed purchase commands are blocked (ShopCog).
FROSTSHART_BLOCKED_SHOP_COMMANDS = frozenset(
    {
        "fart_shop",
        "blue_shell",
        "red_shell",
        "green_shell",
        "banana",
        "big_banana",
        "star",
        "mushroom",
        "bobomb",
        "fart_star",
        "evil_star",
        "thunder_fart",
        "gas_shield",
        "stink_bomb",
        "fart_rocket",
        "fart_lance",
        "fart_trap",
        "fart_twister",
        "stink_cloud",
        "gas_gamble",
        "fart_leech",
        "fart_donation",
        "fart_court",
    }
)

# Shop attack toys Yourt drunkenly hurls during the rampage.
YOURT_ATTACK_ITEMS = (
    "banana",
    "green_shell",
    "red_shell",
    "blue_shell",
    "big_banana",
    "stink_bomb",
    "bobomb",
    "thunder_fart",
    "fart_lance",
)


def drunken_case(text):
    """SpongeBob / drunken ShOuTiNg case, letters only."""
    out = []
    upper = True
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)

import config
from cogs.fart_flavor import compose_fart_body, fart_roll_blurb, pick_fartlord_proclamation
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

# openai = OpenAI(api_key=config.OPENAI_API_KEY)

daily_usage_message = "You have already used your daily action today. The actions are `!fart`, `!fart_gift`, `!fartprediction`. \n Use `!fartrank` to check your score."


class FunCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fart_channel_id = config.FART_CHANNEL_ID
        self.guild_id = config.GUILD_ID
        self.leader_role_id = config.LEADER_ROLE_ID
        self.fun_channel_id = config.FART_CHANNEL_ID

    async def cog_load(self):
        try:
            result = self.repair_legacy_frostshart_locks()
            if result.get("ran"):
                logger.info(
                    "One-shot Frostshart repair: cleared %s freezes, restored %s dailies",
                    result.get("cleared_freezes", 0),
                    result.get("restored_dailies", 0),
                )
        except Exception as e:
            logger.error(f"Error running one-shot Frostshart repair: {e}")
        if not self.yourt_rampage_ticker.is_running():
            self.yourt_rampage_ticker.start()

    def cog_unload(self):
        if self.yourt_rampage_ticker.is_running():
            self.yourt_rampage_ticker.cancel()

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
            # Gift variations
            "gift": "!fart_gift",
            "fartgift": "!fart_gift",
            "fart_gift": "!fart_gift",
            "givefart": "!fart_gift",
            "giftfart": "!fart_gift",
            "gift_fart": "!fart_gift",
            # Prediction variations
            "prediction": "!fartprediction",
            "fartprediction": "!fartprediction",
            "fart_prediction": "!fartprediction",
            "predict": "!fartprediction",
            "predictfart": "!fartprediction",
            "fortune": "!fartprediction",
            "fartfortune": "!fartprediction",
            "forecast": "!fartprediction",
            "fartforecast": "!fartprediction",
            # Bull fart variations
            "bull": "!bullfart",
            "bullfart": "!bullfart",
            "bull_fart": "!bullfart",
            "bullshit": "!bullfart",
            "challenge": "!bullfart",
            "challengefart": "!bullfart",
            "callfart": "!bullfart",
            "callout": "!bullfart",
            # Fart lord variations
            "lord": "!fartlord",
            "fartlord": "!fartlord",
            "fart_lord": "!fartlord",
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
            "fart_taxes": "!taxes",
            "tribute": "!taxes",
            "farttribute": "!taxes",
            "pay": "!taxes",
            "paytax": "!taxes",
            # Wealth variations
            "wealth": "!wealth",
            "fartwealth": "!wealth",
            "fart_wealth": "!wealth",
            "balance": "!wealth",
            "money": "!wealth",
            "gold": "!wealth",
            "cash": "!wealth",
            "bank": "!wealth",
            "bankroll": "!wealth",
            "funds": "!wealth",
            "riches": "!wealth",
            # Rank / help underscore variants
            "fart_rank": "!fartrank",
            "fart_leaderboard": "!fartleaderboard",
            "help_fart": "!helpfart",
            "fart_help": "!helpfart",
        }

        actual_commands = {
            "fart": "!fart",
            "helpfart": "!helpfart",
            "help_fart": "!helpfart",
            "farthelp": "!helpfart",
            "fart_help": "!helpfart",
            "fartrank": "!fartrank",
            "fart_rank": "!fartrank",
            "fartleaderboard": "!fartleaderboard",
            "fart_leaderboard": "!fartleaderboard",
            "fart_gift": "!fart_gift",
            "fartgift": "!fart_gift",
            "gift_fart": "!fart_gift",
            "giftfart": "!fart_gift",
            "fartprediction": "!fartprediction",
            "fart_prediction": "!fartprediction",
            "prediction_fart": "!fartprediction",
            "predictionfart": "!fartprediction",
            "bullfart": "!bullfart",
            "bull_fart": "!bullfart",
            "fart_bull": "!bullfart",
            "fartbull": "!bullfart",
            "fartlord": "!fartlord",
            "fart_lord": "!fartlord",
            "lord_fart": "!fartlord",
            "lordfart": "!fartlord",
            "fartrank": "!fartrank",
            "fart_rank": "!fartrank",
            "rank_fart": "!fartrank",
            "rankfart": "!fartrank",
            "fartleaderboard": "!fartleaderboard",
            "fart_leaderboard": "!fartleaderboard",
            "leaderboard_fart": "!fartleaderboard",
            "leaderboardfart": "!fartleaderboard",
            "taxes": "!taxes",
            "farttaxes": "!taxes",
            "fart_taxes": "!taxes",
            "taxes_fart": "!taxes",
            "taxesfart": "!taxes",
            "wealth": "!wealth",
            "fartwealth": "!wealth",
            "fart_wealth": "!wealth",
            "wealth_fart": "!wealth",
            "wealthfart": "!wealth",
        }

        suggestion = find_best_command_match(failed_command, command_suggestions, actual_commands)
        if suggestion:
            await ctx.send(
                f"{ctx.author.mention}, did you mean `{suggestion}`? Type `!helpfart` to see all available commands."
            )
            return

    # def openai_response(self, prompt, name_of_user):
    #     response = openai.responses.create(
    #         model="gpt-4.1-nano",
    #         instructions=f"in less than 10 words. Respond to the following prompt as if you were "
    #         f"around {name_of_user} farting with a little bit of sarcasm and humor.",
    #         input=prompt,
    #     )
    #     print(response)
    #     return response.output_text
    #
    # def openai_response_to_attack(self, prompt, name_of_user, damage):
    #     response = openai.responses.create(
    #         model="gpt-4.1-nano",
    #         instructions=f"in less than 10 words. Respond to the following prompt as if you were "
    #         f"around {name_of_user} farting to attack another users score with sarcasm and humor. "
    #         f"The fart did {damage} damage to the opponent's score. keep the damage number in the response.",
    #         input=prompt,
    #     )
    #     print(response)
    #     return response.output_text

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

    def _ensure_gift_usage_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fart_gift_usage (
                gifter_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                gifted_at TEXT NOT NULL,
                PRIMARY KEY (gifter_id, recipient_id)
            )
        """)

    def has_gifted_to_this_season(self, gifter_id: int, recipient_id: int) -> bool:
        """True if this gifter already gifted this recipient once this season."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            self._ensure_gift_usage_table(cur)
            cur.execute(
                "SELECT 1 FROM fart_gift_usage WHERE gifter_id = ? AND recipient_id = ?",
                (gifter_id, recipient_id),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    def mark_gifted_this_season(self, gifter_id: int, recipient_id: int):
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            self._ensure_gift_usage_table(cur)
            cur.execute(
                "INSERT OR REPLACE INTO fart_gift_usage (gifter_id, recipient_id, gifted_at) VALUES (?, ?, ?)",
                (gifter_id, recipient_id, datetime.datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_daily_action_used(self, user_id, user_display_name, last_updated):
        """Consume the user's daily fart action without changing their score."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                           (user_id INTEGER PRIMARY KEY,
                            user_display_name TEXT,
                            date_last_updated TEXT,
                            score INTEGER
                           )""")
            cur.execute("SELECT score FROM fart_scores WHERE user_id=?", (user_id,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE fart_scores SET date_last_updated=?, user_display_name=? WHERE user_id=?",
                    (last_updated.isoformat(), user_display_name, user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) VALUES (?, ?, ?, ?)",
                    (user_id, user_display_name, last_updated.isoformat(), 0),
                )
            conn.commit()
        finally:
            conn.close()

    def add_score_points(self, user_id, user_display_name, points):
        """Add points without consuming the user's daily action."""
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                           (user_id INTEGER PRIMARY KEY,
                            user_display_name TEXT,
                            date_last_updated TEXT,
                            score INTEGER
                           )""")
            cur.execute("SELECT score FROM fart_scores WHERE user_id=?", (user_id,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE fart_scores SET score = score + ?, user_display_name=? WHERE user_id=?",
                    (points, user_display_name, user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) VALUES (?, ?, NULL, ?)",
                    (user_id, user_display_name, points),
                )
            conn.commit()
        finally:
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

    @staticmethod
    def classify_fart_roll(roll):
        """Return (fart_message, fart_type) from a 1-100 roll."""
        if roll >= 96:
            return "Curio Shart! 💩💨💨💨💨", "curio_shart"
        if roll >= 86:
            return "Unique Fart! 💨💨💨💨", "unique"
        if roll >= 66:
            return "Elite Fart! 💨💨💨", "elite"
        if roll >= 36:
            return "Exceptional Fart! 💨💨", "exceptional"
        return "Ordinary Fart! 💨", "ordinary"

    def _ensure_uber_rare_curio_table(self, cur):
        """Permanent singleton flag: first-ever Curio special (survives FART GAME RESET)."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS uber_rare_curio_claimed (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                claimed_by_user_id INTEGER,
                variant TEXT NOT NULL,
                claimed_at TEXT NOT NULL
            )
        """)

    def _ensure_uber_rare_season_table(self, cur):
        """Per-player per-variant uber-rare awards for the current season (wiped on reset)."""
        cur.execute("""
            CREATE TABLE IF NOT EXISTS uber_rare_curio_season (
                user_id INTEGER NOT NULL,
                variant TEXT NOT NULL,
                rolled_at TEXT NOT NULL,
                PRIMARY KEY (user_id, variant)
            )
        """)

    def has_rolled_uber_rare_this_season(self, user_id, variant):
        """True if this player already received this uber-rare variant this season."""
        if user_id is None or variant not in UBER_RARE_CURIO_VARIANTS:
            return False
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_uber_rare_season_table(cur)
            cur.execute(
                """
                SELECT 1 FROM uber_rare_curio_season
                WHERE user_id = ? AND variant = ?
                """,
                (user_id, variant),
            )
            already = cur.fetchone() is not None
            conn.close()
            return already
        except sqlite3.Error as e:
            logger.error(f"Error checking uber-rare season flag: {e}")
            if "conn" in locals():
                conn.close()
            # Fail closed so a player cannot farm the same variant on DB errors
            return True

    def mark_uber_rare_rolled_this_season(self, user_id, variant):
        """Record that this player received this uber-rare variant this season."""
        if user_id is None or variant not in UBER_RARE_CURIO_VARIANTS:
            return
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_uber_rare_season_table(cur)
            cur.execute(
                """
                INSERT OR IGNORE INTO uber_rare_curio_season
                    (user_id, variant, rolled_at)
                VALUES (?, ?, ?)
                """,
                (user_id, variant, datetime.datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error marking uber-rare season roll: {e}")
            if "conn" in locals():
                conn.close()

    def is_uber_rare_guaranteed_claimed(self):
        """True once the one-time guaranteed uber-rare Curio has ever been awarded."""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_uber_rare_curio_table(cur)
            cur.execute("SELECT 1 FROM uber_rare_curio_claimed WHERE id = 1")
            claimed = cur.fetchone() is not None
            conn.close()
            return claimed
        except sqlite3.Error as e:
            logger.error(f"Error checking uber-rare curio claimed flag: {e}")
            if "conn" in locals():
                conn.close()
            # Fail closed: treat as claimed so we don't spam 100% specials on DB errors
            return True

    def mark_uber_rare_guaranteed_claimed(self, user_id, variant):
        """Record the one-time guaranteed uber-rare Curio (never cleared by season reset)."""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_uber_rare_curio_table(cur)
            cur.execute(
                """
                INSERT OR IGNORE INTO uber_rare_curio_claimed
                    (id, claimed_by_user_id, variant, claimed_at)
                VALUES (1, ?, ?, ?)
                """,
                (
                    user_id,
                    variant,
                    datetime.datetime.now().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error marking uber-rare curio claimed: {e}")
            if "conn" in locals():
                conn.close()

    def pick_first_curio_variant(self, roll=None):
        """40% lavashart / 40% frostshart / 20% Yourt for the first Curio ever."""
        roll = randrange(1, 101) if roll is None else roll
        if roll <= FIRST_CURIO_LAVA_MAX:
            return "lavashart"
        if roll <= FIRST_CURIO_FROST_MAX:
            return "frostshart"
        return "yourt"

    def roll_uber_rare_curio_variant(self, user_id=None):
        """Roll lavashart/frostshart/yourt for a Curio Shart.

        First Curio Shart ever (after deploy): 100% special, 40/40/20
        lavashart / frostshart / Yourt.
        After that forever:
          - 10% lavashart/frostshart (50/50 between those two)
          - 5% Yourt (skipped if a Yourt rampage is already running)
        The global claimed flag survives FART GAME RESET — 100% never comes back.
        Each player may receive each lava/frost variant at most once per season.
        Returns 'lavashart', 'frostshart', 'yourt', or None.
        """
        claimed = self.is_uber_rare_guaranteed_claimed()
        if not claimed:
            variant = self.pick_first_curio_variant()
            if variant in ("lavashart", "frostshart"):
                if self.has_rolled_uber_rare_this_season(user_id, variant):
                    return None
                self.mark_uber_rare_rolled_this_season(user_id, variant)
            elif variant == "yourt" and self.is_yourt_rampage_active():
                return None
            self.mark_uber_rare_guaranteed_claimed(user_id, variant)
            return variant

        bucket = randrange(1, 101)
        if bucket <= UBER_RARE_CURIO_CHANCE:
            variant = "lavashart" if randrange(2) == 0 else "frostshart"
            if self.has_rolled_uber_rare_this_season(user_id, variant):
                return None
            self.mark_uber_rare_rolled_this_season(user_id, variant)
            return variant
        if bucket <= UBER_RARE_CURIO_CHANCE + YOURT_CURIO_CHANCE:
            if self.is_yourt_rampage_active():
                return None
            return "yourt"
        return None

    def yourt_emoji_markup(self, guild=None):
        """Server :yourt: custom emoji, falling back to the :yourt: name."""
        try:
            guild = guild or self.bot.get_guild(self.guild_id)
            emojis = getattr(guild, "emojis", None) if guild is not None else None
            if emojis:
                for emoji in emojis:
                    name = getattr(emoji, "name", None)
                    emoji_id = getattr(emoji, "id", None)
                    if name == YOURT_EMOJI_NAME and isinstance(emoji_id, int):
                        return str(emoji)
                    # MagicMocks / async getters are not real emoji caches
                    if not isinstance(name, str):
                        break
        except Exception:
            pass
        return YOURT_EMOJI_FALLBACK

    def format_uber_rare_highlight(self, variant, guild=None):
        """One-line unlock banner (flavor lives on the embed only)."""
        info = UBER_RARE_CURIO_VARIANTS[variant]
        if variant == "yourt":
            e = self.yourt_emoji_markup(guild)
            name = drunken_case(info["name"])
            return (
                f"{e}{e} ***__⚡ {drunken_case('UBER-RARE CURIO')}: {name} ⚡__*** {e}{e}\n"
            )
        emoji = info["emoji"]
        return (
            f"{emoji} ***__⚡ UBER-RARE CURIO: {info['name']} ⚡__*** {emoji}\n"
        )

    def build_uber_rare_embed(self, variant, guild=None):
        """Colored embed (lava brown / frost gray / Yourt green)."""
        info = UBER_RARE_CURIO_VARIANTS[variant]
        if variant == "yourt":
            e = self.yourt_emoji_markup(guild)
            return discord.Embed(
                title=f"{e} {drunken_case(info['name'])} {e}",
                description=f"*{info['flavor']}* {e}",
                color=info["color"],
            )
        return discord.Embed(
            title=f"{info['emoji']} {info['name']} {info['emoji']}",
            description=f"*{info['flavor']}*",
            color=info["color"],
        )

    LAVASHART_DAMAGE = 50

    @staticmethod
    def _format_player_mentions(mentions):
        """Join Discord player mentions for effect broadcast messages."""
        if not mentions:
            return ""
        return ", ".join(mentions)

    @staticmethod
    def _format_lavashart_damage_line(mention, actual_damage):
        if actual_damage == FunCog.LAVASHART_DAMAGE:
            return mention
        return f"{mention} (-{actual_damage} pts)"

    def _ensure_frost_shart_freeze_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS frost_shart_freeze (
                user_id INTEGER PRIMARY KEY,
                frozen_until TEXT NOT NULL
            )
        """)

    def frostshart_shop_block_message(self, mention):
        return (
            f"{mention}, you're frozen solid by a Frostshart! "
            f"No shop items for 24 hours!"
        )

    def frostshart_blocks_shop_command(self, command_name):
        """True when this shop command is frozen for Frostshart victims."""
        return command_name in FROSTSHART_BLOCKED_SHOP_COMMANDS

    @staticmethod
    def _frost_freeze_still_active(frozen_until, now=None):
        """Compare freeze expiry in Python so ISO/tz strings don't outlive 24h."""
        until = frozen_until
        if isinstance(until, str):
            until = safe_parse_datetime(until)
        if until is None:
            return False
        if until.tzinfo is not None:
            now = now or datetime.datetime.now(until.tzinfo)
            if now.tzinfo is None:
                now = now.replace(tzinfo=until.tzinfo)
            else:
                now = now.astimezone(until.tzinfo)
        else:
            now = now or datetime.datetime.now()
            if now.tzinfo is not None:
                now = now.replace(tzinfo=None)
        return until > now

    def is_frost_frozen(self, user_id, now=None):
        """True if Frostshart is still blocking shop + specials (default !fart allowed)."""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_frost_shart_freeze_table(cur)
            cur.execute(
                "SELECT frozen_until FROM frost_shart_freeze WHERE user_id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                return False
            return self._frost_freeze_still_active(row[0], now=now)
        except sqlite3.Error as e:
            logger.error(f"Error checking frost shart freeze: {e}")
            if "conn" in locals():
                conn.close()
            return False

    def _get_player_display_name(self, user_id):
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            cur.execute(
                "SELECT user_display_name FROM fart_scores WHERE user_id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                return row[0]
        except sqlite3.Error as e:
            logger.error(f"Error fetching display name for {user_id}: {e}")
            if "conn" in locals():
                conn.close()
        return "Unknown User"

    def apply_frost_shart_freeze(self, user_id, user_display_name=None):
        """Block shop items + specials for 24 hours (same clock as !stink_cloud)."""
        frozen_until = datetime.datetime.now() + FROSTSHART_DURATION
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_frost_shart_freeze_table(cur)
            cur.execute(
                """
                INSERT OR REPLACE INTO frost_shart_freeze (user_id, frozen_until)
                VALUES (?, ?)
                """,
                (user_id, frozen_until),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error applying frost shart freeze to {user_id}: {e}")
            if "conn" in locals():
                conn.close()

    def _ensure_frostshart_legacy_repair_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS frostshart_legacy_repair (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                repaired_at TEXT NOT NULL
            )
        """)

    def has_frostshart_legacy_repair_ran(self):
        """True after the one-shot stuck-Frostshart cleanup has completed."""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_frostshart_legacy_repair_table(cur)
            cur.execute("SELECT 1 FROM frostshart_legacy_repair WHERE id = 1")
            ran = cur.fetchone() is not None
            conn.close()
            return ran
        except sqlite3.Error as e:
            logger.error(f"Error checking Frostshart legacy repair flag: {e}")
            if "conn" in locals():
                conn.close()
            return False

    def _user_has_real_fart_on_est_date(self, cur, user_id, est_date):
        """True if fart_history has a real roll for this player on the EST calendar day."""
        try:
            cur.execute(
                "SELECT timestamp FROM fart_history WHERE user_id = ?",
                (user_id,),
            )
        except sqlite3.Error:
            return False
        for (timestamp,) in cur.fetchall():
            if parse_to_est_date(timestamp) == est_date:
                return True
        return False

    def repair_legacy_frostshart_locks(self, now=None):
        """One-shot: clear stuck Frostshart rows and restore unused dailies.

        Runs once (persisted flag). Later 24h Frostsharts are left alone.
        Daily rewind only happens when there is no fart_history for today EST.
        """
        today = parse_to_est_date((now or get_est_now()).isoformat())
        if today is None:
            today = get_est_date()
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_frost_shart_freeze_table(cur)
            self._ensure_frostshart_legacy_repair_table(cur)
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_history
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            username TEXT NOT NULL,
                            fart_type TEXT NOT NULL,
                            roll INTEGER NOT NULL,
                            timestamp TEXT NOT NULL
                           )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                           (user_id INTEGER PRIMARY KEY,
                            user_display_name TEXT,
                            date_last_updated TEXT,
                            score INTEGER
                           )""")
            cur.execute("SELECT 1 FROM frostshart_legacy_repair WHERE id = 1")
            if cur.fetchone():
                conn.close()
                return {
                    "ran": False,
                    "cleared_freezes": 0,
                    "restored_dailies": 0,
                }

            cur.execute("SELECT user_id FROM frost_shart_freeze")
            frozen_ids = [row[0] for row in cur.fetchall()]
            restored = 0
            for user_id in frozen_ids:
                if self._user_has_real_fart_on_est_date(cur, user_id, today):
                    continue
                cur.execute(
                    "UPDATE fart_scores SET date_last_updated = NULL WHERE user_id = ?",
                    (user_id,),
                )
                if cur.rowcount:
                    restored += 1

            cur.execute("DELETE FROM frost_shart_freeze")
            cleared = cur.rowcount if cur.rowcount is not None else 0
            stamp = (now or datetime.datetime.now()).isoformat()
            cur.execute(
                "INSERT INTO frostshart_legacy_repair (id, repaired_at) VALUES (1, ?)",
                (stamp,),
            )
            conn.commit()
            conn.close()
            return {
                "ran": True,
                "cleared_freezes": cleared,
                "restored_dailies": restored,
            }
        except sqlite3.Error as e:
            logger.error(f"Error repairing legacy Frostshart locks: {e}")
            if "conn" in locals():
                conn.close()
            return {
                "ran": False,
                "cleared_freezes": 0,
                "restored_dailies": 0,
                "error": str(e),
            }

    async def apply_uber_rare_variant_effect(self, ctx, roller_id, variant):
        """Apply lavashart/frostshart/yourt effects. Star-protected players are skipped."""
        if not variant:
            return ""
        if variant == "yourt":
            return await self._apply_yourt_effect(ctx, roller_id)
        shop = self.bot.get_cog("ShopCog")
        if shop is None:
            logger.error("ShopCog not loaded; cannot apply uber-rare variant effect")
            return ""
        if variant == "lavashart":
            return await self._apply_lavashart_effect(ctx, roller_id, shop)
        if variant == "frostshart":
            return await self._apply_frostshart_effect(roller_id, shop)
        return ""

    async def _apply_lavashart_effect(self, ctx, roller_id, shop):
        players = await shop.get_sorted_players()
        if not players:
            return ""

        hit_players = []
        hit_player_ids = []
        protected_players = []

        for player_id, _ in players:
            if player_id == roller_id:
                continue
            if await shop.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                actual_damage = await shop.deduct_damage(
                    player_id, self.LAVASHART_DAMAGE
                )
                hit_players.append((f"<@{player_id}>", actual_damage))
                hit_player_ids.append((player_id, actual_damage))

        lines = []
        if hit_players:
            scorched = [
                self._format_lavashart_damage_line(mention, actual_damage)
                for mention, actual_damage in hit_players
            ]
            lines.append(
                f"🌋💥 **LAVASHART!** Scorched for {self.LAVASHART_DAMAGE}: "
                f"{self._format_player_mentions(scorched)}"
            )
        if protected_players:
            lines.append(
                f"⭐ **Star-shielded:** "
                f"{self._format_player_mentions(protected_players)}"
            )
        if not lines:
            return ""

        for player_id, actual_damage in hit_player_ids:
            await shop.check_gas_shield(ctx, player_id, roller_id, actual_damage)

        return "\n".join(lines) + "\n"

    async def _apply_frostshart_effect(self, roller_id, shop):
        players = await shop.get_sorted_players()
        if not players:
            return ""

        frozen_players = []
        protected_players = []

        for player_id, _ in players:
            if player_id == roller_id:
                continue
            if await shop.is_protected(player_id):
                protected_players.append(f"<@{player_id}>")
            else:
                self.apply_frost_shart_freeze(player_id)
                frozen_players.append(f"<@{player_id}>")

        lines = []
        if frozen_players:
            lines.append(
                "❄🥶 **FROSTSHART!** Frozen 24h "
                "(no shop, no specials — `!fart` still works): "
                f"{self._format_player_mentions(frozen_players)}"
            )
        if protected_players:
            lines.append(
                f"⭐ **Star-shielded:** "
                f"{self._format_player_mentions(protected_players)}"
            )
        if not lines:
            return ""

        return "\n".join(lines) + "\n"

    def _ensure_yourt_rampage_table(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yourt_rampage (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                started_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                attacks_done INTEGER NOT NULL DEFAULT 0,
                channel_id INTEGER NOT NULL,
                summoned_by_user_id INTEGER
            )
        """)

    def get_yourt_rampage_state(self):
        """Return active/expired rampage row as a dict, or None."""
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_yourt_rampage_table(cur)
            cur.execute(
                """
                SELECT started_at, ends_at, attacks_done, channel_id, summoned_by_user_id
                FROM yourt_rampage WHERE id = 1
                """
            )
            row = cur.fetchone()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error reading Yourt rampage: {e}")
            if "conn" in locals():
                conn.close()
            return None
        if not row:
            return None
        return {
            "started_at": row[0],
            "ends_at": row[1],
            "attacks_done": row[2],
            "channel_id": row[3],
            "summoned_by_user_id": row[4],
        }

    def is_yourt_rampage_active(self):
        """True while the 1-hour free-shop Yourt chaos window is running."""
        state = self.get_yourt_rampage_state()
        if not state:
            return False
        try:
            ends = datetime.datetime.fromisoformat(state["ends_at"])
        except (TypeError, ValueError):
            return False
        return datetime.datetime.now() < ends

    def start_yourt_rampage(self, channel_id, summoned_by_user_id):
        """Open the 1-hour shop chaos window. Returns False if already active."""
        if self.is_yourt_rampage_active():
            return False
        now = datetime.datetime.now()
        ends = now + datetime.timedelta(seconds=YOURT_RAMPAGE_SECONDS)
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_yourt_rampage_table(cur)
            cur.execute(
                """
                INSERT OR REPLACE INTO yourt_rampage
                    (id, started_at, ends_at, attacks_done, channel_id, summoned_by_user_id)
                VALUES (1, ?, ?, 0, ?, ?)
                """,
                (
                    now.isoformat(),
                    ends.isoformat(),
                    channel_id,
                    summoned_by_user_id,
                ),
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error starting Yourt rampage: {e}")
            if "conn" in locals():
                conn.close()
            return False

    def clear_yourt_rampage(self):
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_yourt_rampage_table(cur)
            cur.execute("DELETE FROM yourt_rampage WHERE id = 1")
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error clearing Yourt rampage: {e}")
            if "conn" in locals():
                conn.close()

    def _set_yourt_attacks_done(self, attacks_done):
        try:
            conn = sqlite3.connect("fart_scores.db")
            cur = conn.cursor()
            self._ensure_yourt_rampage_table(cur)
            cur.execute(
                "UPDATE yourt_rampage SET attacks_done = ? WHERE id = 1",
                (attacks_done,),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error updating Yourt attacks: {e}")
            if "conn" in locals():
                conn.close()

    def yourt_allowed_mentions(self):
        return discord.AllowedMentions(everyone=True, users=True, roles=False)

    async def _send_yourt_channel_message(self, channel, content):
        if channel is None:
            return
        try:
            await channel.send(
                content, allowed_mentions=self.yourt_allowed_mentions()
            )
        except Exception as e:
            logger.error(f"Error sending Yourt channel message: {e}")

    def _resolve_yourt_channel(self, state=None, ctx=None):
        channel = getattr(ctx, "channel", None) if ctx is not None else None
        if channel is not None:
            return channel
        channel_id = None
        if state:
            channel_id = state.get("channel_id")
        channel_id = channel_id or self.fart_channel_id
        return self.bot.get_channel(channel_id)

    async def _apply_yourt_effect(self, ctx, roller_id):
        """Summon Yourt: ping the channel and open the free-shop window."""
        channel = self._resolve_yourt_channel(ctx=ctx)
        channel_id = getattr(channel, "id", None) or self.fart_channel_id
        guild = getattr(ctx, "guild", None) or getattr(channel, "guild", None)
        e = self.yourt_emoji_markup(guild)
        started = self.start_yourt_rampage(channel_id, roller_id)
        if not started:
            return (
                f"{e}{e} {drunken_case('yourt is already wrecking the vendor tent')} "
                f"*hIc* {e}\n"
            )

        crash = (
            f"@here {e}{e}\n"
            f"**{drunken_case('YOURT IS SUMMONED')}** {e}\n"
            f"{e} {drunken_case('YOURT crashes the shop')} — "
            f"{drunken_case('grab free loot for ONE HOUR')}! *hIc* {e}"
        )
        await self._send_yourt_channel_message(channel, crash)
        return f"{e} {drunken_case('YOURT wrecked the shop')} {e}\n"

    def expected_yourt_attacks(self, state, now=None):
        """How many of the 6 attacks should have fired by `now`."""
        now = datetime.datetime.now() if now is None else now
        try:
            started = datetime.datetime.fromisoformat(state["started_at"])
        except (TypeError, ValueError):
            return 0
        elapsed = max(0.0, (now - started).total_seconds())
        due = int(elapsed // YOURT_ATTACK_EVERY_SECONDS)
        return min(YOURT_ATTACKS_TOTAL, due)

    async def _unprotected_players(self, shop, exclude_ids=None):
        exclude = set(exclude_ids or ())
        players = await shop.get_sorted_players()
        open_players = []
        for player_id, _ in players:
            if player_id in exclude:
                continue
            if await shop.is_protected(player_id):
                continue
            open_players.append(player_id)
        return players, open_players

    async def _yourt_hit_player(self, shop, player_id, damage):
        return await shop.deduct_damage(player_id, damage)

    async def _yourt_random_attack(self, state):
        shop = self.bot.get_cog("ShopCog")
        channel = self._resolve_yourt_channel(state=state)
        guild = getattr(channel, "guild", None)
        e = self.yourt_emoji_markup(guild)
        if shop is None:
            logger.error("ShopCog not loaded; Yourt cannot throw items")
            await self._send_yourt_channel_message(
                channel,
                f"{e}{e} {drunken_case('yourt swings at the air and misses everything')} *hIc* {e}",
            )
            return

        item = random.choice(YOURT_ATTACK_ITEMS)
        all_players, open_players = await self._unprotected_players(shop)
        item_label = drunken_case(item.replace("_", " "))

        if item == "thunder_fart":
            hits = []
            if not open_players:
                body = f"{drunken_case('everybody hid under a star oops')}"
            else:
                for pid in open_players:
                    actual = await self._yourt_hit_player(shop, pid, 10)
                    hits.append(f"<@{pid}> (-{actual})")
                body = (
                    f"{drunken_case('THUNDER FART all over the tent')} "
                    f"{', '.join(hits)}"
                )
        elif item == "bobomb":
            top = [pid for pid, _ in all_players[:5] if pid in set(open_players)]
            if not top:
                body = f"{drunken_case('bobomb rolled into a star and fizzled')}"
            else:
                damage = shop.roll_damage(3)
                hits = []
                for pid in top:
                    actual = await self._yourt_hit_player(shop, pid, damage)
                    hits.append(f"<@{pid}> (-{actual})")
                body = f"{drunken_case('BOBOMB go boom on the top stinkers')} {', '.join(hits)}"
        elif item == "fart_lance":
            if len(open_players) < 1:
                body = f"{drunken_case('lance went into the punch bowl')}"
            else:
                dice = [3, 2, 1]
                targets = open_players[:3]
                hits = []
                for pid, num_dice in zip(targets, dice):
                    actual = await self._yourt_hit_player(
                        shop, pid, shop.roll_damage(num_dice)
                    )
                    hits.append(f"<@{pid}> (-{actual})")
                body = f"{drunken_case('FART LANCE whoosh')} {', '.join(hits)}"
        else:
            if not open_players:
                body = f"{drunken_case('yourt forgot who to throw at')}"
            else:
                target_id = random.choice(open_players)
                if item == "big_banana":
                    damage = shop.roll_d10_damage(4)
                elif item in {"blue_shell"}:
                    damage = shop.roll_damage(6)
                elif item in {"red_shell", "stink_bomb"}:
                    damage = shop.roll_damage(3)
                else:
                    damage = shop.roll_damage(2)
                actual = await self._yourt_hit_player(shop, target_id, damage)
                body = (
                    f"{drunken_case('YOURT yeets a')} **{item_label}** "
                    f"{drunken_case('at')} <@{target_id}> "
                    f"{drunken_case('for')} {actual} {drunken_case('damage')}!"
                )

        msg = (
            f"{e}{e}{e} **{drunken_case('YOURT ATTACK')}** {e}{e}{e}\n"
            f"{e} {drunken_case('hic')} {body} {e}{e}\n"
            f"{e} {drunken_case('who put that on the floor')} {e}"
        )
        await self._send_yourt_channel_message(channel, msg)

    async def _yourt_retreat(self, state):
        channel = self._resolve_yourt_channel(state=state)
        guild = getattr(channel, "guild", None)
        e = self.yourt_emoji_markup(guild)
        msg = (
            f"{e}{e}{e}{e} **{drunken_case('YOURT RETREATS')}** {e}{e}{e}{e}\n"
            f"{e} {drunken_case('ughhh the shopkeeper is yelling')} *hIcC* {e}{e}\n"
            f"{e}{e} {drunken_case('YOURT staggers back into the drunken fart abyss')} "
            f"{e}{e}{e}\n"
            f"{drunken_case('the vendor tent is a shop again')} {e}"
        )
        await self._send_yourt_channel_message(channel, msg)
        self.clear_yourt_rampage()

    async def _tick_yourt_rampage(self, now=None):
        """Fire Yourt's 10-minute attacks and close the window at 1 hour."""
        state = self.get_yourt_rampage_state()
        if not state:
            return
        now = datetime.datetime.now() if now is None else now
        try:
            ends = datetime.datetime.fromisoformat(state["ends_at"])
        except (TypeError, ValueError):
            self.clear_yourt_rampage()
            return

        due = self.expected_yourt_attacks(state, now=now)
        expired = now >= ends
        if expired:
            due = YOURT_ATTACKS_TOTAL

        attacks_done = state["attacks_done"] or 0
        while attacks_done < due:
            await self._yourt_random_attack(state)
            attacks_done += 1
            self._set_yourt_attacks_done(attacks_done)

        if expired:
            await self._yourt_retreat(state)

    @tasks.loop(minutes=1)
    async def yourt_rampage_ticker(self):
        await self._tick_yourt_rampage()

    @yourt_rampage_ticker.before_loop
    async def before_yourt_rampage_ticker(self):
        await self.bot.wait_until_ready()

    def maybe_uber_rare_curio(self, fart_type, user_id=None):
        """If this is a Curio Shart, maybe attach lavashart/frostshart/yourt flair.

        Returns (highlight_prefix, embed_or_None, variant_or_None).
        """
        if fart_type != "curio_shart":
            return "", None, None
        try:
            variant = self.roll_uber_rare_curio_variant(user_id)
        except Exception as e:
            logger.error(f"Error rolling uber-rare curio: {e}")
            return "", None, None
        if not variant:
            return "", None, None
        return (
            self.format_uber_rare_highlight(variant),
            self.build_uber_rare_embed(variant),
            variant,
        )

    @commands.command(aliases=["farthelp", "help_fart", "fart_help"])
    async def helpfart(self, ctx):
        """Get detailed help on all fart commands."""
        if ctx.channel.id != self.fart_channel_id:
            await ctx.send(
                f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
            )
            return

        embed = discord.Embed(
            title="💨 Fart Command Guide",
            description="Master the art of magical flatulence!\nUnderscored and concatenated forms both work (e.g. `!fart_rank` / `!fartrank`).",
            color=discord.Color.green(),
        )

        # Daily Actions Section
        embed.add_field(
            name="📅 Daily Actions (Choose One)",
            value=(
                "`!fart` - Roll for random fart points\n"
                "`!fart_gift` / `!fartgift` `@user` - Roll your daily fart for someone else (once per player per season)\n"
                "`!fartprediction` / `!fart_prediction` - Predict fart type for 2x (or half!)"
            ),
            inline=False,
        )

        # Weekly Actions
        embed.add_field(
            name="📆 Weekly Actions",
            value="`!bullfart` / `!bull_fart` - Bonus points based on last fart (once/week)",
            inline=False,
        )

        # Score Commands Section
        embed.add_field(
            name="📊 Stats & Leaderboard",
            value=(
                "`!fartrank` / `!fart_rank` - Check your score and rank\n"
                "`!fartrank @user` - Check another user's rank\n"
                "`!fartleaderboard` / `!fart_leaderboard` - View top 5 farters"
            ),
            inline=False,
        )

        # Leader Commands Section
        embed.add_field(
            name="👑 Leader-Only Commands",
            value=(
                "`!fartlord` / `!fart_lord` - Make a grand proclamation\n"
                "`!taxes` - Take 20% from everyone, give to fartlord (once/reign)\n"
                "`!wealth` - Redistribute 50% from top 5 (includes you) (once/reign)"
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
            fart_message, fart_type = self.classify_fart_roll(roll)
            uber_prefix, uber_embed, uber_variant = self.maybe_uber_rare_curio(
                fart_type, ctx.author.id
            )
            variant_effect_msg = await self.apply_uber_rare_variant_effect(
                ctx, ctx.author.id, uber_variant
            )

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

            try:
                blurb = fart_roll_blurb(fart_message, fart_type, uber_variant)
                self.save_fart_score(
                    now, ctx.author.id, ctx.author.global_name, points_earned
                )
                mushroom_boost_msg = (
                    "**MUSHROOM BOOST ACTIVATED!** \n" if lucky_charm_active else ""
                )
                await ctx.send(
                    compose_fart_body(
                        uber_prefix,
                        variant_effect_msg,
                        mushroom_boost_msg,
                        blurb,
                        f"You earned {points_earned} points.",
                    ),
                    embed=uber_embed,
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

            # Assign farter role to user
            try:
                guild = self.bot.get_guild(self.guild_id)
                if guild:
                    farter_role = guild.get_role(1445222741686095994)
                    member = guild.get_member(ctx.author.id)
                    if farter_role and member and farter_role not in member.roles:
                        await member.add_roles(farter_role)
            except Exception as e:
                logger.error(f"Error assigning farter role: {e}")

        except Exception as e:
            logger.error(f"Unexpected error in fart command: {e}")
            await ctx.send(
                "💨 Oops! Something went wrong with your fart. Please try again later."
            )

    @commands.command(name="fart_gift", aliases=["fartgift", "gift_fart", "giftfart"])
    async def fart_gift(self, ctx, target: discord.Member = None):
        """Roll your daily fart and gift the points to another user (once per recipient per season). Usage: !fart_gift @user"""
        try:
            if ctx.channel.id != self.fart_channel_id:
                await ctx.send(
                    f"{ctx.author.mention}, please use the fart commands in <#{self.fart_channel_id}>."
                )
                return

            if target is None:
                await ctx.send(
                    f"{ctx.author.mention}, usage: `!fart_gift @user` — roll your daily fart for someone else "
                    f"(once per player per season)!"
                )
                return

            if target.id == ctx.author.id:
                await ctx.send(
                    f"{ctx.author.mention}, you can't gift a fart to yourself. Try `!fart` instead!"
                )
                return

            if target.bot:
                await ctx.send(
                    f"{ctx.author.mention}, bots don't appreciate the gift of flatulence."
                )
                return

            if self.has_gifted_to_this_season(ctx.author.id, target.id):
                await ctx.send(
                    f"{ctx.author.mention}, you've already gifted a fart to <@{target.id}> this season! "
                    f"One gifted roll per player — try `!fart_donation` if you still want to share points."
                )
                return

            # Check daily action on the gifter
            did_user_fart_today = False
            try:
                conn = sqlite3.connect("fart_scores.db")
                cur = conn.cursor()
                cur.execute("""CREATE TABLE IF NOT EXISTS fart_scores
                           (user_id INTEGER PRIMARY KEY,
                            user_display_name TEXT,
                            date_last_updated TEXT,
                            score INTEGER
                           )""")
                cur.execute(
                    "SELECT date_last_updated FROM fart_scores WHERE user_id=?",
                    (ctx.author.id,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    parsed_datetime = safe_parse_datetime(row[0])
                    if parsed_datetime:
                        last_fart_date = parse_to_est_date(row[0])
                        if last_fart_date == get_est_date():
                            did_user_fart_today = True
            except sqlite3.Error as e:
                logger.error(f"Database error while checking fart gift status: {e}")
                await ctx.send(
                    "⚠️ There was an error checking your fart status. Please try again later."
                )
                return
            finally:
                if "conn" in locals():
                    conn.close()

            if did_user_fart_today:
                now = get_est_now()
                midnight = get_est_midnight()
                time_until_next = midnight - now
                hours = int(time_until_next.total_seconds() // 3600)
                minutes = int((time_until_next.total_seconds() % 3600) // 60)
                time_msg = (
                    f"You can use a daily action again in **{hours}h {minutes}m** "
                    f"(resets at midnight EST)"
                )
                await ctx.send(
                    f"{ctx.author.mention} {daily_usage_message}\n{time_msg}"
                )
                return

            # Roll (gifter's mushroom boost applies)
            roll = randrange(1, 101)
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
                    lucky_charm_active = True
                    roll2 = randrange(1, 101)
                    roll = max(roll, roll2)
                    cur.execute(
                        "DELETE FROM lucky_charms WHERE user_id = ?",
                        (ctx.author.id,),
                    )
                    conn.commit()
                conn.close()
            except sqlite3.Error as e:
                logger.error(f"Error checking lucky charm for fart_gift: {e}")
                if "conn" in locals():
                    conn.close()

            fart_message, fart_type = self.classify_fart_roll(roll)
            uber_prefix, uber_embed, uber_variant = self.maybe_uber_rare_curio(
                fart_type, ctx.author.id
            )
            variant_effect_msg = await self.apply_uber_rare_variant_effect(
                ctx, ctx.author.id, uber_variant
            )

            now = datetime.datetime.now()
            points_earned = roll

            try:
                self.save_fart_type(
                    ctx.author.id, ctx.author.global_name, fart_type, roll, now
                )
            except sqlite3.Error as e:
                logger.error(f"Error saving gifted fart type: {e}")

            blurb = fart_roll_blurb(fart_message, fart_type, uber_variant)
            if blurb:
                gift_roll_line = f"{ctx.author.mention} rolled a {blurb}\n"
            else:
                gift_roll_line = f"{ctx.author.mention} gifted this uber-rare curio\n"

            # Consume gifter's daily; award points to recipient; lock recipient for season
            self.mark_daily_action_used(
                ctx.author.id, ctx.author.global_name, now
            )
            self.add_score_points(
                target.id, target.global_name or target.display_name, points_earned
            )
            self.mark_gifted_this_season(ctx.author.id, target.id)

            mushroom_boost_msg = (
                "**MUSHROOM BOOST ACTIVATED!** \n" if lucky_charm_active else ""
            )
            await ctx.send(
                f"{uber_prefix}{variant_effect_msg}{mushroom_boost_msg}🎁 **FART GIFT!** "
                f"{gift_roll_line}"
                f"<@{target.id}> received **{points_earned}** points — how nice!\n"
                f"(Once per player per season)",
                embed=uber_embed,
            )

            try:
                await self.update_fart_leader_role(ctx)
            except Exception as e:
                logger.error(f"Error updating leader role after fart_gift: {e}")

            try:
                guild = self.bot.get_guild(self.guild_id)
                if guild:
                    farter_role = guild.get_role(1445222741686095994)
                    member = guild.get_member(ctx.author.id)
                    if farter_role and member and farter_role not in member.roles:
                        await member.add_roles(farter_role)
            except Exception as e:
                logger.error(f"Error assigning farter role after fart_gift: {e}")

        except Exception as e:
            logger.error(f"Unexpected error in fart_gift command: {e}")
            await ctx.send(
                "💨 Oops! Something went wrong with your fart gift. Please try again later."
            )

    @commands.command(aliases=["fart_rank", "rank_fart", "rankfart"])
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

    @commands.command(aliases=["fart_leaderboard", "leaderboard_fart", "leaderboardfart", "fart_lb", "fartlb"])
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

    @commands.command(aliases=["fart_prediction", "prediction_fart", "predictionfart"])
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

    @commands.command(aliases=["bull_fart", "fart_bull", "fartbull"])
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

    @commands.command(aliases=["fart_lord", "lord_fart", "lordfart"])
    @commands.has_role(config.LEADER_ROLE_ID)
    async def fartlord(self, ctx):
        """Declare yourself the Fart Lord (Leader role only)."""
        await ctx.send(
            f"Hear ye, hear ye! {ctx.author.mention} proclaims: "
            f"{pick_fartlord_proclamation()}"
        )

    def collect_taxes_for_fartlord(self):
        """Take 20% from everyone except #1 and give the full pool to the fartlord.

        Returns:
            dict with keys total_taken, fartlord_id, fartlord_name,
            fartlord_bonus, taxed_count — or None if fewer than 2 players exist.
        """
        conn = sqlite3.connect("fart_scores.db")
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT user_id, user_display_name, score
                   FROM fart_scores
                   ORDER BY score DESC"""
            )
            all_users = cur.fetchall()

            if len(all_users) < 2:
                return None

            fartlord_id, fartlord_name, fartlord_score = all_users[0]
            others = all_users[1:]

            total_taken = 0
            for user_id, _user_display_name, score in others:
                points_to_take = int(score * 0.20)
                if points_to_take <= 0:
                    continue
                cur.execute(
                    "UPDATE fart_scores SET score=? WHERE user_id=?",
                    (score - points_to_take, user_id),
                )
                total_taken += points_to_take

            cur.execute(
                "UPDATE fart_scores SET score=? WHERE user_id=?",
                (fartlord_score + total_taken, fartlord_id),
            )
            conn.commit()
            return {
                "total_taken": total_taken,
                "fartlord_id": fartlord_id,
                "fartlord_name": fartlord_name,
                "fartlord_bonus": total_taken,
                "taxed_count": len(others),
            }
        finally:
            conn.close()

    @commands.command(aliases=["farttaxes", "fart_taxes", "taxes_fart", "taxesfart"])
    @commands.has_role(config.LEADER_ROLE_ID)
    async def taxes(self, ctx):
        """Take 20% from everyone else and give it all to the fartlord (once per reign)."""
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

            cur.execute("SELECT COUNT(*) FROM fart_scores")
            player_count = cur.fetchone()[0]
            if player_count < 2:
                await ctx.send("Not enough users to tax! Need at least 2 players.")
                conn.close()
                return

            cur.execute(
                "INSERT OR REPLACE INTO fart_leader_only_once (user_id, user_display_name) VALUES (?, ?)",
                (ctx.author.id, ctx.author.global_name),
            )
            conn.commit()
            conn.close()

            result = self.collect_taxes_for_fartlord()
            if result is None:
                await ctx.send("Not enough users to tax! Need at least 2 players.")
                return

            response = (
                f"💰 **TAXES COLLECTED!** 💰\n\n"
                f"**Total collected:** {result['total_taken']} points\n\n"
                f"**Fartlord** <@{result['fartlord_id']}> "
                f"({result['fartlord_name']}): "
                f"+{result['fartlord_bonus']} points\n\n"
                f"**Points taken from {result['taxed_count']} users** (20% each)"
            )

            await ctx.send(response)
            await self.update_fart_leader_role(ctx)
        except Exception as e:
            print(f"Error in taxes command: {e}")
            import traceback

            traceback.print_exc()
            await ctx.send(f"An error occurred: {e}")

    @commands.command(aliases=["fartwealth", "fart_wealth", "wealth_fart", "wealthfart"])
    @commands.has_role(config.LEADER_ROLE_ID)
    async def wealth(self, ctx):
        """Robin Hood - Take 50% from top 5 (includes you) and give to everyone else (once per reign)"""
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

                # Calculate total points to take from top 5 (50% — includes you)
                total_taken = 0
                top_5_details = []

                for user_id, user_display_name, score in top_5:
                    points_to_take = int(score * 0.50)
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
                    f"**TOP 5 TAXED (50% each):**\n" + "\n".join(top_5_details) + "\n\n"
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

    @commands.command(aliases=["resetfartcooldown", "reset_cooldown_fart", "fart_reset_cooldown"])
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
        fart_message, fart_type = cog.classify_fart_roll(roll)
        uber_prefix, uber_embed, uber_variant = cog.maybe_uber_rare_curio(
            fart_type, self.user_id
        )
        effect_ctx = await cog.bot.get_context(interaction)
        variant_effect_msg = await cog.apply_uber_rare_variant_effect(
            effect_ctx, self.user_id, uber_variant
        )

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

        blurb = fart_roll_blurb(fart_message, fart_type, uber_variant)
        actual_result = blurb if blurb else "Uber-rare curio — see the highlight above."
        mushroom_boost_msg = (
            "**MUSHROOM BOOST ACTIVATED!** \n" if mushroom_boost_active else ""
        )

        await interaction.followup.send(
            f"{uber_prefix}{variant_effect_msg}🔮 **Your Prediction:** {chosen_prediction}\n"
            f"💨 **Actual Result:** {mushroom_boost_msg}{actual_result}\n"
            f"{result_message} You earned **{points_earned}** points!",
            embed=uber_embed,
        )

        try:
            await cog.update_fart_leader_role(interaction)
        except Exception as e:
            logger.error(f"Error updating leader role: {e}")


async def setup(bot):
    await bot.add_cog(FunCog(bot))
