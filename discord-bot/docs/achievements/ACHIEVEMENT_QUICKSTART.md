# Achievement System Quick Start

## For Users

### View Your Achievements

```
/profile
```

### View All Available Achievements

```
/achievements list
```

### View Your Earned Achievements

```
/achievements earned
```

### View Another User's Profile

```
/profile @username
```

---

## For Admins

### Manual Achievement Check

```
!checkachievements @username
```

### Set Achievement Announcement Channel

Edit `utils/config.py`:

```python
ACHIEVEMENT_CHANNEL_ID = 1234567890123456789
```

---

## For Developers

### Add New Achievement (3 Steps)

#### 1. Add Database Column

In `utils/achievements.py`, update `create_profiles_db()`:

```python
your_achievement_id BOOLEAN DEFAULT 0
```

#### 2. Create Check Function

In `utils/achievements.py`:

```python
async def check_your_achievement_id(discord_id: str) -> bool:
    # Your logic here
    return True  # or False
```

#### 3. Register Achievement

In `utils/achievements.py`, add to `ACHIEVEMENTS` dict:

```python
"your_achievement_id": {
    "name": "Display Name",
    "description": "How to earn this",
    "emoji": "🎯",
    "check_func": check_your_achievement_id
}
```

### Available Data Sources

```python
# Match records and game history
sqlite3.connect("match_records.db")

# Elo ratings
sqlite3.connect("elo.db")

# User profiles and achievements
sqlite3.connect("profiles.db")
```

---

## Current Achievements

### 📊 Victory & Participation

- 🎯 **First Streak** - Win 5 games
- 🏆 **Rising Champion** - Win 10 games
- 👑 **Tournament Victor** - Win 25 games
- 💯 **Century Club** - Play 100 games

### ⚡ Elo Milestones

- ⭐ **Rising Star** - Reach 1600 Elo
- 💫 **Elite Player** - Reach 1700 Elo
- 🌟 **Grand Master** - Reach 1800 Elo

### 🎭 Avatar Collection

- 🅰️ **Alpha Initiate** - Use Alpha avatar
- 🅱️ **Beta Warrior** - Use Beta avatar

### 🌟 Special

- ⚡ **First Strike Master** - 60%+ win rate as first player (10+ games)
- 🔄 **Comeback King** - 55%+ win rate on the draw (10+ games)

---

## Troubleshooting

### Achievement not unlocking?

```
!checkachievements @user
```

### Check bot logs

```
tail -f bot.log
```

### Verify database

```python
import sqlite3
conn = sqlite3.connect("profiles.db")
cur = conn.cursor()
cur.execute("SELECT * FROM profiles WHERE discord_id = ?", (user_id,))
print(cur.fetchone())
```

---

## Files Modified

- ✅ `utils/achievements.py` - Core achievement system
- ✅ `cogs/achievements.py` - Discord commands
- ✅ `utils/database.py` - Match report integration
- ✅ `cogs/lfg.py` - Bot instance passing
- ✅ `utils/config.py` - Configuration
- ✅ `main.py` - Cog loading + Auto-initialize database

## New Files Created

- ✅ `ACHIEVEMENT_SYSTEM.md` - Full documentation
- ✅ `ACHIEVEMENT_QUICKSTART.md` - This file

## Getting Started

The achievement system is **automatically initialized** when you start the bot!

1. **Configure announcement channel (optional)**:

   ```python
   # In utils/config.py
   ACHIEVEMENT_CHANNEL_ID = 1234567890123456789  # or None
   ```

2. **Start the bot**:

   ```bash
   python main.py
   ```

3. **That's it!** The database is created automatically. Start using:
   ```
   /profile
   /achievements list
   ```

No manual database setup required! ✨
