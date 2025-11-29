# Slash Commands Guide

## What are Slash Commands?

Slash commands provide a modern, user-friendly way to interact with the Discord bot. Instead of typing `!command`, you can type `/command` and Discord will show you:

- **Auto-complete** suggestions as you type
- **Command descriptions** to help you understand what each command does
- **Parameter hints** showing what information is required
- **Better discoverability** - just type `/` to see all available commands!

## Benefits Over Prefix Commands

1. **Auto-complete**: Type `/` and see all available commands with descriptions
2. **No memorization needed**: Descriptions appear as you browse commands
3. **Parameter guidance**: Clear labels for required/optional parameters
4. **Type safety**: Discord validates input types automatically
5. **Modern UX**: Native Discord feature with clean interface

## Available Slash Commands

### 🎮 LFG Commands

- `/lfg [timeframe]` - Find a game! Join the LFG queue
- `/check_lfg` - Check who's currently in the LFG queue
- `/cancel` - Cancel your LFG request
- `/challenge @user` - Challenge a specific player to a match
- `/record_game` - Manually record a game that was played

### 📊 Elo & Stats Commands

- `/rank` - Check your current Elo rating and rank
- `/leaderboard` - View the top 10 Elo rankings
- `/mystats` - View your detailed match statistics
- `/mygames` - View your recent game history
- `/replay` - Submit a replay of your game

### 🏆 Tournament Commands

- `/create_tournament` - Create a new tournament (Admin)
- `/join_tournament [tournament_name]` - Join a tournament
- `/my_match` - Check your current tournament match
- `/bracket [tournament_name]` - View tournament bracket
- `/tournament_help` - Learn about tournament features

### ⚙️ Utility Commands

- `/deckcheck` - Check if your deck is legal for tournaments
- `/help` - Get help with bot commands and features
- `/commands` - View all available bot commands
- `/lfg_help` - Learn how to use the LFG system

## Backward Compatibility

**All prefix commands (`!command`) still work!** The bot supports both:

- Old style: `!lfg 30`
- New style: `/lfg timeframe:30`

This ensures existing users can continue using familiar commands while new users benefit from the improved slash command experience.

## How to Use Slash Commands

1. Type `/` in any Discord channel where the bot is active
2. Browse through the auto-complete menu or start typing a command name
3. Select your command from the list
4. Fill in any required parameters (Discord will guide you)
5. Press Enter to execute!

## Technical Implementation

The slash commands are implemented in `cogs/slash_commands.py` and use Discord's Application Commands API (`app_commands`). Each slash command:

- Creates a proper context object
- Defers the response to prevent timeout
- Calls the existing command function from the appropriate cog
- Provides graceful error handling if a cog is unavailable

This architecture ensures code reuse and maintains a single source of truth for command logic.

## Syncing Commands

When the bot starts, it automatically syncs all slash commands with Discord. This process:

- Registers all commands with Discord's API
- Updates command descriptions and parameters
- Typically takes a few minutes to propagate globally
- Is logged in the bot output for verification

## Troubleshooting

**Commands not showing up?**

- Wait a few minutes after bot restart (global sync can take time)
- Check bot logs for sync errors
- Ensure the bot has proper permissions in your server

**Commands show but don't work?**

- Check bot logs for error messages
- Verify the corresponding cog is loaded
- Ensure database connections are working

**Want to use old commands?**

- All `!` prefix commands still work exactly as before
- No functionality is removed, only enhanced!
