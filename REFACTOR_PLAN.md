# Summit Bot Refactor Plan

## Background

This document captures all issues identified during a codebase audit and organises them into
an actionable plan.  Each phase is independently deployable.  Phases are ordered from lowest
to highest risk.

---

## Known Bug: Dual ELO Storage (fix before any refactor work)

### What is happening

`overall_standings` has four ELO columns for a Discord player:

| Column | Role |
|---|---|
| `elo` | Legacy lifetime ELO (kept for backward compat) |
| `event_elo` | Legacy event ELO (kept for backward compat) |
| `online_elo` | **Authoritative** lifetime ELO — read/written by match recording |
| `online_event_elo` | **Authoritative** event ELO — read/written by match recording |

`update_elo_db()` (called on every confirmed match) keeps all four in sync:

```sql
UPDATE overall_standings
SET online_elo = ?, online_event_elo = ?, elo = ?, event_elo = ?
WHERE user_id = ?
```

**The sync breaks in three admin commands that only write the legacy columns:**

### `!recalculate_event_elo`

```python
# Reset step — only clears legacy column
UPDATE overall_standings SET event_elo = 1500

# Write step — only writes legacy column
UPDATE overall_standings SET event_elo = ? WHERE user_id = ?
```

After this command runs, `online_event_elo` is stale.  The very next confirmed match will
calculate ELO from the wrong baseline because `update_elo_db()` reads `online_event_elo`.

### `!correct_match`

```python
UPDATE overall_standings SET elo = elo - ?, event_elo = event_elo - ? WHERE user_id = ?
```

Reverts `elo` and `event_elo` but leaves `online_elo` and `online_event_elo` untouched.
After a correction, the authoritative columns are wrong.

### `!remove_match`

Same pattern as `!correct_match` — only adjusts legacy columns.

### `!spot_elo_reset` — this one is CORRECT

```python
UPDATE overall_standings SET event_elo = ?, online_event_elo = ?, user_display_name = ?
WHERE user_id = ?
```

Correctly writes both columns.  The audit log entry (`previous_state`/`new_state`) is also
used by `get_current_event_match_elo_snapshot()` for ELO history replay, so the audit format
must stay the same.

### Fix required

Every place that writes `event_elo` or `elo` must also write `online_event_elo` or
`online_elo` with the same value.  Concretely:

- `!recalculate_event_elo` — reset and rewrite both `event_elo` AND `online_event_elo`
- `!correct_match` — revert/apply to all four columns
- `!remove_match` — revert to all four columns

---

## Phase 1 — Dead Code Removal

**Risk: None.  Zero behaviour change.**

### Changes

- `repositories/elo_repo.py` — delete `create_challenge_db()` and `save_challenge_match()`
- `utils/database.py` — remove those two from the facade exports
- `cogs/lfg/cog.py` — remove the `!reset` command's `DROP/CREATE challenge_matches` block
- One-time migration on the live DB: `DROP TABLE IF EXISTS challenge_matches`

---

## Phase 2 — Targeted Bug Fixes

**Risk: Low.  Each is a single-location change.**

### 2a — Fix archive missing lifetime ELO columns

File: `services/elo_service.py` → `end_current_event()`

The `INSERT INTO match_records_archive` statement omits `winner_lifetime_elo_change` and
`loser_lifetime_elo_change` even though those columns exist in the archive table.  They are
always written as NULL.

Fix: add those two columns and their corresponding `match_dict.get()` values to the INSERT.

### 2b — Fix ladder matches leaking active pairings

File: `cogs/lfg/persistent_confirm.py` → `_execute_match_confirmation()`

```python
# Current — skips cleanup for ladder matches
elif guild_id and not data.get("ladder_info"):
    mark_pairing_reported(guild_id, data["winner_id"], data["loser_id"])
```

When a ladder match completes the `active_pairings` row stays `status='active'` until the
24-hour expiry job runs.  `get_active_pairing_for_user()` can then return the stale completed
match as an "active" pairing for either player.

Fix: remove the `not data.get("ladder_info")` guard.  Always call `mark_pairing_reported()`
for ranked/ladder matches on completion.

### 2c — Fix dual ELO sync in admin commands (see bug section above)

Files: `cogs/lfg/cog.py` — `recalculate_event_elo`, `correct_match`, `remove_match`

Each must write `online_elo`/`online_event_elo` alongside `elo`/`event_elo`.

### 2d — Move schema creation out of service functions

Files: `services/elo_service.py` — `update_elo_db()`, `update_elo_db_lifetime_only()`,
`update_elo_db_ladder()`

Each contains an inline `CREATE TABLE IF NOT EXISTS overall_standings` block that runs a DDL
statement on every single ELO update.

Fix: remove those inline blocks.  Add a single `migrate_to_dual_elo_system()` call to the
bot startup sequence in `main.py`.

---

## Phase 3 — Consolidate `winner_report` / `losser_report` into `record_match()`

**Risk: Medium.  Touches the core match recording path.  Deploy as a single PR and test all
match paths (ranked win, ranked loss, testing, ladder) before going live.**

### Problem

The current flow has two bugs caused by splitting one logical operation across multiple calls:

1. **Crash window** — `winner_report()` updates winner ELO in `elo.db` and inserts the match
   record, then `persistent_confirm.py` makes a separate `update_elo_db(loser_id)` call.  A
   crash between these leaves winner ELO updated and loser ELO not.

2. **Wrong stored ELO changes** — `winner_report()` approximates the loser's ELO change as
   the negative of the winner's.  The actual loser change depends on their current rating and
   is computed independently in the second call.  The value stored in `match_records` is wrong.

3. **Ladder read-back hack** — `_apply_ladder_elo()` reads `winner_elo_change` back out of
   `match_records` after the fact, calculates a bonus, then issues a second raw UPDATE to
   `elo.db`.  `match_records` never reflects the actual multiplied change.

### New function: `record_match()`

Location: `services/elo_service.py`

```python
async def record_match(
    reporter_id,
    winner_id, winner_global,
    loser_id,  loser_global,
    first_player, match_time, match_comment,
    winner_deck_url, loser_deck_url,
    winner_went_first, loser_went_first,
    match_type="ranked",
    elo_multiplier_winner=1.0,
    elo_multiplier_loser=1.0,
) -> tuple[int, int, int, int, int, bool]:
    # Returns: (match_id, winner_elo_change, loser_elo_change,
    #           winner_lifetime_change, loser_lifetime_change, event_active)
```

### New operation order (fixes both bugs)

SQLite has no cross-database transactions (`elo.db` and `match_records.db` are separate
files).  The best safe ordering is:

1. **Calculate** both players' ELO changes — pure math, no DB
2. Apply multipliers if ladder match (passed in as arguments, no read-back needed)
3. **Update both ELOs** in `elo.db` in a single transaction
4. **Insert match record** in `match_records.db` with the already-correct ELO values

If step 4 fails: ELOs are updated but no match record — recoverable by an admin.
Previously a crash could leave only one player's ELO updated, which is much harder to detect.

### New DB helper: `update_both_player_elos()`

Location: `repositories/elo_repo.py`

Updates winner and loser ELO in a single `elo.db` transaction.  Handles new-player INSERT
and existing-player UPDATE in one connection.

### Files changed

| File | Change |
|---|---|
| `services/elo_service.py` | Add `record_match()`, delete `winner_report()` and `losser_report()` |
| `repositories/elo_repo.py` | Add `update_both_player_elos()` |
| `cogs/lfg/persistent_confirm.py` | Replace `winner_report()` + separate `update_elo_db(loser)` with single `record_match()` call |
| `cogs/lfg/match_reporting.py` | Simplify `_apply_ladder_elo()` — multipliers passed into `record_match()`, entire read-back-and-patch block deleted |
| `cogs/lfg/match_reporting.py` | `MatchReportModal` (direct report path) also updated to call `record_match()` |
| `utils/database.py` | Export `record_match()`, remove `winner_report` / `losser_report` exports |

---

## Phase 4 — Non-blocking Deck Scraping

**Risk: Medium.  Changes timing of when deck JSON is available; match recording is
unaffected.  Depends on Phase 3.**

### Problem

`scrape_Curosa()` uses `requests.get()` (synchronous, blocking) with a 30-second timeout and
a 30-second retry on 400 errors — up to 60 seconds total.  This is called inside an async
Discord button callback (`_execute_match_confirmation`), blocking the entire event loop and
queuing every other Discord event behind it.

A Curiosa API outage currently prevents match recording entirely.

### Change

`record_match()` (from Phase 3) stores deck URLs only — no scraping.

After `record_match()` returns, fire a background task:

```python
asyncio.create_task(_update_deck_data(match_id, winner_deck_url, loser_deck_url))
```

That task fetches deck JSON via `aiohttp` (truly async) and runs:

```sql
UPDATE match_records
SET json_deck_data_winner = ?, json_deck_data_loser = ?
WHERE match_id = ?
```

If Curiosa is down the match is already recorded.  The JSON columns remain `{}` — same
behaviour as today when scraping fails.

### Files changed

| File | Change |
|---|---|
| `utils/deck_checker.py` | Add `async scrape_curosa_async(url)` using `aiohttp`; keep sync version for non-async callers (e.g. `start_arena_run`) |
| `services/elo_service.py` | Add `_update_deck_data(match_id, winner_url, loser_url)` coroutine |
| `cogs/lfg/persistent_confirm.py` | After `record_match()` returns: `asyncio.create_task(_update_deck_data(...))` |

---

## Admin Command Cleanup (separate track, low urgency)

These are improvements to existing admin commands.  None affect match recording.

### Commands with direct `sqlite3.connect()` calls that should use the repository layer

| Command | What it does directly | Should call |
|---|---|---|
| `!recalculate_event_elo` | Raw SELECTs on `match_records`, raw UPDATEs on `overall_standings` | New `recalculate_event_elo()` in `services/elo_service.py` |
| `!correct_match` | Raw SELECT/UPDATE across both DBs | New `correct_match_record()` in `services/elo_service.py` |
| `!remove_match` | Raw SELECT/DELETE/UPDATE across both DBs | New `remove_match_record()` in `services/elo_service.py` |
| `!spot_elo_reset` | Direct UPDATE on `overall_standings` | New `set_player_event_elo()` in `repositories/elo_repo.py` |
| `!remove_player` | Direct DELETE/UPDATE across both DBs | New `remove_player()` in `services/elo_service.py` |
| `!reset_limited_elo` | Already calls `reset_limited_elo_to_default()` — OK | — |

Moving this logic to service/repository functions means:
- Admin commands become thin wrappers (validate args → call service → send embed)
- The same operations can be tested without a Discord context
- Reduces `cog.py` by ~400 lines

### `!recalculate_event_elo` specific improvement

The current implementation replays matches with a single fixed K-value for the whole replay.
The event K-value is dynamic (starts at 16, rises by 2 per day to a cap of 32).  Using the
wrong K per match compounds errors across the whole replay.

The new `recalculate_event_elo()` service function should use
`_calculate_event_k_value_for_time(event_start, match_timestamp)` per match — the same
logic already used in `get_current_event_match_elo_snapshot()`.

### `!correct_match` specific issue

The cascade recalculation (all subsequent matches for both players) uses stored
`winner_elo_change` / `loser_elo_change` to revert ELO.  After Phase 3 these values will be
accurate.  Until then they may be slightly wrong for matches where the loser ELO change was
approximated.

### Leaderboard query reads legacy `event_elo`

`cog.py` line ~188 reads the leaderboard from `event_elo` (legacy column) rather than
`online_event_elo`.  After the dual ELO sync fix in Phase 2c these will always match, but
the query should be updated to read from `online_event_elo` for clarity.

---

## Phase 5 — Remove Legacy ELO Columns

**Risk: Medium.  Touches every ELO read/write path across bot and web app.  Run migration
script first on a copy of the live DB before deploying the code changes.**

### Background

`overall_standings` currently has four ELO columns.  `elo` and `event_elo` are legacy copies
that were kept for backward compatibility when `online_elo` and `online_event_elo` were
introduced.  After Phase 2c (dual ELO sync fix) all four columns are always identical.
This phase removes the redundant pair and consolidates on the authoritative columns.

### Migration script: `migrations/remove_legacy_elo_columns.py`

The script runs in three steps:

**Step 1 — Back-fill** — For any row where `online_elo` is still at the default (1500) but
`elo` has real history, copy the legacy value into the authoritative column.  Same for
`online_event_elo` ← `event_elo`.  This recovers any players whose records pre-date the
dual-ELO system and never had their `online_` columns populated.

```sql
UPDATE overall_standings
SET online_elo = elo
WHERE online_elo = 1500 AND elo != 1500;

UPDATE overall_standings
SET online_event_elo = event_elo
WHERE online_event_elo = 1500 AND event_elo != 1500;
```

**Step 2 — Verify** — Assert that `elo == online_elo` and `event_elo == online_event_elo`
for every row before proceeding.  If any mismatch is found, print a diff and abort.

**Step 3 — Recreate table without legacy columns** — SQLite requires a table rebuild to
drop columns:

```sql
CREATE TABLE overall_standings_new (
    user_id          INTEGER PRIMARY KEY,
    user_display_name TEXT,
    online_elo        INTEGER DEFAULT 1500,
    online_event_elo  INTEGER DEFAULT 1500,
    paper_elo         INTEGER DEFAULT 1500,
    paper_event_elo   INTEGER DEFAULT 1500
);

INSERT INTO overall_standings_new
SELECT user_id, user_display_name,
       online_elo, online_event_elo,
       paper_elo, paper_event_elo
FROM overall_standings;

DROP TABLE overall_standings;
ALTER TABLE overall_standings_new RENAME TO overall_standings;
```

### Code files to update after migration

| File | Change |
|---|---|
| `repositories/elo_repo.py` | Remove `event_elo` from `CREATE TABLE`; remove `ensure_event_elo_column()`; update `migrate_to_dual_elo_system()` |
| `services/elo_service.py` | Remove `elo`/`event_elo` from all `UPDATE` and `CREATE TABLE` statements; remove `COALESCE(online_event_elo, event_elo, 1500)` fallback |
| `cogs/lfg/cog.py` | Leaderboard query and `!spot_elo_reset` INSERT use `online_elo`/`online_event_elo` only |
| `cogs/lfg/match_reporting.py` | Ladder bonus `event_elo = event_elo + ?` → `online_event_elo = online_event_elo + ?` |
| `cogs/elo.py` | 3 queries reading `elo`/`event_elo` → `online_elo`/`online_event_elo` |
| `web-app/repositories/elo.py` | Remove schema-detection fallback branches; read `online_elo`/`online_event_elo` directly |
| `recalculate_event_elo.py` | Update standalone script to write `online_event_elo` |
| `tests/conftest.py` + `test_match_reports.py` | Remove legacy columns from test table schema |

### Rename consideration

After removing the legacy columns, `online_elo` and `online_event_elo` become the *only*
ELO columns.  The `online_` prefix no longer distinguishes them from anything.  A follow-up
rename (`online_elo` → `elo`, `online_event_elo` → `event_elo`) can be done in the same PR
or deferred — it is a pure rename with no semantic change.

---

## Execution Order

| # | Change | Depends on |
|---|---|---|
| Bug fix | Fix dual ELO sync in `recalculate_event_elo`, `correct_match`, `remove_match` | — |
| Phase 1 | Delete `challenge_matches` dead code | — |
| Phase 2a | Fix archive missing lifetime ELO columns | — |
| Phase 2b | Fix ladder pairing leak | — |
| Phase 2d | Move `CREATE TABLE` to startup | — |
| Phase 3 | `record_match()` consolidation | Phase 2d |
| Phase 4 | Async deck scraping | Phase 3 |
| Phase 5 | Remove legacy ELO columns + back-fill migration | Bug fix (all columns in sync) |
| Admin cleanup | Move admin DB calls to service layer | Phase 3 (for correct ELO values) |

---

## Out of Scope

- Limited tables — kept as a separate domain
- `fun.py` / `shop.py` / `fart_scores.db` — entirely separate domain
