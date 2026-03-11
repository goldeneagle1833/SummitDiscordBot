# Web Match Reports Migration

## Problem
Google OAuth user IDs are too large to fit in SQLite's 64-bit INTEGER type. Previously, the system was stripping the "google_" prefix and attempting to store the numeric part, which caused overflow errors.

## Solution
Created a new table `match_reports_web` with TEXT columns for all user IDs to properly store Google OAuth IDs with the "google_" prefix intact.

## Changes Made

### 1. New Database Table
- **Table**: `match_reports_web` in `match_records.db`
- **Schema**: Identical to `match_records` but uses TEXT for all ID columns
- **Source**: Web-based match reports only (marked with `source = 'Web'`)

### 2. Service Updates

#### `services/match_confirmation.py`
- **Removed**: `_normalize_user_id()` calls that stripped "google_" prefix
- **Updated**: `create_match_report()` to keep user IDs as-is (with google_ prefix)
- **Updated**: `confirm_match_report()` to:
  - Compare user IDs directly without normalization
  - Insert into `match_reports_web` instead of `match_records`
  - Use UUID-based match IDs (format: `web_xxxxxxxxxxxx`)
  - Keep google_ prefix in all match data

#### `services/paper_elo.py`
- **Updated**: `to_sqlite_id()` function to:
  - Strip "google_" prefix for ELO storage only
  - Convert to integer for `overall_standings` table (INTEGER PRIMARY KEY)
  - Keep prefix in match_reports_web records

## Data Flow

### Web-Based Match Report
```
User submits match report (google_123456789012345678901)
  ↓
MatchConfirmationService.create_match_report()
  - Stores in match_confirmations with google_ prefix intact
  ↓
Opponent confirms
  ↓
MatchConfirmationService.confirm_match_report()
  - Updates ELO (strips google_ for overall_standings INTEGER keys)
  - Inserts into match_reports_web (keeps google_ prefix)
  - Match ID format: web_abc123def456
```

### Discord Bot Match Report (unchanged)
```
Bot reports match (numeric Discord ID)
  ↓
discord-bot saves directly to match_records
  - Match ID: auto-increment rowid
  - All IDs stored as INTEGER
```

## Migration Instructions

### 1. Run Migration Script
```bash
cd web-app
python migrations/create_match_reports_web.py
```

This will:
- Create `match_reports_web` table if it doesn't exist
- Add appropriate indexes
- Skip if table already exists (safe to run multiple times)

### 2. Verify Table Creation
```bash
sqlite3 ../discord-bot/match_records.db

sqlite> .schema match_reports_web
-- Should show the table schema

sqlite> SELECT COUNT(*) FROM match_reports_web;
-- Should return 0 (new table)
```

### 3. Deploy Code Changes
Deploy the updated web app with the new service files.

## Database Schema Comparison

### match_records (Discord Bot - existing)
- **match_id**: INTEGER PRIMARY KEY (auto-increment rowid)
- **user_id fields**: INTEGER (fits Discord IDs)
- **source**: TEXT DEFAULT 'Discord'

### match_reports_web (Web App - new)
- **match_id**: TEXT PRIMARY KEY (UUID: `web_xxxxxxxxxxxx`)
- **user_id fields**: TEXT (supports google_ prefix)
- **source**: TEXT DEFAULT 'Web'

## Querying Both Tables

To get all matches for a user (across both bot and web):

```sql
-- Discord user (numeric ID)
SELECT * FROM match_records WHERE winner_id = 123456789 OR losser_id = 123456789
UNION ALL
SELECT * FROM match_reports_web WHERE winner_id = '123456789' OR losser_id = '123456789';

-- Google user (with google_ prefix)
SELECT * FROM match_reports_web
WHERE winner_id = 'google_123456789012345678901'
   OR losser_id = 'google_123456789012345678901';
```

## Rollback

If you need to rollback:

```bash
sqlite3 ../discord-bot/match_records.db

sqlite> DROP TABLE IF EXISTS match_reports_web;
```

Then revert the code changes.

## Testing

After deployment, test with:
1. Google OAuth user submits match report
2. Opponent (Google or Discord) confirms
3. Verify match appears in match_reports_web with google_ prefix intact
4. Verify ELO updates correctly in overall_standings
5. Check web UI displays matches correctly

## Notes

- Discord bot continues using `match_records` (unchanged)
- Web app uses `match_reports_web` for all new reports
- ELO system works with both (strips google_ for storage in overall_standings)
- Both tables can coexist and be queried separately or together
