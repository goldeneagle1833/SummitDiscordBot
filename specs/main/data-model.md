# Data Model: Daily Summary Message

## No New Tables Required

This feature is **read-only**. It queries existing tables to generate a daily summary embed. No schema changes, no new tables, no migrations.

## Existing Tables Queried

### `match_records` (in `match_records.db`)

Primary data source for all daily stats. Filtered by:
- `timestamp LIKE 'YYYY-MM-DD%'` (current EST date)
- `match_type = 'ranked'` (excludes testing matches)

**Columns used:**

| Column | Type | Used For |
|--------|------|----------|
| `timestamp` | TEXT (ISO) | Date filtering, match ordering for streak detection |
| `match_type` | TEXT | Filter to ranked only |
| `winner_id` | INTEGER | Player identification |
| `winner_display_name` | TEXT | Display in embed |
| `losser_id` | INTEGER | Player identification (note: typo in schema is intentional) |
| `losser_display_name` | TEXT | Display in embed |
| `winner_lifetime_elo_change` | INTEGER | ELO gain/loss tracking, upset detection |
| `loser_lifetime_elo_change` | INTEGER | ELO gain/loss tracking |
| `match_time` | INTEGER | Average duration stat |

### `overall_standings` (in `elo.db`)

Not directly queried. ELO changes are derived from `match_records` columns (`winner_lifetime_elo_change`, `loser_lifetime_elo_change`), not from the standings table.

## Configuration (in `config.py`)

New constants added — no database storage:

| Constant | Type | Default | Description |
|----------|------|---------|-------------|
| `DAILY_SUMMARY_CHANNEL_ID` | int | Same as `LEADERBOARD_CHANNEL_ID` | Channel where summary posts |
| `DAILY_SUMMARY_HOUR` | int | 23 | Hour in EST (24h format) |
| `DAILY_SUMMARY_MINUTE` | int | 30 | Minute |

## In-Memory State

None. The cog is stateless — each run queries the database fresh. No caching, no persistent state between summaries.

## Data Flow

```
11:30 PM EST trigger
       |
       v
  Compute EST date string ("2026-04-07%")
       |
       v
  Open match_records.db (read-only)
       |
       v
  Execute 7 SQL queries (see research.md R-2)
       |
       v
  Compute win streaks in Python (research.md R-3)
       |
       v
  Build discord.Embed with stats
       |
       v
  Post to DAILY_SUMMARY_CHANNEL_ID
       |
       v
  Close DB connection
```
