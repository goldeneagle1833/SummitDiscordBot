# Tasks: Limited Queue (Arena Draft Mode)

**Input**: Design documents from `/specs/main/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included (Phase 8) - the project has an existing test suite (87+ tests) that must remain passing.

**Organization**: Tasks grouped by user story. US-6 (Start New Arena Run) is merged into US-2 since it's the same arena run creation logic handling the "completed run" case.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new files and wire them into the existing facade pattern

- [x] T001 [P] Create `discord-bot/repositories/limited_repo.py` with `create_limited_tables()` that creates all 4 tables (`limited_arena_runs`, `limited_match_records`, `limited_elo`, `limited_active_pairings`) using CREATE TABLE IF NOT EXISTS and the index from data-model.md SQL section
- [x] T002 [P] Create `discord-bot/services/limited_service.py` skeleton with module docstring and imports from `repositories.limited_repo` and `services.elo_service.update_elo`
- [x] T003 Update `discord-bot/utils/database.py` facade to import and re-export from `repositories.limited_repo` and `services.limited_service` (follow existing facade pattern importing from `repositories.elo_repo` and `services.elo_service`)

**Checkpoint**: New files exist, facade exports work, `create_limited_tables()` is callable

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core limited ELO and pairing operations that ALL user stories depend on

- [x] T004 [P] Implement limited ELO read/write in `discord-bot/repositories/limited_repo.py`: `get_limited_elo(user_id)` returns int (default 1500), `upsert_limited_elo(user_id, display_name, new_elo)` inserts or updates the `limited_elo` table
- [x] T005 [P] Implement limited pairings CRUD in `discord-bot/repositories/limited_repo.py`: `save_limited_pairing(guild_id, p1_id, p2_id, p1_deck_url, p2_deck_url, p1_run_id, p2_run_id)`, `get_limited_pairing_between_players(guild_id, user_id, opponent_id)`, `mark_limited_pairing_reported(guild_id, user_id, opponent_id)`, `cleanup_old_limited_pairings(hours=24)` - mirror existing `active_pairings` functions in `discord-bot/repositories/elo_repo.py` but for `limited_active_pairings` table
- [x] T006 Implement `update_limited_elo(user_id, display_name, did_win, opponent_id)` in `discord-bot/services/limited_service.py` - uses K=32 constant, calls `get_limited_elo()` for both players, applies `update_elo()` from `elo_service.py`, calls `upsert_limited_elo()`, returns `(new_elo, elo_change)`

**Checkpoint**: Limited ELO updates and pairing validation work independently

---

## Phase 3: US-2 + US-6 - Arena Run Tracking (Priority: P1) MVP

**Goal**: Players can start arena runs, track wins/losses, complete runs at 3L/5W, and start new runs after previous ones end

**Independent Test**: Call `start_arena_run()`, verify run created with 0-0 record. Call `update_arena_run_record()` to increment wins/losses. Verify `check_run_complete()` returns True at 3L or 5W. Verify `start_arena_run()` works again after a completed run.

### Implementation

- [x] T007 [P] [US2] Implement arena run CRUD in `discord-bot/repositories/limited_repo.py`: `create_arena_run(user_id, display_name, deck_url, json_deck_data, starting_elo)` inserts row returning run_id, `get_active_arena_run(user_id)` returns dict or None (status='active'), `update_arena_run_record(run_id, wins, losses)` updates wins/losses columns, `complete_arena_run(run_id, status)` sets status to 'completed' or 'forfeited' and sets completed_at timestamp
- [x] T008 [P] [US2] Implement limited match record insert in `discord-bot/repositories/limited_repo.py`: `insert_limited_match_record(reporter_id, winner_id, winner_display_name, loser_id, loser_display_name, did_win, first_player, match_time, curiosa_url_winner, curiosa_url_loser, match_comment, json_deck_data_winner, json_deck_data_loser, winner_elo_change, loser_elo_change, winner_went_first, loser_went_first, winner_run_id, loser_run_id)` inserts into `limited_match_records`, returns match_id
- [x] T009 [US2] Implement `start_arena_run(user_id, display_name, deck_url)` in `discord-bot/services/limited_service.py` - checks for active run (error if exists), gets current limited ELO as starting_elo, scrapes deck data via `scrape_Curosa()`, calls `create_arena_run()`, returns run dict
- [x] T010 [US2] Implement `check_run_complete(run_id)` in `discord-bot/services/limited_service.py` - loads run from DB, returns True if wins>=5 or losses>=3, auto-calls `complete_arena_run(run_id, 'completed')` if so
- [x] T011 [US2] Implement `get_run_summary(run_id)` in `discord-bot/services/limited_service.py` - loads run from DB, returns formatted string with record (e.g., "4-3"), deck URL, Limited ELO, status
- [x] T012 [US2] Implement `forfeit_arena_run(user_id)` in `discord-bot/services/limited_service.py` - loads active run, calculates `losses_to_apply = 3 - current_losses`, applies each phantom loss sequentially via `update_elo(current_elo, starting_elo, did_win=False, k=32)` updating limited_elo after each, calls `complete_arena_run(run_id, 'forfeited')`, returns run summary

**Checkpoint**: Arena run lifecycle fully functional: create, track, complete, forfeit, restart

---

## Phase 4: US-1 - Join Limited Queue with Draft Deck (Priority: P1)

**Goal**: Players can select "Limited" in the LFG queue, provide a deck URL, and get matched only with other limited players

**Independent Test**: Join queue with "limited" type + deck URL, verify queue entry has `queue_type="limited"` and `run_id`. Verify limited players don't match with ranked/testing players. Verify deck URL is required for limited (rejected without it).

### Implementation

- [x] T013 [US1] Update queue entry docstring in `discord-bot/cogs/lfg/state.py` to document `run_id` field for limited queue entries (add to existing comment block at line ~10-12)
- [x] T014 [US1] Add "Limited" as a 4th queue type option in `discord-bot/cogs/lfg/queue.py` - add to the queue type selection UI (Select menu or buttons), validate that deck_url is non-empty when queue_type is "limited" (reject with error message if missing), on queue join: call `get_active_arena_run(user_id)` - if active run exists use it, if no run or completed run call `start_arena_run()`, store `run_id` in queue entry dict
- [x] T015 [US1] Update `check_if_someone_is_lfg()` in `discord-bot/cogs/lfg/cog.py` to handle limited queue isolation - "limited" only matches with "limited" (add to queue type compatibility check alongside ranked/testing/both logic), pass `run_id` from both players' queue entries into the match context dict used by reporting
- [x] T016 [US1] Update `resolve_match_type()` in `discord-bot/cogs/lfg/cog.py` (or helpers) - if either player has `queue_type="limited"`, match type resolves to "limited"
- [x] T017 [US1] Update pairing save in `discord-bot/cogs/lfg/cog.py` - when match_type is "limited", call `save_limited_pairing()` instead of `save_pairing()`, passing both players' run_ids

**Checkpoint**: Limited queue works end-to-end: join with deck → isolated matching → limited pairing saved

---

## Phase 5: US-3 - Limited Match Reporting (Priority: P1)

**Goal**: When limited match is confirmed, results are saved to separate limited tables with separate ELO updates and arena run incremented

**Independent Test**: Two limited-matched players report a result. Verify match saved in `limited_match_records` (not `match_records`). Verify `limited_elo` updated (not `overall_standings`). Verify arena run wins/losses incremented. Verify run completes at 3L/5W with DM.

### Implementation

- [x] T018 [US3] Implement `limited_winner_report(...)` in `discord-bot/services/limited_service.py` - mirrors `winner_report()` from `elo_service.py` but: calls `update_limited_elo()` instead of `update_elo_db()`, calls `insert_limited_match_record()` instead of inserting into `match_records`, increments winner's arena run wins via `update_arena_run_record()`, calls `check_run_complete()` for winner, returns `(match_id, winner_run_complete)`
- [x] T019 [US3] Implement `limited_loser_report(...)` in `discord-bot/services/limited_service.py` - mirrors `losser_report()` from `elo_service.py` but for limited tables, increments loser's arena run losses, calls `check_run_complete()` for loser, returns `(match_id, loser_run_complete)`
- [x] T020 [US3] Thread `is_limited` flag and `run_id` (for both players) through the reporting Views in `discord-bot/cogs/lfg/match_reporting.py` - add parameters to `WentFirstView.__init__()`, `LFGReportButtons.__init__()`, and `MatchConfirmationButtons.__init__()`, pass them through at each handoff
- [x] T021 [US3] Branch at match confirmation in `discord-bot/cogs/lfg/match_reporting.py` `MatchConfirmationButtons.confirm_button` callback - when `match_type == "limited"`: call `limited_winner_report()` / `limited_loser_report()` instead of existing report functions, call `mark_limited_pairing_reported()` instead of `mark_pairing_reported()`, use `get_limited_pairing_between_players()` for pairing validation instead of `get_pairing_between_players()`
- [x] T022 [US3] After limited match confirmation in `discord-bot/cogs/lfg/match_reporting.py`, check run completion for both players - if either player's run is complete (returned from report functions), send them a DM with `get_run_summary(run_id)` showing final record

**Checkpoint**: Limited match reporting fully works: report → confirm → saved to limited tables → ELO updated → run incremented → completion DM

---

## Phase 6: US-4 - Post-Match Run Status DM (Continue / Forfeit) (Priority: P2)

**Goal**: After each limited match (if run still active), DM players with their run record and Continue/Forfeit buttons

**Independent Test**: After a limited match where run is still active, verify player receives DM with record + two buttons. Click Continue → message dismissed, stats reply shown. Click Forfeit → run forfeited, ELO penalty applied, summary DM sent.

### Implementation

- [x] T023 [US4] Create `RunStatusView(discord.ui.View)` class in `discord-bot/cogs/lfg/match_reporting.py` with `timeout=3600` (60 min) - takes `user_id`, `run_id`, `bot` as init params, stores them as instance vars
- [x] T024 [US4] Implement **Continue Run** button in `RunStatusView` - on click: calls `get_run_summary(run_id)`, edits the original message to show current run stats (record, deck URL, Limited ELO), disables both buttons
- [x] T025 [US4] Implement **Forfeit Run** button in `RunStatusView` - on click: calls `forfeit_arena_run(user_id)` from `limited_service.py`, edits the original message to show forfeit summary with final ELO penalty, disables both buttons
- [x] T026 [US4] Integrate `RunStatusView` into post-confirmation flow in `discord-bot/cogs/lfg/match_reporting.py` - after limited match confirmed AND run is NOT complete, send DM to each player with embed showing "Your Limited run: X-Y" + deck URL + the `RunStatusView` buttons. If run IS complete, just send the completion summary (no buttons needed)

**Checkpoint**: Post-match DM flow works: active run → Continue/Forfeit buttons, completed run → summary only

---

## Phase 7: US-5 - Limited Stats on Player Profile (Web App) (Priority: P3 - Can Be Deferred)

**Goal**: Player profile page shows Limited Arena section with ELO, run history, and recent match history

**Independent Test**: View a player profile on the web app who has limited match history. Verify "Limited Arena" section appears below existing stats with correct Limited ELO, run history, and match table.

### Implementation

- [x] T027 [P] [US5] Add limited match query functions in `web-app/repositories/matches.py`: `get_limited_matches_for_player(user_id, limit=20)` queries `limited_match_records` for matches where player is winner or loser, `get_limited_arena_runs(user_id)` queries `limited_arena_runs` for all runs by user ordered by created_at DESC, `get_limited_elo(user_id)` queries `limited_elo` table returning elo or 1500
- [x] T028 [US5] Add limited stats to player profile data in `web-app/services/player.py` - call the new repository functions to fetch limited ELO, arena runs, and recent limited matches, add to the player context dict passed to template
- [x] T029 [US5] Add "Limited Arena" section to `web-app/templates/pages/player.html` - add below existing stats section: Limited ELO display, arena run history table (run record, deck URL, status, date), recent limited match history table (same format as existing match table but sourced from limited data)

**Checkpoint**: Player profile shows complete limited stats section

---

## Phase 8: Testing & Polish

**Purpose**: Verify no regressions and add limited-specific tests

- [x] T030 Run existing test suite `pytest discord-bot/tests/ -v` and verify all 87+ tests still pass (no regressions from changes to queue.py, cog.py, match_reporting.py)
- [x] T031 Create `discord-bot/tests/test_limited.py` with tests covering: arena run lifecycle (create → update → complete at 3L and 5W), limited ELO calculation (K=32, start at 1500), forfeit ELO penalty (phantom losses against starting ELO applied sequentially), `start_arena_run()` works after completed/forfeited run (US-6), deck URL required validation for limited queue type
- [x] T032 [P] Add queue isolation test in `discord-bot/tests/test_limited.py` - verify limited queue entries do NOT match with ranked/testing/both entries, and DO match with other limited entries
- [x] T033 Verify `create_limited_tables()` is called during bot startup or on first use - add call in `discord-bot/repositories/elo_repo.py` `create_db()` or in limited_service functions (idempotent, safe to call multiple times)
- [x] T034 Code review pass: verify no changes to existing ranked/testing/both queue behavior, no changes to existing ELO tables, no changes to existing match_records table

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001, T002, T003)
- **US-2 + US-6 (Phase 3)**: Depends on Phase 2 (needs limited ELO + repo functions)
- **US-1 (Phase 4)**: Depends on Phase 3 (queue join needs `start_arena_run()`)
- **US-3 (Phase 5)**: Depends on Phase 3 (report needs run updates) and Phase 4 (needs queue matching)
- **US-4 (Phase 6)**: Depends on Phase 5 (DM sent after match confirmation)
- **US-5 (Phase 7)**: Depends on Phase 2 only (reads from limited tables) - can run in parallel with Phases 4-6
- **Testing (Phase 8)**: Depends on Phases 3-6 (needs bot-side features complete)

### User Story Dependencies

```
Phase 1 (Setup)
    └── Phase 2 (Foundational)
           ├── Phase 3: US-2+US-6 (Arena Run Tracking)
           │      └── Phase 4: US-1 (Queue Integration)
           │             └── Phase 5: US-3 (Match Reporting)
           │                    └── Phase 6: US-4 (Continue/Forfeit DM)
           └── Phase 7: US-5 (Web Profile) ← can run in parallel with Phases 4-6
```

### Parallel Opportunities

**Within Phase 1**: T001 and T002 can run in parallel (different files)
**Within Phase 2**: T004 and T005 can run in parallel (different functions, same file but independent)
**Within Phase 3**: T007 and T008 can run in parallel (different functions in same repo file)
**Phase 7 vs Phases 4-6**: Web app work (US-5) can run entirely in parallel with Discord bot queue/reporting work
**Within Phase 7**: T027 can start immediately after Phase 2
**Within Phase 8**: T032 can run in parallel with T031

---

## Implementation Strategy

### MVP First (Discord Bot Core)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T006)
3. Complete Phase 3: US-2+US-6 Arena Run Tracking (T007-T012)
4. Complete Phase 4: US-1 Queue Integration (T013-T017)
5. Complete Phase 5: US-3 Match Reporting (T018-T022)
6. **STOP and VALIDATE**: Limited queue works end-to-end (join → match → report → run tracks)
7. Deploy and test with real users

### Incremental Delivery

1. **MVP**: Phases 1-5 → Core limited queue works (join, match, report, track runs)
2. **Enhancement**: Phase 6 → Post-match Continue/Forfeit DM buttons
3. **Web visibility**: Phase 7 → Profile stats on web app
4. **Hardening**: Phase 8 → Tests and regression verification

### Total Task Count

- **Phase 1 (Setup)**: 3 tasks
- **Phase 2 (Foundational)**: 3 tasks
- **Phase 3 (US-2+US-6)**: 6 tasks
- **Phase 4 (US-1)**: 5 tasks
- **Phase 5 (US-3)**: 5 tasks
- **Phase 6 (US-4)**: 4 tasks
- **Phase 7 (US-5)**: 3 tasks
- **Phase 8 (Testing)**: 5 tasks
- **Total**: 34 tasks
