# Data Model: Limited Queue (Arena Draft Mode)

## New Tables

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
active -> forfeited  (when player forfeits)
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

**Note**: Column naming uses `loser_id` (corrected spelling) rather than `losser_id` used in legacy `match_records`.

### `limited_elo` (in `elo.db`)

Separate ELO tracking for limited mode. Simple single-ELO system (no paper/event split).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | INTEGER | PRIMARY KEY | Discord user ID |
| `user_display_name` | TEXT | | Current display name |
| `elo` | INTEGER | NOT NULL DEFAULT 1500 | Current Limited ELO |

### `limited_active_pairings` (in `match_records.db`)

Active pairings for limited matches. Same schema as `active_pairings`.

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

## In-Memory State Additions (in `state.py`)

```python
# No new dictionaries needed - limited entries go in existing lfg_queue
# with queue_type="limited"
#
# Queue entry structure for limited:
# user_id: {
#     "timestamp": datetime,
#     "timeframe": int,
#     "deck_url": str,          # REQUIRED for limited
#     "queue_type": "limited",
#     "run_id": int,            # Active arena run ID
# }
```

## Entity Relationships

```
limited_arena_runs (1) --< limited_match_records (many)
  via winner_run_id / loser_run_id

limited_elo (1) ---- limited_arena_runs (many)
  via user_id

limited_active_pairings (1) ---- limited_match_records (1)
  via pairing validation (not FK, same pattern as existing)
```

## Validation Rules

1. **Queue join**: `deck_url` must be non-empty for `queue_type="limited"`
2. **Arena run**: Only ONE active run per `user_id` at any time
3. **Run completion**: `wins >= 5 OR losses >= 3` triggers auto-completion
4. **Forfeit**: Remaining losses = `3 - current_losses`, each applied sequentially against `starting_elo`
5. **ELO**: Starts at 1500, K=32 constant (no dynamic K-factor for limited)
6. **Pairing**: Same validation pattern as existing - must have active pairing before report accepted

## SQL Table Creation

```sql
-- limited_arena_runs
CREATE TABLE IF NOT EXISTS limited_arena_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_display_name TEXT NOT NULL,
    deck_url TEXT NOT NULL,
    json_deck_data TEXT,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    starting_elo INTEGER NOT NULL DEFAULT 1500,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_limited_runs_user_status ON limited_arena_runs(user_id, status);

-- limited_match_records
CREATE TABLE IF NOT EXISTS limited_match_records (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER,
    winner_id INTEGER,
    winner_display_name TEXT,
    loser_id INTEGER,
    loser_display_name TEXT,
    did_win BOOLEAN,
    timestamp TEXT,
    first_player TEXT,
    match_time INTEGER,
    curiosa_url_winner TEXT,
    curiosa_url_loser TEXT,
    match_comment TEXT,
    json_deck_data_winner TEXT,
    json_deck_data_loser TEXT,
    winner_elo_change INTEGER,
    loser_elo_change INTEGER,
    winner_went_first TEXT,
    loser_went_first TEXT,
    winner_run_id INTEGER,
    loser_run_id INTEGER
);

-- limited_elo (in elo.db)
CREATE TABLE IF NOT EXISTS limited_elo (
    user_id INTEGER PRIMARY KEY,
    user_display_name TEXT,
    elo INTEGER NOT NULL DEFAULT 1500
);

-- limited_active_pairings
CREATE TABLE IF NOT EXISTS limited_active_pairings (
    pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    player1_id INTEGER NOT NULL,
    player2_id INTEGER NOT NULL,
    player1_deck_url TEXT,
    player2_deck_url TEXT,
    player1_run_id INTEGER,
    player2_run_id INTEGER,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
```
