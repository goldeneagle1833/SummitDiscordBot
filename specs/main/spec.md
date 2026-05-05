# Feature Specification: Explorer Standings

## Overview

A new web page called **Explorer Standings** that tracks cumulative season standings across multiple in-person Explorer Series tournament events sourced from the carde.io platform. Authorized admins can add seasons and import events by pasting a sorcerytcg.com event URL. The system fetches player placement and win data from the carde.io API, persists it in a dedicated SQLite database, and computes a three-track season leaderboard.

## Points System

### Pathfinder Points (attendance + win bonus)

Every player who attends earns **10 base Pathfinder points**. Additional **Bonus Pathfinder** points are awarded based on **exact** Swiss win count (players with 3+ wins receive no bonus):

| Swiss Wins | Bonus Pathfinder |
|-----------|-----------------|
| Exactly 0 | +5 |
| Exactly 1 | +4 |
| Exactly 2 | +3 |
| 3 or more | +0 |

### Persecutor Points (top-8 only)

Only players who reach the final single-elimination phase earn Persecutor points:

| Final Standing | Persecutor |
|---------------|-----------|
| 1st | 10 |
| 2nd | 5 |
| 3rd | 4 |
| 4th | 4 |
| 5th | 3 |
| 6th | 3 |
| 7th | 2 |
| 8th | 2 |
| 9th+ | 0 |

### Grand Explorer

`Grand Explorer = Pathfinder + Persecutor`

### Qualified for Trials of the Persecutor

A player is **Qualified** once their cumulative seasonal Persecutor total reaches the threshold (default: **10 points**, configurable per season).

## User Stories

### US-1: Public Leaderboard Page

As a community member, I want to view the Explorer Standings page and see ranked players for a selected season.

**Acceptance Criteria:**
- Route `/explorer` renders the Explorer Standings React page
- A season selector dropdown lets users choose which season to view
- The leaderboard table shows: rank, player name/avatar, Grand Explorer total, Pathfinder total, Persecutor total, events attended, "Qualified?" badge
- Each row can expand to show per-event breakdown (standing, wins, Pathfinder, Persecutor per event)
- The page is public (no login required to read)

### US-2: Admin Season Management

As an authorized Explorer admin, I want to create a new season so I can start tracking events under it.

**Acceptance Criteria:**
- An "Add Season" button is visible only to Explorer admins (global admins + explorer-specific admins)
- Clicking it opens a modal with: Season Name (text), Description (optional)
- Submitting calls `POST /api/explorer/seasons` which creates the `explorer_seasons` record and, if `explorer.db` does not exist, initializes the schema
- The new season appears immediately in the season selector

### US-3: Admin Event Import

As an authorized Explorer admin, I want to import an event from a carde.io URL so its results are added to the leaderboard.

**Acceptance Criteria:**
- An "Add Event" button is visible only to Explorer admins
- Clicking opens a modal with: Event URL (from `https://play.sorcerytcg.com/events/{uuid}`), Season selector
- On submit, the backend:
  1. Extracts the event UUID from the URL
  2. Calls `https://api.carde.io/api/play/events/{uuid}` to get event metadata, phase IDs, and tournament IDs
  3. Fetches the **Swiss phase roster** (`/activityPhases/{swiss_phase_id}/roster?sortBy=seed`) to get ALL players with their `tieBreakers.points` (match points) and `standing`
  4. Derives win count: `wins = tieBreakers.points // 3` (3 pts/win from Swiss config)
  5. If a final phase (single-elim) exists, fetches its standings (`/tournaments/{final_tournament_id}/standings`) for authoritative top-8 placements
  6. Merges: top-8 players use final standings `standing`; rest use Swiss `standing` offset by top-cut size
  7. Persists event + results (with per-player `wins`) to `explorer.db`
- A preview shows event name, date, player count, and first few results (with win counts) before saving
- Duplicate event URLs are rejected with a clear error

### US-4: Explorer Admin Management

As a global admin, I want to grant Explorer admin access to specific Discord users so they can manage events without full site admin.

**Acceptance Criteria:**
- `GET /api/explorer/admins` returns the list of current Explorer admins (admin only)
- `POST /api/explorer/admins` adds a user by Discord ID + display name (admin only)
- `DELETE /api/explorer/admins/{discord_user_id}` removes a user (admin only)
- The admin panel for Explorer Standings shows the current admin list with an add/remove UI
- Explorer admins can add seasons and events but cannot manage other Explorer admins

### US-5: Leaderboard Computation

As a user, I want correctly computed standings using the three-track point system.

**Acceptance Criteria:**
- Per player per event, the service computes:
  - `pathfinder = 10 + bonus_pathfinder[wins]` (exact-win lookup; 0 for wins ≥ 3)
  - `persecutor = persecutor_config[final_standing]` (0 if standing > 8)
  - `grand_explorer = pathfinder + persecutor`
- Season totals: sum of each track across all attended events
- `qualified = season_persecutor_total >= trials_threshold` (default 10)
- Sort: Grand Explorer descending; ties broken by Persecutor total, then Pathfinder total
- All thresholds and point values stored in `explorer_seasons.points_config` (JSON) and configurable per season without code changes

## Data Storage

### Database: `web-app/explorer.db`

Path added to `webapp_config.py` as `EXPLORER_DB_PATH`.

### Schema

```sql
CREATE TABLE explorer_seasons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    points_config TEXT,   -- JSON (see default below)
    created_at TEXT DEFAULT (datetime('now'))
);
-- Default points_config:
-- {
--   "participation": 10,
--   "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
--   "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4,
--                  "5": 3, "6": 3, "7": 2, "8": 2},
--   "trials_threshold": 10
-- }

CREATE TABLE explorer_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id INTEGER NOT NULL REFERENCES explorer_seasons(id),
    cardeio_event_id TEXT NOT NULL UNIQUE,
    cardeio_final_tournament_id TEXT,   -- NULL for Swiss-only events
    cardeio_swiss_phase_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    event_date TEXT,
    total_players INTEGER,
    play_format TEXT,
    venue_name TEXT,
    source_url TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE explorer_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES explorer_events(id),
    cardeio_user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    final_standing INTEGER NOT NULL,  -- 1 = 1st
    wins INTEGER NOT NULL DEFAULT 0,  -- Swiss win count (for bonus pathfinder)
    total_players INTEGER NOT NULL,
    image_url TEXT,
    team_name TEXT,
    UNIQUE(event_id, cardeio_user_id)
);

CREATE TABLE explorer_admins (
    discord_user_id TEXT PRIMARY KEY,
    display_name TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);
```

### Key Design Notes
- `wins` is derived at import time: `tieBreakers.points // 3` from Swiss phase roster
- `points_config` JSON encodes all three point tracks + threshold — no schema migration needed to adjust per season
- `cardeio_user_id` is the stable identity key (handles display name changes)
- `total_players` denormalized per row for leaderboard scaling without joins

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/explorer/seasons` | Public | List all seasons |
| POST | `/api/explorer/seasons` | Explorer admin | Create new season |
| GET | `/api/explorer/seasons/{id}/events` | Public | List events in season |
| POST | `/api/explorer/events/preview` | Explorer admin | Fetch from carde.io, return preview (no save) |
| POST | `/api/explorer/events` | Explorer admin | Import and save event |
| DELETE | `/api/explorer/events/{id}` | Explorer admin | Remove event + results |
| GET | `/api/explorer/leaderboard/{season_id}` | Public | Computed three-track leaderboard |
| GET | `/api/explorer/admins` | Global admin | List Explorer admins |
| POST | `/api/explorer/admins` | Global admin | Add Explorer admin |
| DELETE | `/api/explorer/admins/{user_id}` | Global admin | Remove Explorer admin |

## Non-Functional Requirements

- External carde.io API calls made server-side (avoid CORS issues from browser)
- Timeout on carde.io calls: 10 seconds
- Import is a synchronous operation (events are small, < 200 players)
- All new endpoints must have `@require_explorer_admin` or `@require_admin` decorator or be added to `KNOWN_PUBLIC_ENDPOINTS` in tests
- New `is_explorer_admin()` utility in `utils/auth.py` follows the existing `is_curio_editor()` pattern

## Out of Scope

- Real-time standings refresh (import is manual/on-demand)
- Historical points rule changes (retroactive recalculation)
- Discord bot commands for Explorer standings
- Player profile linking (cardeio_user_id to Discord user)
