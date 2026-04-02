# Research: Limited Queue (Arena Draft Mode) + RealmsDraft API Integration

## Part A: Discord Bot (Original - Already Implemented)

### R-1: Queue Isolation Strategy

**Decision**: Add "limited" as a new queue_type value alongside "ranked", "testing", "both"

**Rationale**: The existing queue system already filters on `queue_type` during matching. Adding "limited" as a fourth type means:
- Limited players only match with other limited players (no compatibility with ranked/testing/both)
- The existing `resolve_match_type()` function needs a small addition for the "limited" case
- The `lfg_queue` dictionary structure can be reused - limited entries just have `queue_type: "limited"`
- No separate in-memory queue needed; isolation is achieved via type filtering during match search

**Alternatives Considered**:
- Separate `limited_queue` dict: Rejected because it duplicates queue logic (FIFO, locking, expiration) and creates maintenance burden. The existing queue already supports type-based filtering.

### R-2: Arena Run Persistence

**Decision**: Store arena runs in a new `limited_arena_runs` table in `match_records.db`

**Rationale**: Arena runs must survive bot restarts (unlike queue entries). A player's run state (wins, losses, active/completed/forfeited) is critical game state that cannot be in-memory only. Using the existing `match_records.db` file keeps all match-related data together.

**Alternatives Considered**:
- In-memory only: Rejected because a bot restart would lose all arena run progress
- Separate `limited.db` file: Possible but unnecessary - `match_records.db` already houses all match-related tables

### R-3: Limited ELO System

**Decision**: Create a separate `limited_elo` table in `elo.db` with a single ELO column (no paper/event split)

**Rationale**: Limited is Discord-bot-only (no paper mode) and doesn't have "events" or "seasons" - it's always active. A simple `user_id -> limited_elo` table with K=32 (constant) is sufficient. The same `update_elo()` pure function from `elo_service.py` can be reused.

**Alternatives Considered**:
- Add `limited_elo` column to `overall_standings`: Rejected because the user explicitly wants "its own everything" - complete separation
- Full dual ELO (lifetime + event): Rejected as overkill - limited has no event/season concept

### R-4: Forfeit ELO Penalty Calculation

**Decision**: On forfeit, calculate remaining losses against the player's ELO at run start time using a "phantom opponent" at the starting ELO

**Rationale**: The user specified "3 losses applied against your player ELO against the starting ELO score." This means:
1. Record the player's Limited ELO when the arena run starts (`starting_elo` in `limited_arena_runs`)
2. On forfeit, calculate how many losses remain: `losses_to_apply = 3 - current_losses`
3. For each phantom loss, use `update_elo(current_elo, starting_elo, did_win=False, k=32)` where opponent ELO = starting ELO
4. Apply sequentially (each loss updates the player's ELO for the next calculation)

**Alternatives Considered**:
- Flat ELO penalty (e.g., -50 per loss): Rejected because it doesn't use the existing ELO formula and would be inconsistent with real match results
- Single bulk penalty: Rejected because applying losses sequentially is more accurate (each loss shifts the expected score)

### R-5: Match Reporting Integration

**Decision**: Reuse the existing match reporting flow (WentFirstView -> LFGReportButtons -> MatchConfirmationButtons) with a `is_limited` flag threaded through

**Rationale**: The reporting UX should be identical - players should not see a different flow just because they're in limited mode. The difference is only in what happens after confirmation:
1. Match saved to `limited_match_records` instead of `match_records`
2. Limited ELO updated instead of main ELO
3. Arena run wins/losses incremented
4. Run completion check + DM

### R-6: Deck URL Requirement

**Decision**: Deck URL is mandatory when joining the limited queue (enforced at queue-join time)

**Rationale**: Unlike ranked/testing where deck URL is optional, limited requires it because the deck is the core of the arena run (drafted deck). The existing `queue_entry["deck_url"]` field handles this.

### R-7: Web App Profile Integration

**Decision**: Add a "Limited Arena" section to the player profile page, below existing stats

**Rationale**: Shows Limited ELO, run history, recent limited matches. Web app needs repository functions to query `limited_elo` and `limited_match_records`.

### R-8: Anti-Rematch in Limited Pool

**Decision**: Use the same anti-rematch logic as existing queue (skip if opponent was most recent match)

**Rationale**: In a small limited pool, strict anti-rematch could create deadlocks.

---

## Part B: RealmsDraft API Integration (New)

### R-9: Authentication for RealmsDraft API Calls

**Decision**: Shared API key via `X-API-Key` header

**Rationale**: RealmsDraft is a trusted first-party service, not a public API consumer. A shared secret (API key) stored in both services' configs is the simplest approach that provides adequate security. The web app already has `webapp_config.py` for secrets and the API is behind Cloudflare + Nginx.

**Alternatives Considered**:
- OAuth2/JWT: Overkill for server-to-server communication between two trusted services
- IP whitelisting only: Too fragile if RealmsDraft's IP changes; API key is more portable
- No auth: Unacceptable - these endpoints modify player state

**Implementation**: Add `REALMSDRAFT_API_KEY` to `webapp_config.py`. Create a `@require_api_key` decorator that checks the `X-API-Key` header against the config value.

### R-10: Draft/Deck Identifier Format

**Decision**: Use Curiosa deck URL string (consistent with existing system)

**Rationale**: The existing limited arena system already stores `deck_url TEXT` in `limited_arena_runs`. RealmsDraft will provide a Curiosa deck URL as the deck identifier. This maintains consistency with the current flow where players paste Curiosa URLs.

**Alternatives Considered**:
- Integer draft ID from RealmsDraft: Would require a new column and mapping layer; unnecessary coupling
- UUID: No benefit over URL string for this use case

### R-11: Forfeit Handling - Flag on POST vs Separate Endpoint

**Decision**: Use a `forfeit: true` flag on the POST run endpoint

**Rationale**: The user explicitly asked "should this also handle a forfeit? With a flag" - this directly answers the question. Having forfeit as a flag on the POST endpoint keeps the API surface small. A separate "end run" endpoint handles natural run completion (all losses consumed).

**Alternatives Considered**:
- Separate DELETE or POST /forfeit endpoint: More RESTful but adds unnecessary endpoint when a flag suffices
- Only via Discord bot: RealmsDraft needs to trigger forfeits when users abandon drafts

### R-12: Win/Loss Thresholds

**Decision**: Keep hardcoded at 5 wins / 3 losses (matching existing spec and code)

**Rationale**: The existing `limited_service.py:check_run_complete()` already hardcodes `wins >= 5 or losses >= 3`. The user's "x losses out of y" phrasing describes the forfeit penalty calculation (remaining losses = 3 - current_losses), not configurability. Introducing config for thresholds adds complexity with no current need.

### R-13: Queue Joining Validation via API

**Decision**: Discord bot calls Summit web API to validate before allowing limited queue join

**Rationale**: The user states "Joining the Limited Queue will have rules around it (can't join if you don't have an active deck and you meet the win loss requirements)." The GET status endpoint returns enough info for the bot to enforce these rules:
- Must have an active run (status = "active")
- Run must not be completed (wins < 5, losses < 3)
- Active run implies a valid deck URL exists

**Implementation**: Bot calls `GET /api/limited/user/<user_id>/status` before allowing queue join. If no active run or run is complete, reject with message directing user to start a new run via RealmsDraft.

### R-14: Existing Code Reuse

**Decision**: Leverage existing `limited_repo.py` and `limited_service.py` from the discord-bot via sys.path

**Rationale**: The web app already imports from the discord-bot path (`sys.path.append` in `app.py`). For write operations, we import directly from the discord-bot's service/repository layers. The existing `web-app/repositories/matches.py` already has read-only limited functions.

### R-15: Endpoint URL Design

**Decision**: Use `/api/limited/` prefix with RESTful resource naming

**Endpoints**:
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/limited/user/<user_id>/status` | Get user's run status + current record |
| `POST` | `/api/limited/user/<user_id>/run` | Start new run with deck URL, or forfeit current run |
| `POST` | `/api/limited/user/<user_id>/end-run` | End current run (apply remaining loss penalties) |
