# Implementation Plan: Mobile Life Counter with Match Reporting

**Branch**: `001-mobile-life-counter` | **Date**: 2026-03-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-mobile-life-counter/spec.md` + push notifications requirement

## Summary

Create a mobile-optimized life counter page accessible via navbar icon that tracks dual-player life totals, element selections, and additional game counters. When a player reaches 0 life, enable match report submission with push notification to opponent for confirmation. Integrate with existing ELO system for confirmed match results.

**Technical Approach**: Extend existing Flask web application with new `/life-counter` page route, client-side JavaScript state management for counter tracking (session storage), new Match Confirmation entity in SQLite database, and push notification integration (method TBD - see research phase).

## Technical Context

**Language/Version**: Python 3.11+ (matches discord-bot requirement)
**Primary Dependencies**: Flask 3.0+, Flask-Login 0.6.3+ (existing), SQLite3 (existing), Web Push API or Firebase Cloud Messaging (see research)
**Storage**: SQLite database (existing `match_records.db` from discord-bot, new `match_confirmations` table)
**Testing**: pytest (existing test infrastructure in discord-bot and web-app)
**Target Platform**: Mobile web browsers (iOS Safari 12+, Android Chrome 80+), responsive design for 320px-768px viewport widths
**Project Type**: Web application (Flask-based, existing multi-component system)
**Performance Goals**: <100ms counter update latency, <3s match report submission, <5s push notification delivery, render at 60fps for animations
**Constraints**: Mobile-only feature (hide icon on desktop), session-only persistence (no database storage of counter state), requires user authentication for match reporting
**Scale/Scope**: Expected 100-500 concurrent mobile users during peak hours, ~50-200 match reports per day, 24-hour confirmation window with auto-confirm fallback

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: No constitution file exists yet (template placeholder found at `.specify/memory/constitution.md`)

Since no project-specific constitution has been ratified, proceeding with industry best practices:
- ✅ Extend existing architecture (Flask routes → services → repositories pattern)
- ✅ Follow existing code organization (new route in `web-app/routes/pages.py`, new service in `web-app/services/`, new repository in `web-app/repositories/`)
- ✅ Maintain test coverage (add tests for new components)
- ✅ No breaking changes to existing APIs
- ✅ Reuse existing authentication (Discord OAuth via Flask-Login)

**Post-Phase 1 Check**: Will verify no new complexity violations after design phase.

## Project Structure

### Documentation (this feature)

```text
specs/001-mobile-life-counter/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── api-endpoints.md # REST API contracts for life counter
│   └── notifications.md # Push notification contract
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
web-app/
├── routes/
│   ├── pages.py              # Add /life-counter route (MODIFY)
│   └── api/
│       ├── life_counter.py   # New API endpoints for match reports (CREATE)
│       └── notifications.py  # New push notification endpoints (CREATE)
├── services/
│   ├── match_confirmation.py # Business logic for confirmations (CREATE)
│   └── notification.py        # Push notification service (CREATE)
├── repositories/
│   └── match_confirmation.py  # Data access for confirmations (CREATE)
├── templates/
│   └── pages/
│       └── life_counter.html  # New mobile life counter page (CREATE)
├── static/
│   ├── css/
│   │   ├── pages/
│   │   │   └── life_counter.css # Life counter styles (CREATE)
│   │   └── components/
│   │       └── navbar.css       # Add life counter icon styles (MODIFY)
│   ├── js/
│   │   └── pages/
│   │       └── life_counter.js  # Counter logic, state management (CREATE)
│   └── images/
│       ├── icons/
│       │   └── life-counter.svg # Navbar icon (CREATE or source from design)
│       └── elements/             # Element icons (VERIFY EXISTS or CREATE)
│           ├── water.svg
│           ├── fire.svg
│           ├── earth.svg
│           └── air.svg
└── tests/
    ├── test_life_counter_api.py        # API endpoint tests (CREATE)
    ├── test_match_confirmation.py       # Confirmation flow tests (CREATE)
    └── test_notification_service.py     # Notification tests (CREATE)

discord-bot/
└── match_records.db           # Add match_confirmations table (MODIFY SCHEMA)
```

**Structure Decision**: Using existing Flask web application structure. New feature adds:
1. Single page route (`/life-counter`) in existing `routes/pages.py`
2. Two new API modules under `routes/api/` for match reporting and notifications
3. Two new service modules under `services/` for business logic
4. One new repository module under `repositories/` for data access
5. Client-side JavaScript for counter state management (session storage, no backend persistence)
6. Standard Flask template + CSS + JS for UI

Follows established patterns in codebase (see `web-app/routes/api/leaderboard.py`, `web-app/services/leaderboard.py`, `web-app/repositories/elo.py` for reference).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations detected. Feature extends existing architecture without introducing new patterns or complexity.

---

## Phase 0: Research & Technical Decisions

See [research.md](research.md) for detailed findings on:

1. **Push Notification Approach**: Evaluate Web Push API vs Firebase Cloud Messaging vs simple polling for match confirmation notifications
   - Decision criteria: browser support (Safari limitations), implementation complexity, cost, latency requirements
   - Deliverable: Chosen notification method with implementation pattern

2. **Session Storage Strategy**: Confirm browser session storage API support for life counter state persistence
   - Validate: Session storage capacity limits (5-10MB typical), serialization approach for counter state
   - Deliverable: Storage format specification (JSON schema for counter state)

3. **Mobile UI Patterns**: Research best practices for touch-friendly counter controls (increment/decrement buttons)
   - Investigate: Button sizing (min 44px tap target), haptic feedback, visual feedback for taps
   - Deliverable: UI component specifications for counter controls

4. **Match Confirmation Flow**: Define detailed workflow for opponent confirmation with push notifications
   - Map out: Notification trigger points, confirmation actions (confirm/dispute), timeout behavior, retry logic
   - Deliverable: State machine diagram for confirmation flow

5. **Integration with Existing ELO System**: Verify integration points with `web-app/services/match.py` and `web-app/repositories/matches.py`
   - Confirm: Data format compatibility, API contracts, transaction handling for ELO updates
   - Deliverable: Integration specification with existing services

---

## Phase 1: Data Model & Contracts

See [data-model.md](data-model.md) for entity definitions.

**Key Entities**:
- **LifeCounterSession** (client-side only, session storage): Current game state with life totals, element selections, counter values
- **MatchReport** (existing, extend): Add fields for life_counter_used, final_life_totals
- **MatchConfirmation** (new database entity): Confirmation request tracking with opponent_id, status, expiration

**Database Changes**:
- New table: `match_confirmations` (fields: id, match_report_id, opponent_discord_id, status, created_at, confirmed_at, expires_at)
- Extend table: `match_records` (add columns: submitted_via_life_counter, final_player1_life, final_player2_life)

See [contracts/](contracts/) for API and notification specifications.

---

## Phase 2: Implementation Tasks

Generated via `/speckit.tasks` command (not part of this plan output).

---

## Next Steps

1. ✅ **Phase 0 Complete**: Review research.md for technical decisions
2. ⬜ **Phase 1 Complete**: Review data-model.md and contracts/ for design artifacts
3. ⬜ **Generate Tasks**: Run `/speckit.tasks` to create tasks.md with implementation checklist
4. ⬜ **Begin Implementation**: Follow tasks.md for step-by-step development

**Current Status**: Phase 0 (Research) in progress - see research.md below.
