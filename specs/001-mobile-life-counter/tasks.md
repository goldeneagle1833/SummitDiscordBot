# Tasks: Mobile Life Counter with Match Reporting

**Input**: Design documents from `/specs/001-mobile-life-counter/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-endpoints.md, contracts/notifications.md, quickstart.md

**Tests**: Tests are included as manual testing steps (no automated test suite requested in spec)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Web application structure (from plan.md):
- Backend: `web-app/` (Flask application root)
- Templates: `web-app/templates/`
- Static assets: `web-app/static/`
- Tests: `web-app/tests/`
- Database: `discord-bot/match_records.db` (shared with Discord bot)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create directory structure per plan.md (web-app/routes/api/, services/, repositories/, static/css/pages/, static/js/pages/, static/images/icons/, templates/pages/)
- [ ] T002 [P] Create or source life counter icon asset at web-app/static/images/icons/life-counter.svg
- [ ] T003 [P] Verify element icon assets exist at web-app/static/images/elements/ (water.svg, fire.svg, earth.svg, air.svg) or create placeholders
- [ ] T004 [P] Create database migration script at web-app/migrations/001_add_life_counter_support.sql per data-model.md

**Checkpoint**: Basic file structure and assets ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Run database migration to create match_confirmations table: `sqlite3 discord-bot/match_records.db < web-app/migrations/001_add_life_counter_support.sql`
- [ ] T006 Run database migration to extend match_records table with new columns (submitted_via_life_counter, final_player1_life, final_player2_life)
- [ ] T007 Verify database schema: `sqlite3 discord-bot/match_records.db ".schema match_confirmations"`
- [ ] T008 [P] Create base repository at web-app/repositories/match_confirmation.py with CRUD function stubs (create_confirmation, get_pending_confirmations, update_confirmation_status, get_expired_confirmations)
- [ ] T009 [P] Create base service at web-app/services/match_confirmation.py with business logic stubs (process_confirmation, create_match_report, auto_confirm_expired)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Track Life During Game (Priority: P1) 🎯 MVP

**Goal**: Enable mobile users to track dual-player life totals during games with element selection and additional counters, with session persistence

**Independent Test**: Load /life-counter on mobile device, adjust life totals for both players using +/- buttons, select elements, refresh page and verify state persists, reset counter to start new game

### Implementation for User Story 1

#### Frontend HTML Template

- [ ] T010 [P] [US1] Create base life counter HTML template at web-app/templates/pages/life_counter.html with header, element selector, two player sections, reset button
- [ ] T011 [US1] Add player 1 life display section with decrement/increment buttons (48px touch targets) to life_counter.html
- [ ] T012 [US1] Add player 2 life display section with decrement/increment buttons (48px touch targets) to life_counter.html
- [ ] T013 [US1] Add element icon selector (water, fire, earth, air) to life_counter.html for both players
- [ ] T014 [US1] Add additional counter controls (dice, pyramid, token) to life_counter.html for both players
- [ ] T015 [US1] Add hidden match report button to life_counter.html (shows when life reaches 0 - implemented in US2)

#### Frontend CSS Styling

- [ ] T016 [P] [US1] Create life counter page styles at web-app/static/css/pages/life_counter.css with mobile-first layout (320px-768px viewports)
- [ ] T017 [US1] Implement touch-optimized button styles (48px min tap targets, active state, scale animation) in life_counter.css
- [ ] T018 [US1] Implement life total number display styles (48px-64px font size, transition animations) in life_counter.css
- [ ] T019 [US1] Implement element icon selector styles (grid layout, active state) in life_counter.css
- [ ] T020 [US1] Add scroll locking and bounce prevention styles (overscroll-behavior: none) in life_counter.css

#### Frontend JavaScript Logic

- [ ] T021 [P] [US1] Create JavaScript module at web-app/static/js/pages/life_counter.js with LifeCounterState object (load, save, reset methods using sessionStorage)
- [ ] T022 [US1] Implement state initialization logic in life_counter.js (load from sessionStorage or create default state with life=20, element=null, counters=0)
- [ ] T023 [US1] Implement updateLife(player, amount) function in life_counter.js with state save and UI render
- [ ] T024 [US1] Implement updateElement(player, element) function in life_counter.js with state save and UI render
- [ ] T025 [US1] Implement updateCounter(player, counterType, amount) function in life_counter.js with state save and UI render
- [ ] T026 [US1] Implement renderUI(state) function in life_counter.js to update DOM from state object
- [ ] T027 [US1] Implement reset button handler in life_counter.js (clear sessionStorage, reload default state, render UI)
- [ ] T028 [US1] Add debouncing to sessionStorage writes (max 1 save per 500ms) in life_counter.js
- [ ] T029 [US1] Add haptic feedback (navigator.vibrate(50)) on button press in life_counter.js with graceful degradation
- [ ] T030 [US1] Implement checkForGameEnd(state) function in life_counter.js to show/hide match report button when life reaches 0

#### Backend Route

- [ ] T031 [US1] Add /life-counter page route in web-app/routes/pages.py that renders life_counter.html template
- [ ] T032 [US1] Add route to Flask blueprint registration in web-app/routes/__init__.py

#### Mobile Navbar Integration

- [ ] T033 [US1] Add life counter icon link to mobile navbar in web-app/templates/components/navbar.html (top-right, mobile-only with md:hidden class)
- [ ] T034 [US1] Add life counter icon styles to web-app/static/css/components/navbar.css (w-10 h-10 rounded hover:bg-white/10)
- [ ] T035 [US1] Add active state indicator to navbar when on /life-counter page in navbar.css

#### Manual Testing

- [ ] T036 [US1] Test life counter page on iOS Safari 12+ (load page, adjust life totals, verify state persistence on refresh)
- [ ] T037 [US1] Test life counter page on Android Chrome 80+ (load page, adjust life totals, verify state persistence on refresh)
- [ ] T038 [US1] Test element selection and additional counters on mobile devices
- [ ] T039 [US1] Test reset functionality clears sessionStorage and resets to default state
- [ ] T040 [US1] Test touch target sizes are at least 48px (tap accuracy on real devices)

**Checkpoint**: At this point, User Story 1 should be fully functional - users can track games with life counter, persist state, and reset for new games

---

## Phase 4: User Story 2 - Report Match Results (Priority: P2)

**Goal**: Enable match reporting when a player reaches 0 life, with opponent identification and confirmation request creation

**Independent Test**: Reduce player life to 0, verify report button appears, fill out match report form with opponent info and deck links, submit report, verify confirmation record created in database and success message displayed

### Implementation for User Story 2

#### Database Repository Implementation

- [ ] T041 [P] [US2] Implement create_confirmation() function in web-app/repositories/match_confirmation.py (insert into match_confirmations table, return confirmation_id)
- [ ] T042 [P] [US2] Implement get_pending_confirmations(user_id) function in web-app/repositories/match_confirmation.py (SELECT with status='pending' and opponent_discord_id filter)
- [ ] T043 [P] [US2] Implement check_duplicate_pending() function in web-app/repositories/match_confirmation.py (check for existing pending confirmation within 1 hour for same players)
- [ ] T044 [P] [US2] Implement get_recent_lfg_opponents(user_id, limit) function in web-app/repositories/match_confirmation.py (query match_records for recent opponents)

#### Service Layer Implementation

- [ ] T045 [US2] Implement create_match_report() function in web-app/services/match_confirmation.py (validate input, check for duplicates, create confirmation record, return confirmation_id and expires_at)
- [ ] T046 [US2] Add opponent identification logic to create_match_report() (support discord_username lookup, discord_id direct, lfg_lookup methods)
- [ ] T047 [US2] Add validation to create_match_report() (at least one player life ≤ 0, winner ≠ loser, opponent exists in system)

#### API Endpoints

- [ ] T048 [P] [US2] Create Flask blueprint at web-app/routes/api/life_counter.py with /api/life-counter URL prefix
- [ ] T049 [US2] Implement POST /api/life-counter/match-report endpoint in life_counter.py (parse request JSON, call create_match_report service, return confirmation_id)
- [ ] T050 [US2] Add Flask-Login @login_required decorator to match-report endpoint in life_counter.py
- [ ] T051 [US2] Add error handling to match-report endpoint (400 for validation errors, 409 for duplicates, 401 for auth failures)
- [ ] T052 [US2] Implement GET /api/life-counter/lfg-opponents endpoint in life_counter.py (return recent opponents for auto-fill)
- [ ] T053 [US2] Register life_counter blueprint in web-app/routes/__init__.py

#### Frontend Match Report Form

- [ ] T054 [P] [US2] Add match report modal HTML to life_counter.html (hidden by default, shows when report button clicked)
- [ ] T055 [US2] Add opponent identification dropdown to match report form in life_counter.html (method selection: discord_username, discord_id, lfg_lookup)
- [ ] T056 [US2] Add winner/loser fields to match report form in life_counter.html (auto-populated from life counter state)
- [ ] T057 [US2] Add optional deck URL fields to match report form in life_counter.html (self_deck_url, opponent_deck_url)
- [ ] T058 [US2] Add match report modal styles to life_counter.css (modal overlay, form layout, submit button)

#### Frontend JavaScript for Match Reporting

- [ ] T059 [US2] Implement showMatchReportModal() function in life_counter.js (display modal, pre-fill winner/loser from state)
- [ ] T060 [US2] Implement fetchLFGOpponents() function in life_counter.js (call GET /api/life-counter/lfg-opponents, populate dropdown)
- [ ] T061 [US2] Implement submitMatchReport() function in life_counter.js (build request payload, POST to /api/life-counter/match-report, handle response)
- [ ] T062 [US2] Add error handling to submitMatchReport() (display error messages for 400/409/401, retry logic for network failures with exponential backoff)
- [ ] T063 [US2] Add success handling to submitMatchReport() (display confirmation message, clear sessionStorage, hide modal)
- [ ] T064 [US2] Connect match report button click handler to showMatchReportModal() in life_counter.js

#### Manual Testing

- [ ] T065 [US2] Test match report button appears when any player life reaches 0
- [ ] T066 [US2] Test opponent identification via discord_username lookup
- [ ] T067 [US2] Test opponent identification via discord_id direct entry
- [ ] T068 [US2] Test opponent identification via lfg_lookup auto-fill
- [ ] T069 [US2] Test duplicate prevention (submit report, try submitting again within 1 hour, verify 409 error)
- [ ] T070 [US2] Test match report submission creates confirmation record in database (check match_confirmations table)
- [ ] T071 [US2] Test error handling for invalid opponents (non-existent user, verify 400 error)

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - users can track games AND submit match reports

---

## Phase 5: User Story 3 - Confirm Match Results (Priority: P3)

**Goal**: Enable opponents to receive real-time notifications of match reports and confirm/dispute results, with ELO integration and auto-confirm fallback

**Independent Test**: Submit match report (US2), open different browser/account as opponent, verify SSE notification received, confirm match, verify ELO ratings updated in database and match_records entry created

### Implementation for User Story 3

#### Service Layer for Confirmation Processing

- [ ] T072 [P] [US3] Implement process_confirmation(confirmation_id, action, user_id) function in web-app/services/match_confirmation.py (update status to 'confirmed' or 'disputed')
- [ ] T073 [US3] Implement _finalize_confirmed_match() helper in web-app/services/match_confirmation.py (call existing match.record_match(), update ELO via discord-bot ELO service)
- [ ] T074 [US3] Add ELO integration to _finalize_confirmed_match() (import from discord-bot/services/elo_service.py, calculate ratings, update elo.db)
- [ ] T075 [US3] Add match_records creation to _finalize_confirmed_match() (populate submitted_via_life_counter=1, final_player1_life, final_player2_life)
- [ ] T076 [US3] Implement auto_confirm_expired() function in web-app/services/match_confirmation.py (query expired pending confirmations, process each as 'auto_confirmed')

#### Repository Extensions

- [ ] T077 [P] [US3] Implement update_confirmation_status(confirmation_id, status, confirmed_at, dispute_reason) function in web-app/repositories/match_confirmation.py
- [ ] T078 [P] [US3] Implement get_expired_confirmations() function in web-app/repositories/match_confirmation.py (SELECT where status='pending' AND expires_at <= current_timestamp)
- [ ] T079 [P] [US3] Implement get_confirmation_by_id(confirmation_id) function in web-app/repositories/match_confirmation.py (SELECT single confirmation with all fields)

#### API Endpoints for Confirmation Actions

- [ ] T080 [P] [US3] Implement POST /api/life-counter/confirm/{confirmation_id} endpoint in web-app/routes/api/life_counter.py (call process_confirmation with action='confirm', return ELO changes)
- [ ] T081 [P] [US3] Implement POST /api/life-counter/dispute/{confirmation_id} endpoint in web-app/routes/api/life_counter.py (call process_confirmation with action='dispute', return success)
- [ ] T082 [P] [US3] Implement GET /api/life-counter/pending-confirmations endpoint in web-app/routes/api/life_counter.py (return all pending confirmations for current user)
- [ ] T083 [US3] Add authorization checks to confirm/dispute endpoints (verify current_user is opponent_discord_id)
- [ ] T084 [US3] Add error handling for invalid confirmation IDs (404), already processed (410), unauthorized (403)

#### SSE Notification Service

- [ ] T085 [P] [US3] Create notification service at web-app/services/notification.py with format_confirmation_payload() and format_update_payload() helpers
- [ ] T086 [P] [US3] Create SSE blueprint at web-app/routes/api/notifications.py with /api/notifications URL prefix
- [ ] T087 [US3] Implement GET /api/notifications/stream SSE endpoint in notifications.py (stream_with_context generator, Flask-Login required)
- [ ] T088 [US3] Add initial heartbeat and pending confirmations send on SSE connection open in notifications.py
- [ ] T089 [US3] Add 5-second polling loop in SSE generator (check for new pending_confirmation events for current_user)
- [ ] T090 [US3] Add 30-second heartbeat events in SSE generator (yield heartbeat event with timestamp)
- [ ] T091 [US3] Add confirmation_update event detection in SSE generator (when opponent confirms/disputes report you submitted)
- [ ] T092 [US3] Register notifications blueprint in web-app/routes/__init__.py

#### Frontend Confirmation Modal

- [ ] T093 [P] [US3] Add confirmation request modal HTML to life_counter.html (displays when SSE event received, shows match details)
- [ ] T094 [US3] Add confirm/dispute buttons to confirmation modal in life_counter.html
- [ ] T095 [US3] Add confirmation modal styles to life_counter.css (modal overlay, match details layout, action buttons)

#### Frontend SSE Client

- [ ] T096 [P] [US3] Implement connectSSE() function in life_counter.js (create EventSource for /api/notifications/stream)
- [ ] T097 [US3] Add pending_confirmation event listener in life_counter.js (parse event.data JSON, call showConfirmationModal())
- [ ] T098 [US3] Add confirmation_update event listener in life_counter.js (parse event.data JSON, display toast notification with ELO changes)
- [ ] T099 [US3] Add heartbeat event listener in life_counter.js (update lastHeartbeat timestamp)
- [ ] T100 [US3] Implement SSE error handling and reconnection logic in life_counter.js (max 5 reconnect attempts with 5s delay)
- [ ] T101 [US3] Implement fallbackToPolling() function in life_counter.js (setInterval to poll /api/life-counter/pending-confirmations every 30s)
- [ ] T102 [US3] Add disconnectSSE() cleanup on page unload in life_counter.js

#### Frontend Confirmation Actions

- [ ] T103 [P] [US3] Implement confirmMatch(confirmation_id) function in life_counter.js (POST to /api/life-counter/confirm/{id}, display success toast with ELO changes)
- [ ] T104 [P] [US3] Implement disputeMatch(confirmation_id, reason) function in life_counter.js (POST to /api/life-counter/dispute/{id}, display dispute confirmation)
- [ ] T105 [US3] Connect confirm button to confirmMatch() handler in life_counter.js
- [ ] T106 [US3] Connect dispute button to disputeMatch() handler in life_counter.js

#### Cron Job for Auto-Confirm

- [ ] T107 [US3] Create auto-confirm cron script at web-app/scripts/auto_confirm_matches.py (call auto_confirm_expired service function, log results)
- [ ] T108 [US3] Add crontab entry to run auto_confirm_matches.py every 15 minutes (*/15 * * * *)

#### Manual Testing

- [ ] T109 [US3] Test SSE connection establishes on page load for logged-in users
- [ ] T110 [US3] Test pending_confirmation event triggers modal display when match report submitted by another user
- [ ] T111 [US3] Test confirm action updates database (status='confirmed'), creates match_records entry, updates ELO ratings
- [ ] T112 [US3] Test dispute action updates database (status='disputed'), does NOT create match_records or update ELO
- [ ] T113 [US3] Test confirmation_update event notifies submitter when opponent confirms/disputes
- [ ] T114 [US3] Test SSE reconnection logic when connection drops (disconnect WiFi, verify reconnection after 5s)
- [ ] T115 [US3] Test fallback to polling when SSE fails after 5 reconnect attempts
- [ ] T116 [US3] Test auto-confirm cron job (create pending confirmation, manually set expires_at to past timestamp, run script, verify status='auto_confirmed' and ELO updated)

**Checkpoint**: All user stories should now be independently functional - complete match lifecycle from tracking to reporting to confirmation

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T117 [P] Add loading spinners to match report submission and confirmation actions in life_counter.js
- [ ] T118 [P] Add visual feedback for successful/failed actions (toast notifications with color coding) in life_counter.js
- [ ] T119 [P] Optimize sessionStorage write debouncing (test with rapid button clicks, verify max 2 writes per second) in life_counter.js
- [ ] T120 [P] Test life counter on tablet devices (iPad, Android tablets) to verify responsive layout works at 768px+ viewports
- [ ] T121 Add aria-label attributes to all buttons for screen reader accessibility in life_counter.html
- [ ] T122 Test keyboard navigation support (tab through buttons, enter to activate) on life counter page
- [ ] T123 Add error logging for SSE connection failures (log to server-side error log) in notifications.py
- [ ] T124 Add rate limiting to match report endpoint (10 requests per hour per user) in life_counter.py
- [ ] T125 Verify all database queries use indexes (check EXPLAIN QUERY PLAN for match_confirmations queries)
- [ ] T126 Run quickstart.md validation checklist (verify all manual testing steps pass)
- [ ] T127 Create deployment checklist (verify migrations run on staging, SSE works with Nginx, cron job scheduled)
- [ ] T128 Update CLAUDE.md with life counter feature documentation (add to web-app routes section)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User Story 1 (P1): Can start after Foundational - No dependencies on other stories
  - User Story 2 (P2): Can start after Foundational - Integrates with US1 UI (match report button) but US1 can function without US2
  - User Story 3 (P3): Can start after Foundational - Integrates with US2 (confirmation processing) but US2 can function with auto-confirm only
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Completely independent - can be deployed alone as MVP
- **User Story 2 (P2)**: Extends US1 (adds match report button) - can function independently with confirmation creation
- **User Story 3 (P3)**: Extends US2 (adds confirmation processing) - US2 would work with auto-confirm only, US3 adds interactive confirmation

### Within Each User Story

- Frontend HTML/CSS can be developed in parallel with backend services/APIs
- JavaScript depends on HTML structure being complete
- API endpoints depend on service layer being complete
- Service layer depends on repository layer being complete
- Manual testing depends on all implementation tasks being complete

### Parallel Opportunities

**Phase 1 (Setup)**: All 4 tasks can run in parallel (T001-T004)

**Phase 2 (Foundational)**: Tasks T008-T009 can run in parallel (repository and service stubs)

**Phase 3 (US1)**:
- T010, T016, T021 can run in parallel (HTML, CSS, JS initialization)
- T011-T015 can run in sequence after T010 (HTML structure)
- T017-T020 can run in sequence after T016 (CSS styles)
- T022-T030 can run in sequence after T021 (JS logic)
- T033-T034 can run in parallel (navbar HTML and CSS)

**Phase 4 (US2)**:
- T041-T044 can run in parallel (repository functions)
- T048, T054, T055 can run in parallel (API blueprint, modal HTML)
- T059-T064 can run in parallel with API development (frontend JS)

**Phase 5 (US3)**:
- T072-T076 can run in sequence (service layer with ELO integration)
- T077-T079 can run in parallel (repository functions)
- T080-T082 can run in parallel (API endpoints)
- T085-T086 can run in parallel (notification service and blueprint setup)
- T093-T095 can run in parallel (confirmation modal HTML/CSS)
- T096-T102 can run in parallel with API development (SSE client)
- T103-T106 can run in parallel (confirmation action functions)

**Phase 6 (Polish)**: T117-T125 can run in parallel (different concerns)

---

## Parallel Example: User Story 1

```bash
# Launch all initial foundation tasks together:
Task T010: "Create base life counter HTML template"
Task T016: "Create life counter page styles"
Task T021: "Create JavaScript module with LifeCounterState"

# Launch all repository tasks together (User Story 2):
Task T041: "Implement create_confirmation() function"
Task T042: "Implement get_pending_confirmations() function"
Task T043: "Implement check_duplicate_pending() function"
Task T044: "Implement get_recent_lfg_opponents() function"

# Launch all SSE-related tasks together (User Story 3):
Task T085: "Create notification service"
Task T086: "Create SSE blueprint"
Task T093: "Add confirmation request modal HTML"
Task T094: "Add confirm/dispute buttons"
Task T095: "Add confirmation modal styles"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. ✅ Complete Phase 1: Setup (T001-T004)
2. ✅ Complete Phase 2: Foundational (T005-T009)
3. ✅ Complete Phase 3: User Story 1 (T010-T040)
4. **STOP and VALIDATE**: Test User Story 1 independently on real mobile devices
5. Deploy/demo life counter for casual game tracking (no match reporting yet)

**Result**: Functional life counter that tracks games locally - delivers value immediately

### Incremental Delivery

1. ✅ Setup + Foundational → Foundation ready (T001-T009)
2. ✅ Add User Story 1 → Test independently → **Deploy MVP** (T010-T040)
3. ✅ Add User Story 2 → Test independently → Deploy match reporting (T041-T071)
4. ✅ Add User Story 3 → Test independently → Deploy full confirmation flow (T072-T116)
5. ✅ Polish → Deploy final version (T117-T128)

Each story adds value without breaking previous stories.

### Parallel Team Strategy

With 2-3 developers:

1. **Team completes Setup + Foundational together** (1-2 hours)
2. **Once Foundational is done**:
   - Developer A: User Story 1 (frontend-focused) - Day 1-2
   - Developer B: User Story 2 (backend-focused) - Day 1-2
   - Developer C: User Story 3 (full-stack) - Day 2-3
3. **Integration**: User Story 2 connects to US1's UI, User Story 3 connects to US2's confirmation data
4. **Testing**: Each developer tests their story independently, then integration test

**Timeline**: 3-5 days with 1 developer, 2-3 days with parallel team

---

## Task Statistics

- **Total Tasks**: 128 tasks
- **Setup Phase**: 4 tasks
- **Foundational Phase**: 5 tasks
- **User Story 1 (P1)**: 31 tasks (24% of total)
- **User Story 2 (P2)**: 31 tasks (24% of total)
- **User Story 3 (P3)**: 45 tasks (35% of total)
- **Polish Phase**: 12 tasks (9% of total)

- **Parallelizable Tasks**: 47 tasks marked [P] (37% can run in parallel)
- **Sequential Tasks**: 81 tasks (63% have dependencies)

- **Frontend Tasks**: ~45 tasks (HTML, CSS, JavaScript)
- **Backend Tasks**: ~55 tasks (API, services, repositories, database)
- **Testing Tasks**: ~20 tasks (manual testing on devices)
- **Infrastructure Tasks**: ~8 tasks (setup, migrations, cron)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- No automated tests included (not requested in spec) - manual testing on real devices recommended
- Commit after each task or logical group of related tasks
- Stop at any checkpoint to validate story independently
- Verify all database queries use proper indexes before production deployment
- Test SSE with Nginx reverse proxy before production (SSE can have proxy issues)
- Ensure element icon assets exist or create simple SVG placeholders
