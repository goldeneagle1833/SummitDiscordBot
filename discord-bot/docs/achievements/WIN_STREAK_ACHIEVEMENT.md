# Win Streak Achievement - November 29, 2025

## New Achievement Added: Unstoppable Force 🔥

### Overview

Added a new achievement that rewards players for winning 5 consecutive games, demonstrating sustained excellence and consistency.

## Achievement Details

**Name:** Unstoppable Force  
**Emoji:** 🔥  
**Description:** Win 5 games in a row  
**Database Column:** `win_streak_5`  
**Check Function:** `check_win_streak_5()`

## Implementation

### 1. Database Schema

Added new column to `profiles` table:

```sql
win_streak_5 BOOLEAN DEFAULT 0
```

Includes automatic migration that adds the column if it doesn't exist.

### 2. Check Function

```python
async def check_win_streak_5(discord_id: str) -> bool:
    """Check if user has won 5 games in a row."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    # Get all games ordered by timestamp (most recent first)
    cur.execute("""
        SELECT did_win, timestamp FROM match_records
        WHERE reporter_id = ?
        UNION ALL
        SELECT is_winner, timestamp FROM solo_match_reports
        WHERE reporter_id = ?
        ORDER BY timestamp DESC
    """, (discord_id, discord_id))

    rows = cur.fetchall()
    conn.close()

    if len(rows) < 5:
        return False

    # Check for any streak of 5 consecutive wins
    current_streak = 0
    for row in rows:
        if row[0]:  # If won
            current_streak += 1
            if current_streak >= 5:
                return True
        else:  # If lost
            current_streak = 0

    return False
```

### 3. Achievement Registry Entry

```python
"win_streak_5": {
    "name": "Unstoppable Force",
    "description": "Win 5 games in a row",
    "emoji": "🔥",
    "check_func": check_win_streak_5
}
```

## How It Works

### Detection Logic

1. **Query Games:** Retrieves all games for the user ordered by timestamp (most recent first)
2. **Minimum Games:** Requires at least 5 games played
3. **Streak Counting:** Iterates through games, counting consecutive wins
4. **Reset on Loss:** Any loss resets the streak counter to 0
5. **Achievement Unlock:** Returns `True` when 5 consecutive wins are found

### Key Features

- ✅ Detects win streaks at any point in match history
- ✅ Works with both `match_records` and `solo_match_reports` tables
- ✅ Chronological ordering ensures proper streak detection
- ✅ Resets streak counter on each loss
- ✅ Can detect multiple streaks (unlocks on first occurrence)

## Testing

Comprehensive test suite in `tests/test_win_streak.py` covers:

1. ✅ Exactly 5 wins in a row
2. ✅ More than 5 wins in a row (7 wins)
3. ✅ 5 wins after losses
4. ✅ 5 wins followed by losses
5. ✅ 5 wins in the middle of match history
6. ✅ Correctly rejects 4 wins
7. ✅ Correctly rejects two separate 4-win streaks
8. ✅ Correctly rejects alternating wins/losses
9. ✅ Correctly requires minimum 5 games
10. ✅ Detects multiple 5-win streaks

All tests pass successfully!

## Example Scenarios

### ✅ Scenario 1: Perfect Start

```
Games: W W W W W
Result: Achievement Unlocked! 🔥
```

### ✅ Scenario 2: Comeback Streak

```
Games: L L W W W W W
Result: Achievement Unlocked! 🔥
```

### ❌ Scenario 3: Broken Streak

```
Games: W W W W L W W W W
Result: No achievement (4-win streak broken)
```

### ✅ Scenario 4: Multiple Streaks

```
Games: W W W W W L W W W W W
Result: Achievement Unlocked! 🔥
(Unlocks on first 5-win streak)
```

## Total Achievements

The system now tracks **13 achievements** (was 12):

### Win-Based (4)

- 🎯 Early Success (5 wins)
- 🏆 Rising Champion (10 wins)
- 👑 Proven Victor (25 wins)
- 🔥 **Unstoppable Force (5-win streak)** ← NEW

### Elo-Based (3)

- ⭐ Rising Star (1600 Elo)
- 💫 Elite Player (1700 Elo)
- 🌟 Grand Master (1800 Elo)

### Avatar-Based (2)

- 🅰️ Alpha Initiate (Alpha set avatar)
- 🅱️ Beta Warrior (Beta set avatar)

### Performance-Based (4)

- 💯 Century Club (100 games played)
- ⚡ First Strike Master (65%+ win rate first player)
- 🔄 Comeback King (60%+ win rate on draw)
- ⚔️ Peasant's Fury (Win with Ordinary/Exceptional cards only)

## Deployment

### No Manual Steps Required

1. ✅ Database migration runs automatically on bot startup
2. ✅ Column added automatically if missing
3. ✅ Existing achievements unaffected
4. ✅ Achievement checks run after every match report

### Verification Steps

1. Restart the bot to ensure migration runs
2. Have a user win 5 consecutive games
3. Verify "🔥 Unstoppable Force" achievement unlocks
4. Check announcement in channel 1444292011372052511
5. Verify progress shows "X/13 achievements completed"

## Technical Notes

### Database Query

- Uses `UNION ALL` to combine both match reporting tables
- Orders by `timestamp DESC` for chronological order
- Efficient single-pass algorithm with O(n) time complexity

### Edge Cases Handled

- ✅ Minimum game requirement (< 5 games)
- ✅ Streak detection at any position
- ✅ Multiple streaks in history
- ✅ Proper streak reset on loss
- ✅ NULL/missing data handling

## Future Enhancements

Potential additional streak achievements:

- **Legendary Run** (10-win streak)
- **Domination** (15-win streak)
- **Perfection** (Win all games in a day)
- **Weekend Warrior** (5-win streak on weekend)

---

**Added by:** GitHub Copilot  
**Date:** November 29, 2025  
**Status:** ✅ Complete and Tested
