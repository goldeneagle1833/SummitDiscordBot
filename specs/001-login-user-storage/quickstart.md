# Quickstart: Login User Storage

**Feature Branch**: `001-login-user-storage`
**Date**: 2026-03-07

## Overview

This feature adds a `user_profiles` table to the match records database and populates it automatically whenever a user logs in via Discord OAuth on the web application.

## Files to Create

1. **`web-app/repositories/user_profiles.py`** - New repository class for user profile storage
   - `UserProfileRepository` class following existing repository pattern
   - `_ensure_table()` for auto-creating the table on first use
   - `upsert_profile()` for creating or updating a user profile on login
   - Connects to `match_records.db` via `MATCH_RECORDS_DB_PATH`

## Files to Modify

1. **`web-app/routes/auth.py`** - Hook profile storage into Discord OAuth callback
   - Import `UserProfileRepository`
   - After session variables are set (line 84), call `upsert_profile()` with user data
   - Wrap in try/except so login is never disrupted by a storage failure

## How It Works

1. User clicks "Login with Discord" on the web app
2. Discord OAuth flow completes, callback receives user data
3. Session is populated with `user_id`, `username`, `avatar` (existing behavior)
4. **NEW**: `UserProfileRepository.upsert_profile()` is called with the same data
5. The repository performs an `INSERT ... ON CONFLICT ... DO UPDATE` to either:
   - Create a new record (first-time user) with both timestamps set to now
   - Update existing record (returning user) with fresh `display_name`, `avatar`, `last_login_at`
6. If the DB write fails, the error is logged and the user's login continues normally
7. User is redirected to the home page (existing behavior)

## Testing

Run tests from the `web-app/` directory:
```bash
pytest tests/ -v
```

Key scenarios to test:
- First-time login creates a new record
- Returning login updates existing record (no duplicates)
- Missing avatar field is stored as NULL
- Database failure does not break the login flow
- Table is auto-created on first repository instantiation
