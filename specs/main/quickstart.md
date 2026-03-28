# Quickstart: Limited Queue (Arena Draft Mode)

## What This Feature Does

Adds a new "Limited" queue type to the LFG system for arena-style draft play:
- Players draft a deck on Curiosa (vs 7 bots), then queue to play other drafters
- Arena runs track wins/losses: run ends at 3 losses or 5 wins
- Completely separate ELO, match history, and stats from ranked/testing modes
- Forfeit option applies remaining losses as ELO penalty

## Key Files to Modify

### Discord Bot (Primary)

| File | Change |
|------|--------|
| `discord-bot/cogs/lfg/state.py` | Add `run_id` to queue entry docstring |
| `discord-bot/cogs/lfg/queue.py` | Add "limited" queue type option, enforce deck URL requirement |
| `discord-bot/cogs/lfg/cog.py` | Update `check_if_someone_is_lfg()` matching to isolate limited pool |
| `discord-bot/cogs/lfg/match_reporting.py` | Branch at confirmation: limited saves to separate tables, updates arena run |
| `discord-bot/repositories/elo_repo.py` | Add limited table creation + limited pairing/ELO read/write functions |
| `discord-bot/services/elo_service.py` | Add `update_limited_elo()`, `limited_winner_report()`, `forfeit_arena_run()` |
| `discord-bot/utils/database.py` | Re-export new limited functions from facade |

### New Files

| File | Purpose |
|------|---------|
| `discord-bot/repositories/limited_repo.py` | Data access for limited tables (arena runs, match records, pairings, ELO) |
| `discord-bot/services/limited_service.py` | Business logic (run creation, completion, forfeit, ELO updates) |

### Web App (Secondary)

| File | Change |
|------|--------|
| `web-app/repositories/matches.py` | Add functions to query `limited_match_records` |
| `web-app/services/player.py` | Add limited stats to player data |
| `web-app/templates/player_profile.html` | Add "Limited Arena" section |

## How It Works

### Player Flow
```
1. Player selects "Limited" queue type
2. Must provide Curiosa deck URL (required)
3. System creates/loads arena run (0-0 record)
4. Matched with another Limited player (FIFO)
5. Report match result (same UI as ranked)
6. Run updated: winner +1W, loser +1L
7. If run still active -> DM with "Continue Run" / "Forfeit Run" buttons
   - Continue: dismisses prompt, shows current run stats
   - Forfeit: applies remaining losses to ELO, ends run
   - No response: run stays active, player re-queues manually later
8. At 5W or 3L -> run complete, DM final summary
```

### Queue Matching
- Limited players ONLY match with other limited players
- Uses same FIFO + anti-rematch logic as ranked queue
- `queue_type="limited"` is incompatible with "ranked", "testing", "both"

### ELO System
- Separate `limited_elo` table, starts at 1500
- Constant K=32 (no dynamic K-factor)
- Same formula as main ELO: `new = old + K * (actual - expected)`
- Forfeit: phantom losses calculated against starting ELO

## Dev Workflow

```bash
# 1. Create limited repo + service
# 2. Update queue.py with "limited" option
# 3. Update matching in cog.py
# 4. Update match_reporting.py confirmation flow
# 5. Add forfeit command
# 6. Run existing tests (should pass - no changes to existing flow)
# 7. Add limited-specific tests
# 8. Web app profile changes (can be done later)
```
