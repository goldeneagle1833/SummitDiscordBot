"""
Achievement System for Summit Discord Bot
==========================================

This module manages user achievements based on game performance, Elo ratings,
and avatar usage. Achievements are stored in profiles.db and checked after
every match submission.

To add a new achievement:
1. Add a new BOOLEAN column to the profiles table (via create_profiles_db())
2. Add an entry to the ACHIEVEMENTS dictionary below
3. Create a check function following the naming convention: check_<achievement_id>
"""

import sqlite3
import json
import logging
from typing import Dict, Any, Callable, Optional, Tuple
import discord

logger = logging.getLogger("discord_bot")


def create_profiles_db():
    """Create the profiles database table with all achievement columns."""
    conn = sqlite3.connect("profiles.db")
    cur = conn.cursor()
    
    cur.execute("""CREATE TABLE IF NOT EXISTS profiles
                   (discord_id TEXT PRIMARY KEY,
                    username TEXT,
                    win_5_games BOOLEAN DEFAULT 0,
                    win_10_games BOOLEAN DEFAULT 0,
                    win_25_games BOOLEAN DEFAULT 0,
                    elo_1600 BOOLEAN DEFAULT 0,
                    elo_1700 BOOLEAN DEFAULT 0,
                    play_100_games BOOLEAN DEFAULT 0,
                    first_player_master BOOLEAN DEFAULT 0,
                    comeback_king BOOLEAN DEFAULT 0,
                    peasants_fury BOOLEAN DEFAULT 0
                   )""")
    
    # Migration: Add peasants_fury column if it doesn't exist
    try:
        cur.execute("SELECT peasants_fury FROM profiles LIMIT 1")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        logger.info("Adding peasants_fury column to profiles table...")
        cur.execute("ALTER TABLE profiles ADD COLUMN peasants_fury BOOLEAN DEFAULT 0")
        logger.info("Successfully added peasants_fury column")
    
    conn.commit()
    conn.close()
    logger.info("Profiles database initialized")


def get_or_create_profile(discord_id: str, username: str) -> Dict[str, Any]:
    """
    Get a user's profile or create one if it doesn't exist.
    
    Args:
        discord_id: Discord user ID
        username: Discord username
        
    Returns:
        Dictionary containing the user's profile data
    """
    create_profiles_db()
    conn = sqlite3.connect("profiles.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Try to get existing profile
    cur.execute("SELECT * FROM profiles WHERE discord_id = ?", (discord_id,))
    row = cur.fetchone()
    
    if row:
        profile = dict(row)
    else:
        # Create new profile with default values
        cur.execute(
            "INSERT INTO profiles (discord_id, username) VALUES (?, ?)",
            (discord_id, username)
        )
        conn.commit()
        
        # Fetch the newly created profile
        cur.execute("SELECT * FROM profiles WHERE discord_id = ?", (discord_id,))
        row = cur.fetchone()
        profile = dict(row)
    
    conn.close()
    return profile


def update_profile_achievement(discord_id: str, achievement_id: str) -> None:
    """
    Update a specific achievement in the user's profile.
    
    Args:
        discord_id: Discord user ID
        achievement_id: Achievement identifier (column name in profiles table)
    """
    conn = sqlite3.connect("profiles.db")
    cur = conn.cursor()
    
    cur.execute(
        f"UPDATE profiles SET {achievement_id} = 1 WHERE discord_id = ?",
        (discord_id,)
    )
    
    conn.commit()
    conn.close()
    logger.info(f"Achievement '{achievement_id}' unlocked for user {discord_id}")


# ============================================================================
# ACHIEVEMENT CHECK FUNCTIONS
# ============================================================================
# Each function returns True if the user qualifies for that achievement
# ============================================================================

async def check_win_5_games(discord_id: str) -> bool:
    """Check if user has won 5 or more games."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    # Count wins from both tables
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM match_records 
            WHERE reporter_id = ? AND did_win = 1
            UNION ALL
            SELECT 1 FROM solo_match_reports
            WHERE reporter_id = ? AND is_winner = 1
        )
    """, (discord_id, discord_id))
    
    wins = cur.fetchone()[0]
    conn.close()
    
    return wins >= 5


async def check_win_10_games(discord_id: str) -> bool:
    """Check if user has won 10 or more games."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM match_records 
            WHERE reporter_id = ? AND did_win = 1
            UNION ALL
            SELECT 1 FROM solo_match_reports
            WHERE reporter_id = ? AND is_winner = 1
        )
    """, (discord_id, discord_id))
    
    wins = cur.fetchone()[0]
    conn.close()
    
    return wins >= 10


async def check_win_25_games(discord_id: str) -> bool:
    """Check if user has won 25 or more games."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM match_records 
            WHERE reporter_id = ? AND did_win = 1
            UNION ALL
            SELECT 1 FROM solo_match_reports
            WHERE reporter_id = ? AND is_winner = 1
        )
    """, (discord_id, discord_id))
    
    wins = cur.fetchone()[0]
    conn.close()
    
    return wins >= 25


async def check_elo_1600(discord_id: str) -> bool:
    """Check if user has reached 1600 Elo rating."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    
    cur.execute("SELECT elo FROM overall_standings WHERE user_id = ?", (discord_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return row[0] >= 1600
    return False


async def check_elo_1700(discord_id: str) -> bool:
    """Check if user has reached 1700 Elo rating."""
    conn = sqlite3.connect("elo.db")
    cur = conn.cursor()
    
    cur.execute("SELECT elo FROM overall_standings WHERE user_id = ?", (discord_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return row[0] >= 1700
    return False


async def check_avatar_usage(discord_id: str, avatar_name: str) -> bool:
    """
    Check if user has played a game with a specific avatar.
    
    Args:
        discord_id: Discord user ID
        avatar_name: Name of the avatar to check for
    """
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    # Check both match_records and solo_match_reports
    cur.execute("""
        SELECT json_deck_data FROM match_records 
        WHERE reporter_id = ? AND json_deck_data IS NOT NULL
        UNION ALL
        SELECT json_deck_data FROM solo_match_reports
        WHERE reporter_id = ? AND json_deck_data IS NOT NULL
    """, (discord_id, discord_id))
    
    rows = cur.fetchall()
    conn.close()
    
    for row in rows:
        try:
            deck_data = json.loads(row[0])
            avatar = deck_data.get("avatar", [{}])
            if avatar and avatar[0].get("name", "").lower() == avatar_name.lower():
                return True
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
    
    return False


async def check_alpha_avatar(discord_id: str) -> bool:
    """Check if user has played with an Alpha avatar."""
    return await check_avatar_usage(discord_id, "Alpha")


async def check_beta_avatar(discord_id: str) -> bool:
    """Check if user has played with a Beta avatar."""
    return await check_avatar_usage(discord_id, "Beta")


async def check_play_100_games(discord_id: str) -> bool:
    """Check if user has played 100 or more games."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT 1 FROM match_records WHERE reporter_id = ?
            UNION ALL
            SELECT 1 FROM solo_match_reports WHERE reporter_id = ?
        )
    """, (discord_id, discord_id))
    
    total_games = cur.fetchone()[0]
    conn.close()
    
    return total_games >= 100


async def check_first_player_master(discord_id: str) -> bool:
    """Check if user has a 60%+ win rate as first player (minimum 10 games)."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    # Get all games where user went first
    cur.execute("""
        SELECT did_win FROM match_records 
        WHERE reporter_id = ? AND first_player LIKE '%y%'
        UNION ALL
        SELECT is_winner FROM solo_match_reports
        WHERE reporter_id = ? AND first_player LIKE '%y%'
    """, (discord_id, discord_id))
    
    rows = cur.fetchall()
    conn.close()
    
    if len(rows) < 10:
        return False
    
    wins = sum(1 for row in rows if row[0])
    win_rate = wins / len(rows)
    
    return win_rate >= 0.60


async def check_comeback_king(discord_id: str) -> bool:
    """Check if user has a 55%+ win rate on the draw (minimum 10 games)."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    # Get all games where user went second (not first)
    cur.execute("""
        SELECT did_win FROM match_records 
        WHERE reporter_id = ? AND (first_player NOT LIKE '%y%' OR first_player = '')
        UNION ALL
        SELECT is_winner FROM solo_match_reports
        WHERE reporter_id = ? AND (first_player NOT LIKE '%y%' OR first_player = '')
    """, (discord_id, discord_id))
    
    rows = cur.fetchall()
    conn.close()
    
    if len(rows) < 10:
        return False
    
    wins = sum(1 for row in rows if row[0])
    win_rate = wins / len(rows)
    
    return win_rate >= 0.55


async def check_peasants_fury(discord_id: str) -> bool:
    """
    Check if user has won a game using only Ordinary and Exceptional rarity cards.
    Avatar rarity is excluded from this check.
    """
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()
    
    # Get all winning games with deck data
    cur.execute("""
        SELECT json_deck_data FROM match_records 
        WHERE reporter_id = ? AND did_win = 1 AND json_deck_data IS NOT NULL
        UNION ALL
        SELECT json_deck_data FROM solo_match_reports
        WHERE reporter_id = ? AND is_winner = 1 AND json_deck_data IS NOT NULL
    """, (discord_id, discord_id))
    
    rows = cur.fetchall()
    conn.close()
    
    for row in rows:
        try:
            deck_data = json.loads(row[0])
            
            # Check all cards except avatar
            cards_to_check = []
            
            # Add spellbook cards
            if "spellbook" in deck_data:
                cards_to_check.extend(deck_data["spellbook"])
            
            # Add atlas (site) cards
            if "atlas" in deck_data:
                cards_to_check.extend(deck_data["atlas"])
            
            # Add sideboard cards
            if "sideboard" in deck_data:
                cards_to_check.extend(deck_data["sideboard"])
            
            # Check if ALL cards are Ordinary or Exceptional
            if cards_to_check:
                all_common = all(
                    card.get("rarity", "").lower() in ["ordinary", "exceptional"]
                    for card in cards_to_check
                )
                
                if all_common:
                    return True
                    
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    
    return False


# ============================================================================
# ACHIEVEMENT REGISTRY
# ============================================================================

ACHIEVEMENTS = {
    "win_5_games": {
        "name": "First Streak",
        "description": "Win 5 recorded games",
        "emoji": "🎯",
        "check_func": check_win_5_games
    },
    "win_10_games": {
        "name": "Rising Champion",
        "description": "Win 10 recorded games",
        "emoji": "🏆",
        "check_func": check_win_10_games
    },
    "win_25_games": {
        "name": "Tournament Victor",
        "description": "Win 25 recorded games",
        "emoji": "👑",
        "check_func": check_win_25_games
    },
    "elo_1600": {
        "name": "Rising Star",
        "description": "Reach 1600 Elo rating",
        "emoji": "⭐",
        "check_func": check_elo_1600
    },
    "elo_1700": {
        "name": "Elite Player",
        "description": "Reach 1700 Elo rating",
        "emoji": "💫",
        "check_func": check_elo_1700
    },
    "elo_1800": {
        "name": "Grand Master",
        "description": "Reach 1800 Elo rating",
        "emoji": "🌟",
        "check_func": check_elo_1800
    },
    "alpha_avatar": {
        "name": "Alpha Initiate",
        "description": "Play a game using an Alpha avatar",
        "emoji": "🅰️",
        "check_func": check_alpha_avatar
    },
    "beta_avatar": {
        "name": "Beta Warrior",
        "description": "Play a game using a Beta avatar",
        "emoji": "🅱️",
        "check_func": check_beta_avatar
    },
    "play_100_games": {
        "name": "Century Club",
        "description": "Play 100 recorded games",
        "emoji": "💯",
        "check_func": check_play_100_games
    },
    "first_player_master": {
        "name": "First Strike Master",
        "description": "Achieve 60%+ win rate as first player (min 10 games)",
        "emoji": "⚡",
        "check_func": check_first_player_master
    },
    "comeback_king": {
        "name": "Comeback King",
        "description": "Achieve 55%+ win rate on the draw (min 10 games)",
        "emoji": "🔄",
        "check_func": check_comeback_king
    },
    "peasants_fury": {
        "name": "Peasant's Fury",
        "description": "Win a game using only Ordinary and Exceptional rarity cards",
        "emoji": "⚔️",
        "check_func": check_peasants_fury
    }
}


# ============================================================================
# ACHIEVEMENT EVALUATION
# ============================================================================

async def evaluate_achievements(
    discord_id: str, 
    username: str, 
    bot: discord.Client,
    announcement_channel_id: Optional[int] = None
) -> list[str]:
    """
    Evaluate all achievements for a user and unlock any newly earned ones.
    
    Args:
        discord_id: Discord user ID (as string)
        username: Discord username
        bot: Discord bot instance (for sending announcements)
        announcement_channel_id: Channel ID for achievement announcements
        
    Returns:
        List of newly unlocked achievement IDs
    """
    newly_unlocked = []
    
    # Get or create user profile
    profile = get_or_create_profile(discord_id, username)
    
    # Check each achievement
    for achievement_id, config in ACHIEVEMENTS.items():
        # Skip if already unlocked
        if profile.get(achievement_id):
            continue
        
        # Check if user qualifies
        try:
            if await config["check_func"](discord_id):
                # Update database
                update_profile_achievement(discord_id, achievement_id)
                newly_unlocked.append(achievement_id)
                
                # Send announcement if channel is specified
                if announcement_channel_id and bot:
                    try:
                        channel = bot.get_channel(announcement_channel_id)
                        if channel:
                            # Get updated profile to count total earned achievements
                            updated_profile = get_or_create_profile(discord_id, username)
                            total_achievements = len(ACHIEVEMENTS)
                            earned_count = sum(1 for aid in ACHIEVEMENTS.keys() if updated_profile.get(aid))
                            
                            # Get the user object to mention them
                            try:
                                user = await bot.fetch_user(int(discord_id))
                                user_mention = user.mention
                            except:
                                user_mention = username
                            
                            embed = discord.Embed(
                                title="🎉 Achievement Unlocked! 🎉",
                                description=f"{user_mention} has earned a new achievement!",
                                color=discord.Color.gold()
                            )
                            embed.add_field(
                                name=f"{config['emoji']} {config['name']}",
                                value=config['description'],
                                inline=False
                            )
                            embed.add_field(
                                name="Progress",
                                value=f"{earned_count}/{total_achievements} achievements completed",
                                inline=False
                            )
                            
                            await channel.send(embed=embed)
                            logger.info(
                                f"Achievement announcement sent for {username}: {achievement_id} ({earned_count}/{total_achievements})"
                            )
                    except Exception as e:
                        logger.error(f"Failed to send achievement announcement: {e}")
        
        except Exception as e:
            logger.error(f"Error checking achievement '{achievement_id}' for {discord_id}: {e}")
    
    return newly_unlocked


def get_user_achievements(discord_id: str, username: str) -> Tuple[Dict[str, bool], Dict[str, Any]]:
    """
    Get all achievements for a user with their completion status.
    
    Args:
        discord_id: Discord user ID
        username: Discord username
        
    Returns:
        Tuple of (achievement_status_dict, profile_dict)
    """
    profile = get_or_create_profile(discord_id, username)
    
    achievement_status = {}
    for achievement_id in ACHIEVEMENTS.keys():
        achievement_status[achievement_id] = bool(profile.get(achievement_id, False))
    
    return achievement_status, profile


def get_earned_achievements(discord_id: str, username: str) -> list[str]:
    """
    Get list of achievement IDs that the user has earned.
    
    Args:
        discord_id: Discord user ID
        username: Discord username
        
    Returns:
        List of earned achievement IDs
    """
    profile = get_or_create_profile(discord_id, username)
    
    earned = []
    for achievement_id in ACHIEVEMENTS.keys():
        if profile.get(achievement_id):
            earned.append(achievement_id)
    
    return earned
