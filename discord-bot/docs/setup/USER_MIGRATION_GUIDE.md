# User Migration Guide: Prefix to Slash Commands

## 🎉 New Feature: Slash Commands!

We've added Discord's modern slash commands to make using the bot easier than ever!

## What's New?

### Before (Prefix Commands)

```
!lfg 30
!rank
!fart
!help
```

You had to remember exact command names and syntax.

### After (Slash Commands)

```
/lfg timeframe:30
/rank
/fart
/help
```

Just type `/` and see all commands with auto-complete!

## Quick Comparison

| Feature            | Prefix (`!`)   | Slash (`/`)               |
| ------------------ | -------------- | ------------------------- |
| **Discovery**      | Must memorize  | Auto-complete shows all   |
| **Help Text**      | Must use !help | Shows inline descriptions |
| **Parameters**     | Positional     | Named with labels         |
| **Typos**          | Command fails  | Harder to make mistakes   |
| **Mobile**         | Typing heavy   | Easier with suggestions   |
| **Learning Curve** | Steep          | Gentle                    |

## Command Translation Guide

### LFG Commands

| Old Command        | New Slash Command       |
| ------------------ | ----------------------- |
| `!lfg 30`          | `/lfg timeframe:30`     |
| `!check_lfg`       | `/check_lfg`            |
| `!cancel`          | `/cancel`               |
| `!challenge @user` | `/challenge user:@user` |
| `!lfg_help`        | `/lfg_help`             |
| `!record_game`     | `/record_game`          |

### Stats Commands

| Old Command    | New Slash Command |
| -------------- | ----------------- |
| `!rank`        | `/rank`           |
| `!leaderboard` | `/leaderboard`    |
| `!mystats`     | `/mystats`        |
| `!mygames`     | `/mygames`        |
| `!replay`      | `/replay`         |

### Tournament Commands

| Old Command                | New Slash Command                                  |
| -------------------------- | -------------------------------------------------- |
| `!create_tournament`       | `/create_tournament`                               |
| `!join Tournament Name`    | `/join_tournament tournament_name:Tournament Name` |
| `!my_round`                | `/my_match`                                        |
| `!bracket Tournament Name` | `/bracket tournament_name:Tournament Name`         |
| `!tournament_help`         | `/tournament_help`                                 |

### Fart Game Commands

| Old Command        | New Slash Command      |
| ------------------ | ---------------------- |
| `!fart`            | `/fart`                |
| `!fartrank`        | `/fartrank`            |
| `!fartrank @user`  | `/fartrank user:@user` |
| `!fartleaderboard` | `/fartleaderboard`     |
| `!attackfart`      | `/attackfart`          |
| `!syphonfart`      | `/syphonfart`          |
| `!syphonstatus`    | `/syphonstatus`        |
| `!fartprediction`  | `/fartprediction`      |
| `!bullfart`        | `/bullfart`            |
| `!fartlord`        | `/fartlord`            |
| `!taxes`           | `/taxes`               |
| `!wealth`          | `/wealth`              |
| `!helpfart`        | `/helpfart`            |

### Shop Commands

| Old Command    | New Slash Command |
| -------------- | ----------------- |
| `!fart_shop`   | `/fart_shop`      |
| `!blue_shell`  | `/blue_shell`     |
| `!red_shell`   | `/red_shell`      |
| `!green_shell` | `/green_shell`    |
| `!banana`      | `/banana`         |
| `!star`        | `/star`           |
| `!mushroom`    | `/mushroom`       |
| `!bobomb`      | `/bobomb`         |

### Utility Commands

| Old Command  | New Slash Command |
| ------------ | ----------------- |
| `!deckcheck` | `/deckcheck`      |
| `!help`      | `/help`           |
| `!commands`  | `/commands`       |

## How to Use Slash Commands

### Step 1: Start with `/`

Type `/` in any channel and pause. Discord will show you a list of all available commands.

### Step 2: Browse or Search

- **Browse**: Scroll through the list to discover commands
- **Search**: Start typing a command name (e.g., `/lf` shows LFG commands)

### Step 3: Select Your Command

Click on the command you want. You'll see:

- Command description
- Required parameters
- Optional parameters with defaults

### Step 4: Fill Parameters

Discord will guide you:

```
/lfg timeframe: [Type a number]
```

You'll see what to enter with clear labels.

### Step 5: Execute

Press Enter and the bot responds!

## Examples

### Example 1: Simple Command

**Old way:**

```
!rank
```

**New way:**

1. Type `/rank`
2. Press Enter
3. Done!

### Example 2: Command with Parameter

**Old way:**

```
!lfg 45
```

Had to remember: parameter is time in minutes.

**New way:**

1. Type `/lfg`
2. See prompt: `timeframe: How many minutes you're available`
3. Type `45`
4. Press Enter

### Example 3: Command with User Mention

**Old way:**

```
!challenge @JohnDoe
```

**New way:**

1. Type `/challenge`
2. See prompt: `opponent: The player you want to challenge`
3. Type `@JohnDoe` or select from list
4. Press Enter

### Example 4: Complex Command

**Old way:**

```
!join Summit Championship
```

**New way:**

1. Type `/join_tournament`
2. See prompt: `tournament_name: Name of the tournament to join`
3. Type `Summit Championship`
4. Press Enter

## Pro Tips

### 💡 Tip 1: Quick Access

Slash commands auto-complete as you type:

- `/lf` → Shows `/lfg`, `/lfg_help`
- `/fart` → Shows all fart commands
- `/help` → Shows help commands

### 💡 Tip 2: Mobile Friendly

On mobile, slash commands are especially useful:

- Large tap targets
- No keyboard switching
- Auto-suggest user mentions

### 💡 Tip 3: Explore New Commands

You might discover commands you didn't know existed! Browse the full list by typing `/`.

### 💡 Tip 4: Optional Parameters

Many commands have optional parameters:

```
/lfg                    → Uses default (30 minutes)
/lfg timeframe:60       → Custom time
```

### 💡 Tip 5: User Selection

When commands need user mentions:

```
/fartrank               → Shows your rank
/fartrank user:@friend  → Shows friend's rank
```

## FAQ

### Q: Do I have to switch to slash commands?

**A:** No! All old `!` commands still work. Use whichever you prefer.

### Q: What if I forget the slash command?

**A:** Type `/` and browse, or use the old `!` command you remember.

### Q: Are slash commands faster?

**A:** They execute at the same speed, but you'll find them faster to use once you're familiar.

### Q: Can I still use !help?

**A:** Yes! Both `!help` and `/help` work identically.

### Q: What if slash commands break?

**A:** All functionality still works with `!` commands as a backup.

### Q: How do I know which to use?

**A:** We recommend:

- **New users**: Start with `/` commands (easier to learn)
- **Power users**: Use whichever is faster for you
- **Both work perfectly!**

## Benefits You'll Love

### ✅ No More Typos

Discord validates commands before sending. If you mistype, it won't let you submit.

### ✅ Better Discovery

Find commands you didn't know existed by browsing the `/` menu.

### ✅ Clear Parameters

No more guessing "was it `!lfg 30` or `!lfg time:30`?" - Discord shows you exactly what's needed.

### ✅ Mobile Optimized

Much easier to use on phone/tablet with auto-complete.

### ✅ Accessible

Screen readers work better with slash commands.

## Still Have Questions?

Use `/help` or `!help` to see the full help menu, or ask in the support channel!

## Feedback Welcome!

Let us know:

- Which commands you use most
- Any suggestions for improvements
- Commands that would be helpful to add

We're constantly improving the bot based on your feedback!

---

**Remember**: Both command styles work! This is about making the bot easier to use, not forcing you to change. Pick whatever works best for you! 🎮
