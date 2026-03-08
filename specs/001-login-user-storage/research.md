# Research: Login User Storage

**Feature Branch**: `001-login-user-storage`
**Date**: 2026-03-07

## R1: Where to Hook User Profile Storage in the Login Flow

**Decision**: Insert the profile save call in `web-app/routes/auth.py` inside the `discord_callback()` function, immediately after the session variables are populated (after line 84) and before the redirect.

**Rationale**: This is the single point where Discord user data is available and the login is confirmed successful. The session has just been set with `user_id`, `username`, and `avatar`. Adding the save here keeps the change minimal and localized.

**Alternatives considered**:
- Flask `before_request` or signal-based approach: Overly complex for a single-point integration. Would fire on every request, not just logins.
- Middleware/decorator pattern: Unnecessary abstraction for one call site.

## R2: Database Table Design (Upsert Strategy)

**Decision**: Use SQLite `INSERT ... ON CONFLICT ... DO UPDATE` (upsert) with a composite unique constraint on `(user_id, provider)`.

**Rationale**: SQLite 3.24+ supports the `ON CONFLICT` clause natively. This handles both first-time insert and returning-user update in a single atomic statement, matching FR-003 and FR-004 requirements. The composite key on `(user_id, provider)` naturally supports future login providers (FR-005).

**Alternatives considered**:
- SELECT then INSERT/UPDATE: Race condition risk with concurrent logins. Two round-trips to DB.
- `INSERT OR REPLACE`: Replaces the entire row, which would overwrite `first_login_at`. The upsert approach preserves `first_login_at` while updating other fields.

## R3: Repository Pattern Alignment

**Decision**: Create a new `UserProfileRepository` class in `web-app/repositories/user_profiles.py` following the exact pattern used by `MatchRepository`.

**Rationale**: All existing repositories follow the same structure: `__init__` with optional `db_path`, `_get_connection()` returning `sqlite3.Connection`, open/close per method call. Consistency is critical. The repository connects to `match_records.db` via `MATCH_RECORDS_DB_PATH` from `webapp_config.py`.

**Alternatives considered**:
- Adding methods to `MatchRepository`: Violates single responsibility. User profiles are a distinct domain entity.
- Creating a service layer: Unnecessary complexity. The logic is a single upsert with no business rules beyond what the repository handles.

## R4: Table Auto-Initialization

**Decision**: Use `CREATE TABLE IF NOT EXISTS` in the repository's `__init__` method (via a private `_ensure_table()` method), mirroring how `MatchRepository._ensure_columns()` works.

**Rationale**: Follows existing project patterns. The table is created on first use without requiring migration scripts. The `IF NOT EXISTS` clause makes it safe to call on every instantiation.

**Alternatives considered**:
- Migration scripts: The project doesn't use any migration framework. Adding one for a single table is overkill.
- Manual table creation: Fragile and error-prone in deployment.

## R5: Error Handling for Non-Blocking Login

**Decision**: Wrap the repository call in `auth.py` with a try/except that logs the error and continues. The user's login session is never interrupted by a profile storage failure.

**Rationale**: FR-006 requires that the login experience is not disrupted. The existing `auth.py` already uses this pattern (try/except with logger.error and redirect on failure). A profile save failure is non-critical.

**Alternatives considered**:
- Background task/queue: Unnecessary complexity for a fast SQLite write.
- Retry logic: Overkill for a local SQLite operation that rarely fails.

## R6: Data Available from Discord OAuth

**Decision**: Store `user_id` (int), `username` (str), `avatar` (str, nullable), `provider` ("discord"), `first_login_at` (ISO timestamp), `last_login_at` (ISO timestamp).

**Rationale**: These fields are already extracted from the Discord `/users/@me` endpoint in the current callback handler. The `avatar` field is a hash string (not a URL or binary), which is consistent with how Discord stores avatars. No additional OAuth scopes are needed.

**Alternatives considered**:
- Storing email: Would require adding the "email" scope to OAuth, which is out of scope for this feature.
- Storing discriminator: Deprecated by Discord and no longer meaningful.
- Storing access/refresh tokens: Security risk and not needed for profile storage.
