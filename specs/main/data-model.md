# Data Model: Limited Queue (Arena Draft Mode) + RealmsDraft API

## Existing Tables (Already Implemented in Discord Bot)

All four limited tables already exist in `repositories/limited_repo.py` and are fully operational.

### `limited_arena_runs` (in `match_records.db`)

Tracks each player's arena run lifecycle (draft -> play -> complete/forfeit).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `run_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique run identifier |
| `user_id` | INTEGER | NOT NULL | Discord user ID |
| `user_display_name` | TEXT | NOT NULL | Display name at run start |
| `deck_url` | TEXT | NOT NULL | Curiosa deck URL for this run |
| `json_deck_data` | TEXT | | Scraped deck JSON (cached at run creation) |
| `wins` | INTEGER | NOT NULL DEFAULT 0 | Current win count (max 5) |
| `losses` | INTEGER | NOT NULL DEFAULT 0 | Current loss count (max 3) |
| `starting_elo` | INTEGER | NOT NULL DEFAULT 1500 | Player's Limited ELO at run start (for forfeit calc) |
| `status` | TEXT | NOT NULL DEFAULT 'active' | 'active', 'completed', 'forfeited' |
| `created_at` | TEXT | NOT NULL | ISO timestamp of run creation |
| `completed_at` | TEXT | | ISO timestamp of run completion/forfeit |

**Indexes**: `CREATE INDEX IF NOT EXISTS idx_limited_runs_user_status ON limited_arena_runs(user_id, status)`

**State Transitions**:
```
active -> completed  (when wins=5 or losses=3)
active -> forfeited  (when player forfeits via DM button or RealmsDraft API)
```

### `limited_match_records` (in `match_records.db`)

Stores confirmed limited match results. Mirrors `match_records` schema but for limited games.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `match_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique match identifier |
| `reporter_id` | INTEGER | | Discord ID of reporting player |
| `winner_id` | INTEGER | | Discord ID of winner |
| `winner_display_name` | TEXT | | Winner's display name |
| `loser_id` | INTEGER | | Discord ID of loser |
| `loser_display_name` | TEXT | | Loser's display name |
| `did_win` | BOOLEAN | | True if reporter won |
| `timestamp` | TEXT | | ISO timestamp |
| `first_player` | TEXT | | 'y'/'n' reporter went first |
| `match_time` | INTEGER | | Duration in minutes |
| `curiosa_url_winner` | TEXT | | Winner's deck URL |
| `curiosa_url_loser` | TEXT | | Loser's deck URL |
| `match_comment` | TEXT | | User notes |
| `json_deck_data_winner` | TEXT | | Winner's deck JSON |
| `json_deck_data_loser` | TEXT | | Loser's deck JSON |
| `winner_elo_change` | INTEGER | | Winner's Limited ELO change |
| `loser_elo_change` | INTEGER | | Loser's Limited ELO change |
| `winner_went_first` | TEXT | | 'y'/'n' |
| `loser_went_first` | TEXT | | 'y'/'n' |
| `winner_run_id` | INTEGER | | FK to winner's arena run |
| `loser_run_id` | INTEGER | | FK to loser's arena run |

### `limited_elo` (in `elo.db`)

Separate ELO tracking for limited mode. Simple single-ELO system (no paper/event split).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | INTEGER | PRIMARY KEY | Discord user ID |
| `user_display_name` | TEXT | | Current display name |
| `elo` | INTEGER | NOT NULL DEFAULT 1500 | Current Limited ELO |

### `limited_active_pairings` (in `match_records.db`)

Active pairings for limited matches. Same pattern as `active_pairings`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pairing_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique pairing identifier |
| `guild_id` | INTEGER | NOT NULL | Discord guild ID |
| `player1_id` | INTEGER | NOT NULL | First player's Discord ID |
| `player2_id` | INTEGER | NOT NULL | Second player's Discord ID |
| `player1_deck_url` | TEXT | | Player 1's deck URL |
| `player2_deck_url` | TEXT | | Player 2's deck URL |
| `player1_run_id` | INTEGER | | FK to player 1's arena run |
| `player2_run_id` | INTEGER | | FK to player 2's arena run |
| `created_at` | TEXT | NOT NULL | ISO timestamp |
| `status` | TEXT | NOT NULL DEFAULT 'active' | 'active', 'reported', 'expired', 'cancelled' |

## No New Tables Required for RealmsDraft API

The RealmsDraft API endpoints read/write the **same four tables** listed above. No schema changes needed. The web app accesses these tables via the discord-bot's repository and service layers (already on `sys.path` in `app.py`).

## Entity Relationships

```
limited_arena_runs (1) --< limited_match_records (many)
  via winner_run_id / loser_run_id

limited_elo (1) ---- limited_arena_runs (many)
  via user_id

limited_active_pairings (1) ---- limited_match_records (1)
  via pairing validation (not FK, same pattern as existing)
```

## API Data Flow

```
RealmsDraft                    Summit Web App                    SQLite DBs
    |                               |                                |
    |-- GET /status --------------->|                                |
    |                               |-- get_active_arena_run() ----->|
    |                               |-- get_limited_elo() ---------->|
    |                               |<------- run + elo data --------|
    |<------ JSON response ---------|                                |
    |                               |                                |
    |-- POST /run (new deck) ------>|                                |
    |                               |-- start_arena_run() ---------->|
    |                               |<------- run_id ----------------|
    |<------ JSON response ---------|                                |
    |                               |                                |
    |-- POST /run (forfeit) ------->|                                |
    |                               |-- forfeit_arena_run() -------->|
    |                               |<------- summary ---------------|
    |<------ JSON response ---------|                                |
    |                               |                                |
    |-- POST /end-run ------------->|                                |
    |                               |-- forfeit_arena_run() -------->|
    |                               |<------- summary ---------------|
    |<------ JSON response ---------|                                |
```

## Validation Rules

1. **Queue join**: `deck_url` must be non-empty for `queue_type="limited"`
2. **Arena run**: Only ONE active run per `user_id` at any time
3. **Run completion**: `wins >= 5 OR losses >= 3` triggers auto-completion
4. **Forfeit**: Remaining losses = `3 - current_losses`, each applied sequentially against `starting_elo`
5. **ELO**: Starts at 1500, K=32 constant (no dynamic K-factor for limited)
6. **Pairing**: Same validation pattern as existing - must have active pairing before report accepted
7. **API Auth**: All RealmsDraft endpoints require valid `X-API-Key` header
