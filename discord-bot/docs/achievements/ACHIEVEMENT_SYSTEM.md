# Achievement System Documentation

## Overview

The Achievement System is a comprehensive user engagement feature that tracks and rewards player accomplishments in the Summit Discord Bot. Users earn achievements based on their game performance, Elo ratings, and avatar usage.

## Architecture

The achievement system consists of three main components:

1. **`utils/achievements.py`** - Core achievement logic and database management
2. **`cogs/achievements.py`** - Discord command interface
3. **`profiles.db`** - SQLite database storing user achievement data

## Database Structure

### Profiles Table (`profiles.db`)

```sql
CREATE TABLE profiles (
    discord_id TEXT PRIMARY KEY,
    username TEXT,

    -- Win-based achievements
    win_5_games BOOLEAN DEFAULT 0,
    win_10_games BOOLEAN DEFAULT 0,
    win_25_games BOOLEAN DEFAULT 0,

    -- Elo-based achievements
    elo_1600 BOOLEAN DEFAULT 0,
    elo_1700 BOOLEAN DEFAULT 0,
    elo_1800 BOOLEAN DEFAULT 0,

    -- Avatar-based achievements
    alpha_avatar BOOLEAN DEFAULT 0,
    beta_avatar BOOLEAN DEFAULT 0,

    -- Special achievements
    play_100_games BOOLEAN DEFAULT 0,
    first_player_master BOOLEAN DEFAULT 0,
    comeback_king BOOLEAN DEFAULT 0,
    peasants_fury BOOLEAN DEFAULT 0
)
```

## Achievement Registry

All achievements are defined in the `ACHIEVEMENTS` dictionary in `utils/achievements.py`:

```python
ACHIEVEMENTS = {
    "achievement_id": {
        "name": "Display Name",
        "description": "How to earn this achievement",
        "emoji": "🎯",
        "check_func": check_function_name
    }
}
```

### Current Achievements

#### 🎯 Victory & Participation

- **First Streak** - Win 5 recorded games
- **Rising Champion** - Win 10 recorded games
- **Tournament Victor** - Win 25 recorded games
- **Century Club** - Play 100 recorded games

#### ⚡ Elo Milestones

- **Rising Star** - Reach 1600 Elo rating
- **Elite Player** - Reach 1700 Elo rating
- **Grand Master** - Reach 1800 Elo rating

#### 🎭 Avatar Collection

- **Alpha Initiate** - Play a game using an Alpha avatar
- **Beta Warrior** - Play a game using a Beta avatar

#### 🌟 Special Achievements

- **First Strike Master** - Achieve 60%+ win rate as first player (min 10 games)
- **Comeback King** - Achieve 55%+ win rate on the draw (min 10 games)
- **Peasant's Fury** - Win a game using only Ordinary and Exceptional rarity cards

> **Note on Peasant's Fury:** This achievement checks the `json_deck_data` stored in `match_records.db`. All cards in the spellbook, atlas (sites), and sideboard must be either "Ordinary" or "Exceptional" rarity. The avatar card is excluded from this check - you can use any avatar. Elite and Unique rarity cards will disqualify the deck.

## How It Works

### 1. Automatic Evaluation

After every match submission (win/loss report), the system automatically:

1. Loads the user's profile from `profiles.db`
2. Checks all achievements they haven't earned yet
3. Runs the check function for each achievement
4. Updates the database if criteria are met
5. Posts an announcement in the configured channel

### 2. Check Functions

Each achievement has an associated check function with this signature:

```python
async def check_achievement_name(discord_id: str) -> bool:
    # Query databases to check if user qualifies
    # Return True if achievement earned, False otherwise
```

Check functions can query:

- `match_records.db` - Match history, wins/losses, deck data
- `elo.db` - Current Elo ratings
- `profiles.db` - User profile data

### 3. Achievement Announcements

When a user earns an achievement, an embed is posted to the configured announcement channel:

```
🎉 Achievement Unlocked! 🎉
Username has earned a new achievement!

🏆 Achievement Name
Description of the achievement
```

## Discord Commands

### Slash Commands

#### `/profile [@user]`

View a user's profile with all achievements and progress bar.

**Usage:**

- `/profile` - View your own profile
- `/profile @JohnDoe` - View another user's profile

**Display:**

- Achievement progress bar
- Categorized list of all achievements (earned ✅ / not earned ❌)
- Completion percentage

#### `/achievements list`

Display all available achievements with descriptions.

**Shows:**

- All achievements grouped by category
- Achievement names, emojis, and how to earn them

#### `/achievements earned [@user]`

Show only the achievements a user has completed.

**Usage:**

- `/achievements earned` - Your earned achievements
- `/achievements earned @JohnDoe` - Another user's earned achievements

### Admin Commands

#### `!checkachievements [@user]`

Manually trigger achievement evaluation for a user.

**Requirements:** Administrator permission

**Usage:**

- `!checkachievements` - Check your achievements
- `!checkachievements @JohnDoe` - Check another user's achievements

**Purpose:**

- Testing new achievements
- Fixing stuck achievements
- Retroactively awarding achievements

## Configuration

### Achievement Announcement Channel

Edit `utils/config.py`:

```python
# Set to your channel ID for achievement announcements
ACHIEVEMENT_CHANNEL_ID = 1234567890123456789

# Set to None to disable announcements (achievements still tracked)
ACHIEVEMENT_CHANNEL_ID = None
```

## Adding New Achievements

Adding a new achievement requires 3 steps:

### Step 1: Add Database Column

Update `create_profiles_db()` in `utils/achievements.py`:

```python
cur.execute("""CREATE TABLE IF NOT EXISTS profiles
               (discord_id TEXT PRIMARY KEY,
                username TEXT,
                ...existing columns...,
                new_achievement_id BOOLEAN DEFAULT 0  # Add this line
               )""")
```

### Step 2: Create Check Function

Add a new check function in `utils/achievements.py`:

```python
async def check_new_achievement(discord_id: str) -> bool:
    """Check if user qualifies for this achievement."""
    conn = sqlite3.connect("appropriate_db.db")
    cur = conn.cursor()

    # Your logic here
    # Query databases, check conditions

    conn.close()
    return True  # or False
```

### Step 3: Register in ACHIEVEMENTS Dictionary

Add entry to `ACHIEVEMENTS` in `utils/achievements.py`:

```python
ACHIEVEMENTS = {
    ...existing achievements...,
    "new_achievement_id": {
        "name": "Achievement Display Name",
        "description": "How to earn this achievement",
        "emoji": "🎨",  # Choose an appropriate emoji
        "check_func": check_new_achievement
    }
}
```

### Example: Adding "Hat Trick" Achievement

```python
# Step 1: Column already added via migration or database update

# Step 2: Check function
async def check_hat_trick(discord_id: str) -> bool:
    """Check if user won 3 games in a row."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Get last 3 games
    cur.execute("""
        SELECT did_win FROM match_records
        WHERE reporter_id = ?
        ORDER BY timestamp DESC LIMIT 3
    """, (discord_id,))

    last_three = cur.fetchall()
    conn.close()

    # Check if all 3 were wins
    return len(last_three) == 3 and all(game[0] for game in last_three)

# Step 3: Registry entry
"hat_trick": {
    "name": "Hat Trick",
    "description": "Win 3 games in a row",
    "emoji": "🎩",
    "check_func": check_hat_trick
}
```

## Integration Points

### Match Submission

Achievement evaluation is triggered in three places:

1. **`winner_report()`** in `utils/database.py`
2. **`losser_report()`** in `utils/database.py`
3. **`solo_match_report()`** in `utils/database.py`

Each function calls:

```python
from utils.achievements import evaluate_achievements
from utils.config import ACHIEVEMENT_CHANNEL_ID

await evaluate_achievements(
    str(user_id),
    username,
    bot,
    ACHIEVEMENT_CHANNEL_ID
)
```

### Required Bot Instance

All match report UI classes now accept a `bot` parameter:

- `MatchReportModal(winner_id, winner_global, loser_id, loser_global, is_winner, bot)`
- `LFGReportButtons(match_id, player1_id, player1_global, player2_id, player2_global, bot)`
- `ReportButtonsSolo(reporter_id, reporter_global, bot)`
- `SoloMatchReportModal(reporter_id, reporter_global, is_winner, bot)`

## Data Flow

```
User submits match
    ↓
winner_report() / losser_report() / solo_match_report()
    ↓
evaluate_achievements(discord_id, username, bot, channel_id)
    ↓
For each achievement not yet earned:
    ↓
    Run check_func(discord_id)
    ↓
    If True: Update profile, send announcement
```

## Testing

### Manual Testing

1. Use `!checkachievements` command as admin
2. Check user profiles with `/profile`
3. Verify database with SQLite browser

### Testing New Achievements

```python
# In Python console or test script
import asyncio
from utils.achievements import check_new_achievement

# Test the check function
result = asyncio.run(check_new_achievement("123456789"))
print(f"User qualifies: {result}")
```

### Retroactive Awards

If you add a new achievement and want to award it to existing users:

```python
# Run this script once
import sqlite3
from utils.achievements import evaluate_achievements

# Get all users
conn = sqlite3.connect("profiles.db")
cur = conn.cursor()
cur.execute("SELECT discord_id, username FROM profiles")
users = cur.fetchall()
conn.close()

# Check achievements for each user
for discord_id, username in users:
    await evaluate_achievements(discord_id, username, bot, ACHIEVEMENT_CHANNEL_ID)
```

## Performance Considerations

- Achievement checks run asynchronously to avoid blocking match submissions
- Database queries are optimized with proper indexing
- Check functions should be fast (< 100ms)
- Announcement failures are logged but don't block the system

## Error Handling

The system includes comprehensive error handling:

1. **Database Errors**: Logged with details, don't crash bot
2. **Missing Channels**: Achievements still tracked, just not announced
3. **Permission Errors**: Silently skipped
4. **Invalid Data**: Gracefully handled with fallbacks

## Troubleshooting

### Achievement Not Unlocking

1. Check if user actually meets criteria
2. Run `!checkachievements @user` manually
3. Check bot logs for errors
4. Verify database connectivity
5. Ensure check function logic is correct

### Announcements Not Posting

1. Verify `ACHIEVEMENT_CHANNEL_ID` is set correctly
2. Check bot has permission to post in that channel
3. Ensure channel exists
4. Check bot logs for permission errors

### Profile Not Found

- Profiles are created automatically on first achievement check
- If needed, manually create with `get_or_create_profile(discord_id, username)`

## Future Enhancements

Potential additions to the achievement system:

1. **Tiered Achievements** - Bronze/Silver/Gold versions
2. **Secret Achievements** - Hidden until earned
3. **Seasonal Achievements** - Time-limited challenges
4. **Achievement Points** - Scoring system for leaderboard
5. **Badges/Roles** - Discord roles for achievements
6. **Achievement Rewards** - Shop currency or perks
7. **Achievement Statistics** - Global completion rates
8. **Achievement Notifications** - DM users on unlock

## Maintenance

### Database Migrations

When adding new achievement columns:

```python
# Add column to existing database
conn = sqlite3.connect("profiles.db")
cur = conn.cursor()
cur.execute("ALTER TABLE profiles ADD COLUMN new_achievement BOOLEAN DEFAULT 0")
conn.commit()
conn.close()
```

### Backing Up Data

```bash
# Regular backups recommended
cp profiles.db profiles.db.backup
```

## Summary

The achievement system is:

- ✅ **Automatic** - Checks after every match
- ✅ **Extensible** - Easy to add new achievements
- ✅ **Robust** - Comprehensive error handling
- ✅ **User-Friendly** - Clear commands and displays
- ✅ **Integrated** - Works with existing match system

For questions or issues, check the bot logs or contact the development team.
