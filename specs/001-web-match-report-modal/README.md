# Web-Based Match Reporting Modal - Setup Instructions

## Overview
This feature implements a web-based match reporting system with opponent confirmation flow.

## Database Migration Required

The system uses the `match_confirmations` table in `match_records.db`. This table needs to be created before the feature can function.

### Step 1: Create the Table

Run the `create_table.sql` script against your `match_records.db` database:

```bash
# On your cloud server where the database exists
cd /path/to/SummitDiscordBot/discord-bot/

# Run the migration
sqlite3 match_records.db < /path/to/specs/001-web-match-report-modal/create_table.sql
```

**Verify the table was created:**
```bash
sqlite3 match_records.db "PRAGMA table_info(match_confirmations);"
```

Expected output should show columns:
- id, submitter_discord_id, opponent_discord_id, winner_discord_id, loser_discord_id
- winner_deck_url, loser_deck_url, went_first, final_life_winner, final_life_loser
- status, created_at, expires_at, reminder_sent_at, confirmed_at, dispute_reason

### Step 2 (Optional): Run Additional Migrations

The `migration.sql` file contains additional indexes and optimizations. If you've made changes to the table schema in the past, you can apply these enhancements:

```bash
sqlite3 match_records.db < /path/to/specs/001-web-match-report-modal/migration.sql
```

## Known Issues & Fixes

### Issue 1: Google OAuth User Search (FIXED ✅)
**Error**: `ValueError: invalid literal for int() with base 10: 'google_113075264611538227218'`

**Status**: Fixed in `web-app/services/match_confirmation.py`

**Solution**: The `search_opponents()` method now gracefully handles non-numeric user IDs from Google OAuth by skipping the recent opponents lookup and relying on display name search only.

### Issue 2: Missing Database Table (REQUIRES ACTION ⚠️)
**Error**: `sqlite3.OperationalError: no such table: match_confirmations`

**Status**: Requires manual migration (see Step 1 above)

**Solution**: Run `create_table.sql` on your cloud server to create the table.

## Multi-Provider Authentication Note

The web app supports both Discord OAuth and Google OAuth for authentication. However, the match reporting system is designed for Discord users (since matches happen via Discord).

**Current Limitation**: Google OAuth users can browse the site and view leaderboards, but match reporting features expect Discord user IDs. If you need Google OAuth users to report matches, you'll need to:

1. Add a Discord ID mapping in the `user_profiles` table
2. Update `create_match_report()` to look up Discord IDs from the session user_id
3. Modify the ID conversion logic to handle both numeric and string IDs throughout the stack

For now, match reporting should work for Discord-authenticated users.

## Testing Checklist

After running the migration, verify the feature works:

- [ ] Discord user can log in via web app
- [ ] Match report modal opens and loads properly
- [ ] Opponent search returns results (no `ValueError`)
- [ ] Match report can be submitted
- [ ] Pending confirmations appear on opponent's page
- [ ] Opponent can confirm/deny reports
- [ ] Background jobs send reminders (24hr)
- [ ] Background jobs expire reports (48hr)

## Files Modified

### Backend
- `web-app/services/match_confirmation.py` - Fixed search_opponents() for multi-provider auth
- `web-app/routes/api/match_reporting.py` - Updated endpoints for deck URL handling

### Frontend
- `web-app/templates/pages/life_counter.html` - Moved opponent deck URL to confirmation modal
- `web-app/static/js/pages/life_counter.js` - Updated form validation and submission

### Database
- `specs/001-web-match-report-modal/create_table.sql` - NEW: Initial table creation
- `specs/001-web-match-report-modal/migration.sql` - Existing: Additional indexes
- `specs/001-web-match-report-modal/data-model.md` - Schema documentation

## Support

If you encounter issues, check:
1. Database file path is correct (`discord-bot/match_records.db`)
2. Web app has read/write permissions on the database file
3. SQLite version supports partial indexes (`WHERE` clauses in `CREATE INDEX`)
4. The table was created successfully (verify with `PRAGMA table_info`)
