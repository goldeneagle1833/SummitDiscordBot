# Data Model: Explorer Standings

## Backend Schema (explorer.db)

### explorer_seasons
Tracks named seasons (e.g., "Season 1", "Season 2").

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT UNIQUE NOT NULL | Display name |
| description | TEXT | Optional |
| points_config | TEXT | JSON: three-track config (see default below) |
| created_at | TEXT | ISO datetime |

### explorer_events
One row per imported event; links to a season.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| season_id | INTEGER FK | -> explorer_seasons.id |
| cardeio_event_id | TEXT UNIQUE | UUID from sorcerytcg.com URL |
| cardeio_final_tournament_id | TEXT | Tournament ID for top-cut standings |
| cardeio_swiss_phase_id | TEXT NOT NULL | Phase ID for full roster (always present) |
| event_name | TEXT NOT NULL | From carde.io event.name |
| event_date | TEXT | ISO date (startsAt) |
| total_players | INTEGER | registrationCount from API |
| play_format | TEXT | e.g. "Constructed" |
| venue_name | TEXT | event.owner.name |
| source_url | TEXT | Original sorcerytcg.com URL |
| fetched_at | TEXT | ISO datetime |

### explorer_results
One row per player per event; final placement.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| event_id | INTEGER FK | -> explorer_events.id |
| cardeio_user_id | TEXT NOT NULL | Stable player identity |
| display_name | TEXT NOT NULL | user.displayName |
| final_standing | INTEGER NOT NULL | 1 = 1st place |
| wins | INTEGER NOT NULL | Swiss win count — drives bonus Pathfinder calc |
| total_players | INTEGER NOT NULL | Denormalized for point scaling |
| image_url | TEXT | Profile image from carde.io |
| team_name | TEXT | gameUser.teamName |
| UNIQUE | (event_id, cardeio_user_id) | No duplicate entries per event |

### explorer_admins
Explorer-specific authorized users (supplement global admins).

| Column | Type | Notes |
|--------|------|-------|
| discord_user_id | TEXT PK | Discord user ID string |
| display_name | TEXT | For display in admin UI |
| added_at | TEXT | ISO datetime |

---

## API Response Shapes

### GET /api/explorer/seasons
```json
[
  {
    "id": 1,
    "name": "Season 2",
    "description": "Spring 2026",
    "points_config": {
      "participation": 10,
      "bonus_pathfinder": {"0": 5, "1": 4, "2": 3},
      "persecutor": {"1": 10, "2": 5, "3": 4, "4": 4, "5": 3, "6": 3, "7": 2, "8": 2},
      "trials_threshold": 10
    },
    "created_at": "2026-04-01T00:00:00",
    "event_count": 4
  }
]
```

### GET /api/explorer/leaderboard/{season_id}
```json
{
  "season": {"id": 1, "name": "Season 2", "points_config": {...}},
  "events": [
    {"id": 1, "event_name": "WV Explorer", "event_date": "2026-04-11", "total_players": 22}
  ],
  "standings": [
    {
      "rank": 1,
      "cardeio_user_id": "d7a1eb2c-...",
      "display_name": "Brandon P",
      "image_url": "https://...",
      "grand_explorer": 61,
      "pathfinder_total": 40,
      "persecutor_total": 21,
      "events_attended": 4,
      "best_finish": 1,
      "qualified": true,
      "event_results": {
        "1": {
          "standing": 1,
          "wins": 5,
          "pathfinder": 10,
          "persecutor": 10,
          "grand_explorer": 20
        },
        "2": {
          "standing": 3,
          "wins": 4,
          "pathfinder": 10,
          "persecutor": 4,
          "grand_explorer": 14
        }
      }
    }
  ]
}
```

### POST /api/explorer/events (request body)
```json
{
  "url": "https://play.sorcerytcg.com/events/88a56f3f-d35f-4b19-b783-b3d20e1edd47",
  "season_id": 1
}
```

### POST /api/explorer/events/preview (response)
```json
{
  "event_name": "Explorer Series -- West Virginia",
  "event_date": "2026-04-11",
  "total_players": 22,
  "venue_name": "Kitchen Table Cards and Games",
  "play_format": "Constructed",
  "top_cut_size": 8,
  "results": [
    {"display_name": "BubbaMoo", "final_standing": 1, "wins": 5, "image_url": "https://..."},
    {"display_name": "Brandon P", "final_standing": 2, "wins": 4, "image_url": "https://..."},
    {"display_name": "TawnytheTerrible", "final_standing": 20, "wins": 1, "image_url": null}
  ]
}
```

### POST /api/explorer/events/confirm (saves to DB)
```json
{
  "url": "https://play.sorcerytcg.com/events/...",
  "season_id": 1
}
```

---

## Frontend State Shapes

### ExplorerStandings page state
```js
{
  seasons: [],          // from GET /api/explorer/seasons
  selectedSeasonId: 1,
  leaderboard: null,    // from GET /api/explorer/leaderboard/{id}
  loading: false,
  error: null,
  // admin state
  showAddSeasonModal: false,
  showAddEventModal: false,
  eventPreview: null,   // preview before confirming import
}
```

### Admin panel (within ExplorerStandings)
```js
{
  explorerAdmins: [],   // from GET /api/explorer/admins
  showAdminPanel: false,
}
```
