# Tasks: Fun Stats Page

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/fun-stats-api.md, quickstart.md

**Tests**: Not explicitly requested. Verify via syntax checks and manual browser testing.

**Organization**: Tasks grouped by user story. US1 is the MVP (page + filters + user-requested stats). US2 and US3 add additional stats incrementally.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Include exact file paths in descriptions

## User Stories

- **US1**: Page scaffolding + event filtering + core stats (win streaks, most diverse, most active) — MVP
- **US2**: Battle stats (biggest upset, nemesis pairs, first player advantage)
- **US3**: Activity stats (match duration, most improved, ironman streak)

---

## Phase 1: Setup

**Purpose**: Create all new files and register the blueprint

- [X] T001 [P] Create the Fun Stats API blueprint skeleton with filter endpoint in `web-app/routes/api/fun_stats.py`. Include: imports (json, logging, sqlite3, Flask Blueprint/jsonify/request), `fun_stats_bp = Blueprint("fun_stats", __name__)`, and `GET /fun-stats/filters` endpoint that returns events + sources. Copy the filter logic from `routes/api/avatars.py:20-79` (query events table from elo.db, query distinct sources from match_records, append SEASON_FILTERS).
- [X] T002 [P] Create the Fun Stats page template in `web-app/templates/pages/fun_stats.html`. Extend `base.html`. Include: page title "Fun Stats", a filter bar with event and source dropdowns (copy HTML structure from avatar page filter bar), and an empty `<div id="stats-grid">` container for JS-rendered stat cards. Load page-specific CSS/JS in the appropriate blocks.
- [X] T003 [P] Create page-specific CSS in `web-app/static/css/pages/fun-stats.css`. Define: `.stats-grid` (CSS grid: 1-col on mobile, 2-col on tablet ≥768px, 3-col on desktop ≥1024px, gap 1rem), `.stat-card` (background bg-elevated, border-radius, padding, box-shadow matching existing card styles), `.stat-card h3` (title styling), `.stat-table` (full-width table with existing table styles), `.stat-highlight` (large centered number for single-value stats like first player advantage).
- [X] T004 [P] Create page-specific JS skeleton in `web-app/static/js/pages/fun-stats.js`. Include: IIFE wrapper, `fetchFilters()` function that calls `GET /api/fun-stats/filters` and populates event/source dropdowns, `fetchStats()` function stub that calls `GET /api/fun-stats` with filter params and calls `renderStats(data)`, event listeners on filter dropdowns to trigger `fetchStats()`, and `DOMContentLoaded` init that calls `fetchFilters()` then `fetchStats()`. Follow the pattern from the avatar page JS.
- [X] T005 Add the `/fun-stats` page route in `web-app/routes/pages.py`. Add a function that renders `pages/fun_stats.html`. Place it near the other public page routes (after `/elements`). No admin check required.
- [X] T006 Add "Fun Stats" link to the sidebar menu in `web-app/templates/components/navbar.html`. Insert `<a href="/fun-stats" class="block px-4 py-3 text-text hover:bg-secondary/10 hover:text-secondary transition-colors font-medium">Fun Stats</a>` after the "Element Winrates" link (after line 681).
- [X] T007 Register the fun_stats blueprint in `web-app/app.py`. Add `from routes.api.fun_stats import fun_stats_bp` to imports and `app.register_blueprint(fun_stats_bp, url_prefix="/api")` alongside the other blueprint registrations.

**Checkpoint**: Visiting `/fun-stats` shows the page skeleton with filter dropdowns. Filters endpoint returns events/sources. No stats rendered yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Event/source filter infrastructure in the API — shared by all stats

**⚠️ CRITICAL**: All stat computation depends on this filter→query logic

- [X] T008 Implement event/source filter→query helper functions in `web-app/routes/api/fun_stats.py`. Add: `_get_event_date_range(event_id)` (copy from `avatars.py:82-130` — resolves event IDs to start/end dates using elo.db events table and SEASON_FILTERS), and `_collect_match_rows(event_filter, source_filter, columns)` that builds the appropriate SQL query selecting the requested columns from `match_records` (current), `match_records_archive` (historical), or both (with optional source and date-range WHERE clauses). Include `WHERE match_type = 'ranked'` filter. Return list of row tuples. Follow the connection pattern: open/close per function, import paths from `webapp_config`.
- [X] T009 Add the main `GET /fun-stats` endpoint skeleton in `web-app/routes/api/fun_stats.py`. Parse `event` and `source` query params from request.args. Call `_collect_match_rows()` to get filtered match data. Return `{"success": true, "stats": {}}` JSON with empty stat objects. Wrap in try/except returning `{"success": false, "error": str}` on failure.

**Checkpoint**: `GET /api/fun-stats?event=all` returns `{"success": true, "stats": {}}`. Filter params are parsed and passed to helper. No stats computed yet.

---

## Phase 3: User Story 1 — Core Stats (Priority: P1) — MVP

**Goal**: Deliver the 3 user-requested stats: win streaks, most diverse player, most active player

**Independent Test**: Visit `/fun-stats`, verify 3 stat cards render with data. Change event filter, verify stats update.

### Implementation

- [X] T010 [US1] Implement `_compute_win_streaks(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, losser_id, losser_display_name, timestamp)` tuples sorted by timestamp ASC. Port the algorithm from `admin.py:516-563`: iterate matches tracking `{current, best, type}` per player_id. Build display-name lookup from winner/loser names. Return top 10 players with `best_streak >= 3`, sorted by best_streak DESC, each as `{"name", "best_streak", "current_streak"}`. Current_streak is 0 if player's last result type is "L".
- [X] T011 [US1] Implement `_compute_most_diverse(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, json_deck_data_winner, losser_id, losser_display_name, json_deck_data_loser)` tuples. For each match, extract avatar name from winner and loser deck JSON using the pattern from `avatars.py:115-125` (`json.loads(deck_str).get("avatar", [{}])[0].get("name")`). Build `{player_id: {"name": str, "avatars": set()}}` mapping. Return top 10 by `len(avatars)` DESC as `{"name", "unique_avatars", "avatars": list}`.
- [X] T012 [US1] Implement `_compute_most_active(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, losser_id, losser_display_name)` tuples. Count wins and losses per player_id, build `games = wins + losses`. Return top 10 by games DESC as `{"name", "wins", "losses", "games"}`.
- [X] T013 [US1] Wire the 3 core stat functions into the `GET /fun-stats` endpoint in `web-app/routes/api/fun_stats.py`. Call `_collect_match_rows()` with the columns needed by each stat function. Call each compute function and add results to the `stats` dict: `win_streaks`, `most_diverse`, `most_active`. Note: use a single broad query that returns all needed columns to avoid multiple DB round-trips, then slice the relevant columns for each function.
- [X] T014 [US1] Implement `renderStats(data)` in `web-app/static/js/pages/fun-stats.js` for the 3 core stats. For each stat, generate a card HTML string and insert into `#stats-grid`. Win Streaks: table with rank, name, best streak, current streak (show fire emoji if current > 0). Most Diverse: table with rank, name, unique avatar count, avatar list as comma-separated text. Most Active: table with rank, name, games, W-L record. Show loading spinner while fetching, hide on render. Hide cards with empty data arrays.

**Checkpoint**: MVP complete. `/fun-stats` shows 3 stat cards with real data. Event/source filters work. Empty stats hidden gracefully.

---

## Phase 4: User Story 2 — Battle Stats (Priority: P2)

**Goal**: Add biggest upset, nemesis pairs, and first player advantage stats

**Independent Test**: Visit `/fun-stats`, verify 3 new stat cards appear below the core stats with correct data.

### Implementation

- [X] T015 [P] [US2] Implement `_compute_biggest_upsets(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_display_name, losser_display_name, winner_elo_change, loser_elo_change, timestamp)` tuples. Filter to rows where `winner_elo_change` is not NULL and > 0. Sort by `winner_elo_change` DESC. Return top 5 as `{"winner_name", "loser_name", "elo_change", "timestamp"}`.
- [X] T016 [P] [US2] Implement `_compute_nemesis_pairs(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, losser_id, losser_display_name)` tuples. For each match, create canonical pair key `(min(id1, id2), max(id1, id2))`. Track encounters count and per-player wins. Filter to pairs with `encounters >= 3`. Return top 5 by encounters DESC as `{"player1_name", "player2_name", "encounters", "p1_wins", "p2_wins"}`.
- [X] T017 [P] [US2] Implement `_compute_first_player_advantage(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_went_first, loser_went_first)` tuples. Count matches where both columns are not NULL/empty (has data). Count how many times `winner_went_first` is truthy (winner was the one who went first). Calculate `first_player_win_rate = first_player_wins / total * 100`. Return `{"total_matches", "first_player_wins", "first_player_win_rate"}` or null if no data.
- [X] T018 [US2] Wire the 3 battle stat functions into the `GET /fun-stats` endpoint in `web-app/routes/api/fun_stats.py`. Add columns to the main query as needed. Call each function and add to `stats` dict: `biggest_upsets`, `nemesis_pairs`, `first_player_advantage`.
- [X] T019 [US2] Add rendering for battle stats in `web-app/static/js/pages/fun-stats.js`. Biggest Upsets: table with rank, winner name, "beat", loser name, ELO change with + prefix, date. Nemesis Pairs: table showing both names, total encounters, head-to-head record (e.g., "8-7"). First Player Advantage: single highlight card showing win rate percentage as a large number, plus total matches below. Hide cards with null/empty data.

**Checkpoint**: 6 stat cards now visible. Battle stats render correctly with event filtering.

---

## Phase 5: User Story 3 — Activity Stats (Priority: P3)

**Goal**: Add match duration, most improved, and ironman streak stats

**Independent Test**: Visit `/fun-stats`, verify 3 new stat cards appear. Check that "Most Improved" shows last-7-days data.

### Implementation

- [X] T020 [P] [US3] Implement `_compute_match_duration(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(match_time,)` tuples. Filter out NULL and 0 values. Calculate average (rounded to 1 decimal), min, and max. Return `{"average_minutes", "fastest_minutes", "longest_minutes", "total_with_data"}` or null if no valid data.
- [X] T021 [P] [US3] Implement `_compute_most_improved(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, winner_lifetime_elo_change, losser_id, losser_display_name, loser_lifetime_elo_change, timestamp)` tuples. Filter to matches within the last 7 days (compare timestamp to current date minus 7 days). Sum ELO changes per player (positive when winning, negative when losing). Return top 5 players with net positive change, sorted DESC, as `{"name", "elo_change"}`.
- [X] T022 [P] [US3] Implement `_compute_ironman_streak(rows)` in `web-app/routes/api/fun_stats.py`. Input: list of `(winner_id, winner_display_name, losser_id, losser_display_name, timestamp)` tuples. Extract date from each timestamp. Build `{player_id: {"name": str, "dates": set()}}`. For each player, sort dates ascending and find the longest consecutive-day run (iterate, check if next date == prev date + 1 day). Return top 10 by consecutive_days DESC as `{"name", "consecutive_days"}`.
- [X] T023 [US3] Wire the 3 activity stat functions into the `GET /fun-stats` endpoint in `web-app/routes/api/fun_stats.py`. Add to `stats` dict: `match_duration`, `most_improved`, `ironman_streak`.
- [X] T024 [US3] Add rendering for activity stats in `web-app/static/js/pages/fun-stats.js`. Match Duration: highlight card showing average as large number, plus fastest/longest as secondary stats below. Most Improved: table with rank, name, ELO change with + prefix and green color, labeled "Last 7 Days". Ironman Streak: table with rank, name, consecutive days count. Hide cards with null/empty data.

**Checkpoint**: All 9 stat cards visible and functional. Full feature complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: UX improvements, edge cases, final verification

- [X] T025 [P] Add loading and empty states in `web-app/static/js/pages/fun-stats.js`. Show a spinner/skeleton in `#stats-grid` while API call is in-flight. On error response, show a user-friendly error message. For individual stats with no data, either hide the card entirely or show a "No data available" message inside the card.
- [X] T026 [P] Add responsive fine-tuning in `web-app/static/css/pages/fun-stats.css`. Ensure stat tables don't overflow on mobile (add `overflow-x: auto` wrapper). Verify filter bar stacks vertically on mobile. Test card grid at all breakpoints.
- [X] T027 Run syntax verification: `python -c "from routes.api.fun_stats import fun_stats_bp"` from the `web-app/` directory to confirm the blueprint imports cleanly with no errors.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — all T001-T004 can run in parallel (different files), T005-T007 are edits to existing files
- **Foundational (Phase 2)**: Depends on T001 (blueprint file exists). BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 (filter infrastructure). T010-T012 can run in parallel (independent functions), T013 depends on T010-T012, T014 depends on T013
- **US2 (Phase 4)**: Depends on Phase 2. T015-T017 can run in parallel. T018 depends on T015-T017. T019 depends on T018
- **US3 (Phase 5)**: Depends on Phase 2. T020-T022 can run in parallel. T023 depends on T020-T022. T024 depends on T023
- **Polish (Phase 6)**: Depends on US1 at minimum. T025-T026 can run in parallel

### User Story Dependencies

- **US1 (P1)**: Depends only on Phase 2 — no cross-story dependencies
- **US2 (P2)**: Depends only on Phase 2 — no cross-story dependencies. Can run in parallel with US1
- **US3 (P3)**: Depends only on Phase 2 — no cross-story dependencies. Can run in parallel with US1/US2

### Within Each User Story

- Compute functions (parallel) → wire into endpoint → frontend rendering (sequential)

### Parallel Opportunities

```
Phase 1: T001 | T002 | T003 | T004  (all parallel — different files)
          then T005, T006, T007      (edits to existing files — sequential)
Phase 2: T008 → T009                 (sequential — same file)
Phase 3: T010 | T011 | T012         (parallel — independent functions)
          then T013 → T014           (sequential)
Phase 4: T015 | T016 | T017         (parallel — independent functions)
          then T018 → T019           (sequential)
Phase 5: T020 | T021 | T022         (parallel — independent functions)
          then T023 → T024           (sequential)
Phase 6: T025 | T026 | T027         (parallel — different files)
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (page exists, filters load)
2. Complete Phase 2: Foundational (event/source filter→query works)
3. Complete Phase 3: US1 — Core Stats (3 user-requested stats render)
4. **STOP and VALIDATE**: Page loads, filters work, 3 stats show data
5. Deploy if ready — page is already useful

### Incremental Delivery

1. Setup + Foundational → page skeleton with working filters
2. Add US1 → 3 core stats visible → **MVP deployed**
3. Add US2 → 6 stats visible (battle stats added)
4. Add US3 → 9 stats visible (activity stats added)
5. Polish → loading states, responsive tweaks, error handling

---

## Notes

- All stat computation happens in `web-app/routes/api/fun_stats.py` — single file for all backend logic
- All rendering happens in `web-app/static/js/pages/fun-stats.js` — single file for all frontend logic
- The `losser_id` / `losser_display_name` column typo is intentional — match the existing schema exactly
- Event filtering uses two databases: `elo.db` for event metadata, `match_records.db` for match data
- "Most Improved" uses a rolling 7-day window regardless of event filter
- All stats default to current event data when no filter is selected
