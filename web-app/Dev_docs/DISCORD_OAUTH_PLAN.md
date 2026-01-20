# Discord OAuth Login Implementation Plan

## Overview

Allow players to log in with Discord to edit their player page and add avatars they used for match reports.

---

## Current Status (Updated 2026-01-20)

| Item                                 | Status  | Notes                                          |
| ------------------------------------ | ------- | ---------------------------------------------- |
| `is_owner` logic scaffolded          | ✅ Done | Hardcoded to `False` in `app.py:987`           |
| Player page conditional deck display | ✅ Done | Already hides deck URLs when not owner         |
| Avatar stats privacy                 | ❌ TODO | Need to hide avatar performance unless owner   |
| OAuth routes                         | ❌ TODO | No `/auth/discord*` routes exist               |
| Requirements                         | ❌ TODO | Missing `requests`, `Flask-Login`, `Flask-WTF` |
| Session/SECRET_KEY                   | ❌ TODO | No session config in app.py                    |
| `.env` file                          | ❌ TODO | Does not exist                                 |
| Navbar login UI                      | ❌ TODO | No login/logout buttons                        |
| Avatar API endpoint                  | ❌ TODO | `/api/player/<id>/avatars` missing             |
| `player.js`                          | ❌ TODO | No dedicated JS for avatar selection           |

---

## Phase 1: Discord OAuth Setup

### 1.1 Discord Developer Portal

- Create application at https://discord.com/developers/applications
- Set up OAuth2 redirect URI: `https://yoursite.com/auth/discord/callback`
- Get **Client ID** and **Client Secret**
- Required scopes: `identify` (gets user ID, username, avatar)

### 1.2 Environment Variables

```
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=https://yoursite.com/auth/discord/callback
SECRET_KEY=random_secret_for_sessions
```

---

## Phase 2: Backend Implementation

### 2.1 New Dependencies

Add to `web-app/requirements.txt`:

```
requests>=2.31.0
Flask-Login>=0.6.3
Flask-WTF>=1.2.0
python-dotenv>=1.0.0
```

- `requests` - Discord API calls
- `Flask-Login` - Session management
- `Flask-WTF` - CSRF protection
- `python-dotenv` - Environment variable loading

### 2.2 New Routes in `web-app/app.py`

| Route                      | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `/auth/discord`            | Redirects user to Discord OAuth            |
| `/auth/discord/callback`   | Handles Discord response, creates session  |
| `/auth/logout`             | Clears session                             |
| `/api/player/<id>/avatars` | POST - Add avatar to match (requires auth) |

### 2.3 App Configuration

Add to `web-app/app.py` after creating Flask app:

```python
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
```

### 2.4 Database Changes

**Important:** The existing `overall_standings` table in `elo.db` already uses Discord user IDs as `user_id`. No migration needed for linking - just match the logged-in Discord ID to `user_id`.

```sql
-- elo.db - Existing schema (no changes needed)
-- user_id is already the Discord ID!
CREATE TABLE overall_standings (
    user_id INTEGER PRIMARY KEY,  -- This IS the Discord user ID
    user_display_name TEXT,
    elo INTEGER DEFAULT 1500
);

-- match_records.db - New table for avatar selections
CREATE TABLE IF NOT EXISTS match_avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    player_discord_id INTEGER NOT NULL,
    avatar_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES match_records(match_id)
);
```

---

## Phase 3: Frontend Implementation

### 3.1 Login Button

Add to navbar when not logged in:

```html
<a href="/auth/discord" class="nav-link">Login with Discord</a>
```

When logged in, show:

```html
<span>Welcome, {{ user.username }}</span> <a href="/auth/logout">Logout</a>
```

### 3.2 Player Page Enhancements

On `web-app/templates/pages/player.html`:

- **Hide avatar performance stats** unless `is_owner` is true (privacy)
- **Hide "Performance Against Other Avatars"** section unless `is_owner` is true (privacy)
- **Hide recent decks** section unless `is_owner` is true (already implemented)
- Show "Edit" button only if logged-in user matches page owner
- Add avatar selector dropdown for each match in match history
- Save button to submit avatar choices

### 3.3 New Components

- Avatar selector modal/dropdown
- Success/error toast notifications

---

## Phase 4: Security & Privacy Considerations

1. **CSRF Protection** - Use Flask-WTF for form protection
2. **Session Security** - Secure cookies, HTTP-only flags
3. **Rate Limiting** - Prevent abuse of avatar updates
4. **Validation** - Only allow valid avatar names from a whitelist
5. **Authorization** - Users can only edit their own player page
6. **Privacy Protection** - Hide sensitive data unless `is_owner` is true:
   - Avatar performance statistics (which avatars they play)
   - Performance against other avatars (matchup data)
   - Recent decks list
   - Deck URLs in match history

---

## File Changes Summary

| File                                       | Changes                                                          | Status |
| ------------------------------------------ | ---------------------------------------------------------------- | ------ |
| `web-app/app.py`                           | Add OAuth routes, session handling, avatar API, `is_owner` logic | ❌     |
| `web-app/requirements.txt`                 | Add Flask-Login, requests, Flask-WTF, python-dotenv              | ❌     |
| `web-app/templates/components/navbar.html` | Add login/logout button                                          | ❌     |
| `web-app/templates/pages/player.html`      | Add edit mode, avatar selector (partially ready)                 | 🟡     |
| `web-app/static/js/player.js`              | Handle avatar selection, API calls                               | ❌     |
| `web-app/static/css/components/`           | New styles for login button, avatar selector                     | ❌     |
| `web-app/.env`                             | Discord credentials                                              | ❌     |
| `discord-bot/utils/database.py`            | Add `match_avatars` table creation                               | ❌     |

---

## Implementation Order

1. **Set up Discord app** and get credentials
2. **Create `.env` file** with credentials
3. **Update `requirements.txt`** and install dependencies
4. **Add session configuration** to app.py (SECRET_KEY, dotenv)
5. **Add OAuth routes** to app.py (`/auth/discord`, callback, logout)
6. **Add Flask-Login** user loader and session management
7. **Update `is_owner` logic** in `/api/player/<id>` route (line ~987)
8. **Update API response** to exclude avatar stats when `is_owner` is false
9. **Update navbar** with login/logout buttons
10. **Create avatar API endpoint** (`/api/player/<id>/avatars`)
11. **Create `match_avatars` table** in database.py
12. **Add `player.js`** for avatar selection UI
13. **Update player page** with edit functionality and privacy controls
14. **Test end-to-end** including privacy restrictions

---

## Estimated Effort

- Phase 1: 30 minutes (Discord setup)
- Phase 2: 2-3 hours (backend)
- Phase 3: 2-3 hours (frontend)
- Phase 4: 1 hour (security hardening)

**Total: ~6-7 hours**
