# Research: Limited Queue (Arena Draft Mode)

## R-1: Queue Isolation Strategy

**Decision**: Add "limited" as a new queue_type value alongside "ranked", "testing", "both"

**Rationale**: The existing queue system already filters on `queue_type` during matching. Adding "limited" as a fourth type means:
- Limited players only match with other limited players (no compatibility with ranked/testing/both)
- The existing `resolve_match_type()` function needs a small addition for the "limited" case
- The `lfg_queue` dictionary structure can be reused - limited entries just have `queue_type: "limited"`
- No separate in-memory queue needed; isolation is achieved via type filtering during match search

**Alternatives Considered**:
- Separate `limited_queue` dict: Rejected because it duplicates queue logic (FIFO, locking, expiration) and creates maintenance burden. The existing queue already supports type-based filtering.

## R-2: Arena Run Persistence

**Decision**: Store arena runs in a new `limited_arena_runs` table in `match_records.db`

**Rationale**: Arena runs must survive bot restarts (unlike queue entries). A player's run state (wins, losses, active/completed/forfeited) is critical game state that cannot be in-memory only. Using the existing `match_records.db` file keeps all match-related data together.

**Alternatives Considered**:
- In-memory only: Rejected because a bot restart would lose all arena run progress
- Separate `limited.db` file: Possible but unnecessary - `match_records.db` already houses all match-related tables

## R-3: Limited ELO System

**Decision**: Create a separate `limited_elo` table in `elo.db` with a single ELO column (no paper/event split)

**Rationale**: Limited is Discord-bot-only (no paper mode) and doesn't have "events" or "seasons" - it's always active. A simple `user_id -> limited_elo` table with K=32 (constant) is sufficient. The same `update_elo()` pure function from `elo_service.py` can be reused.

**Alternatives Considered**:
- Add `limited_elo` column to `overall_standings`: Rejected because the user explicitly wants "its own everything" - complete separation
- Full dual ELO (lifetime + event): Rejected as overkill - limited has no event/season concept

## R-4: Forfeit ELO Penalty Calculation

**Decision**: On forfeit, calculate remaining losses against the player's ELO at run start time using a "phantom opponent" at the starting ELO

**Rationale**: The user specified "3 losses applied against your player ELO against the starting ELO score." This means:
1. Record the player's Limited ELO when the arena run starts (`starting_elo` in `limited_arena_runs`)
2. On forfeit, calculate how many losses remain: `losses_to_apply = 3 - current_losses`
3. For each phantom loss, use `update_elo(current_elo, starting_elo, did_win=False, k=32)` where opponent ELO = starting ELO
4. Apply sequentially (each loss updates the player's ELO for the next calculation)

**Alternatives Considered**:
- Flat ELO penalty (e.g., -50 per loss): Rejected because it doesn't use the existing ELO formula and would be inconsistent with real match results
- Single bulk penalty: Rejected because applying losses sequentially is more accurate (each loss shifts the expected score)

## R-5: Match Reporting Integration

**Decision**: Reuse the existing match reporting flow (WentFirstView -> LFGReportButtons -> MatchConfirmationButtons) with a `is_limited` flag threaded through

**Rationale**: The reporting UX should be identical - players should not see a different flow just because they're in limited mode. The difference is only in what happens after confirmation:
1. Match saved to `limited_match_records` instead of `match_records`
2. Limited ELO updated instead of main ELO
3. Arena run wins/losses incremented
4. Run completion check + DM

The existing Views already pass `match_type` through the flow. We can extend this to include "limited" and branch at the database save point.

**Alternatives Considered**:
- Separate reporting Views: Rejected because it duplicates UI code for no UX benefit
- New cog submodule: Possible for the limited-specific DB/service layer, but the reporting flow itself stays in `match_reporting.py`

## R-6: Deck URL Requirement

**Decision**: Deck URL is mandatory when joining the limited queue (enforced at queue-join time)

**Rationale**: The user specified "the rules would be based of a deck url provided." Unlike ranked/testing where deck URL is optional, limited requires it because:
1. The deck is the core of the arena run (drafted deck)
2. It's stored on the arena run record for history/profile display
3. It's used for match reporting (both players' decks tracked)

The existing `queue_entry["deck_url"]` field handles this - validation just needs to reject `None` for limited queue type.

## R-7: Web App Profile Integration

**Decision**: Add a "Limited Arena" section to the player profile page, below existing stats

**Rationale**: The user wants "a new table at the bottom of the player profile for limited game reports - separate from the main stats but with the same features." This means:
1. New section on profile page showing: Limited ELO, run history, recent limited matches
2. Web app needs new repository functions to query `limited_elo` and `limited_match_records`
3. Same visual format as existing match history table

This is a web-app change (templates + routes + repositories) that can be implemented after the Discord bot side.

## R-8: Anti-Rematch in Limited Pool

**Decision**: Use the same anti-rematch logic as existing queue (skip if opponent was most recent match)

**Rationale**: In a small limited pool, strict anti-rematch could create deadlocks (only 2 players in queue). The existing "most recent match only" check is a good balance. If only 2 players are in queue and they just played, they'll have to wait for a third player or for the anti-rematch window to expire.

**Alternatives Considered**:
- No anti-rematch for limited: Rejected because back-to-back rematches are annoying regardless of mode
- Full match history anti-rematch: Rejected because in a small pool this could prevent any matches
