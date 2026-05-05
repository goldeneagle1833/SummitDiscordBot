# Tasks: Explorer Standings

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/explorer-api.md

**Organization**: Grouped by user story — each phase is independently testable.
**Tests**: In final Polish phase (not TDD; spec does not require upfront tests).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Parallelizable (different files, no pending dependencies)
- **[Story]**: User story this task belongs to

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire the new database path, schema migration, and blueprint into the existing app. No user-facing changes.

- [ ] T001 Add `EXPLORER_DB_PATH` to `web-app/webapp_config.py` — `Path(os.environ.get("EXPLORER_DB_PATH", BASE_DIR / "explorer.db"))`, following the `ANALYTICS_DB_PATH` pattern
- [ ] T002 Create `web-app/migrations/create_explorer_tables.py` — `create_explorer_tables()` opens `EXPLORER_DB_PATH` and creates all 4 tables (`explorer_seasons`, `explorer_events`, `explorer_results`, `explorer_admins`) with schema from spec.md using `CREATE TABLE IF NOT EXISTS`
- [ ] T003 Import and call `create_explorer_tables()` in `web-app/app.py` `create_app()` startup block (alongside existing `create_analytics_tables()` call)

**Checkpoint**: App starts without errors; `explorer.db` is auto-created in `web-app/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Repository layer, auth utilities, and blueprint shell. All user story phases depend on these.

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Create `web-app/repositories/explorer.py` with `ExplorerRepository` class and methods: `create_season`, `get_all_seasons` (with `event_count`), `get_season`, `create_event`, `get_events_for_season`, `get_event_by_cardeio_id`, `save_results` (bulk insert list of result dicts), `get_results_for_season` (JOIN across events+results), `delete_event` (cascade deletes results), `add_explorer_admin`, `get_explorer_admins`, `remove_explorer_admin`, `is_explorer_admin`
- [ ] T005 [P] Add `is_explorer_admin() -> bool` and `require_explorer_admin` decorator to `web-app/utils/auth.py` — pattern mirrors `is_curio_editor()` / `require_creator`; `is_explorer_admin` returns True if `is_admin()` OR session user is in `explorer_admins` table; decorator sets `_auth_required = True`
- [ ] T006 [P] Create `web-app/routes/api/explorer.py` — define `explorer_bp = Blueprint("explorer", __name__)` and `DEFAULT_POINTS_CONFIG` dict; no routes yet
- [ ] T007 Register `explorer_bp` in `web-app/routes/__init__.py` with url prefix `/api/explorer` (follow existing blueprint registration pattern)

**Checkpoint**: App starts; `/api/explorer/...` returns 404 (blueprint wired, no routes); auth module imports cleanly

---

## Phase 3: User Story 4 — Explorer Admin Management

**Goal**: Global admins can grant/revoke Explorer admin access through the API and a UI panel.

**Independent Test**: `POST /api/explorer/admins` with Discord ID → `GET /api/explorer/admins` returns the user → `DELETE` removes them. Non-admin gets 403.

- [ ] T008 [P] [US4] Implement `GET /api/explorer/admins` in `web-app/routes/api/explorer.py` — `@require_admin`, returns `ExplorerRepository().get_explorer_admins()`
- [ ] T009 [P] [US4] Implement `POST /api/explorer/admins` in `web-app/routes/api/explorer.py` — `@require_admin`, body `{discord_user_id, display_name}`, calls `repo.add_explorer_admin()`, returns 201
- [ ] T010 [US4] Implement `DELETE /api/explorer/admins/<discord_user_id>` in `web-app/routes/api/explorer.py` — `@require_admin`, calls `repo.remove_explorer_admin()`; returns 404 if not found
- [ ] T011 [US4] Create `web-app/frontend/src/components/explorer/ExplorerAdminPanel.jsx` — lists current Explorer admins (ID, name, added_at); "Add Admin" form calls `POST /api/explorer/admins`; remove button calls `DELETE`; rendered only when `user.is_admin` from AuthContext

**Checkpoint**: Admin can add/remove Explorer admins via panel; non-admins receive 403

---

## Phase 4: User Story 2 — Season Management

**Goal**: Explorer admins can create named seasons; anyone can list them and their events.

**Independent Test**: `POST /api/explorer/seasons` with a name → `GET /api/explorer/seasons` returns it with `event_count: 0`; duplicate name returns 409.

- [ ] T012 [P] [US2] Implement `GET /api/explorer/seasons` in `web-app/routes/api/explorer.py` — public (no auth decorator), returns `repo.get_all_seasons()` with `points_config` parsed from JSON
- [ ] T013 [P] [US2] Implement `POST /api/explorer/seasons` in `web-app/routes/api/explorer.py` — `@require_explorer_admin`; body `{name, description, points_config}`; uses `DEFAULT_POINTS_CONFIG` if `points_config` is null; catches UNIQUE constraint to return 409
- [ ] T014 [US2] Implement `GET /api/explorer/seasons/<int:season_id>/events` in `web-app/routes/api/explorer.py` — public; returns `repo.get_events_for_season(season_id)`; 404 if season not found
- [ ] T015 [US2] Create `web-app/frontend/src/api/explorer.js` — export async functions: `fetchSeasons()`, `createSeason(name, description, pointsConfig)`, `fetchSeasonEvents(seasonId)`; use `credentials: "include"` on all fetches
- [ ] T016 [US2] Create `web-app/frontend/src/components/explorer/AddSeasonModal.jsx` — Season Name (required) + Description inputs; submit calls `createSeason()`; 409 shows "Season already exists" error inline; on success closes and refreshes season list; only rendered for Explorer admins

**Checkpoint**: Explorer admin creates a season; season appears in UI dropdown; non-Explorer-admin gets 403

---

## Phase 5: User Story 3 — Event Import

**Goal**: Explorer admins can import event results from a sorcerytcg.com URL with a two-step preview/confirm flow.

**Independent Test**: `POST /api/explorer/events/preview` with a valid URL returns player list with win counts. `POST /api/explorer/events` saves to DB. Duplicate URL returns 409.

- [ ] T017 [US3] Create `web-app/services/explorer.py` with `ExplorerFetchError` exception and `ExplorerService` class. Implement `fetch_event_data(url: str) -> dict`: (1) validate/extract UUID from `https://play.sorcerytcg.com/events/{uuid}` — raise `ValueError` on mismatch; (2) call `https://api.carde.io/api/play/events/{uuid}` with 10s timeout — raise `ExplorerFetchError` on non-200 or timeout; (3) identify Swiss phase (stage "1") and final phase (highest stage number); (4) fetch Swiss roster from `/activityPhases/{swiss_phase_id}/roster?sortBy=seed`; (5) derive `wins = player["tieBreakers"].get("points", 0) // 3` per player; (6) if final phase exists, fetch `/tournaments/{final_tournament_id}/standings`; (7) call `_merge_standings()` and return structured dict with `{event_name, event_date, total_players, venue_name, play_format, top_cut_size, cardeio_event_id, cardeio_swiss_phase_id, cardeio_final_tournament_id, results}`
- [ ] T018 [US3] Add `_merge_standings(swiss_roster, top_cut_standings: dict) -> list[dict]` to `ExplorerService` in `web-app/services/explorer.py` — top-cut players use `top_cut_standings[uid]` for `final_standing`; remaining players get Swiss `standing` offset by `len(top_cut_standings)`; sort ascending by `final_standing`; each result: `{cardeio_user_id, display_name, final_standing, wins, total_players, image_url, team_name}`; handles Swiss-only (empty `top_cut_standings`)
- [ ] T019 [P] [US3] Implement `POST /api/explorer/events/preview` in `web-app/routes/api/explorer.py` — `@require_explorer_admin`; body `{url, season_id}`; duplicate check via `repo.get_event_by_cardeio_id()`; calls `ExplorerService().fetch_event_data(url)`; returns preview dict without saving; maps `ValueError` → 400, `ExplorerFetchError` → 502, duplicate → 409
- [ ] T020 [US3] Implement `POST /api/explorer/events` in `web-app/routes/api/explorer.py` — `@require_explorer_admin`; same duplicate check; fetches via service; calls `repo.create_event()` then `repo.save_results()`; returns 201 with saved event summary
- [ ] T021 [US3] Implement `DELETE /api/explorer/events/<int:event_id>` in `web-app/routes/api/explorer.py` — `@require_explorer_admin`; calls `repo.delete_event()`; 404 if not found
- [ ] T022 [US3] Add to `web-app/frontend/src/api/explorer.js`: `previewEvent(url, seasonId)`, `saveEvent(url, seasonId)`, `deleteEvent(eventId)`
- [ ] T023 [US3] Create `web-app/frontend/src/components/explorer/AddEventModal.jsx` — two-step: (1) URL input + season selector → calls `previewEvent()` → shows preview table (event name, date, venue, player count, standings list with standing/wins columns); (2) Confirm saves via `saveEvent()`; error states for 400 (bad URL), 409 (duplicate), 502 (fetch failed); cancel resets to step 1

**Checkpoint**: Explorer admin pastes a real sorcerytcg.com URL, previews results with wins, confirms import; event appears in season event list; duplicate rejected

---

## Phase 6: User Story 5 — Leaderboard Computation

**Goal**: Compute three-track standings (Pathfinder, Persecutor, Grand Explorer) from stored event results.

**Independent Test**: After importing the example event from spec.md, `GET /api/explorer/leaderboard/{season_id}` returns Brandon P with `{pathfinder: 10, persecutor: 10, grand_explorer: 20}` and Tony D with `{pathfinder: 13, persecutor: 0, grand_explorer: 13}`.

- [ ] T024 [US5] Add `compute_leaderboard(season_id: int) -> dict` to `web-app/services/explorer.py`: (1) fetch season + parse `points_config` (fall back to `DEFAULT_POINTS_CONFIG`); (2) fetch all results via `repo.get_results_for_season(season_id)`; (3) group by `cardeio_user_id`; per-player per-event: `pathfinder = config["participation"] + config["bonus_pathfinder"].get(str(wins), 0)`, `persecutor = config["persecutor"].get(str(final_standing), 0)`, `grand_explorer = pathfinder + persecutor`; (4) aggregate season totals; `qualified = persecutor_total >= config["trials_threshold"]`; (5) sort by `grand_explorer` desc then `persecutor_total` desc then `pathfinder_total` desc; (6) return full response shape per contracts/explorer-api.md
- [ ] T025 [US5] Implement `GET /api/explorer/leaderboard/<int:season_id>` in `web-app/routes/api/explorer.py` — public; calls `ExplorerService().compute_leaderboard(season_id)`; 404 if season not found
- [ ] T026 [US5] Add `fetchLeaderboard(seasonId)` to `web-app/frontend/src/api/explorer.js`

**Checkpoint**: `GET /api/explorer/leaderboard/1` returns correctly computed standings matching spec point examples

---

## Phase 7: User Story 1 — Public Leaderboard Page

**Goal**: The React page that ties together all data and admin components into a single public-facing view.

**Independent Test**: Navigate to `/explorer` — season selector populates; selecting a season loads the three-column table (Grand Explorer, Pathfinder, Persecutor); Qualified badge shows for threshold-reaching players; admin controls visible only when logged in as Explorer admin.

- [ ] T027 [US1] Create `web-app/frontend/src/pages/ExplorerStandings.jsx` — on mount calls `fetchSeasons()` and selects latest; on season change calls `fetchLeaderboard(seasonId)`; table columns: Rank, Avatar+Name, Grand Explorer, Pathfinder, Persecutor, Events, Qualified; expandable rows showing per-event detail (event name, standing, wins, per-track points); admin controls (Add Season button, Add Event button, admin panel toggle) conditional on `user.is_explorer_admin`; loading + error states
- [ ] T028 [US1] Add `is_explorer_admin` field to `/api/me` response — find the `/api/me` endpoint and add `"is_explorer_admin": is_explorer_admin()` to the returned dict; import `is_explorer_admin` from `utils.auth`
- [ ] T029 [US1] Add `/explorer` route in `web-app/frontend/src/App.jsx` — import `ExplorerStandings` from `@/pages/ExplorerStandings`, add `{ path: "/explorer", element: <ExplorerStandings /> }` to router
- [ ] T030 [US1] Add "Explorer" nav link in `web-app/frontend/src/components/layout/Nav.jsx` — link to `/explorer`, visible to all users

**Checkpoint**: Full page renders at `/explorer`; season selector and leaderboard table work end-to-end; admin modals open for authorized users only

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Update `web-app/tests/test_endpoint_auth.py` — add public endpoints (`GET /api/explorer/seasons`, `GET /api/explorer/seasons/<id>/events`, `GET /api/explorer/leaderboard/<id>`) to `KNOWN_PUBLIC_ENDPOINTS`; verify protected endpoints have `_auth_required = True` via the existing introspection test
- [ ] T032 [P] Create `web-app/tests/test_explorer_repo.py` — unit tests for `ExplorerRepository` against a temp in-memory SQLite DB: season CRUD, event CRUD, bulk result save, `get_results_for_season` JOIN, cascade delete, admin add/remove/list/check
- [ ] T033 [P] Create `web-app/tests/test_explorer_service.py` — unit tests for `ExplorerService`: `_merge_standings` with Swiss-only and Swiss+top-8 fixtures; `compute_leaderboard` point math with known inputs (verify Tony D = 13, Brandon P = 20 per event using spec tables); mock `requests.get` for `fetch_event_data` URL validation and error handling
- [ ] T034 [P] Create `web-app/tests/test_explorer_routes.py` — Flask test client tests: season create/list, event preview (mock service), event save/delete, leaderboard endpoint, admin 403 guards

**Checkpoint**: `cd web-app && pytest tests/test_explorer*.py -v` all pass; `pytest tests/test_endpoint_auth.py -v` still passes

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
  └→ Phase 2 (Foundational)
        ├→ Phase 3 (US4 Admin Mgmt)  ─────┐
        └→ Phase 4 (US2 Seasons)           │
              └→ Phase 5 (US3 Events)      │
                    └→ Phase 6 (US5 LB)    │
                          └→ Phase 7 (US1) ┘
                                └→ Phase 8 (Polish)
```

Phases 3 and 4 can run in parallel after Phase 2.

### Parallel Opportunities

| Phase | Parallel Tasks |
|-------|---------------|
| Phase 2 | T004, T005, T006 (different files) |
| Phase 3 | T008, T009 (different endpoints) |
| Phase 4 | T012, T013 (different endpoints) |
| Phase 6 | T025, T026 (after T024) |
| Phase 8 | T031, T032, T033, T034 (all different files) |

---

## Implementation Strategy

### MVP (Fastest working leaderboard)

1. Phase 1 + Phase 2 (infrastructure)
2. Phase 4 T012–T014 backend only (season endpoints)
3. Phase 5 T017–T021 backend only (event import)
4. Phase 6 T024–T025 backend only (leaderboard)
5. **Validate** with curl: standings compute correctly
6. Then add frontend (Phase 7), admin UI (Phase 3), tests (Phase 8)

### Full Delivery

Complete phases in order: 1 → 2 → 3+4 (parallel) → 5 → 6 → 7 → 8

---

## Notes

- `DEFAULT_POINTS_CONFIG` defined once in `web-app/routes/api/explorer.py` (or `services/explorer.py`) and imported where needed
- `ExplorerFetchError` custom exception defined in `web-app/services/explorer.py`
- Win derivation: `tieBreakers.get("points", 0) // 3` — empty `{}` (seen in some API responses) defaults to 0 wins, which is correct
- The `is_explorer_admin` field on `/api/me` lets React show admin controls without a separate auth call
