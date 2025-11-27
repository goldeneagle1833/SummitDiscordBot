# Testing Slash Commands

## Quick Start

After restarting your bot, slash commands will be automatically synced with Discord. Here's how to test them:

## Step 1: Restart the Bot

```bash
# From the discord-bot directory
python main.py
```

Look for this message in the console:

```
Synced X slash commands
```

## Step 2: Wait for Sync (First Time Only)

- **In your test server**: Commands appear almost instantly
- **Globally**: Can take up to 1 hour for Discord to propagate
- **Tip**: Test in a private server first for instant results

## Step 3: Test Commands

### Option 1: Browse All Commands

1. Type `/` in any channel
2. Scroll through the list
3. Click any command to see its description and parameters

### Option 2: Use Specific Command

1. Type `/lfg` and press space
2. See the `timeframe` parameter with its description
3. Enter a value (or use default)
4. Press Enter

### Option 3: Quick Test Commands

```
/help          - Should show help embed
/rank          - Check your Elo (or show "no rating" message)
/fart          - Fart game (most interactive)
/leaderboard   - View rankings
/lfg           - Test LFG system
```

## Common Test Scenarios

### Test LFG Flow

1. User A: `/lfg timeframe:30`
2. User B: `/lfg timeframe:30`
3. Both should be matched
4. Test buttons (Accept/Decline/Win/Loss)

### Test Stats

1. `/rank` - Check initial state
2. Play some games
3. `/rank` - Verify Elo updated
4. `/mystats` - Check detailed stats
5. `/leaderboard` - See rankings

### Test Fart Game

1. `/fart` - Release a fart
2. `/fartrank` - Check your rank
3. `/wealth` - Check points
4. `/fart_shop` - Browse shop
5. `/fartleaderboard` - View leaders

### Test Help System

1. `/help` - General help
2. `/commands` - Command list
3. `/lfg_help` - LFG-specific help
4. `/helpfart` - Fart game help
5. `/tournament_help` - Tournament help

## Verification Checklist

- [ ] Bot starts without errors
- [ ] Console shows "Synced X slash commands"
- [ ] Typing `/` shows command list
- [ ] Command descriptions are visible
- [ ] Parameters show correct labels
- [ ] Commands execute successfully
- [ ] Responses appear correctly
- [ ] Buttons/interactions still work
- [ ] Old `!` commands still work

## Debugging

### Commands Not Showing?

```python
# Check bot logs for:
# "Failed to sync slash commands: <error>"
```

### Check Bot Permissions

The bot needs:

- `applications.commands` scope
- `Send Messages` permission
- `Embed Links` permission
- `Use External Emojis` permission

### Force Re-sync (if needed)

```python
# In main.py on_ready(), temporarily add:
await bot.tree.sync()  # Already included
```

### Test Individual Cog

```python
# If a specific command fails, check if cog is loaded:
cog = bot.get_cog("LFGCog")
print(f"LFG Cog loaded: {cog is not None}")
```

## Expected Behavior

### Slash Command

```
User: /lfg timeframe:30
Bot: [Shows thinking indicator]
Bot: ✅ You've joined the LFG queue! Available for 30 minutes.
```

### Prefix Command (Still Works!)

```
User: !lfg 30
Bot: ✅ You've joined the LFG queue! Available for 30 minutes.
```

Both produce identical results!

## Performance Notes

- Slash commands may take slightly longer to respond (Discord's defer mechanism)
- All commands use `.defer()` to prevent timeout errors
- This shows a "Bot is thinking..." indicator to users
- Actual command execution is unchanged

## Troubleshooting Common Issues

### Issue: "This interaction failed"

**Cause**: Command took too long to respond
**Solution**: Already using `.defer()` - check for slow database/API calls

### Issue: Commands appear but do nothing

**Cause**: Cog not loaded or error in command logic
**Solution**: Check logs for errors, verify cog initialization

### Issue: Some commands work, others don't

**Cause**: Specific cog or dependency issue
**Solution**: Test the corresponding `!` command to isolate the issue

### Issue: Parameters not working correctly

**Cause**: Type mismatch between slash and prefix versions
**Solution**: Verify parameter types match in both implementations

## Next Steps

After testing:

1. Announce slash commands to your users
2. Update server welcome message
3. Create command documentation channel
4. Monitor bot logs for errors
5. Gather user feedback on UX improvements

## Additional Resources

- Discord.py documentation: https://discordpy.readthedocs.io/
- Application Commands guide: https://discordpy.readthedocs.io/en/stable/interactions/api.html
- Bot logs: Check `bot.log` file for detailed information
