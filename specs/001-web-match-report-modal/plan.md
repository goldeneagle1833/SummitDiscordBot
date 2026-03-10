# Implementation Plan: Web-Based Match Reporting Modal

**Branch**: `001-web-match-report-modal` | **Date**: 2026-03-10 | **Spec**: [spec.md](./spec.md)

## Summary

Add web-based match reporting functionality that allows users to submit match results through the website with opponent confirmation workflow. Users report matches via modal forms on the life counter page, opponents receive notifications to confirm/deny, and the system automatically handles expiration (48hr) and reminders (24hr) for pending reports. Extends existing `match_confirmations` infrastructure with turn order tracking, autocomplete opponent search, and background job processing.

**Key Features**:
- Match report modal with opponent search, deck URLs, and turn order selection
- Two-phase confirmation: submitter reports → opponent confirms/denies
- Automatic expiration: 24hr reminder → 48hr auto-expire/void
- RESTful API endpoints for CRUD operations
- Background scheduler for reminders and expiration handling

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Flask 2.x, APScheduler 3.10+ (NEW), SQLite3
**Storage**: SQLite (`match_records.db`) - existing database with `match_confirmations`, `user_profiles`, `match_records` tables
**Testing**: pytest 7.x+ (existing)
**Target Platform**: Linux server (production), Windows/Mac (development)
**Project Type**: Web application (Flask backend + vanilla JS frontend)
**Performance Goals**: <500ms API response time, handle 50+ concurrent match reports, 30s notification polling
**Constraints**:
- Must integrate with existing Discord OAuth authentication
- Must use existing ELO calculation service (no changes to ELO logic)
- Must preserve existing database schema (additive changes only)
- Background jobs must be lightweight (no Celery/Redis infrastructure)

**Scale/Scope**:
- Expected load: 10-50 match reports per day, 100-500 autocomplete searches per day
- User base: ~100-500 active players
- Database size: ~1000 match confirmations per month
- Frontend: Single page (life counter) with 2 modals (report + confirmation)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution Status**: ❌ Not defined for this project

**Note**: The project does not have an established constitution (`.specify/memory/constitution.md` contains only template placeholders). This feature proceeds with standard Flask web application best practices:

✅ **Repository-Service-Route Pattern** (existing pattern in codebase):
- Clear separation: Routes (HTTP) → Services (business logic) → Repositories (data access)
- Already implemented for existing features (ELO, matches, players)
- This feature follows same architecture

✅ **Test Coverage Requirements**:
- Unit tests for repositories and services (pytest)
- Integration tests for API endpoints
- Frontend tests for modal interactions (manual QA initially)

✅ **Security Standards**:
- Authentication required for all API endpoints (Flask session)
- Input validation at multiple layers (client + server)
- SQL injection prevention (parameterized queries)
- XSS prevention (Jinja2 auto-escaping)

✅ **Performance Considerations**:
- Database indexes for query optimization
- Polling-based notifications (acceptable 30s latency)
- Graceful degradation (Curiosa API failures don't block reporting)

**Re-evaluation After Phase 1**: ✅ Design adheres to existing patterns, no constitution violations

## Project Structure

### Documentation (this feature)

```text
specs/001-web-match-report-modal/
├── spec.md              # Feature specification (functional requirements)
├── plan.md              # This file (implementation plan)
├── research.md          # Technical decisions and best practices
├── data-model.md        # Database schema and entity relationships
├── quickstart.md        # Developer setup guide
├── contracts/           # API contracts
│   └── api-endpoints.md # REST API documentation
├── checklists/          # Quality validation
│   └── requirements.md  # Spec validation checklist
└── tasks.md             # NOT YET CREATED - use /speckit.tasks command
```

### Source Code (repository root)

```text
web-app/                              # Flask web application
├── routes/
│   └── api/
│       └── match_reporting.py        # NEW: REST API endpoints
├── services/
│   └── match_confirmation.py         # EXTEND: Complete stub implementations
├── repositories/
│   ├── match_confirmation.py         # EXTEND: Add turn order, reminder methods
│   └── user_profiles.py              # EXISTING: No changes (used for autocomplete)
├── templates/
│   └── pages/
│       └── life_counter.html         # EXTEND: Add full modal forms
├── static/
│   ├── css/
│   │   └── pages/
│   │       └── life_counter.css      # EXTEND: Add modal styles
│   └── js/
│       └── pages/
│           └── life_counter.js       # EXTEND: Add modal interactions + API calls
├── app.py                            # EXTEND: Register match_reporting_bp, start scheduler
├── requirements.txt                  # EXTEND: Add APScheduler==3.10.4
└── webapp_config.py                  # EXISTING: No changes needed

discord-bot/
└── match_records.db                  # EXTEND: Add went_first, reminder_sent_at columns

specs/001-web-match-report-modal/
└── migration.sql                     # NEW: Database migration script
```

**Structure Decision**: Single web application (Option 2 pattern) with backend routes, services, repositories and frontend templates/static assets. This feature extends existing Flask application structure without introducing new projects or services.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations - table not applicable.*

## Phase 0: Research ✅ Complete

**Status**: All technical decisions finalized in [research.md](./research.md)

**Key Decisions**:
1. ✅ Database: Extend existing `match_confirmations` table (add 2 columns, 3 indexes)
2. ✅ Opponent Search: Server-side autocomplete with 2-tier approach (recent opponents → all users)
3. ✅ Notifications: Polling-based (30s interval), WebSocket future enhancement
4. ✅ Expiration System: APScheduler background jobs (5min reminders, 15min expiration checks)
5. ✅ Turn Order Storage: Relative to submitter ('submitter'|'opponent')
6. ✅ Frontend: Vanilla JavaScript (matches existing codebase)
7. ✅ Deck URL Validation: Multi-level (client regex → server validation → optional Curiosa API check)

**Output**: [research.md](./research.md) with rationale, alternatives considered, and implementation guidance

## Phase 1: Design & Contracts ✅ Complete

**Status**: Data model and API contracts defined

**Artifacts**:
1. ✅ [data-model.md](./data-model.md) - Database schema, state diagrams, migration script
2. ✅ [contracts/api-endpoints.md](./contracts/api-endpoints.md) - REST API specifications (6 endpoints)
3. ✅ [quickstart.md](./quickstart.md) - Developer setup and workflow guide

**Database Changes**:
- **match_confirmations** table: Add `went_first TEXT`, `reminder_sent_at INTEGER`
- Add 3 indexes for query performance
- Update expiration logic from 24hr to 48hr (code change)

**API Endpoints** (6 total):
1. `GET /api/match-report/search-opponents` - Autocomplete opponent search
2. `POST /api/match-report/submit` - Submit new match report
3. `GET /api/match-report/pending` - Get user's pending confirmations
4. `GET /api/match-report/confirmation/{id}` - Get confirmation details
5. `POST /api/match-report/confirm/{id}` - Confirm opponent's report
6. `POST /api/match-report/deny/{id}` - Deny opponent's report

**Frontend Components**:
- Match Report Modal (7 UI elements: opponent search, deck URL inputs, turn order toggle, cancel/won/lost buttons)
- Match Confirmation Modal (3 UI elements: details display, confirm/deny buttons)
- Notification polling (background JavaScript)

## Phase 2: Task Generation

**Next Command**: `/speckit.tasks`

**Expected Task Breakdown** (estimate: 40-50 tasks):

### Backend (25-30 tasks)
- Database migration (2 tasks)
- Repository layer extensions (5-7 tasks)
- Service layer implementations (8-10 tasks)
- API route handlers (6 tasks)
- Background scheduler setup (3-4 tasks)
- Unit tests (8-10 tasks)
- Integration tests (3-5 tasks)

### Frontend (15-20 tasks)
- HTML modal structure (3-4 tasks)
- CSS styling for modals (4-5 tasks)
- JavaScript form handling (6-8 tasks)
- API integration (4-5 tasks)
- Manual QA testing (2-3 tasks)

### Documentation & Deployment (3-5 tasks)
- Update README (1 task)
- Deployment guide (1 task)
- Production deployment (2-3 tasks)

## Implementation Sequence

**Recommended Order** (following dependency chain):

1. **Database Foundation** (1-2 hours)
   - Run migration script
   - Add indexes
   - Verify schema changes

2. **Repository Layer** (3-4 hours)
   - Extend `MatchConfirmationRepository` with new methods
   - Add turn order support
   - Add reminder tracking methods
   - Write repository unit tests

3. **Service Layer** (4-6 hours)
   - Implement `MatchConfirmationService` methods (complete stubs)
   - Add validation logic
   - Implement confirmation/denial workflows
   - Add background job methods (send_reminders, expire_reports)
   - Write service unit tests

4. **API Routes** (3-4 hours)
   - Create `match_reporting.py` blueprint
   - Implement 6 API endpoints
   - Add authentication/authorization checks
   - Write integration tests

5. **Background Scheduler** (2-3 hours)
   - Setup APScheduler in `app.py`
   - Register reminder job (every 5 minutes)
   - Register expiration job (every 15 minutes)
   - Add graceful shutdown handling

6. **Frontend - Match Report Modal** (4-6 hours)
   - Add HTML form structure
   - Implement opponent autocomplete
   - Add deck URL inputs with validation
   - Add turn order toggle buttons
   - Wire up submit logic (I Won / I Lost)
   - Add CSS styling

7. **Frontend - Confirmation Modal** (2-3 hours)
   - Add HTML confirmation display
   - Implement confirm/deny buttons
   - Add notification polling
   - Display pending count badge

8. **Integration & Testing** (3-4 hours)
   - End-to-end manual testing
   - Fix bugs and edge cases
   - Performance testing (load simulation)

9. **Documentation & Deployment** (2-3 hours)
   - Update webapp README
   - Document deployment steps
   - Deploy to production
   - Monitor logs

**Total Estimated Time**: 24-35 hours

## Testing Strategy

### Unit Tests

**Target Coverage**: >80%

**Test Files**:
- `tests/test_match_confirmation_repo.py` - Repository methods
- `tests/test_match_confirmation_service.py` - Service business logic
- `tests/test_match_reporting_api.py` - API endpoint handlers

**Key Test Cases**:
1. Repository: CRUD operations, duplicate detection, expiration queries
2. Service: Validation rules, confirmation workflow, ELO integration
3. API: Authentication, authorization, error handling, happy paths

### Integration Tests

**Scope**: API endpoints → Service → Repository → Database (in-memory SQLite)

**Test Scenarios**:
1. Full match reporting flow: submit → confirm → verify match created
2. Denial flow: submit → deny → verify no match created
3. Expiration flow: submit → wait 48hr (mocked) → verify expired
4. Duplicate prevention: submit → submit again → verify error

### Manual QA Checklist

**Pre-Deployment**:
- [ ] Authentication works (Discord OAuth)
- [ ] Opponent search returns results
- [ ] Deck URL validation shows errors
- [ ] Turn order required (buttons disabled until selected)
- [ ] Match report submission creates pending confirmation
- [ ] Opponent sees pending confirmation notification
- [ ] Confirm button finalizes match and updates ELO
- [ ] Deny button rejects report with no ELO changes
- [ ] 24hr reminder sends notification (test with mocked time)
- [ ] 48hr expiration marks report as void (test with mocked time)
- [ ] Error messages are user-friendly
- [ ] Mobile responsive design works

## Dependencies & Blockers

**External Dependencies**:
- ✅ Discord OAuth (already configured)
- ✅ SQLite database (already exists)
- ✅ ELO service (existing, no changes needed)
- ⚠️ Curiosa API (optional, graceful degradation if down)

**Internal Dependencies**:
- ✅ `user_profiles` table populated (via OAuth login)
- ✅ `match_records` table exists (for recent opponent lookup)
- ✅ Existing repository/service pattern (architecture reference)

**Potential Blockers**:
- ⚠️ Background scheduler conflicts with Gunicorn workers (solution: use single worker or external cron)
- ⚠️ Database migration on production (solution: test on staging first, backup before migration)
- ⚠️ User confusion about 48hr expiration (solution: clear UI messaging + reminder notifications)

## Risk Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Database migration fails in production | HIGH | LOW | Test on staging, backup DB, have rollback script ready |
| APScheduler doesn't work with Gunicorn multi-worker | MEDIUM | MEDIUM | Use single worker or systemd timer as fallback |
| Users miss pending confirmations (no notifications) | MEDIUM | MEDIUM | Add prominent badge + email notifications (future) |
| Duplicate reports slip through validation | HIGH | LOW | Thorough unit tests, add unique constraint (optional) |
| Expiration job misses reports (downtime) | MEDIUM | LOW | Job catches up on restart, alerts on queue backlog |
| Curiosa API down blocks match reporting | LOW | MEDIUM | Graceful degradation (accept URL without validation) |

## Rollback Plan

**If Critical Issues Arise**:

1. **Disable Feature** (< 1 minute):
   ```python
   # In app.py, comment out:
   # app.register_blueprint(match_reporting_bp, url_prefix='/api/match-report')
   # scheduler.shutdown()
   # Restart Flask app
   ```

2. **Database Rollback** (< 5 minutes):
   ```sql
   -- New columns are nullable, can remain without breaking existing functionality
   -- If needed to fully rollback:
   DROP INDEX idx_opponent_pending;
   DROP INDEX idx_expires_reminder;
   DROP INDEX idx_submitter_recent;
   -- Note: SQLite doesn't support DROP COLUMN, columns remain but unused
   ```

3. **Code Rollback** (< 5 minutes):
   ```bash
   git revert <commit-hash>
   git push
   # Redeploy previous version
   systemctl restart summit-web
   ```

**Data Preservation**:
- Pending reports remain in database (can be processed later)
- No data loss even if feature is disabled
- Re-enabling feature resumes normal operation

## Monitoring & Observability

**Metrics to Track** (post-deployment):
1. Match report submission rate (per day/hour)
2. Confirmation rate (confirmed vs denied vs expired %)
3. Average time to confirmation (hours)
4. API endpoint response times
5. Background job execution time
6. Error rate by endpoint
7. Opponent search query performance

**Logging**:
```python
# Key log points:
logger.info(f"Match report submitted: id={confirmation_id}, submitter={user_id}")
logger.info(f"Match confirmed: id={confirmation_id}, match_id={match_id}")
logger.warning(f"Match denied: id={confirmation_id}, reason={reason}")
logger.error(f"Match expiration failed: id={confirmation_id}", exc_info=True)
```

**Alerts** (recommended):
- Background job failures (error count > 5 in 1 hour)
- API error rate > 10%
- Database connection errors
- Pending confirmations backlog > 100

## Success Criteria

**Functional** (from spec.md):
- ✅ Users can submit match reports in <60 seconds
- ✅ 95% of reports include valid deck URLs and all required fields
- ✅ 80% of confirmations occur within 24 hours
- ✅ <10% of reports expire due to timeout
- ✅ Zero duplicate or invalid match records created
- ✅ 90% first-attempt success rate

**Technical**:
- ✅ API response time <500ms (p95)
- ✅ Background jobs complete in <10 seconds
- ✅ Database queries use indexes (EXPLAIN QUERY PLAN shows index usage)
- ✅ Test coverage >80%
- ✅ Zero regressions in existing match reporting (Discord bot)

**User Experience**:
- ✅ Mobile responsive (tested on iOS/Android)
- ✅ Clear error messages (no technical jargon)
- ✅ Accessible (keyboard navigation, screen reader support)
- ✅ Translation keys for internationalization

## Future Enhancements

**Not in Scope for v1** (potential future work):

1. **WebSocket Notifications** (real-time)
   - Replace polling with Socket.IO
   - Instant notification delivery
   - Estimated effort: 8-12 hours

2. **Email Notifications**
   - Send email reminders at 24hr
   - Send expiration notices
   - Estimated effort: 4-6 hours

3. **Match Report Editing**
   - Allow submitter to edit before confirmation
   - Version history tracking
   - Estimated effort: 6-8 hours

4. **Admin Override**
   - Admins can force-confirm or reject reports
   - Audit trail for admin actions
   - Estimated effort: 4-6 hours

5. **Analytics Dashboard**
   - Match report statistics
   - Confirmation rate trends
   - User engagement metrics
   - Estimated effort: 12-16 hours

## References

- **Feature Spec**: [spec.md](./spec.md) - Functional requirements
- **Research**: [research.md](./research.md) - Technical decisions
- **Data Model**: [data-model.md](./data-model.md) - Database schema
- **API Contracts**: [contracts/api-endpoints.md](./contracts/api-endpoints.md) - REST API docs
- **Quickstart**: [quickstart.md](./quickstart.md) - Developer guide
- **Existing Code**: `web-app/repositories/match_confirmation.py`, `web-app/services/match_confirmation.py`

---

## Next Steps

1. ✅ Phase 0 Research - Complete
2. ✅ Phase 1 Design - Complete
3. → **Phase 2 Task Generation** - Run `/speckit.tasks` to generate detailed implementation tasks
4. → **Implementation** - Execute tasks in recommended order
5. → **Testing** - Run test suite, perform manual QA
6. → **Deployment** - Deploy to production, monitor metrics

**Command to Continue**: `/speckit.tasks`

---

**Plan Status**: ✅ Complete and ready for task generation

**Last Updated**: 2026-03-10
