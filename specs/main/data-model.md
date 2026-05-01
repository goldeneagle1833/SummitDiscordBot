# Data Model: Flask/Jinja2 → React SPA Migration

## Overview

No backend schema changes. All data models here represent **frontend state shapes** — the JSON structures the React app receives from Flask API responses and stores in component state or React Context.

---

## Core Entities

### User (AuthContext)

Returned by `GET /api/me`. Stored globally in `AuthContext`.

```js
// null = not yet loaded, false = unauthenticated, object = authenticated
{
  user_id: string,       // Discord ID or "google_<id>"
  username: string,      // Display name
  avatar: string | null, // Avatar URL (Discord CDN or Google picture)
  auth_provider: 'discord' | 'google',
  is_admin: boolean      // True if user_id is in ADMINS list
}
```

**State transitions**: `null` → (fetch /api/me) → `false` | `User object`

---

### LeaderboardEntry

Returned by `GET /api/leaderboard` as an array.

```js
{
  rank: number,
  player_id: string,
  display_name: string,
  elo: number,
  wins: number,
  losses: number,
  win_rate: number,        // 0.0–1.0
  avatar_url: string | null
}
```

---

### PlayerProfile

Returned by `GET /api/players/:id`.

```js
{
  player_id: string,
  display_name: string,
  elo: number,
  wins: number,
  losses: number,
  win_rate: number,
  rank: number | null,
  avatar_url: string | null,
  recent_matches: Match[],
  avatar_stats: AvatarStat[]
}
```

---

### Match

Returned by `GET /api/match-history` (array) and embedded in `PlayerProfile.recent_matches`.

```js
{
  match_id: number,
  winner_id: string,
  winner_name: string,
  loser_id: string,
  loser_name: string,
  winner_elo_change: number,
  loser_elo_change: number,
  winner_avatar: string | null,
  loser_avatar: string | null,
  match_time: string | null,   // ISO timestamp
  match_type: 'ranked' | 'unranked',
  event: string | null
}
```

---

### Event

Returned by the events listing (via `GET /api/games` or `pages.py` event data, adapted to `/api/events`).

```js
{
  folder: string,        // Event folder name (used as route param)
  display_name: string,
  star_rating: 1 | 2 | 3,
  date: string | null,
  top8: Deck[],
  all_decks: Deck[]
}
```

---

### Deck

Embedded in `Event.top8` and `Event.all_decks`.

```js
{
  player_name: string,
  placement: number | null,
  curiosa_url: string | null,
  deck_data: DeckData | null
}
```

---

### DeckData

Returned by `GET /api/cards/:id` (Curiosa API proxy).

```js
{
  avatar: {
    name: string,
    element: string,
    image_url: string
  },
  cards: CardEntry[]
}

// CardEntry
{
  name: string,
  quantity: number,
  element: string,
  image_url: string | null,
  type: string
}
```

---

### AvatarStat

Embedded in `PlayerProfile.avatar_stats`.

```js
{
  avatar_name: string,
  wins: number,
  losses: number,
  win_rate: number,
  image_url: string | null
}
```

---

### CurioEntry

Returned by `GET /api/curios` (existing endpoint).

```js
{
  id: number,
  player_name: string,
  curio_name: string,
  set_name: string,
  image_url: string | null,
  submitted_at: string
}
```

---

### CommunityLink

Returned by repositories data (community servers + websites).

```js
// Discord server
{
  type: 'discord',
  name: string,
  invite_url: string,
  member_count: number | null,
  description: string | null
}

// Website
{
  type: 'website',
  name: string,
  url: string,
  description: string | null
}
```

---

## Frontend State Architecture

### Global State (React Context)

| Context | State | Provider location |
|---------|-------|-------------------|
| `AuthContext` | `{ user, loading }` where `user` is `null | false | User` | `App.jsx` wraps all routes |

### Page-Level State (useState / route loader)

Each page component manages its own fetch state locally:

```js
// Pattern for all data pages
const [data, setData] = useState(null)
const [loading, setLoading] = useState(true)
const [error, setError] = useState(null)
```

Pages with multiple independent data sources use `Promise.all` in the api layer:

```js
// Example: Player page needs profile + matches simultaneously
const [profile, matches] = await Promise.all([
  api.players.getProfile(playerId),
  api.players.getMatches(playerId)
])
```

### No Global Store

React Context is sufficient for auth state. No Redux, Zustand, or other state management library. All other state is local to pages/components.

---

## Validation Rules

All validation happens on the Flask backend (unchanged). The React app treats all API responses as trusted — no client-side schema validation required.

**Error handling pattern** (in `api/client.js`):
- HTTP 401 → redirect to `/login`
- HTTP 4xx → throw `ApiError` with `status` and `message`
- HTTP 5xx → throw `ApiError` with generic message
- Network failure → throw `NetworkError`

---

## State Transitions: Auth Flow

```
App loads
  └─> AuthContext calls GET /api/me
        ├─> 200 OK  → user = { user_id, username, avatar, auth_provider }
        └─> 401     → user = false

User clicks "Login with Discord"
  └─> Navigate to /discord (proxied → Flask OAuth redirect)
        └─> Discord OAuth completes
              └─> Flask callback sets session cookie
                    └─> redirect(FRONTEND_URL) → React app loads
                          └─> AuthContext calls GET /api/me → 200 OK → user hydrated

User clicks "Logout"
  └─> Call GET /logout (proxied → Flask clears session)
        └─> AuthContext sets user = false
              └─> Navigate to /
```
