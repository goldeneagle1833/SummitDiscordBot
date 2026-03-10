# Tasks: Web-Based Match Reporting Modal

**Input**: Design documents from `/specs/001-web-match-report-modal/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api-endpoints.md

**Tests**: Not explicitly requested in specification - tasks focus on implementation and manual QA

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `web-app/` directory with Flask backend + static frontend
- **Database**: `discord-bot/match_records.db` (shared database)
- Paths use absolute references from repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency management

- [ ] T001 Add APScheduler==3.10.4 to web-app/requirements.txt
- [ ] T002 Install new dependencies with pip install -r web-app/requirements.txt

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database Migration

- [ ] T003 Create migration script at specs/001-web-match-report-modal/migration.sql with ALTER TABLE and CREATE INDEX statements from data-model.md
- [ ] T004 Run database migration on discord-bot/match_records.db to add went_first and reminder_sent_at columns
- [ ] T005 Verify migration success by querying table schema and checking indexes exist

### Repository Layer Extensions

- [ ] T006 [P] Add went_first parameter support to create_confirmation() method in web-app/repositories/match_confirmation.py
- [ ] T007 [P] Add get_confirmations_needing_reminder() method in web-app/repositories/match_confirmation.py (24hr filter, reminder_sent_at IS NULL)
- [ ] T008 [P] Add update_reminder_sent() method in web-app/repositories/match_confirmation.py to set reminder_sent_at timestamp
- [ ] T009 [P] Update get_expired_confirmations() to use 48hr expiration (was 24hr) in web-app/repositories/match_confirmation.py
- [ ] T010 [P] Add search_user_profiles_by_name() method in web-app/repositories/user_profiles.py for opponent autocomplete

### Service Layer Core Methods

- [ ] T011 Implement validate_match_report_input() method in web-app/services/match_confirmation.py (checks opponent, deck URL, turn order)
- [ ] T012 Implement calculate_winner_loser() helper method in web-app/services/match_confirmation.py (maps submitter result to winner/loser IDs)
- [ ] T013 Add logging configuration for match reporting operations in web-app/services/match_confirmation.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Stories 1 & 2 - Match Report Submission (Priority: P1) 🎯 MVP

**Goal**: Enable users to submit match reports (win or loss) via web modal with opponent search, deck URLs, and turn order selection

**Independent Test**: Log into website → open life counter page → trigger match report modal → search for opponent → enter deck URL → select turn order → click "I Won" or "I Lost" → verify pending match report created in database with correct winner/loser and all fields

**Covers**:
- User Story 1: Report Match Victory
- User Story 2: Report Match Loss (same UI, different result parameter)
- User Story 4: Cancel Match Report (cancel button in modal)

### Backend Implementation

#### API Routes

- [ ] T014 Create new Blueprint in web-app/routes/api/match_reporting.py and import dependencies (Flask, jsonify, request, session, services)
- [ ] T015 [P] [US1] Implement GET /api/match-report/search-opponents endpoint in web-app/routes/api/match_reporting.py (calls service layer, returns JSON)
- [ ] T016 [US1] Implement POST /api/match-report/submit endpoint in web-app/routes/api/match_reporting.py (validates auth, calls service.create_match_report())
- [ ] T017 Register match_reporting_bp blueprint in web-app/app.py with url_prefix='/api/match-report'

#### Service Layer Business Logic

- [ ] T018 [US1] Implement create_match_report() method in web-app/services/match_confirmation.py (validation → duplicate check → repo.create_confirmation())
- [ ] T019 [US1] Implement search_opponents() method in web-app/services/match_confirmation.py (2-tier: recent opponents → user_profiles search)
- [ ] T020 [US1] Add duplicate pending report detection in create_match_report() method (within 1 hour, same opponent)
- [ ] T021 [US1] Add deck URL validation (regex pattern) in validate_match_report_input() method

### Frontend Implementation

#### HTML Structure

- [ ] T022 [P] [US1] Update match report modal HTML structure in web-app/templates/pages/life_counter.html (opponent search input, deck URL inputs, turn order buttons)
- [ ] T023 [P] [US1] Add turn order toggle button group to modal body in web-app/templates/pages/life_counter.html (First/Second with ButtonGroup styling)
- [ ] T024 [P] [US1] Update modal footer buttons in web-app/templates/pages/life_counter.html (Cancel, I Lost, I Won with correct color schemes)
- [ ] T025 [P] [US1] Add loading indicator HTML in web-app/templates/pages/life_counter.html (spinner shown during submission)
- [ ] T026 [P] [US1] Add success/error message containers in web-app/templates/pages/life_counter.html (toast-style notifications)

#### CSS Styling

- [ ] T027 [P] [US1] Add modal base styles in web-app/static/css/pages/life_counter.css (overlay, centered content, backdrop)
- [ ] T028 [P] [US1] Add form field styles in web-app/static/css/pages/life_counter.css (input groups, labels, error states)
- [ ] T029 [P] [US1] Add button styles for turn order toggle in web-app/static/css/pages/life_counter.css (selected blue, unselected gray)
- [ ] T030 [P] [US1] Add action button styles in web-app/static/css/pages/life_counter.css (Cancel gray, I Won green, I Lost red)
- [ ] T031 [P] [US1] Add loading indicator styles in web-app/static/css/pages/life_counter.css (spinner animation, disabled state overlay)
- [ ] T032 [P] [US1] Add responsive mobile styles in web-app/static/css/pages/life_counter.css (modal full-screen on mobile, adjusted spacing)

#### JavaScript Logic

- [ ] T033 [US1] Create formState object in web-app/static/js/pages/life_counter.js (tracks opponentSelected, deckUrlValid, turnOrderSelected, isSubmitting)
- [ ] T034 [US1] Implement opponent autocomplete in web-app/static/js/pages/life_counter.js (debounce 300ms, fetch /search-opponents, display results dropdown)
- [ ] T035 [US1] Implement deck URL validation in web-app/static/js/pages/life_counter.js (regex check on blur, show/hide error message)
- [ ] T036 [US1] Implement turn order toggle logic in web-app/static/js/pages/life_counter.js (First/Second button click handlers, update formState)
- [ ] T037 [US1] Implement updateSubmitButtons() function in web-app/static/js/pages/life_counter.js (enable/disable based on formState)
- [ ] T038 [US1] Implement handleSubmitReport() function in web-app/static/js/pages/life_counter.js (POST /submit, show loading, handle success/error)
- [ ] T039 [US1] Wire up "I Won" button click handler in web-app/static/js/pages/life_counter.js (calls handleSubmitReport with result='won')
- [ ] T040 [US1] Wire up "I Lost" button click handler in web-app/static/js/pages/life_counter.js (calls handleSubmitReport with result='lost')
- [ ] T041 [US1] Wire up "Cancel" button and X close button click handlers in web-app/static/js/pages/life_counter.js (closeModal, reset formState)
- [ ] T042 [US1] Implement modal open/close animations in web-app/static/js/pages/life_counter.js (add/remove 'hidden' class with CSS transitions)

**Checkpoint**: At this point, users can submit match reports (win/loss) with all validation. Reports are saved as pending in database. Cancel functionality works. Test independently before proceeding.

---

## Phase 4: User Story 3 - Match Confirmation/Denial (Priority: P2)

**Goal**: Enable users to view pending match confirmation requests from opponents and confirm or deny them, finalizing matches or rejecting reports

**Independent Test**: Have opponent submit match report → log in as opponent's opponent → see pending confirmation notification → open confirmation modal → review match details → click "Confirm" → verify match record created, ELO updated, both players notified. Repeat with "Deny" to verify rejection flow.

### Backend Implementation

#### API Routes

- [ ] T043 [P] [US3] Implement GET /api/match-report/pending endpoint in web-app/routes/api/match_reporting.py (fetch user's pending confirmations)
- [ ] T044 [P] [US3] Implement GET /api/match-report/confirmation/{id} endpoint in web-app/routes/api/match_reporting.py (get specific confirmation details)
- [ ] T045 [US3] Implement POST /api/match-report/confirm/{id} endpoint in web-app/routes/api/match_reporting.py (validate auth, call service.process_confirmation with action='confirm')
- [ ] T046 [US3] Implement POST /api/match-report/deny/{id} endpoint in web-app/routes/api/match_reporting.py (validate auth, call service.process_confirmation with action='deny')

#### Service Layer Business Logic

- [ ] T047 [US3] Implement process_confirmation() method in web-app/services/match_confirmation.py (validate → confirm or deny → update status)
- [ ] T048 [US3] Implement _finalize_confirmed_match() helper in web-app/services/match_confirmation.py (create match_records entry, call ELO service, atomic transaction)
- [ ] T049 [US3] Add authorization check in process_confirmation() (verify current user is opponent_discord_id) in web-app/services/match_confirmation.py
- [ ] T050 [US3] Add double-submission prevention in process_confirmation() (check status not already confirmed/denied) in web-app/services/match_confirmation.py

### Frontend Implementation

#### HTML Structure

- [ ] T051 [P] [US3] Update confirmation modal HTML structure in web-app/templates/pages/life_counter.html (match details display, confirm/deny buttons)
- [ ] T052 [P] [US3] Add pending confirmation badge/indicator in header in web-app/templates/pages/life_counter.html (shows count when > 0)
- [ ] T053 [P] [US3] Add match details section in confirmation modal body in web-app/templates/pages/life_counter.html (opponent name, result, deck URL, turn order)

#### CSS Styling

- [ ] T054 [P] [US3] Add confirmation modal styles in web-app/static/css/pages/life_counter.css (similar to report modal, adjusted for read-only content)
- [ ] T055 [P] [US3] Add match details display styles in web-app/static/css/pages/life_counter.css (info grid, labeled fields, deck URL links)
- [ ] T056 [P] [US3] Add confirm/deny button styles in web-app/static/css/pages/life_counter.css (green confirm, red deny, disabled states)
- [ ] T057 [P] [US3] Add pending badge styles in web-app/static/css/pages/life_counter.css (notification dot, count bubble in header)

#### JavaScript Logic

- [ ] T058 [US3] Implement pending confirmation polling in web-app/static/js/pages/life_counter.js (fetch /pending every 30s, update badge count)
- [ ] T059 [US3] Implement loadPendingConfirmations() function in web-app/static/js/pages/life_counter.js (GET /pending, populate modal if confirmations exist)
- [ ] T060 [US3] Implement displayConfirmationModal() function in web-app/static/js/pages/life_counter.js (show match details, wire up buttons)
- [ ] T061 [US3] Implement handleConfirmMatch() function in web-app/static/js/pages/life_counter.js (POST /confirm/{id}, show loading, handle success/error, display toast)
- [ ] T062 [US3] Implement handleDenyMatch() function in web-app/static/js/pages/life_counter.js (POST /deny/{id}, show loading, handle success/error, display toast)
- [ ] T063 [US3] Wire up "Confirm" button click handler in web-app/static/js/pages/life_counter.js (calls handleConfirmMatch)
- [ ] T064 [US3] Wire up "Deny" button click handler in web-app/static/js/pages/life_counter.js (calls handleDenyMatch)
- [ ] T065 [US3] Update polling to refresh pending count after confirm/deny in web-app/static/js/pages/life_counter.js

**Checkpoint**: At this point, users can see pending confirmations, review details, and confirm or deny reports. Matches are finalized with ELO updates on confirmation. Test independently.

---

## Phase 5: Background Jobs - Expiration & Reminders (Cross-Cutting)

**Goal**: Implement automated 24-hour reminder notifications and 48-hour expiration for pending match reports

**Independent Test**: Create test match report → mock time to 24hr later → verify reminder sent → mock time to 48hr later → verify report expired and marked void → verify both players notified

### Background Scheduler Setup

- [ ] T066 Import APScheduler in web-app/app.py (from apscheduler.schedulers.background import BackgroundScheduler)
- [ ] T067 Create scheduler instance in web-app/app.py (scheduler = BackgroundScheduler())
- [ ] T068 Implement send_pending_reminders() job function in web-app/services/match_confirmation.py (queries confirmations needing reminder, sends notifications)
- [ ] T069 Implement expire_old_reports() job function in web-app/services/match_confirmation.py (queries expired reports, updates status, sends notifications)
- [ ] T070 Register reminder job in web-app/app.py (scheduler.add_job(send_pending_reminders, 'interval', minutes=5))
- [ ] T071 Register expiration job in web-app/app.py (scheduler.add_job(expire_old_reports, 'interval', minutes=15))
- [ ] T072 Start scheduler in web-app/app.py after app initialization (scheduler.start())
- [ ] T073 Add graceful shutdown handling in web-app/app.py (scheduler.shutdown on SIGTERM/SIGINT)

### Notification Logic

- [ ] T074 [P] Implement send_reminder_notification() helper in web-app/services/match_confirmation.py (logs reminder, updates reminder_sent_at)
- [ ] T075 [P] Implement send_expiration_notification() helper in web-app/services/match_confirmation.py (logs expiration, notifies both players)
- [ ] T076 Add error handling and retry logic for notification failures in web-app/services/match_confirmation.py

**Checkpoint**: Background jobs run automatically. Reminders sent at 24hr, reports expire at 48hr. Test with mocked time or wait for real-time triggers.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, error handling, and deployment readiness

### Error Handling & Edge Cases

- [ ] T077 [P] Add self-reporting prevention check in web-app/services/match_confirmation.py (submitter_id != opponent_id)
- [ ] T078 [P] Add graceful Curiosa API failure handling in web-app/services/match_confirmation.py (optional validation, log warning if API down)
- [ ] T079 [P] Add concurrent submission race condition handling in web-app/repositories/match_confirmation.py (database-level checks)
- [ ] T080 Add comprehensive error logging for all API endpoints in web-app/routes/api/match_reporting.py (logger.error with exc_info=True)

### Security & Validation

- [ ] T081 [P] Add session authentication checks to all API endpoints in web-app/routes/api/match_reporting.py (verify user_id in session)
- [ ] T082 [P] Add authorization checks to confirm/deny endpoints in web-app/routes/api/match_reporting.py (verify user is opponent)
- [ ] T083 [P] Add input sanitization for all user inputs in web-app/services/match_confirmation.py (prevent XSS, SQL injection)

### Performance Optimization

- [ ] T084 [P] Add database query performance logging in web-app/repositories/match_confirmation.py (log slow queries > 100ms)
- [ ] T085 [P] Verify all indexes are used with EXPLAIN QUERY PLAN on key queries in web-app/repositories/match_confirmation.py

### Documentation & Deployment

- [ ] T086 Update web-app README with match reporting feature documentation (setup, usage, API endpoints)
- [ ] T087 Add deployment notes to specs/001-web-match-report-modal/quickstart.md (production checklist, migration steps)
- [ ] T088 Create runbook for troubleshooting common issues in specs/001-web-match-report-modal/ (e.g., stuck pending reports, scheduler not running)

### Manual QA Testing

- [ ] T089 Run manual QA checklist from plan.md (authentication, opponent search, deck validation, turn order, submission, confirmation, denial, expiration)
- [ ] T090 Test mobile responsive design on iOS and Android devices (modal layout, button sizes, touch interactions)
- [ ] T091 Test error scenarios (network failures, API timeouts, duplicate submissions, invalid inputs)
- [ ] T092 Verify translation keys work correctly (if i18n system configured, test with different locales)

### Production Deployment

- [ ] T093 Backup discord-bot/match_records.db before migration on production
- [ ] T094 Run database migration on production database (test rollback procedure first)
- [ ] T095 Deploy web-app code to production server (git pull, pip install, restart systemd service)
- [ ] T096 Verify background scheduler starts successfully on production (check logs for job registrations)
- [ ] T097 Monitor production logs for first 24 hours after deployment (watch for errors, performance issues)
- [ ] T098 Run smoke tests on production (submit match report, confirm, verify database updated correctly)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories 1 & 2 (Phase 3)**: Depends on Foundational phase completion
- **User Story 3 (Phase 4)**: Depends on Foundational phase completion (can run parallel to Phase 3 with different developers)
- **Background Jobs (Phase 5)**: Depends on Phase 2 (repository/service methods) - can run parallel to frontend work
- **Polish (Phase 6)**: Depends on Phases 3-5 being functional

### User Story Dependencies

- **User Stories 1 & 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Independent of Phase 3 backend, but needs Phase 3 frontend to have full flow
- **Background Jobs (Phase 5)**: Can start after Foundational repository methods - Independent of user story UI implementation

### Within Each User Story

**Phase 3 (US1 & US2)**:
- Backend API routes can start after foundational (T014-T021)
- Frontend HTML/CSS can start in parallel (T022-T032)
- Frontend JavaScript depends on API routes being defined (T033-T042)

**Phase 4 (US3)**:
- Backend API routes can start independently (T043-T050)
- Frontend HTML/CSS can start in parallel (T051-T057)
- Frontend JavaScript depends on API routes (T058-T065)

**Phase 5 (Background Jobs)**:
- Scheduler setup depends on service methods (T066-T073)
- Notification logic can be developed in parallel (T074-T076)

### Parallel Opportunities

**Phase 1 (Setup)**: Both tasks are sequential (dependency installation)

**Phase 2 (Foundational)**:
- T006-T010 (Repository methods) can ALL run in parallel - different methods, no conflicts
- T011-T013 (Service methods) are sequential within service, but can overlap with repository work

**Phase 3 (US1 & US2)**:
- T015 (search-opponents endpoint) can run parallel to T016 (submit endpoint) - different routes
- T022-T026 (HTML structure) can ALL run in parallel with backend work and with each other - different sections of template
- T027-T032 (CSS styles) can ALL run in parallel with backend and HTML - separate stylesheet
- T033-T042 (JavaScript) are partially sequential (formState setup first), but T034-T036 (autocomplete, validation, toggle) can run in parallel after T033

**Phase 4 (US3)**:
- T043-T044 (GET endpoints) can run in parallel
- T045-T046 (POST endpoints) can run in parallel
- T051-T053 (HTML structure) can ALL run in parallel
- T054-T057 (CSS styles) can ALL run in parallel
- T058-T065 (JavaScript) have some dependencies but T060-T062 can overlap

**Phase 5 (Background Jobs)**:
- T074-T075 (notification helpers) can run in parallel

**Phase 6 (Polish)**:
- T077-T079 (error handling) can ALL run in parallel - different files/methods
- T081-T083 (security) can ALL run in parallel - different concerns
- T084-T085 (performance) can run in parallel

---

## Parallel Example: Phase 3 (User Stories 1 & 2)

```bash
# Launch all repository extensions in parallel (Phase 2):
Task T006: "Add went_first parameter to create_confirmation() in match_confirmation.py"
Task T007: "Add get_confirmations_needing_reminder() method"
Task T008: "Add update_reminder_sent() method"
Task T009: "Update get_expired_confirmations() to 48hr"
Task T010: "Add search_user_profiles_by_name() method"

# Launch backend + frontend HTML + CSS in parallel (Phase 3):
Task T014: "Create match_reporting.py blueprint"
Task T022: "Update match report modal HTML structure"
Task T027: "Add modal base styles in CSS"

# Launch all HTML sections together (Phase 3):
Task T023: "Add turn order toggle HTML"
Task T024: "Update modal footer buttons"
Task T025: "Add loading indicator HTML"
Task T026: "Add success/error message containers"

# Launch all CSS styling together (Phase 3):
Task T028: "Add form field styles"
Task T029: "Add button styles for turn order toggle"
Task T030: "Add action button styles"
Task T031: "Add loading indicator styles"
Task T032: "Add responsive mobile styles"
```

---

## Implementation Strategy

### MVP First (Phases 1-3 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T013) - CRITICAL BLOCKER
3. Complete Phase 3: User Stories 1 & 2 (T014-T042)
4. **STOP and VALIDATE**: Test match report submission independently
   - Submit win report → verify pending confirmation created
   - Submit loss report → verify opponent marked as winner
   - Test cancel functionality → verify no data saved
   - Test all validation rules → verify buttons disabled appropriately
5. Deploy/demo if ready (basic match reporting works, confirmation manual for now)

### Incremental Delivery

1. **Foundation**: Complete Phase 1 + Phase 2 → Database ready, services stubbed
2. **MVP (Match Submission)**: Add Phase 3 → Test independently → Deploy/Demo
   - Users can submit match reports via web
   - Reports are pending awaiting confirmation
   - Cancel works, validation works
3. **Confirmation Flow**: Add Phase 4 → Test independently → Deploy/Demo
   - Opponents can confirm or deny reports
   - Matches finalized with ELO updates
   - Full two-phase workflow operational
4. **Automation**: Add Phase 5 → Test with mocked time → Deploy/Demo
   - 24hr reminders automated
   - 48hr expiration automated
   - System self-maintains pending reports
5. **Polish**: Add Phase 6 → Final QA → Production deployment
   - Error handling robust
   - Security hardened
   - Performance optimized
   - Ready for production load

### Parallel Team Strategy

With 3 developers:

**Week 1: Foundation + Parallel Story Work**
1. All devs: Complete Phase 1 + Phase 2 together (pair on complex migrations)
2. Once Phase 2 done:
   - **Developer A**: Phase 3 Backend (T014-T021)
   - **Developer B**: Phase 3 Frontend HTML/CSS (T022-T032)
   - **Developer C**: Phase 5 Background Jobs (T066-T076)

**Week 2: Confirmation + Polish**
3. After Phase 3 backend complete:
   - **Developer A**: Phase 3 JavaScript (T033-T042)
   - **Developer B**: Phase 4 Backend (T043-T050)
   - **Developer C**: Continue Phase 5, then start Phase 6 polish

4. After Phase 4 backend complete:
   - **Developer B**: Phase 4 Frontend (T051-T065)
   - **Developer A + C**: Phase 6 polish tasks in parallel

5. All devs: Final integration testing, manual QA, deployment (T089-T098)

---

## Task Summary

**Total Tasks**: 98

**By Phase**:
- Phase 1 (Setup): 2 tasks
- Phase 2 (Foundational): 11 tasks (CRITICAL BLOCKER)
- Phase 3 (US1 & US2 - P1): 29 tasks 🎯 MVP
- Phase 4 (US3 - P2): 23 tasks
- Phase 5 (Background Jobs): 11 tasks
- Phase 6 (Polish & Deployment): 22 tasks

**Parallel Opportunities**:
- Phase 2: 5 repository methods can run in parallel
- Phase 3: 6 HTML sections, 6 CSS sections can run in parallel
- Phase 4: 4 HTML sections, 4 CSS sections can run in parallel
- Phase 6: 9 tasks can run in parallel (error handling, security, performance)

**Estimated Timeline**:
- Phase 1: 1 hour
- Phase 2: 4-6 hours (CRITICAL PATH)
- Phase 3: 8-12 hours (MVP)
- Phase 4: 6-8 hours
- Phase 5: 3-4 hours
- Phase 6: 6-8 hours

**Total Estimated Time**: 28-39 hours (matches plan.md estimate of 24-35 hours ✅)

---

## Notes

- **[P]** tasks = different files, no dependencies, can run in parallel
- **[Story]** label maps task to specific user story for traceability (US1, US2, US3)
- Each user story should be independently completable and testable
- Tests not included per specification (manual QA in Phase 6 instead)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **CRITICAL**: Phase 2 must complete before any user story work begins
- **MVP scope**: Phases 1-3 deliver functional match report submission
- Avoid: modifying same file simultaneously (coordinate if needed)
