# Discord OAuth Login Implementation Plan

## Overview

Allow players to log in with Discord to edit their player page and add avatars they used for match reports.

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

- `requests` (for Discord API calls)
- `Flask-Login` (session management)

### 2.2 New Routes in `web-app/app.py`

| Route                      | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `/auth/discord`            | Redirects user to Discord OAuth            |
| `/auth/discord/callback`   | Handles Discord response, creates session  |
| `/auth/logout`             | Clears session                             |
| `/api/player/<id>/avatars` | POST - Add avatar to match (requires auth) |

### 2.3 Database Changes

New table `user_sessions` or use existing player data:

```sql
-- Option A: Link Discord to existing ELO players
ALTER TABLE players ADD COLUMN discord_id TEXT UNIQUE;

-- Option B: New table for avatar selections
CREATE TABLE match_avatars (
    id INTEGER PRIMARY KEY,
    match_id INTEGER,
    player_discord_id TEXT,
    avatar_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

- Show "Edit" button only if logged-in user matches page owner
- Add avatar selector dropdown for each match
- Save button to submit avatar choices

### 3.3 New Components

- Avatar selector modal/dropdown
- Success/error toast notifications

---

## Phase 4: Security Considerations

1. **CSRF Protection** - Use Flask-WTF for form protection
2. **Session Security** - Secure cookies, HTTP-only flags
3. **Rate Limiting** - Prevent abuse of avatar updates
4. **Validation** - Only allow valid avatar names from a whitelist
5. **Authorization** - Users can only edit their own player page

---

## File Changes Summary

| File                                       | Changes                                        |
| ------------------------------------------ | ---------------------------------------------- |
| `web-app/app.py`                           | Add OAuth routes, session handling, avatar API |
| `web-app/requirements.txt`                 | Add Flask-Login, requests                      |
| `web-app/templates/components/navbar.html` | Add login/logout button                        |
| `web-app/templates/pages/player.html`      | Add edit mode, avatar selector                 |
| `web-app/static/js/player.js`              | Handle avatar selection, API calls             |
| `web-app/static/css/components/`           | New styles for login button, avatar selector   |
| `.env`                                     | Discord credentials                            |

---

## Implementation Order

1. **Set up Discord app** and get credentials
2. **Add OAuth routes** to app.py
3. **Add session management** with Flask-Login
4. **Update navbar** with login/logout
5. **Create avatar API endpoint**
6. **Update player page** with edit functionality
7. **Test end-to-end**

---

## Estimated Effort

- Phase 1: 30 minutes (Discord setup)
- Phase 2: 2-3 hours (backend)
- Phase 3: 2-3 hours (frontend)
- Phase 4: 1 hour (security hardening)

**Total: ~6-7 hours**
