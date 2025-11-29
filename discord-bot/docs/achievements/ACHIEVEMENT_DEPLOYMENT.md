# Achievement System Deployment Checklist

## Pre-Deployment

### 1. Verify Files Created ✅

- [ ] `utils/achievements.py` - Core achievement system
- [ ] `cogs/achievements.py` - Discord commands
- [ ] `init_achievements_db.py` - Database initialization script
- [ ] `test_achievements.py` - Test suite
- [ ] `ACHIEVEMENT_SYSTEM.md` - Technical documentation
- [ ] `ACHIEVEMENT_QUICKSTART.md` - Quick reference
- [ ] `ACHIEVEMENT_COMMANDS.md` - User guide
- [ ] `ACHIEVEMENT_IMPLEMENTATION_SUMMARY.md` - Summary

### 2. Verify Files Modified ✅

- [ ] `utils/database.py` - Added async + achievement integration
- [ ] `cogs/lfg.py` - Added bot parameter passing
- [ ] `utils/config.py` - Added ACHIEVEMENT_CHANNEL_ID
- [ ] `main.py` - Added AchievementsCog loading

### 3. Run Syntax Check ✅

```bash
python -m py_compile utils/achievements.py
python -m py_compile cogs/achievements.py
```

### 4. Initialize Database ✅

```bash
cd discord-bot
python init_achievements_db.py
```

Expected output:

```
🎯 Achievement System Database Initialization
==================================================
📊 Creating profiles.db table...
✅ Profiles database created successfully!
📋 Database schema verified:
   - Table: profiles
   - Columns: 17
   - Achievement fields: 15
✨ Achievement system is ready to use!
```

### 5. Run Tests (Optional) ✅

```bash
python test_achievements.py
```

Expected output:

```
Tests passed: 5/5
✨ All tests passed! Achievement system is ready.
```

---

## Configuration

### 1. Set Achievement Channel ID

Edit `utils/config.py`:

```python
# Replace None with your channel ID
ACHIEVEMENT_CHANNEL_ID = 1234567890123456789
```

**To get channel ID:**

1. Enable Developer Mode in Discord (Settings → Advanced)
2. Right-click on channel → Copy ID
3. Paste into config.py

**Or leave as None:**

- Achievements will still be tracked
- No announcements will be posted
- Users can still view with `/profile`

---

## Deployment

### 1. Install Dependencies

Ensure these are in `requirements.txt` and installed:

```
discord.py>=2.0.0
python-dotenv
```

### 2. Start the Bot

```bash
python main.py
```

### 3. Verify Bot Startup

Check console output for:

```
Logged in as YourBotName
Synced X slash commands  # Should include new achievement commands
```

### 4. Check Cog Loading

Look for in logs:

- No errors loading AchievementsCog
- Achievement commands registered

---

## Post-Deployment Testing

### 1. Test Slash Commands

#### Test /profile

```
/profile
```

Expected: Embed showing your profile with 0/12 achievements

#### Test /achievements list

```
/achievements list
```

Expected: Embed showing all 12 achievements with descriptions

#### Test /achievements earned

```
/achievements earned
```

Expected: Message indicating no achievements earned yet

### 2. Test Achievement Unlocking

#### Submit a test match

```
!record_game
```

Submit a win or loss in the modal

Expected behavior:

- Match recorded successfully
- Achievement check runs (check logs)
- If conditions met, achievement unlocked
- Announcement posted (if channel configured)

#### Check profile again

```
/profile
```

Expected: Profile updated with any new achievements

### 3. Test Admin Command

#### Manual achievement check (as admin)

```
!checkachievements
```

Expected: Message confirming achievements checked

### 4. Test with Another User

#### View another user's profile

```
/profile @username
```

Expected: That user's profile displayed

---

## Verification Checklist

### Database ✅

- [ ] profiles.db exists
- [ ] profiles table has 14 columns (2 + 12 achievements)
- [ ] Can create new profiles
- [ ] Can query existing profiles

### Commands ✅

- [ ] /profile works
- [ ] /achievements list works
- [ ] /achievements earned works
- [ ] !checkachievements works (admin only)

### Integration ✅

- [ ] Match reports still work normally
- [ ] Elo updates still work
- [ ] LFG system still functional
- [ ] Solo reports still work

### Achievement Logic ✅

- [ ] Achievements check automatically after matches
- [ ] Database updates when earned
- [ ] Announcements post (if configured)
- [ ] No errors in logs

---

## Troubleshooting

### Issue: Bot won't start

**Check:**

- [ ] All imports successful (check for typos)
- [ ] profiles.db created successfully
- [ ] No syntax errors (run py_compile)

**Solution:**

```bash
python -m py_compile utils/achievements.py
python -m py_compile cogs/achievements.py
python init_achievements_db.py
```

### Issue: Commands not appearing

**Check:**

- [ ] AchievementsCog loaded in main.py
- [ ] Bot has proper permissions
- [ ] Slash commands synced successfully

### Issue: Achievements not unlocking

**Check:**

- [ ] Match reports completing successfully
- [ ] Bot instance passed to report functions
- [ ] No errors in bot.log
- [ ] Database has data (match_records.db, elo.db)

**Solution:**

```bash
# Check logs
tail -f bot.log

# Manual check
!checkachievements @user
```

### Issue: Announcements not posting

**Check:**

- [ ] ACHIEVEMENT_CHANNEL_ID set correctly
- [ ] Channel exists
- [ ] Bot has permissions in channel (Send Messages, Embed Links)

**Solution:**

- Verify channel ID in config.py
- Check bot permissions in Discord

---

## Success Criteria

The deployment is successful when:

✅ Bot starts without errors
✅ All slash commands work
✅ Profiles display correctly
✅ Achievements unlock automatically
✅ Announcements post (if configured)
✅ No performance degradation
✅ Users can view their progress
✅ No error spikes in logs

---

## Final Pre-Launch Checklist

- [ ] All files created and modified
- [ ] No syntax errors
- [ ] Database initialized
- [ ] Tests passing (optional)
- [ ] Configuration set (channel ID)
- [ ] Bot starts successfully
- [ ] Commands registered
- [ ] Test match submitted
- [ ] Achievement unlocked
- [ ] Announcement posted
- [ ] No errors in logs
- [ ] Documentation reviewed

---

## 🎉 Ready to Launch!

Once all items are checked:

1. Start the bot: `python main.py`
2. Announce to users: "New achievement system live! Use `/profile` to see your progress!"
3. Monitor for the first few days
4. Enjoy your new achievement system!

**Good luck! 🚀**
