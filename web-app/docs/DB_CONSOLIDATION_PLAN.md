# Plan: Consolidate Match Tables — Unified `match_records` + Remove `source_elo`

**STATUS: COMPLETE** — `external_match_reports` and `source_elo` tables are fully deprecated. All matches write to `match_records` with a `source` column. All ELO is unified in `overall_standings`.

## Context
The current setup had too many tables across two DBs:
- `match_records` (match_records.db) — Discord matches only
- `external_match_reports` (match_records.db) — External API matches (separate table)
- `overall_standings` (elo.db) — Unified ELO, one row per user
- `source_elo` (elo.db) — Per-source ELO tracking

The fix: added a `source` column to `match_records` so ALL matches live in one table. `external_match_reports` is no longer read or written.

## Key Decisions
- **Existing `external_match_reports` data** is test data — no migration needed
- **Unified ELO only** — no per-source ELO rankings
- **Source tracking** via `match_records.source` column for source-specific web pages (win/loss records)
- **Match type tracking** via `match_records.match_type` column to distinguish ranked vs casual/testing games

## Files to Modify (in order)

| # | File | Changes |
|---|------|---------|
| 1 | `web-app/repositories/matches.py` | Add `source` column migration + new source-aware methods |
| 2 | `web-app/repositories/external_matches.py` | Remove source_elo methods, delegate insert to MatchRepository |
| 3 | `web-app/services/external_match.py` | Remove source ELO calc, simplify return dict |
| 4 | `web-app/services/leaderboard.py` | Remove source_elo fallbacks, rewrite source leaderboard |
| 5 | `web-app/routes/api/leaderboard.py` | Switch sources endpoint to MatchRepository |
| 6 | `web-app/routes/api/players.py` | Switch source_breakdown to MatchRepository |
| 7 | `web-app/routes/api/avatars.py` | Query match_records instead of external_match_reports, prevent double-counting |
| 8 | `web-app/routes/api/external_matches.py` | Update docstring |
| 9 | `discord-bot/repositories/elo_repo.py` | Add `source` + `match_type` column migrations |
| 10 | `discord-bot/services/elo_service.py` | Store `match_type` in INSERT for `winner_report()` |

## Implementation Steps

### Step 1: MatchRepository — Schema + New Methods
**File:** `web-app/repositories/matches.py`

**1a. Migration in `_ensure_tables()`:**
```python
# Add source column
try:
    cur.execute("ALTER TABLE match_records ADD COLUMN source TEXT DEFAULT 'Discord'")
except sqlite3.OperationalError:
    pass
# Backfill existing rows (ALTER TABLE DEFAULT only applies to new rows in SQLite)
try:
    cur.execute("UPDATE match_records SET source = 'Discord' WHERE source IS NULL")
except sqlite3.OperationalError:
    pass
# Add match_type column (ranked vs testing/casual)
try:
    cur.execute("ALTER TABLE match_records ADD COLUMN match_type TEXT DEFAULT 'ranked'")
except sqlite3.OperationalError:
    pass
# Backfill existing rows as ranked
try:
    cur.execute("UPDATE match_records SET match_type = 'ranked' WHERE match_type IS NULL")
except sqlite3.OperationalError:
    pass
```

**1b. New `insert_external_match()` method** — maps external field names to match_records columns (handling the `losser_id`/`losser_display_name` typos):
- `loser_id` → `losser_id` column
- `loser_display_name` → `losser_display_name` column
- `winner_deck_url` → `curiosa_url_winner` column
- `loser_deck_url` → `curiosa_url_loser` column
- `reporter_id` = NULL, `did_win` = 1, `source` = source name

**1c. New query methods:**
- `get_distinct_sources()` — `SELECT DISTINCT source FROM match_records WHERE source != 'Discord'`
- `get_source_win_loss(user_id, source)` — win/loss counts for user from specific source
- `get_player_source_breakdown(player_id)` — win/loss by source (non-Discord), GROUP BY source
- `get_source_leaderboard_data(source)` — all players + win/loss for a source (single query, no N+1)

**1d. Remove `external_match_reports` fallbacks** from these 5 existing methods (they now query only `match_records` which has everything):
- `get_wins_count()` — delete external_match_reports try/except block
- `get_losses_count()` — same
- `get_season_wins_count()` — same
- `get_season_losses_count()` — same
- `get_season_players()` — same

### Step 2: ExternalMatchRepository — Simplify
**File:** `web-app/repositories/external_matches.py`

**Remove these methods entirely** (no more per-source ELO):
- `get_source_elo()`
- `update_source_elo()`
- `get_source_elo_standings()`
- `get_all_source_elo_players()`

**Modify `insert_report()`** — delegate to `MatchRepository.insert_external_match()` instead of inserting into `external_match_reports`

**Modify `get_player_external_matches()`** — query `match_records WHERE source != 'Discord'` instead of `external_match_reports`. Preserve same tuple format for callers.

**Modify delegates:**
- `get_all_sources()` → delegate to `MatchRepository.get_distinct_sources()`
- `get_match_count_by_source()` → delegate to `MatchRepository.get_source_win_loss()`
- `get_player_source_breakdown()` → delegate to `MatchRepository.get_player_source_breakdown()`

Keep `get_overall_elo()`, `upsert_overall_standings()`, `get_active_event()` — these handle elo.db access which MatchRepository doesn't cover.

### Step 3: ExternalMatchService — Remove Source ELO
**File:** `web-app/services/external_match.py`

- **Delete** source ELO calculation block (lines 73-88): `get_source_elo()`, `calculate_elo()` for source, `update_source_elo()`
- **Keep** main ELO updates (overall_standings) — this is the unified ELO
- **Update return dict** — remove source-specific fields, rename `winner_main_elo` → `winner_elo` etc. (only one ELO now)

### Step 4: LeaderboardService — Remove source_elo Fallbacks
**File:** `web-app/services/leaderboard.py`

- `get_leaderboard()` — delete the `get_all_source_elo_players()` fallback block. All players are in `overall_standings`.
- `get_combined_leaderboard()` — delete `ext_player_names` lookup and `source_elo-only players` loop. Remove `ExternalMatchRepository` import.
- `get_source_leaderboard(source)` — rewrite to use `MatchRepository.get_source_leaderboard_data(source)`. Returns win/loss data (no per-source ELO). Set `elo: None` in response.

### Step 5: Leaderboard Routes
**File:** `web-app/routes/api/leaderboard.py`

- `get_leaderboard_sources()` — use `MatchRepository.get_distinct_sources()` instead of `ExternalMatchRepository.get_all_sources()`

### Step 6: Player Routes
**File:** `web-app/routes/api/players.py`

- Source breakdown: switch from `ExternalMatchRepository` to `MatchRepository.get_player_source_breakdown()` (or keep as-is since delegate handles it)

### Step 7: Avatar Routes — Prevent Double-Counting
**File:** `web-app/routes/api/avatars.py`

This is the trickiest file. Currently `_collect_discord_rows()` queries ALL `match_records` and `_collect_external_rows()` queries `external_match_reports`. After consolidation, both would hit `match_records`, causing double-counting.

- `_collect_discord_rows()` — add `AND (source = 'Discord' OR source IS NULL)` filter
- `_collect_external_rows()` — change from `external_match_reports` to `match_records WHERE source != 'Discord' AND source IS NOT NULL`
- `get_avatar_filters()` — query `match_records` for distinct sources instead of `external_match_reports`

### Step 8: External Match Route — Docstring
**File:** `web-app/routes/api/external_matches.py`

- Update docstring: remove "Each source gets its own ELO tracking in the source_elo table"

### Step 9: Discord Bot Migration
**File:** `discord-bot/repositories/elo_repo.py`

In `create_db()`, add after existing migrations:
```python
try:
    cur.execute("ALTER TABLE match_records ADD COLUMN source TEXT DEFAULT 'Discord'")
except sqlite3.OperationalError:
    pass
try:
    cur.execute("UPDATE match_records SET source = 'Discord' WHERE source IS NULL")
except sqlite3.OperationalError:
    pass
try:
    cur.execute("ALTER TABLE match_records ADD COLUMN match_type TEXT DEFAULT 'ranked'")
except sqlite3.OperationalError:
    pass
try:
    cur.execute("UPDATE match_records SET match_type = 'ranked' WHERE match_type IS NULL")
except sqlite3.OperationalError:
    pass
```
Keep existing `create_source_elo_table()` and `create_external_match_reports_table()` calls for backward compat.

### Step 10: Discord Bot — Store match_type in match records
**File:** `discord-bot/services/elo_service.py`

The `winner_report()` function (line ~279) already receives `match_type` parameter but does NOT include it in the INSERT statement (line ~322-350). Update the INSERT to include `match_type`:
- Add `match_type` to the column list and VALUES
- Pass `match_type` param (defaults to `"ranked"`, set to `"testing"` for casual matches)

This enables querying how many casual vs ranked games a player has played:
```sql
SELECT COUNT(*) FROM match_records WHERE winner_id = ? AND match_type = 'testing'
```

## Edge Cases
- **Typo columns**: `losser_id` / `losser_display_name` in match_records — `insert_external_match()` maps correctly
- **String vs Integer IDs**: External IDs are TEXT, Discord are INTEGER. SQLite handles this, and existing code already uses `str(user_id)` for comparisons
- **NULL vs 'Discord'**: The backfill `UPDATE ... WHERE source IS NULL` handles pre-migration rows. Run at startup, idempotent.
- **Archive table**: `match_records_archive` doesn't need source column yet (only event-based Discord matches get archived)

## Verification
1. **Syntax**: `cd web-app && python -c "from services.external_match import ExternalMatchService; from repositories.matches import MatchRepository; from services.leaderboard import LeaderboardService"`
2. **Leaderboard**: `GET /api/leaderboard` — players appear from overall_standings only, no source_elo fallback
3. **Combined**: `GET /api/leaderboard/combined` — event leaderboard works without ext_player_names
4. **Sources**: `GET /api/leaderboard/sources` — returns sources from match_records
5. **Source board**: `GET /api/leaderboard/source/<source>` — win/loss data, no ELO column
6. **External POST**: `POST /api/report-external-match` — writes to match_records with source column, updates overall_standings
7. **Player**: `GET /api/player/<id>` — shows source on matches, source breakdown
8. **Avatars**: `GET /api/avatars?source=all` — no double-counting
