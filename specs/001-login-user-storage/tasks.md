# Tasks: Login User Storage

**Input**: Design documents from `/specs/001-login-user-storage/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No test tasks included (not explicitly requested in the feature specification).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No project initialization needed - this feature adds to an existing Flask web application with an established repository pattern.

*No setup tasks required. Project structure, dependencies, and database configuration already exist.*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the UserProfileRepository class that all user stories depend on. This establishes the `user_profiles` table and provides the data access layer.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T001 Create `UserProfileRepository` class in `web-app/repositories/user_profiles.py` with `__init__(self, db_path=None)` accepting optional db_path parameter, `_get_connection()` returning a `sqlite3.Connection` to `match_records.db` via `MATCH_RECORDS_DB_PATH`, and private `_ensure_table()` method called from `__init__` that executes `CREATE TABLE IF NOT EXISTS user_profiles` with schema: `user_id TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'discord', display_name TEXT NOT NULL, avatar TEXT, first_login_at TEXT NOT NULL, last_login_at TEXT NOT NULL, PRIMARY KEY (user_id, provider)`. Follow the exact pattern from `web-app/repositories/matches.py` (MatchRepository).

- [x] T002 Add `upsert_profile(self, user_id, display_name, avatar, provider="discord")` method to `UserProfileRepository` in `web-app/repositories/user_profiles.py`. Method must: open connection via `_get_connection()`, generate current ISO 8601 timestamp, execute `INSERT INTO user_profiles ... ON CONFLICT (user_id, provider) DO UPDATE SET display_name=excluded.display_name, avatar=excluded.avatar, last_login_at=excluded.last_login_at` (preserving `first_login_at`), commit, and close connection. The `user_id` parameter should be converted to string before storage for consistency with how Discord IDs are stored elsewhere.

**Checkpoint**: `UserProfileRepository` is importable, table auto-creates on instantiation, `upsert_profile()` can insert and update records.

---

## Phase 3: User Story 1 & 2 - First-Time and Returning Login Profile Capture (Priority: P1)

**Goal**: Every successful Discord OAuth login creates or updates a user profile record in the database. First-time logins create a new record; returning logins update the existing record. The login flow is never disrupted by profile storage failures.

**Independent Test**: Log in via Discord OAuth and verify a record exists in the `user_profiles` table with correct user ID, username, avatar, provider="discord", and timestamps. Log in again and verify the record was updated (not duplicated) with a refreshed `last_login_at`.

**Why combined**: US1 (first login) and US2 (returning login) are both P1 and are implemented by the same upsert mechanism - the `INSERT ... ON CONFLICT ... DO UPDATE` statement atomically handles both cases.

### Implementation for User Story 1 & 2

- [x] T003 [US1] Modify `discord_callback()` in `web-app/routes/auth.py` to import `UserProfileRepository` from `repositories.user_profiles` and call `upsert_profile()` after session variables are set (after the line `session["avatar"] = user_data.get("avatar")`). Pass `user_id=str(session["user_id"])`, `display_name=session["username"]`, `avatar=session["avatar"]`, `provider="discord"`. Wrap the call in a try/except block that catches `Exception`, logs the error with `logger.error(f"Failed to save user profile: {e}")`, and continues without interrupting the login flow. The redirect to `url_for("pages.home")` must always execute regardless of profile save success or failure.

- [x] T004 [US1] Verify the complete login flow by reviewing `web-app/routes/auth.py` end-to-end: confirm that (1) the import is at the top of the file, (2) `upsert_profile()` is called after all three session assignments but before the redirect, (3) the try/except does not catch errors from session assignment (only from profile storage), and (4) the existing `logger.info` login message still fires.

**Checkpoint**: Discord OAuth login creates a `user_profiles` record on first login and updates it on subsequent logins. Login flow works normally even if the database write fails.

---

## Phase 4: User Story 3 - Future Login Provider Support (Priority: P2)

**Goal**: The `user_profiles` table schema supports multiple login providers via the composite primary key `(user_id, provider)`. Different providers can store records for the same user ID without conflicts.

**Independent Test**: Verify the table schema includes the `provider` field as part of the primary key. Insert a record with `provider="discord"` and another with `provider="google"` for the same `user_id` and confirm both coexist without conflict.

### Implementation for User Story 3

- [x] T005 [US3] Verify that `UserProfileRepository.upsert_profile()` in `web-app/repositories/user_profiles.py` correctly accepts a `provider` parameter (defaulting to `"discord"`) and that the composite primary key `(user_id, provider)` in the `CREATE TABLE` statement allows the same `user_id` to have separate records per provider. No code changes expected - this validates the foundational design from Phase 2 satisfies US3 requirements.

**Checkpoint**: Schema is verified provider-aware. A future login integration only needs to call `upsert_profile(user_id, display_name, avatar, provider="new_provider")` with no schema changes.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and edge case handling.

- [x] T006 Run Python syntax check on both modified/created files: `python -m py_compile web-app/repositories/user_profiles.py` and `python -m py_compile web-app/routes/auth.py` to confirm no syntax errors.

- [x] T007 Review edge case handling: confirm `avatar` parameter accepts `None` (Discord users without custom avatars), confirm `user_id` is stored as string (large Discord IDs), and confirm timestamps use ISO 8601 format via `datetime.utcnow().isoformat()` or equivalent.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Skipped - existing project
- **Foundational (Phase 2)**: No dependencies - can start immediately. T001 → T002 (sequential, same file)
- **User Story 1 & 2 (Phase 3)**: Depends on Phase 2 completion (T002). T003 → T004 (sequential, same file)
- **User Story 3 (Phase 4)**: Depends on Phase 2 completion (T002). Can run in parallel with Phase 3.
- **Polish (Phase 5)**: Depends on Phases 3 and 4 completion

### User Story Dependencies

- **User Story 1 & 2 (P1)**: Depends on Foundational (Phase 2) only. No dependencies on US3.
- **User Story 3 (P2)**: Depends on Foundational (Phase 2) only. No dependencies on US1/US2. Can run in parallel with Phase 3.

### Within Each Phase

- T001 before T002 (T002 adds method to class created in T001)
- T003 before T004 (T004 verifies changes made in T003)
- T005 is standalone (verification only)
- T006 and T007 can run in parallel [P]

### Parallel Opportunities

- Phase 3 (US1/US2) and Phase 4 (US3) can run in parallel after Phase 2 completes
- T006 and T007 in Phase 5 can run in parallel

---

## Parallel Example: After Phase 2

```text
# These can run in parallel after Phase 2 (Foundational) completes:
Task: "T003 [US1] Hook upsert_profile into discord_callback in web-app/routes/auth.py"
Task: "T005 [US3] Verify provider-aware schema in web-app/repositories/user_profiles.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 & 2 Only)

1. Complete Phase 2: Foundational (T001, T002) - Create repository and upsert method
2. Complete Phase 3: User Story 1 & 2 (T003, T004) - Hook into auth callback
3. **STOP and VALIDATE**: Login via Discord, check `user_profiles` table for record
4. Deploy if ready - profile storage is fully functional for Discord logins

### Incremental Delivery

1. Phase 2 → Repository and table created
2. Phase 3 → Discord login stores profiles (MVP!)
3. Phase 4 → Verified future provider support (no code change, schema validation)
4. Phase 5 → Polish and edge case verification

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 and US2 are combined into Phase 3 because they share the same upsert implementation
- US3 requires no additional code beyond the foundational schema design - Phase 4 is a verification phase
- No test tasks generated (not requested in spec). Add tests with `/speckit.tasks` if needed later.
- Commit after each phase completion
- Total: 7 tasks across 5 phases
