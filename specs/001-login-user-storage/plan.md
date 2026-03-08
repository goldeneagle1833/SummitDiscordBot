# Implementation Plan: Login User Storage

**Branch**: `001-login-user-storage` | **Date**: 2026-03-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-login-user-storage/spec.md`

## Summary

Add a `user_profiles` table to the match records database that captures user information (Discord ID, username, avatar, provider, timestamps) whenever a user logs in via Discord OAuth on the web application. Uses an upsert pattern to create records on first login and update them on subsequent logins. Designed with a composite primary key `(user_id, provider)` to support future login providers without schema changes.

## Technical Context

**Language/Version**: Python 3.x
**Primary Dependencies**: Flask, sqlite3 (stdlib), requests (for Discord OAuth)
**Storage**: SQLite (`match_records.db` via `MATCH_RECORDS_DB_PATH` in `webapp_config.py`)
**Testing**: pytest (with asyncio_mode=auto)
**Target Platform**: Linux server (production), Windows (development)
**Project Type**: Web service (Flask)
**Performance Goals**: Login flow must remain under 500ms additional overhead (SC-002)
**Constraints**: Non-blocking - DB failures must not disrupt login (FR-006)
**Scale/Scope**: 10,000+ user records (SC-004), single table addition, 2 files touched

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No constitution has been configured for this project (template file contains placeholders only). No gates apply. Proceeding.

**Post-Phase 1 re-check**: No violations. The design follows existing project patterns (repository class, SQLite, open/close per method).

## Project Structure

### Documentation (this feature)

```text
specs/001-login-user-storage/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: Entity model and SQL schema
├── quickstart.md        # Phase 1: Implementation guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
web-app/
├── repositories/
│   ├── matches.py            # Existing - match records access (pattern reference)
│   └── user_profiles.py      # NEW - user profile storage repository
├── routes/
│   └── auth.py               # MODIFIED - hook profile save into Discord callback
└── webapp_config.py          # Existing - MATCH_RECORDS_DB_PATH (no changes needed)
```

**Structure Decision**: This feature adds a single new repository file and modifies the existing auth route. It follows the established repository pattern in `web-app/repositories/` where each repository class manages one domain entity with its own `_get_connection()` method connecting to the appropriate SQLite database. No new directories, services, or architectural patterns are introduced.
