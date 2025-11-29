# Achievement System - Command Reference

## User Commands

### View Your Profile

```
/profile
```

Shows your achievement progress, completion percentage, and all achievements (earned and unearned).

**Example Output:**

```
🎮 YourUsername's Profile
Discord ID: @YourUsername
Achievements: 5/11

Progress: ████░░░░░░ 33.3%

📊 Victory & Participation
✅ 🎯 First Streak
✅ 🏆 Rising Champion
❌ 👑 Tournament Victor
...
```

### View Another User's Profile

```
/profile @username
```

Check out another player's achievement progress.

### List All Achievements

```
/achievements list
```

Displays all available achievements with descriptions and how to earn them.

**Example Output:**

```
🏆 All Available Achievements

📊 Victory & Participation
🎯 First Streak
Win 5 recorded games.

🏆 Rising Champion
Win 10 recorded games.
...
```

### View Your Earned Achievements

```
/achievements earned
```

Shows only the achievements you've completed.

### View Another User's Earned Achievements

```
/achievements earned @username
```

See what achievements another player has unlocked.

---

## Admin Commands

### Manual Achievement Check

```
!checkachievements
```

Triggers an immediate achievement check for yourself.

**Requires:** Administrator permission

```
!checkachievements @username
```

Checks achievements for another user.

**Use Cases:**

- Testing new achievements
- Retroactively awarding achievements
- Fixing stuck achievements
- Verifying achievement logic

---

## How Achievements Work

### Automatic Tracking

- Achievements are checked automatically after every match report
- When you earn an achievement, it's announced in the designated channel
- Your profile is updated instantly

### Categories

#### 📊 Victory & Participation

Track your competitive success and dedication.

#### ⚡ Elo Milestones

Recognize climbing the rankings.

#### 🎭 Avatar Collection

Reward exploring different avatars.

#### 🌟 Special Achievements

Advanced challenges for dedicated players.

### Earning Achievements

- Play matches using `!lfg` or `/record_game`
- Submit match reports
- Achievements unlock automatically when you meet the criteria
- Some achievements require minimum games played

---

## Tips

1. **Use `/profile` regularly** to track your progress
2. **Check `/achievements list`** to see what you can work towards
3. **Play with different avatars** to unlock avatar achievements
4. **Focus on win rate** for special achievements
5. **Be patient** - some achievements require many games

---

## Frequently Asked Questions

### Q: I think I earned an achievement but didn't get it?

A: Ask an admin to run `!checkachievements @you`. Sometimes the check might be delayed.

### Q: Can I see achievement progress?

A: Use `/profile` to see which achievements you've earned and which are still locked.

### Q: Do old matches count towards achievements?

A: Yes! When you earn an achievement, the system checks your entire match history.

### Q: What happens when I earn an achievement?

A: You'll see an announcement in the achievement channel, and your profile will be updated immediately.

### Q: Can achievements be lost?

A: No! Once earned, achievements are permanent.

### Q: Do solo match reports count?

A: Yes! Both regular matches and solo reports count towards achievements.

---

## Examples

### Checking Your Progress

```
/profile
```

→ Shows 5/12 achievements (41.7% complete)

### Seeing What's Available

```
/achievements list
```

→ Lists all 12 achievements with descriptions

### Comparing with Friends

```
/profile @friend
```

→ See what achievements they've earned

### Admin Testing

```
!checkachievements @testuser
```

→ Manually triggers achievement evaluation

---

## Integration with Other Features

### Match Reports

- Every match report triggers achievement checks
- Works with LFG matches, challenges, and solo reports

### Elo System

- Elo-based achievements update when your rating changes
- Tracked across all ranked matches

### Avatar System

- Playing with different avatars unlocks collection achievements
- Deck data from Curiosa links is analyzed

---

## For Developers

Want to add custom achievements? See:

- `ACHIEVEMENT_SYSTEM.md` - Full technical documentation
- `ACHIEVEMENT_QUICKSTART.md` - Quick reference guide
- `utils/achievements.py` - Achievement implementation

Adding a new achievement takes just 3 steps!

---

## Support

Having issues with achievements?

1. Check bot logs
2. Ask an admin to run `!checkachievements`
3. Report bugs to the development team
4. Check `ACHIEVEMENT_SYSTEM.md` for troubleshooting

---

**Ready to start earning achievements? Submit your first match report and see your profile grow!** 🎯
