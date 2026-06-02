# Tasks: Top-8 Events Page Redesign

**Input**: Design documents from `specs/main/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/api-changes.md, quickstart.md

**Tests**: Not explicitly requested — test tasks omitted. Run existing test suites after implementation to verify no regressions.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `web-app/` (Flask)
- **Frontend**: `web-app/frontend/src/` (React)

---

## Phase 1: Setup

**Purpose**: No new project structure needed — this feature modifies existing files only. Setup is read-only orientation.

- [x] T001 Read and understand current `extract_year_from_name()` and `format_event_name()` in `web-app/utils/formatting.py`
- [x] T002 [P] Read and understand current `get_all_events()` in `web-app/repositories/events.py` (lines 242-302)
- [x] T003 [P] Read and understand current event card rendering in `web-app/frontend/src/pages/Events.jsx`

---

## Phase 2: Foundational (Backend Utilities)

**Purpose**: Date extraction and name cleanup utilities that all user stories depend on

**CRITICAL**: Frontend changes depend on these backend utilities being complete

- [x] T004 Add `extract_date_from_name(folder_name: str) -> str | None` function to `web-app/utils/formatting.py` — parse ISO date from folder name patterns: `YYYY M D`, `M_D_YYYY`, `M D YYYY`, `Month D-D YYYY` per research.md R1. Return None for unparseable names like `GenCon2024Stats`.
- [x] T005 [P] Add `strip_date_from_name(name: str) -> str` function to `web-app/utils/formatting.py` — remove date components from display names (e.g., "Ascanrask III 2026 4 4" -> "Ascanrask III", "Battle of Elverson Fields May 23rd 2026" -> "Battle of Elverson Fields"). Strip trailing whitespace after removal.
- [x] T006 [P] Add `format_date_display(iso_date: str | None, year: int | None) -> str | None` function to `web-app/utils/formatting.py` — format ISO date to human-readable (e.g., "2026-04-04" -> "Apr 4, 2026"). If iso_date is None but year is provided, return year string (e.g., "2024"). Return None if both are None.

**Checkpoint**: Date utilities ready — repository and frontend work can begin

---

## Phase 3: User Story 1 - Readable Event Cards with Dates and Winner Info (Priority: P1) MVP

**Goal**: Replace confusing stars with meaningful info: event date, winner name + avatar, clean event name. Sort events by most recent date.

**Independent Test**: `GET /api/top-8-events` returns events with `event_date`, `event_date_display`, `winner_username`, `winner_avatar`, `winner_avatar_id` fields. Events sorted by date descending. Card UI shows date, clean name, winner info — no stars.

### Implementation for User Story 1

- [x] T007 [US1] Extend `get_all_events()` in `web-app/repositories/events.py` to extract winner data from top8 JSON first entry: add `winner_username` (from `data[0]["username"]`), `winner_avatar` (from `data[0]["avatar"][0]["name"]`), `winner_avatar_id` (from `data[0]["avatar"][0]["identifier"]`) to each event dict. Set all three to None if no top8 JSON or data is empty. Use try/except for safety.
- [x] T008 [US1] Extend `get_all_events()` in `web-app/repositories/events.py` to add date fields: check metadata override `event_date` field first, then call `extract_date_from_name(folder.name)` for `event_date`. Call `format_date_display(event_date, extract_year_from_name(name))` for `event_date_display`. Import new functions from `utils.formatting`.
- [x] T009 [US1] Update `name` field in `get_all_events()` in `web-app/repositories/events.py` — when no admin name override exists, apply `strip_date_from_name(format_event_name(folder.name))` instead of just `format_event_name(folder.name)`. Import `strip_date_from_name` from `utils.formatting`.
- [x] T010 [US1] Update default sort in `get_all_events()` in `web-app/repositories/events.py` — replace `extract_year_from_name()` sort key with `event_date` field (ISO string sorts correctly). Events with None dates sort last. Admin custom order (`_event_order.json`) still takes priority when present.
- [x] T011 [US1] Redesign event card layout in `web-app/frontend/src/pages/Events.jsx` — remove star rating display (the `[1,2,3].map` block rendering gold/white stars), replace card content with: event date (top-right, muted text), clean event name (prominent h3), winner line showing "Winner: {username} ({avatar})" if available, deck count. Keep admin drag handle and edit button unchanged.
- [x] T012 [US1] Update page hero section in `web-app/frontend/src/pages/Events.jsx` — update subtitle text, remove "Top 8 Available" badge from cards (since winner info now indicates top 8 presence).

**Checkpoint**: Event cards now show date, winner, clean name. Sorted by recent date. Stars removed from card display. MVP complete.

---

## Phase 4: User Story 2 - Featured "Latest Event" Hero Section (Priority: P2)

**Goal**: Add a large, visually distinct card at the top of the page for the most recent event, breaking up the grid monotony.

**Independent Test**: Page shows a full-width hero card above the grid for `filtered[0]` (most recent event). Hero card links to event detail page. Grid starts from `filtered[1]` onward.

### Implementation for User Story 2

- [x] T013 [US2] Add featured event section in `web-app/frontend/src/pages/Events.jsx` — render `filtered[0]` as a full-width hero card between the filter bar and the grid. Show: "Latest Event" label, event name (large text), formatted date, player/deck count, winner name + avatar name. Wrap in `<Link to={/top-8/${folder}}>`. Use accent border (`border-primary/50`) and distinct background. Only render when `filtered.length > 0`.
- [x] T014 [US2] Adjust grid rendering in `web-app/frontend/src/pages/Events.jsx` — change grid data source from `filtered` to `filtered.slice(1)` to avoid duplicating the featured event. Handle edge case: if only 1 event exists, show hero only with empty grid section hidden. If 0 events, show "No events match your filters" message (existing behavior).

**Checkpoint**: Page has visual hierarchy — featured hero + grid. Both US1 and US2 functional.

---

## Phase 5: User Story 3 - Admin Date Override (Priority: P3)

**Goal**: Allow admins to manually set event dates for events with unparseable folder names (e.g., "OchoaDecklists").

**Independent Test**: Admin edit modal shows date field. Saving date persists to `_event_metadata.json`. Event card displays the overridden date. API `PUT /api/events/{folder}/metadata` accepts `event_date` field.

### Implementation for User Story 3

- [x] T015 [P] [US3] Update `update_event_metadata()` in `web-app/repositories/events.py` to accept and persist optional `event_date: str | None` parameter to `_event_metadata.json`. Add `event_date` to the metadata dict alongside existing `name`, `rating`, `description` fields.
- [x] T016 [P] [US3] Update metadata endpoint in `web-app/routes/api/events.py` — extract `event_date` from `request.json` and pass to `repo.update_event_metadata()` in the existing `update_event_metadata_route()` function.
- [x] T017 [US3] Add date input field to edit modal in `web-app/frontend/src/pages/Events.jsx` — add `<input type="date">` for `event_date` in the edit modal (between title and stars fields), initialize `editModal` state to include `event_date` from `event.event_date`, include `event_date` in the `saveMetadata()` API call to `updateEventMetadata()`.
- [x] T018 [US3] Update `updateEventMetadata()` in `web-app/frontend/src/api/events.js` — add `event_date` to the request body passed to `PUT /api/events/{folder}/metadata`.

**Checkpoint**: Admins can override dates for any event. All 3 user stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify nothing broke and clean up

- [x] T019 Run backend tests: `cd web-app && pytest tests/ -v` — fix any failures caused by changed `get_all_events()` response shape or `format_event_name()` behavior
- [x] T020 [P] Run frontend tests: `cd web-app/frontend && npm test` — fix any failures in Events page tests if they exist
- [x] T021 [P] Run Python syntax check: `cd web-app && python -m py_compile utils/formatting.py && python -m py_compile repositories/events.py`
- [x] T022 Verify admin workflows still work: drag-reorder, edit modal (with new date field), create event modal — no regressions in existing functionality

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup — read only)
  └-> Phase 2 (Foundational — date utilities)
        └-> Phase 3 (US1 — cards + sort + winner) MVP
              ├-> Phase 4 (US2 — featured hero)
              └-> Phase 5 (US3 — admin date override)
                    └-> Phase 6 (Polish)
```

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational only — core MVP, delivers all major user feedback
- **US2 (P2)**: Depends on US1 (needs redesigned cards + date-sorted `filtered` array)
- **US3 (P3)**: Depends on US1 backend (needs `event_date` field in API response). Independent of US2.

### Within Each User Story

- Backend changes before frontend changes
- Repository changes before route changes
- Core rendering before edge cases

### Parallel Opportunities

| Phase | Parallel Tasks | Reason |
|-------|---------------|--------|
| Phase 1 | T001, T002, T003 | Read-only, different files |
| Phase 2 | T004, T005, T006 | Independent functions in same file |
| Phase 5 | T015, T016 | Different files (repo vs route) |
| Phase 6 | T019, T020, T021 | Independent test suites |

---

## Parallel Example: Phase 2 (Foundational)

```
# These add independent functions to formatting.py:
T004: extract_date_from_name() in web-app/utils/formatting.py
T005: strip_date_from_name() in web-app/utils/formatting.py
T006: format_date_display() in web-app/utils/formatting.py
```

## Parallel Example: User Story 3

```
# Different files, no dependencies between them:
T015: Update repository in web-app/repositories/events.py
T016: Update route in web-app/routes/api/events.py
# Then sequentially:
T017: Update frontend edit modal in web-app/frontend/src/pages/Events.jsx
T018: Update API client in web-app/frontend/src/api/events.js
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (3 utility functions)
2. Complete Phase 3: US1 (backend + frontend card redesign)
3. **STOP and VALIDATE**: Cards show dates, winner info, no stars. Sorted by date.
4. Deploy if ready — this alone addresses all major user complaints

### Incremental Delivery

1. Phase 2 (Foundational) -> Date utilities ready
2. US1 -> Cards redesigned, dates + winners, stars removed -> **Deploy (MVP!)**
3. US2 -> Featured hero section added -> Deploy
4. US3 -> Admin date override -> Deploy
5. Each story adds value without breaking previous stories

---

## Notes

- No new files created — all modifications to existing files
- `rating` field kept in metadata and admin edit modal but removed from card display
- `_event_order.json` custom sort still overrides date sort when set by admin
- Winner data extraction is best-effort — events without top8 JSON get null winner fields
- Date parsing is best-effort — unparseable folder names get null dates (sort last)
- Total: 22 tasks across 6 phases
