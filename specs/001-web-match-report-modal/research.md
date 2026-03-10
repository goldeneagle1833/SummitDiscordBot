# Research: Web-Based Match Reporting Modal

**Feature**: 001-web-match-report-modal
**Date**: 2026-03-10
**Status**: Complete

## Executive Summary

This research phase investigated implementation approaches for adding web-based match reporting functionality to the existing Flask application. The system already has partial infrastructure (database schema, repository layer) but needs completion of service logic, API routes, frontend forms, and background task handling for expirations/reminders.

## Technical Decisions

### Decision 1: Database Schema - Extend Existing vs New Table

**Chosen**: **Extend existing `match_confirmations` table** with minor modifications

**Rationale**:
- Table already exists with 90% of required fields
- Current schema: `submitter_discord_id`, `opponent_discord_id`, `winner_discord_id`, `loser_discord_id`, `winner_deck_url`, `loser_deck_url`, `final_life_winner`, `final_life_loser`, `status`, `created_at`, `expires_at`, `confirmed_at`, `dispute_reason`
- **Missing fields**: `went_first` (turn order), `reminder_sent_at` (for 24hr reminder tracking)
- Existing repository has all CRUD methods stubbed out

**Required Changes**:
1. Add `went_first` column (TEXT: 'submitter' | 'opponent' | NULL)
2. Add `reminder_sent_at` (INTEGER, Unix timestamp)
3. Update `expires_at` calculation from 24hr to 48hr
4. Add migration script to alter table

**Alternatives Considered**:
- **Create new `pending_match_reports` table**: Rejected - would duplicate 90% of fields and require complex joins. The user's suggestion was good but the table already exists as `match_confirmations`.
- **Use separate tables for pending vs confirmed**: Rejected - status column already handles this elegantly

---

### Decision 2: Opponent Autocomplete - Implementation Strategy

**Chosen**: **Server-side search with debounced AJAX requests**

**Rationale**:
- User profiles table already exists with `display_name` field
- `match_confirmation_repository.get_recent_lfg_opponents()` method already implemented
- 2-tier search approach:
  1. **Primary**: Recent opponents from match history (fast, personalized)
  2. **Fallback**: Full user_profiles table search by display_name (if no recent matches)
- Prevents loading thousands of users on page load
- Better UX: shows relevant opponents first

**Implementation**:
```python
# Pseudocode API endpoint
GET /api/match-report/search-opponents?q=username&limit=10
→ Returns: [{"user_id": "123", "display_name": "PlayerName", "avatar": "url", "recent_match_count": 5}]
```

**Alternatives Considered**:
- **Client-side autocomplete with full user list**: Rejected - poor performance with large user base, stale data issues
- **Discord username only (no display_name)**: Already implemented - display_name field exists in user_profiles table
- **LFG-only lookup**: Rejected - too restrictive, user wants all profiles searchable

---

### Decision 3: Notification System - Push vs Poll

**Chosen**: **Polling-based notification system** (for now, with WebSocket readiness)

**Rationale**:
- **Simplest MVP**: Client polls `/api/notifications/pending-confirmations` every 30 seconds when page is active
- No additional infrastructure required (no WebSocket server, no Redis pub/sub)
- Acceptable latency: 30s average notification delay is fine for match confirmations
- **Future-proof**: API design allows later WebSocket upgrade without breaking changes

**Implementation**:
```javascript
// Client-side polling
setInterval(() => {
  if (document.visibilityState === 'visible') {
    fetch('/api/notifications/pending-confirmations')
      .then(r => r.json())
      .then(data => {
        if (data.pending_count > 0) showConfirmationBadge();
      });
  }
}, 30000); // 30 seconds
```

**Alternatives Considered**:
- **WebSockets (Flask-SocketIO)**: Rejected for MVP - adds complexity (WSGI server limitations, requires Gunicorn with eventlet/gevent worker), overkill for low-frequency events
- **Server-Sent Events (SSE)**: Rejected - browser connection limits (6 per domain), not needed for this use case
- **Email/Discord DM notifications**: Out of scope for this feature (but API allows adding later)

---

### Decision 4: Expiration & Reminder System - Cron vs Background Worker

**Chosen**: **Background worker with APScheduler** (Python in-process scheduler)

**Rationale**:
- Flask app already runs 24/7 as systemd service
- APScheduler lightweight, no external dependencies (no Celery/Redis needed)
- **Jobs**:
  1. **Every 5 minutes**: Check for pending reports needing 24hr reminder → send notification
  2. **Every 15 minutes**: Check for 48hr expired reports → mark as void, notify both players
- Graceful handling: Job state survives app restarts (reads from DB)
- Alternative: Could use systemd timer + cron, but in-process is simpler for this scale

**Implementation**:
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(send_pending_reminders, 'interval', minutes=5)
scheduler.add_job(expire_old_reports, 'interval', minutes=15)
scheduler.start()
```

**Alternatives Considered**:
- **Celery + Redis**: Rejected - massive overkill for 2 simple periodic tasks, adds infrastructure burden
- **systemd timer + bash cron**: Rejected - requires separate script management, less integrated with app state
- **Database triggers**: Rejected - can't send HTTP notifications, mixing concerns

---

### Decision 5: Turn Order Storage Format

**Chosen**: **Store as relative to submitter** ('submitter' | 'opponent')

**Rationale**:
- Unambiguous: Always relative to the person who created the report
- Simpler logic: Don't need to track absolute player1/player2 positions
- Matches UX: User clicks "I went First" → stored as `went_first='submitter'`
- Easy to display in confirmation modal: "PlayerA reported they went first"

**Database Column**:
```sql
went_first TEXT CHECK(went_first IN ('submitter', 'opponent'))
```

**Alternatives Considered**:
- **Absolute player1/player2**: Rejected - requires tracking board positions, error-prone
- **Boolean (TRUE=first, FALSE=second)**: Rejected - ambiguous (whose perspective?), NULL handling unclear
- **winner/loser relative**: Rejected - doesn't work if submitter reported they lost

---

### Decision 6: Frontend Framework - Vanilla JS vs React/Vue

**Chosen**: **Vanilla JavaScript with modern ES6+**

**Rationale**:
- Existing codebase uses vanilla JS (life_counter.js, other pages)
- No build step required - direct .js file serving
- Modal forms are simple CRUD - no complex state management needed
- Faster dev cycle: Edit → Refresh vs Edit → Build → Refresh
- Lighter weight: No framework bundle overhead

**Architecture**:
- **Modular pattern**: Separate concerns (form validation, API calls, UI updates)
- **Event delegation**: Handle dynamic elements efficiently
- **Fetch API**: Native HTTP requests, no jQuery needed
- **CSS Variables**: Theming via custom properties (already used in site)

**Alternatives Considered**:
- **React/Vue**: Rejected - adds build complexity, overkill for forms, breaking change to existing architecture
- **Alpine.js**: Considered - lightweight, but still introduces new dependency/learning curve
- **HTMX**: Rejected - excellent for hypermedia, but modals need more client-side state management

---

### Decision 7: Deck URL Validation Strategy

**Chosen**: **Multi-level validation** (client + server + optional external)

**Levels**:
1. **Client-side (instant feedback)**:
   ```javascript
   const deckUrlRegex = /^https?:\/\/(www\.)?curiosa\.io\/decks\/[a-zA-Z0-9_-]+$/;
   ```
2. **Server-side (security)**:
   - Same regex validation (prevent malicious input)
   - Length limits (max 500 chars)
   - Required field validation (combined with opponent + turn order)

3. **External API validation (optional, best-effort)**:
   - HEAD request to Curiosa API to verify deck exists
   - Non-blocking: If API down, accept URL anyway (logged for manual review)
   - Prevents typos, catches 404s early

**Rationale**:
- **Defense in depth**: Client-side for UX, server-side for security
- **Graceful degradation**: External API failure doesn't block match reporting
- **User experience**: Immediate feedback on typos (client), but forgiving (server allows edge cases)

**Alternatives Considered**:
- **Client-side only**: Rejected - security risk, easily bypassed
- **Strict external validation (blocking)**: Rejected - creates dependency on Curiosa API uptime
- **No validation**: Rejected - leads to bad data, broken links in match history

---

## Best Practices Applied

### Flask Application Architecture

**Repository-Service-Route Pattern** (already in codebase):
```
routes/api/*.py → services/*.py → repositories/*.py → SQLite DB
```

**Benefits**:
- **Testable**: Services can be unit tested with mocked repositories
- **Reusable**: Business logic in services used by both API and background jobs
- **Maintainable**: Clear separation of concerns (HTTP → logic → data)

**Implementation for this feature**:
- `routes/api/match_reporting.py`: REST endpoints
- `services/match_confirmation.py`: Business logic (already stubbed)
- `repositories/match_confirmation.py`: Database access (already exists)

---

### Frontend Form Handling

**Progressive Enhancement**:
1. **Base HTML form** (works without JS)
2. **JS enhancement** (AJAX submission, live validation)
3. **Accessibility** (ARIA labels, keyboard nav, screen reader support)

**Validation Strategy**:
- Inline validation on blur (opponent, deck URL, turn order)
- Aggregate validation on submit (all fields)
- Clear error messages (next to field + summary at top)
- Disable submit button until all valid

**State Management**:
```javascript
const formState = {
  opponentSelected: false,
  deckUrlValid: false,
  turnOrderSelected: false,
  isSubmitting: false
};

function updateSubmitButton() {
  const allValid = formState.opponentSelected &&
                   formState.deckUrlValid &&
                   formState.turnOrderSelected;
  submitBtn.disabled = !allValid || formState.isSubmitting;
}
```

---

### Error Handling & Resilience

**API Error Responses** (standardized format):
```json
{
  "success": false,
  "error": {
    "code": "DUPLICATE_PENDING",
    "message": "You already have a pending match report with this opponent.",
    "details": {"confirmation_id": 123, "expires_at": 1234567890}
  }
}
```

**Client-side Handling**:
- Retry logic for network errors (3 retries with exponential backoff)
- User-friendly error messages (no stack traces)
- Fallback: "Something went wrong, try again" + log to console for debugging

**Server-side Handling**:
- Try-catch blocks in services with specific exception types
- Database transaction rollback on errors
- Comprehensive logging (logger.error with exc_info=True)

---

### Security Considerations

**Authentication & Authorization**:
- All API endpoints require Flask session authentication (existing OAuth)
- User can only:
  - Create reports as themselves (submitter_id = session user_id)
  - Confirm/deny reports where they are the opponent
  - View their own pending reports
- Prevent CSRF: Use Flask-WTF CSRF tokens or SameSite cookies

**Input Validation**:
- Whitelist validation: Turn order must be 'submitter'|'opponent'
- Prevent SQL injection: Parameterized queries (already using sqlite3 placeholders)
- Prevent XSS: Escape all user input in templates (Jinja2 auto-escaping enabled)

**Rate Limiting** (optional but recommended):
- Limit match report submissions: 10 per hour per user
- Limit opponent search requests: 30 per minute per user
- Use Flask-Limiter extension

---

## Technology Stack Confirmation

| Component | Technology | Version | Notes |
|-----------|------------|---------|-------|
| **Backend** | Python | 3.11+ | Existing constraint |
| **Web Framework** | Flask | 2.x | Existing |
| **Database** | SQLite | 3.x | match_records.db (existing) |
| **ORM** | None | N/A | Direct sqlite3 module (existing pattern) |
| **Scheduler** | APScheduler | 3.10+ | New dependency (add to requirements.txt) |
| **Frontend** | Vanilla JS | ES6+ | Existing pattern |
| **HTTP Client** | Fetch API | Native | No library needed |
| **Testing** | pytest | 7.x+ | Existing |
| **Production Server** | Gunicorn + Nginx | Existing | No changes |

**New Dependencies to Add**:
```txt
# requirements.txt additions
APScheduler==3.10.4  # Background job scheduler for reminders/expiration
```

---

## Performance Considerations

**Database Indexing** (required for query performance):
```sql
-- Add these indexes to match_confirmations table
CREATE INDEX idx_opponent_status_expires ON match_confirmations(opponent_discord_id, status, expires_at);
CREATE INDEX idx_status_created ON match_confirmations(status, created_at);
CREATE INDEX idx_expires_at ON match_confirmations(expires_at) WHERE status = 'pending';
```

**Expected Load**:
- Match report submissions: ~10-50 per day (low frequency)
- Opponent autocomplete searches: ~100-500 per day
- Notification polling: ~1000-5000 requests per day (30s interval × active users)
- Background jobs: 2 tasks every 5-15 minutes (minimal CPU)

**Optimization**:
- Cache recent opponents list: 5-minute TTL in memory
- Debounce autocomplete: 300ms client-side delay
- Connection pooling: SQLite handles well with low concurrency

---

## Migration & Rollout Strategy

**Phase 1: Database Migration** (zero downtime)
```sql
-- Add columns to existing table
ALTER TABLE match_confirmations ADD COLUMN went_first TEXT;
ALTER TABLE match_confirmations ADD COLUMN reminder_sent_at INTEGER;
-- Create indexes
CREATE INDEX ...
```

**Phase 2: Backend Deployment** (staged rollout)
1. Deploy repository changes (passive - no breaking changes)
2. Deploy service layer implementation
3. Deploy API routes (new endpoints - no impact on existing)
4. Start background scheduler

**Phase 3: Frontend Deployment**
1. Update life_counter.html with full match report modal form
2. Add life_counter.js modal handling logic
3. Add polling for pending confirmations

**Rollback Plan**:
- If issues detected: Disable background scheduler, remove API routes
- Database changes are additive (safe to leave columns)
- Frontend changes can be reverted instantly (static files)

---

## Open Questions (All Resolved)

1. ~~Turn order requirement~~ → **RESOLVED**: Required field, no default
2. ~~Expiration timing~~ → **RESOLVED**: 24hr reminder, 48hr auto-expire
3. ~~Opponent search scope~~ → **RESOLVED**: All user_profiles, prioritize recent opponents
4. ~~Notification method~~ → **RESOLVED**: Polling for MVP, WebSocket future enhancement

---

## References & Resources

- **Flask APScheduler**: https://apscheduler.readthedocs.io/en/3.x/
- **Fetch API MDN**: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
- **SQLite ALTER TABLE**: https://www.sqlite.org/lang_altertable.html
- **Flask Session Security**: https://flask.palletsprojects.com/en/2.3.x/security/

---

## Next Steps

Proceed to Phase 1: Design & Contracts
- Create data-model.md with updated schema
- Define API contracts (REST endpoints)
- Write quickstart.md for development setup
