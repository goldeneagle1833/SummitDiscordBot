# Tasks: RealmsDraft ↔ Summit API Integration

**Input**: Design documents from `/specs/main/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/realmsdraft-api.md, quickstart.md

**Tests**: Not explicitly requested. Manual curl testing described in quickstart.md.

**Organization**: Tasks grouped by API endpoint (user story). Each endpoint can be tested independently once the setup phase is complete.

**Context**: The Discord bot's limited arena system (database tables, repositories, services, match reporting, forfeit logic) is already fully implemented and tested (87+ tests passing). This task list covers ONLY the new web app API surface for RealmsDraft integration.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., API1, API2, API3, API4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add API key config and authentication decorator needed by all endpoints

- [ ] T001 [P] Add `REALMSDRAFT_API_KEY` config value to `web-app/webapp_config.py` — add `REALMSDRAFT_API_KEY = os.environ.get("REALMSDRAFT_API_KEY", "")` alongside existing secret config values, import `os` if not already imported
- [ ] T002 [P] Create `web-app/utils/api_auth.py` with `@require_api_key` decorator — import `functools.wraps`, `flask.request`, `flask.jsonify`, and `webapp_config`; decorator checks `request.headers.get("X-API-Key")` against `webapp_config.REALMSDRAFT_API_KEY`, returns 401 JSON `{"success": false, "error": "Invalid API key"}` if missing or mismatched (see contract `realmsdraft-api.md` Authentication section for exact implementation)

**Checkpoint**: Auth decorator exists and can be imported. Config value is readable from environment.

---

## Phase 2: Foundational (Blueprint Registration)

**Purpose**: Create the limited API blueprint skeleton and wire it into the Flask app

**CRITICAL**: Must complete before any endpoint implementation

- [ ] T003 Create `web-app/routes/api/limited.py` with empty Flask Blueprint — `limited_bp = Blueprint("limited", __name__)`, add imports for `flask.Blueprint`, `flask.jsonify`, `flask.request`, and the `require_api_key` decorator from `utils.api_auth`; also import from discord-bot layer: `repositories.limited_repo.get_active_arena_run`, `repositories.limited_repo.get_limited_elo`, `services.limited_service.start_arena_run`, `services.limited_service.forfeit_arena_run` (these are available because `app.py` adds `discord-bot/` to `sys.path`)
- [ ] T004 Register `limited_bp` in `web-app/routes/api/__init__.py` — add `from routes.api.limited import limited_bp` and `api_bp.register_blueprint(limited_bp, url_prefix="/limited")` following the existing pattern (see `match_reporting_bp` and `curios_bp` registrations with url_prefix)

**Checkpoint**: Blueprint registered. Server starts without errors. `GET /api/limited/` returns 404 (no routes yet).

---

## Phase 3: API-US1 — GET User Status Endpoint (Priority: P1) MVP

**Goal**: RealmsDraft can check a player's current limited arena run status, record, ELO, and queue eligibility

**Independent Test**: `curl -H "X-API-Key: <key>" http://localhost:5000/api/limited/user/123/status` returns JSON with `has_active_run`, `run`, `limited_elo`, and `can_queue` fields per contract

### Implementation

- [ ] T005 [API1] Implement `GET /api/limited/user/<user_id>/status` in `web-app/routes/api/limited.py` — decorate with `@require_api_key`, call `get_active_arena_run(int(user_id))` to get active run dict (or None), call `get_limited_elo(int(user_id))` for current ELO. Build response per contract: `has_active_run` = True only if run exists and status is "active", `can_queue` = True only if active run with wins < 5 and losses < 3, `run` = most recent run dict (active or last completed/forfeited) or None if player has never played. If run exists, include: `run_id`, `deck_url`, `wins`, `losses`, `status`, `starting_elo`, `created_at`, and `completed_at` (if present). Return 200 with `jsonify()`.
- [ ] T006 [API1] Handle edge case in GET status: player has no active run but has past runs — query `limited_arena_runs` for most recent run (any status) ordered by `created_at DESC LIMIT 1`. If `get_active_arena_run()` returns None, fall back to this query. Add `get_most_recent_run(user_id)` helper function in `web-app/routes/api/limited.py` or import from `repositories.limited_repo` if the function already exists (check `get_arena_run()` which takes `run_id` — may need a new repo function `get_latest_arena_run(user_id)` in `discord-bot/repositories/limited_repo.py` that queries by user_id ordered by created_at DESC LIMIT 1)

**Checkpoint**: GET status endpoint returns correct JSON for: active run, completed run, no run history, invalid API key (401).

---

## Phase 4: API-US2 — POST Start/Forfeit Run Endpoint (Priority: P1)

**Goal**: RealmsDraft can start a new arena run with a deck URL, or forfeit the current active run using a flag

**Independent Test**: `curl -X POST -H "X-API-Key: <key>" -H "Content-Type: application/json" -d '{"deck_url":"https://curiosa.io/decks/abc","display_name":"Test"}' http://localhost:5000/api/limited/user/123/run` returns 201 with new run. `curl -X POST ... -d '{"forfeit":true}' .../run` returns 200 with forfeited run + penalty summary.

### Implementation

- [ ] T007 [API2] Implement `POST /api/limited/user/<user_id>/run` in `web-app/routes/api/limited.py` — decorate with `@require_api_key`, parse JSON body with `request.get_json()`. Branch on `forfeit` flag:
  - **If `forfeit: true`**: call `forfeit_arena_run(int(user_id))` from `services.limited_service`. If no active run, return 400 `{"success": false, "error": "No active run to forfeit"}`. On success, return 200 with `action: "forfeited"`, the forfeited run dict, updated `limited_elo`, and `penalty_summary` string from the forfeit function.
  - **If no forfeit flag (new run)**: validate `deck_url` and `display_name` are present in body, return 400 if missing. Call `start_arena_run(int(user_id), display_name, deck_url)` from `services.limited_service`. If player already has active run, return 400 `{"success": false, "error": "Player already has an active run (run_id: X). Forfeit or complete it first."}`. On success, return 201 with `action: "created"`, new run dict, and `limited_elo`.
- [ ] T008 [API2] Handle forfeit response formatting in POST /run — `forfeit_arena_run()` returns a summary string. Parse this to extract the ELO before/after for the `penalty_summary` field, and fetch the updated run dict by calling `get_arena_run(run_id)` after forfeit completes. Also fetch updated `limited_elo` via `get_limited_elo(user_id)` since it changed during forfeit.

**Checkpoint**: POST /run creates new runs (201), forfeits active runs (200), rejects missing fields (400), rejects duplicate active runs (400), rejects forfeit with no active run (400), rejects invalid API key (401).

---

## Phase 5: API-US3 — POST End Run Endpoint (Priority: P1)

**Goal**: RealmsDraft can force-end a player's current run (e.g., user abandons draft session), applying remaining losses as ELO penalties

**Independent Test**: `curl -X POST -H "X-API-Key: <key>" http://localhost:5000/api/limited/user/123/end-run` returns 200 with forfeited run, `losses_applied` count, and `penalty_summary`.

### Implementation

- [ ] T009 [API3] Implement `POST /api/limited/user/<user_id>/end-run` in `web-app/routes/api/limited.py` — decorate with `@require_api_key`. Get active run via `get_active_arena_run(int(user_id))`. If no active run, return 400 `{"success": false, "error": "No active run to end"}`. Calculate `losses_applied = 3 - run["losses"]`. Call `forfeit_arena_run(int(user_id))`. Fetch updated run and ELO. Return 200 with run dict (now status "forfeited"), `limited_elo`, `losses_applied` integer, and `penalty_summary` string per contract.

**Checkpoint**: POST /end-run forfeits active run (200), returns correct `losses_applied` count, rejects when no active run (400), rejects invalid API key (401).

---

## Phase 6: API-US4 — Discord Bot Queue Validation (Priority: P2)

**Goal**: Discord bot validates that a player has an active arena run before allowing them to join the Limited queue, enforcing "can't join if you don't have an active deck and you meet the win loss requirements"

**Independent Test**: Try to join limited queue without an active run — bot rejects with message. Start a run via API, then join — bot accepts. Complete a run (5W or 3L), try to join again — bot rejects.

### Implementation

- [ ] T010 [API4] Update limited queue join validation in `discord-bot/cogs/lfg/queue.py` — when `queue_type == "limited"`, before adding player to queue: call `get_active_arena_run(user_id)` from `repositories.limited_repo`. If no active run (None) or run status is not "active", send ephemeral error message: "You need an active arena run to join the Limited queue. Start one on RealmsDraft first." If active run exists but is completed (wins >= 5 or losses >= 3), send: "Your current run is complete. Start a new run on RealmsDraft to continue playing Limited." Only allow queue join if active run exists with `status == "active"` and `wins < 5` and `losses < 3`. Store `run_id` and `deck_url` from the active run into the queue entry dict.
- [ ] T011 [API4] Remove the existing auto-create-run-on-queue-join logic in `discord-bot/cogs/lfg/queue.py` — the current code calls `start_arena_run()` when a player joins limited queue without an active run. This should now be removed since RealmsDraft is responsible for creating runs. Players MUST have a pre-existing active run (created via the POST /run API) before they can join the queue. Keep the `get_active_arena_run()` check but change the else-branch from auto-creating a run to rejecting the queue join.

**Checkpoint**: Bot rejects limited queue join without active run. Bot accepts with active run. Run creation only happens via RealmsDraft API.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, logging, and validation hardening

- [ ] T012 Add error handling wrapper to all 3 endpoints in `web-app/routes/api/limited.py` — wrap each endpoint body in try/except, catch `ValueError` (invalid user_id conversion), `sqlite3.Error` (database failures), and generic `Exception`. Return appropriate HTTP status (400 for ValueError, 500 for database/unexpected errors) with `{"success": false, "error": "<message>"}` format. Add `logging.getLogger(__name__)` and log errors at ERROR level.
- [ ] T013 [P] Add request logging to `web-app/routes/api/limited.py` — log each incoming request at INFO level with method, path, user_id, and action taken (e.g., "GET status for user 123: active run found" or "POST run for user 123: new run created"). Use the existing logging pattern from `web-app/app.py`.
- [ ] T014 Verify existing test suite still passes — run `pytest discord-bot/tests/ -v` from `discord-bot/` directory to confirm all 87+ existing tests still pass after the queue.py changes in T010-T011. No new test files needed since the API endpoints are tested manually via curl.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001, T002) — needs config + auth decorator
- **API-US1 (Phase 3)**: Depends on Phase 2 (T003, T004) — needs blueprint registered
- **API-US2 (Phase 4)**: Depends on Phase 2 — can run in parallel with Phase 3
- **API-US3 (Phase 5)**: Depends on Phase 2 — can run in parallel with Phases 3-4
- **API-US4 (Phase 6)**: No dependency on Phases 3-5 (bot reads DB directly, doesn't call API)
- **Polish (Phase 7)**: Depends on Phases 3-6 complete

### User Story Dependencies

```
Phase 1 (Setup: config + auth)
    └── Phase 2 (Blueprint skeleton + registration)
           ├── Phase 3: API-US1 (GET status)     ─┐
           ├── Phase 4: API-US2 (POST run/forfeit) ├── All 3 can run in parallel
           └── Phase 5: API-US3 (POST end-run)   ─┘
Phase 6: API-US4 (Bot queue validation) ← independent, can run anytime after Phase 1
    └── Phase 7 (Polish) ← after all above complete
```

### Parallel Opportunities

**Within Phase 1**: T001 and T002 can run in parallel (different files)
**Phases 3, 4, 5**: All three endpoint implementations can run in parallel (same file but independent functions, no dependencies between them)
**Phase 6 vs Phases 3-5**: Bot queue validation (T010-T011) is independent of web app API work — can run in parallel
**Within Phase 7**: T012 and T013 can run in parallel (different concerns in same file)

---

## Parallel Example: Endpoint Implementation

```bash
# After Phase 2 completes, launch all three endpoints in parallel:
Task: "T005 [API1] Implement GET /api/limited/user/<user_id>/status in web-app/routes/api/limited.py"
Task: "T007 [API2] Implement POST /api/limited/user/<user_id>/run in web-app/routes/api/limited.py"
Task: "T009 [API3] Implement POST /api/limited/user/<user_id>/end-run in web-app/routes/api/limited.py"

# Simultaneously, work on bot-side validation:
Task: "T010 [API4] Update limited queue join validation in discord-bot/cogs/lfg/queue.py"
```

---

## Implementation Strategy

### MVP First (GET Status Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Blueprint registration (T003-T004)
3. Complete Phase 3: GET status endpoint (T005-T006)
4. **STOP and VALIDATE**: RealmsDraft can call GET to check player status
5. Deploy and verify with RealmsDraft team

### Incremental Delivery

1. **MVP**: Phases 1-3 → RealmsDraft can read player status (GET)
2. **Run management**: Phase 4 → RealmsDraft can create runs and forfeit (POST /run)
3. **Run termination**: Phase 5 → RealmsDraft can force-end runs (POST /end-run)
4. **Queue enforcement**: Phase 6 → Bot enforces "must have active run" rule
5. **Hardening**: Phase 7 → Error handling, logging, regression check

### Total Task Count

- **Phase 1 (Setup)**: 2 tasks
- **Phase 2 (Foundational)**: 2 tasks
- **Phase 3 (API-US1: GET status)**: 2 tasks
- **Phase 4 (API-US2: POST run/forfeit)**: 2 tasks
- **Phase 5 (API-US3: POST end-run)**: 1 task
- **Phase 6 (API-US4: Bot queue validation)**: 2 tasks
- **Phase 7 (Polish)**: 3 tasks
- **Total**: 14 tasks

### Task Count per User Story

| Story | Description | Tasks |
|-------|-------------|-------|
| Setup | Config + auth decorator | 2 |
| Foundational | Blueprint + registration | 2 |
| API-US1 | GET user status | 2 |
| API-US2 | POST start/forfeit run | 2 |
| API-US3 | POST end run | 1 |
| API-US4 | Bot queue validation | 2 |
| Polish | Error handling, logging, tests | 3 |
