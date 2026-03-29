# Implementation Plan: Limited Queue (Arena Draft Mode)

**Branch**: `main` | **Date**: 2026-03-27 | **Spec**: [spec.md](specs/main/spec.md)
**Input**: Feature specification from `/specs/main/spec.md`

## Summary

Add a new "Limited" queue type to the LFG system enabling arena-style draft play. Players draft a deck on Curiosa, then queue to play other drafters in a win/loss-tracked arena run (ends at 3 losses or 5 wins). The entire system is fully isolated: separate database tables (`limited_arena_runs`, `limited_match_records`, `limited_elo`, `limited_active_pairings`), separate ELO tracking (K=32, starts at 1500), and separate web profile section. Players can forfeit a run, applying remaining losses as ELO penalty against their starting ELO.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: discord.py 2.3+, sqlite3 (stdlib), aiohttp
**Storage**: SQLite (match_records.db, elo.db) - 4 new tables
**Testing**: pytest with asyncio_mode=auto (87+ existing tests)
**Target Platform**: Linux server (systemd + Nginx + Cloudflare)
**Project Type**: Discord bot + Flask web app
**Performance Goals**: N/A (low-traffic community bot)
**Constraints**: Cannot test locally (verify via syntax checks + import tests)
**Scale/Scope**: ~100 active players, <50 concurrent queue entries

## Constitution Check

*Constitution template is not filled in for this project - no gates to check.*

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              # This file
├── research.md          # Phase 0 output (8 research decisions)
├── data-model.md        # Phase 1 output (4 new tables)
├── quickstart.md        # Phase 1 output (dev workflow guide)
└── spec.md              # Feature specification (6 user stories)
```

### Source Code (repository root)

```text
discord-bot/
├── cogs/lfg/
│   ├── state.py              # MODIFY: update queue entry docstring for run_id
│   ├── queue.py              # MODIFY: add "limited" queue type, enforce deck URL
│   ├── cog.py                # MODIFY: update matching to isolate limited pool
│   └── match_reporting.py    # MODIFY: branch at confirmation for limited saves
├── repositories/
│   ├── elo_repo.py           # MODIFY: add limited table creation functions
│   └── limited_repo.py       # NEW: data access for all limited tables
├── services/
│   ├── elo_service.py        # MODIFY: add update_limited_elo() function
│   └── limited_service.py    # NEW: arena run logic, forfeit, limited match reporting
├── utils/
│   └── database.py           # MODIFY: re-export limited functions from facade
└── tests/
    └── test_limited.py       # NEW: tests for limited queue system

web-app/
├── repositories/
│   └── matches.py            # MODIFY: add limited match queries
├── services/
│   └── player.py             # MODIFY: add limited stats to player data
└── templates/
    └── player_profile.html   # MODIFY: add "Limited Arena" section
```

**Structure Decision**: Follows existing repository/service pattern. New `limited_repo.py` and `limited_service.py` keep limited logic isolated from existing code. Modifications to existing files are minimal (queue type additions, matching filter, reporting branch).

## Implementation Phases

### Phase 1: Data Layer (limited_repo.py)

Create the data access layer for all 4 limited tables:
- `create_limited_tables()` - idempotent table creation (all 4 tables)
- Arena run CRUD: `create_arena_run()`, `get_active_arena_run()`, `update_arena_run_record()`, `complete_arena_run()`
- Limited ELO: `get_limited_elo()`, `upsert_limited_elo()`
- Limited pairings: `save_limited_pairing()`, `get_limited_pairing_between_players()`, `mark_limited_pairing_reported()`
- Limited match records: `insert_limited_match_record()`

### Phase 2: Business Logic (limited_service.py)

Create service layer with arena run management:
- `start_arena_run(user_id, display_name, deck_url)` - creates run, records starting ELO
- `update_limited_elo(user_id, display_name, did_win, opponent_id)` - K=32, simple ELO update
- `limited_winner_report(...)` / `limited_loser_report(...)` - save match + update ELO + update run
- `check_run_complete(run_id)` - returns True if wins>=5 or losses>=3
- `forfeit_arena_run(user_id)` - apply remaining phantom losses, mark run forfeited
- `get_run_summary(run_id)` - format run stats for DM

### Phase 3: Queue Integration

Modify existing LFG queue to support "limited" type:
- `queue.py`: Add "Limited" as a 4th option in queue type selection
  - Enforce deck URL requirement (reject join if no URL for limited)
  - Create/load arena run on queue join
- `cog.py` `check_if_someone_is_lfg()`: Update queue type compatibility
  - "limited" only matches with "limited" (no cross-type matching)
  - Add `run_id` to match context passed to reporting
- `state.py`: Document `run_id` field in queue entry structure

### Phase 4: Match Reporting Integration

Modify `match_reporting.py` to handle limited matches:
- Thread `is_limited` flag + `run_id` through WentFirstView -> ReportButtons -> ConfirmationButtons
- At confirmation, branch on `match_type == "limited"`:
  - Call `limited_winner_report()` / `limited_loser_report()` instead of main report functions
  - Save to `limited_active_pairings` instead of `active_pairings`
  - After save: check if either player's run is complete
    - If complete (3L or 5W): send run-complete DM summary
    - If still active: send **RunStatusView** DM with current record + two buttons:
      - **Continue Run**: Dismisses prompt, replies with current run stats (record, deck, ELO)
      - **Forfeit Run**: Calls `forfeit_arena_run()`, sends final summary DM
      - No response = run stays active (player can manually re-queue later)
      - Buttons timeout after 60 minutes
- New View class: `RunStatusView(discord.ui.View)` with Continue + Forfeit buttons

### Phase 5: Testing

- Add `test_limited.py` covering:
  - Arena run lifecycle (create, update, complete, forfeit)
  - Limited ELO calculations
  - Queue isolation (limited doesn't match with ranked/testing)
  - Forfeit ELO penalty calculation
  - Run completion at 3L and 5W boundaries
- Verify all existing tests still pass (no regression)

### Phase 6: Web App Profile (can be deferred)

- `web-app/repositories/matches.py`: Add `get_limited_matches_for_player()`, `get_limited_elo()`
- `web-app/services/player.py`: Include limited stats in player profile data
- `web-app/templates/player_profile.html`: Add "Limited Arena" section with:
  - Limited ELO display
  - Arena run history (wins/losses per run)
  - Recent limited match history table

## Complexity Tracking

No constitution violations to justify - feature follows existing patterns exactly.

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Limited pool too small for matchmaking | Anti-rematch uses "most recent only" check; display queue count |
| Bot restart loses queue state mid-run | Arena runs are DB-persisted; only queue position is lost (consistent with existing behavior) |
| Forfeit ELO abuse | Phantom losses use real ELO formula, so penalty scales appropriately |
| Match reporting code complexity | Branch at DB save point only - UI flow is unchanged |
