# Research: Fun Stats Page

## R1: Event Filtering Pattern

**Decision**: Reuse the exact event/source filtering pattern from the avatar winrate page

**Rationale**: The avatar page (`routes/api/avatars.py`) has a proven, battle-tested pattern:
- `GET /api/avatars/filters` returns available events + sources
- API endpoints accept `?event=<id>&source=<value>` query params
- `_get_event_date_range(event_id)` resolves event IDs to date ranges (supports DB events, season filters, and active events)
- Queries dynamically switch between `match_records` (current) and `match_records_archive` (historical)
- The Fun Stats API will share the same filter endpoint pattern

**Alternatives considered**:
- Separate filter endpoint for fun-stats — rejected (same data, just duplicates code)
- Server-side rendering with form POST — rejected (doesn't match existing SPA-like pattern)

## R2: Win Streak Calculation

**Decision**: Port the algorithm from `admin.py:516-563` into the new fun-stats blueprint

**Rationale**: The admin dashboard already computes win streaks correctly:
1. Fetch all matches ordered by `timestamp ASC`
2. Iterate through matches tracking `{current: int, best: int, type: "W"/"L"}` per player
3. Winner: increment current if type is "W", else reset to 1 + set type "W"; update best
4. Loser: increment current if type is "L", else reset to 1 + set type "L"
5. Filter to players with `best >= 3`, sort descending

**Adaptation needed**: The admin code uses `_online_union()` helper which is local to admin.py. The fun-stats blueprint will build its own query based on event filter (current table, archive table, or date-range filtered).

**Alternatives considered**:
- Importing/sharing the admin function — rejected (admin code is tightly coupled to its internal UNION helpers)
- Precomputing streaks in a separate table — rejected (over-engineering for the dataset size)

## R3: Avatar Diversity (Most Unique Avatars)

**Decision**: Parse `json_deck_data_winner` and `json_deck_data_loser` columns using the established extraction pattern

**Rationale**: Avatar extraction from deck JSON is already proven in `avatars.py:115-125`:
```python
deck_data = json.loads(deck_str)
avatar = deck_data.get("avatar", [{}])
name = avatar[0].get("name", "Unknown") if avatar else "Unknown"
```

For diversity:
1. Query all matches in scope (filtered by event/source)
2. For each match, extract avatar from winner's and loser's deck data
3. Build `{player_id: set(avatar_names)}` mapping
4. Rank by `len(set)` descending, top 10

**Alternatives considered**:
- SQL-level JSON extraction — rejected (SQLite's JSON functions are limited, Python approach is proven)

## R4: Biggest Upset Calculation

**Decision**: Use `winner_elo_change` column as a proxy for ELO gap

**Rationale**: When a low-rated player beats a high-rated player, the ELO change is larger (the system awards more points for upsets). The match with the highest `winner_elo_change` is the biggest upset.

Display: both player names, result, ELO delta, timestamp.

**Alternatives considered**:
- Comparing actual ELO ratings at time of match — not stored, would require reconstruction
- Using lifetime ELO change columns — these accumulate, not per-match

## R5: Nemesis Pairs

**Decision**: Aggregate matchups by unordered player pair, count total encounters

**Rationale**: For each match, create a canonical pair key `(min(winner_id, loser_id), max(winner_id, loser_id))` to count encounters regardless of who won. Track wins per side for the head-to-head record.

```sql
SELECT
  MIN(winner_id, losser_id) as p1,
  MAX(winner_id, losser_id) as p2,
  COUNT(*) as encounters
FROM match_records
GROUP BY MIN(winner_id, losser_id), MAX(winner_id, losser_id)
ORDER BY encounters DESC
LIMIT 5
```

Minimum 3 encounters to qualify.

## R6: First Player Advantage

**Decision**: Analyze `winner_went_first` column across all matches

**Rationale**: The `winner_went_first` column is populated since Feb 2026 (newer matches). Determine first-player win rate by counting matches where winner went first vs loser went first. Show as a simple percentage stat.

Note: Will show "Data available since Feb 2026" for transparency.

## R7: Frontend Architecture

**Decision**: Card-based grid layout with JavaScript-driven rendering

**Rationale**: Follows the existing web app pattern:
- Jinja2 template provides page skeleton + filter bar
- Page-specific JS fetches from API on load and on filter change
- Results rendered client-side into DOM elements
- CSS grid for responsive layout (1-col mobile, 2-col tablet, 3-col desktop)
- Each stat rendered as a card with title, icon/emoji, and ranked table or highlight value

**Alternatives considered**:
- Server-side rendering — rejected (no dynamic filtering without page reload)
- React/Vue — rejected (doesn't match codebase, massive over-engineering)

## R8: Match Duration Stats

**Decision**: Use `match_time` column, excluding NULL and zero values

**Rationale**: `match_time` stores duration in minutes. Many older matches have NULL or 0. Stats to show:
- Average match time
- Fastest match (min non-zero)
- Longest match (max)

Simple aggregate queries that work with event/source filtering.

## R9: Most Improved Player

**Decision**: Sum per-match ELO changes across the filtered period

**Rationale**: Each match record stores `winner_lifetime_elo_change` (positive) and `loser_lifetime_elo_change` (negative). Sum a player's changes across all matches in the period = net ELO movement. Top 5 positive movers = "Most Improved".

## R10: Ironman Streak (Consecutive Days Playing)

**Decision**: Extract distinct dates per player, find longest consecutive-day sequence in Python

**Rationale**: For each player, collect unique dates they played, then find the longest gap-free run. Requires Python-side processing (gap-and-island problems are hard in SQLite).

Algorithm:
1. Query player IDs + dates from matches
2. Group dates by player, sort ascending
3. For each player, iterate finding longest consecutive run
