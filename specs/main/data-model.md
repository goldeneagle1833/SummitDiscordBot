# Data Model: Fun Stats Page

## No New Tables Required

This feature is **read-only**. All stats are computed from existing tables using SELECT queries. No schema changes, no new tables, no migrations.

## Existing Tables Used

### `match_records` (match_records.db) — Current Matches

| Column | Type | Used For |
|--------|------|----------|
| `match_id` | INTEGER PK | Unique match identifier |
| `winner_id` | INTEGER | Player ID of winner |
| `winner_display_name` | TEXT | Winner's display name |
| `losser_id` | INTEGER | Player ID of loser (note: column typo is intentional) |
| `losser_display_name` | TEXT | Loser's display name |
| `timestamp` | TEXT | ISO datetime — used for event filtering by date range |
| `match_time` | INTEGER | Duration in minutes — for match duration stats |
| `json_deck_data_winner` | TEXT | JSON deck data — for avatar extraction (diversity stat) |
| `json_deck_data_loser` | TEXT | JSON deck data — for avatar extraction (diversity stat) |
| `winner_elo_change` | INTEGER | Per-match ELO delta — for biggest upset detection |
| `loser_elo_change` | INTEGER | Per-match ELO delta — for biggest upset detection |
| `winner_lifetime_elo_change` | INTEGER | Lifetime ELO change — for most improved calculation |
| `loser_lifetime_elo_change` | INTEGER | Lifetime ELO change — for most improved calculation |
| `winner_went_first` | TEXT | Who went first — for first player advantage stat |
| `loser_went_first` | TEXT | Who went first — for first player advantage stat |
| `source` | TEXT | Match source — for source filtering ("Discord", etc.) |
| `match_type` | TEXT | "ranked" or "testing" — filter to ranked only |

### `match_records_archive` (match_records.db) — Historical Matches

Same schema as `match_records` plus:

| Column | Type | Used For |
|--------|------|----------|
| `archive_id` | INTEGER PK | Archive entry identifier |
| `event_id` | INTEGER | Links to events table — for event-specific queries |
| `original_match_id` | INTEGER | Original match ID reference |
| `archived_at` | TEXT | When the match was archived |

### `events` (elo.db) — Event Metadata

| Column | Type | Used For |
|--------|------|----------|
| `event_id` | INTEGER PK | Event identifier |
| `event_name` | TEXT | Display name |
| `start_date` | TEXT | ISO date — filter boundary |
| `end_date` | TEXT | ISO date — filter boundary |
| `is_active` | BOOLEAN | Whether event is currently running |

### `overall_standings` (elo.db) — Player ELO

| Column | Type | Used For |
|--------|------|----------|
| `user_id` | INTEGER PK | Player ID |
| `user_display_name` | TEXT | Display name (fallback for name resolution) |

## Computed Data Structures (API Response)

### Win Streaks

```python
{
    "name": str,           # Player display name
    "best_streak": int,    # All-time longest win streak
    "current_streak": int  # Active win streak (0 if last match was a loss)
}
```

### Most Diverse Players

```python
{
    "name": str,           # Player display name
    "unique_avatars": int, # Count of distinct avatars used
    "avatars": list[str]   # List of avatar names played
}
```

### Most Active Players

```python
{
    "name": str,    # Player display name
    "wins": int,    # Total wins in period
    "losses": int,  # Total losses in period
    "games": int    # Total games (wins + losses)
}
```

### Biggest Upsets

```python
{
    "winner_name": str,    # Underdog who won
    "loser_name": str,     # Favorite who lost
    "elo_change": int,     # Winner's ELO gain (higher = bigger upset)
    "timestamp": str       # When it happened
}
```

### Nemesis Pairs

```python
{
    "player1_name": str,   # First player
    "player2_name": str,   # Second player
    "encounters": int,     # Total matches between them
    "p1_wins": int,        # Player 1's wins
    "p2_wins": int         # Player 2's wins
}
```

### First Player Advantage

```python
{
    "total_matches": int,         # Matches with first-player data
    "first_player_wins": int,     # Times first player won
    "first_player_win_rate": float # Percentage
}
```

### Match Duration Stats

```python
{
    "average_minutes": float,  # Mean match time
    "fastest_minutes": int,    # Shortest match
    "longest_minutes": int,    # Longest match
    "total_with_data": int     # Matches that have time data
}
```

### Most Improved Players

```python
{
    "name": str,        # Player display name
    "elo_change": int   # Net ELO gained in period
}
```

### Ironman Streak

```python
{
    "name": str,               # Player display name
    "consecutive_days": int    # Longest run of consecutive days with matches
}
```

## Query Patterns

### Event Filtering

All queries support optional event/date-range filtering:

- **No filter (default)**: Query `match_records` only (current event data)
- **Specific event**: Query `match_records_archive WHERE event_id = ?`
- **"all"**: UNION of `match_records` + `match_records_archive`
- **Season filter**: Query with `timestamp BETWEEN start_date AND end_date`
- **Source filter**: Additional `WHERE source = ?` clause

### Match Type Filter

All queries include `WHERE match_type = 'ranked'` to exclude testing matches (where the column exists).
