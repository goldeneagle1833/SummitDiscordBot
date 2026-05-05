# Implementation Plan: Explorer Standings

**Branch**: `main` | **Date**: 2026-05-05 | **Spec**: specs/main/spec.md

## Summary

New "Explorer Standings" leaderboard page tracking cumulative season points across Explorer Series in-person tournaments. Authorized admins import events by pasting a sorcerytcg.com URL; the backend fetches placement data from the carde.io API, persists it in a dedicated `explorer.db`, and computes season standings. The page is publicly readable; write operations require an Explorer admin role.

## Technical Context

**Language/Version**: Python 3.11 (Flask backend) + React 18 (Vite frontend)  
**Primary Dependencies**: Flask, SQLite3, `requests` (server-side carde.io API calls), React, React Router v6  
**Storage**: `web-app/explorer.db` — new SQLite database (4 tables)  
**Testing**: pytest (backend), Vitest + React Testing Library (frontend)  
**Target Platform**: Linux server (existing deployment, Gunicorn + Nginx + Cloudflare)  
**Project Type**: web-service feature addition  
**Performance Goals**: Leaderboard page load < 500ms; event import < 10s (carde.io API dependent)  
**Constraints**: All carde.io calls server-side (no CORS); import is synchronous (small events, < 200 players); no schema migrations to existing databases  
**Scale/Scope**: ~10 events/season, ~50 players/event, ~100 distinct players across a season

## Constitution Check

No constitution is defined for this project. Applying general quality gates:

- **No duplicate logic**: Explorer admin auth follows the existing `is_curio_editor()` pattern exactly
- **Auth coverage**: All write endpoints use `@require_explorer_admin` or `@require_admin`; all new endpoints added to `test_endpoint_auth.py` allowlist or decorated
- **Repository pattern**: Data access in `repositories/explorer.py`; business logic in `services/explorer.py`
- **Migration pattern**: Schema initialization in `migrations/create_explorer_tables.py`, called in `app.py`

**Gate Status**: PASS — no violations

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md              # This file
├── research.md          # R-1 through R-6 (API, DB, auth, points, migration)
├── data-model.md        # DB schema + API/frontend response shapes
├── contracts/
│   └── explorer-api.md  # All 9 endpoint contracts
└── tasks.md             # Phase 2 output (run /speckit.tasks)
```

### Source Code

```text
web-app/
├── migrations/
│   └── create_explorer_tables.py    # NEW: initialize explorer.db schema
├── repositories/
│   └── explorer.py                  # NEW: ExplorerRepository (CRUD for all 4 tables)
├── services/
│   └── explorer.py                  # NEW: ExplorerService (carde.io fetch + leaderboard calc)
├── routes/api/
│   └── explorer.py                  # NEW: explorer_bp Blueprint (9 endpoints)
├── routes/__init__.py               # MODIFY: register explorer_bp
├── utils/auth.py                    # MODIFY: add is_explorer_admin() + require_explorer_admin
├── webapp_config.py                 # MODIFY: add EXPLORER_DB_PATH
├── app.py                           # MODIFY: call create_explorer_tables() on startup
└── tests/
    ├── test_explorer_repo.py        # NEW: repository unit tests
    ├── test_explorer_service.py     # NEW: service unit tests (mock carde.io)
    ├── test_explorer_routes.py      # NEW: route integration tests
    └── test_endpoint_auth.py        # MODIFY: add new endpoints to coverage

web-app/frontend/src/
├── pages/
│   └── ExplorerStandings.jsx        # NEW: main page component
├── api/
│   └── explorer.js                  # NEW: fetch wrappers for all endpoints
├── components/
│   └── explorer/
│       ├── AddSeasonModal.jsx       # NEW: modal for creating a season
│       ├── AddEventModal.jsx        # NEW: modal for importing event (URL + preview)
│       └── ExplorerAdminPanel.jsx   # NEW: manage explorer admins (global admin only)
├── App.jsx                          # MODIFY: add /explorer route
└── components/layout/Nav.jsx        # MODIFY: add Explorer link in nav
```

## Complexity Tracking

No constitution violations requiring justification.

---

## Phase 0 Artifacts

- [research.md](research.md) — API discovery, DB location, auth pattern, points config, migration pattern

## Phase 1 Artifacts

- [data-model.md](data-model.md) — DB schema (4 tables) + API response shapes + frontend state
- [contracts/explorer-api.md](contracts/explorer-api.md) — 9 endpoint contracts with request/response shapes and error codes

## Next Step

Run `/speckit.tasks` to generate the implementation task list.
