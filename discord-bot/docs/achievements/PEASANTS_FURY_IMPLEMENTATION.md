# Peasant's Fury Achievement - Implementation Summary

## Overview

Added a new achievement called **"Peasant's Fury"** that rewards players for winning a game using only Ordinary and Exceptional rarity cards (excluding the avatar).

## Changes Made

### 1. Database Schema (`utils/achievements.py`)

Added new column to profiles table:

```sql
peasants_fury BOOLEAN DEFAULT 0
```

**Migration Handling:**

- Added automatic migration code in `create_profiles_db()` to add the column to existing databases
- Uses try/except to check if column exists before attempting to add it
- Logs migration actions for debugging

### 2. Check Function (`utils/achievements.py`)

Created `check_peasants_fury()` function that:

- Queries all winning games with `json_deck_data` from both `match_records` and `solo_match_reports`
- Parses JSON deck data to extract cards from:
  - `spellbook` (creature and spell cards)
  - `atlas` (site/land cards)
  - `sideboard` (sideboard cards)
- **Excludes avatar** from rarity check (any avatar can be used)
- Checks if ALL non-avatar cards have rarity "Ordinary" or "Exceptional"
- Returns `True` if player has won at least one qualifying game

**Card Rarities:**

- ✅ **Qualifying:** "Ordinary", "Exceptional"
- ❌ **Disqualifying:** "Elite", "Unique"
- 🔄 **Ignored:** Avatar card (any rarity allowed)

### 3. Achievement Registry (`utils/achievements.py`)

Added entry to `ACHIEVEMENTS` dictionary:

```python
"peasants_fury": {
    "name": "Peasant's Fury",
    "description": "Win a game using only Ordinary and Exceptional rarity cards",
    "emoji": "⚔️",
    "check_func": check_peasants_fury
}
```

### 4. Documentation Updates

Updated all documentation to reflect 12 total achievements (previously 11):

- **ACHIEVEMENT_SYSTEM.md:**

  - Added `peasants_fury` to database schema
  - Listed achievement in Special Achievements section
  - Added detailed note explaining how deck checking works

- **ACHIEVEMENT_DEPLOYMENT.md:**

  - Updated profile expectations (0/12 instead of 0/11)
  - Updated achievement list expectations (12 instead of 11)
  - Updated database column count (14 columns: 2 + 12 achievements)

- **ACHIEVEMENT_COMMANDS.md:**

  - Updated progress examples (5/12 instead of 5/11)
  - Updated percentage calculations

- **ACHIEVEMENT_IMPLEMENTATION_SUMMARY.md:**
  - Updated achievement count to 12

### 5. Configuration

Channel ID for announcements is already configured:

```python
ACHIEVEMENT_CHANNEL_ID = 1444292011372052511
```

When users earn this achievement, they will be tagged in this channel with a message showing their progress.

## Testing

Created `test_peasants_fury.py` to verify the logic:

**Test Results:**

- ✅ Correctly identifies decks with Elite/Unique cards as disqualified
- ✅ Correctly identifies decks with only Ordinary/Exceptional as qualified
- ✅ Properly ignores avatar rarity
- ✅ Checks all card locations (spellbook, atlas, sideboard)

## Database Structure

Total achievements now: **12**

### Achievement Categories:

1. **Win-Based (3):** win_5_games, win_10_games, win_25_games
2. **Elo-Based (3):** elo_1600, elo_1700, elo_1800
3. **Avatar-Based (2):** alpha_avatar, beta_avatar
4. **Special (4):** play_100_games, first_player_master, comeback_king, **peasants_fury** ⬅️ NEW

## How It Works

1. **Trigger:** After every match win report (both regular and solo matches)
2. **Check:** System evaluates if the deck used contains only Ordinary/Exceptional cards
3. **Award:** If true, updates `profiles.db` and sends announcement
4. **Announcement:** Tags user in channel 1444292011372052511 with achievement details and progress (X/12 completed)

## Example Deck Analysis

### ❌ Example 1: Big Fury (DISQUALIFIED)

- Contains: Earthquake (Elite), Courtesan Thais (Unique)
- Result: Does not qualify

### ✅ Example 2: Budget Deck (QUALIFIES)

- Spellbook: Root Spider (Exceptional), Bury (Ordinary), etc.
- Atlas: Holy Ground (Exceptional), Arid Desert (Ordinary)
- Avatar: Sorcerer (any rarity - ignored)
- Result: Achievement earned!

## Implementation Notes

- **No breaking changes:** Existing code continues to work
- **Automatic migration:** New column added automatically on bot startup
- **Backward compatible:** Works with existing match records
- **Performance:** Efficient JSON parsing with error handling
- **Extensible:** Easy to modify rarity requirements if needed

## Deployment

1. Pull the updated code
2. Restart the bot
3. The database will automatically add the new column
4. Achievement will start being checked on all new match reports
5. Use `!checkachievements` to retroactively award to eligible users

## Files Modified

- `discord-bot/utils/achievements.py` (added column, check function, registry entry)
- `discord-bot/utils/config.py` (updated ACHIEVEMENT_CHANNEL_ID)
- `discord-bot/docs/achievements/ACHIEVEMENT_SYSTEM.md`
- `discord-bot/docs/achievements/ACHIEVEMENT_DEPLOYMENT.md`
- `discord-bot/docs/achievements/ACHIEVEMENT_COMMANDS.md`
- `discord-bot/docs/achievements/ACHIEVEMENT_IMPLEMENTATION_SUMMARY.md`

## Total Achievement Count: 12

🎯 Victory & Participation: 4
⚡ Elo Milestones: 3  
🎭 Avatar Collection: 2
🌟 Special Achievements: 3
⚔️ **Peasant's Fury: 1** ⬅️ NEW
