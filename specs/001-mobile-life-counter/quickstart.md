# Developer Quickstart: Mobile Life Counter

**Feature**: Mobile Life Counter with Match Reporting
**Branch**: `001-mobile-life-counter`
**Date**: 2026-03-09

This guide helps developers quickly understand and implement the mobile life counter feature.

---

## What We're Building

A mobile-optimized life counter page that:
1. ✅ Tracks dual-player life totals during Sorcery games
2. ✅ Supports element selection and additional game counters
3. ✅ Enables match result reporting when a player reaches 0 life
4. ✅ Sends real-time notifications to opponents for match confirmation
5. ✅ Integrates with existing ELO ranking system

**Target Users**: Mobile web users (iOS Safari 12+, Android Chrome 80+)
**Architecture**: Flask web app + client-side JavaScript + SSE notifications + SQLite database

---

## Prerequisites

Before starting implementation:

- [ ] Read [spec.md](spec.md) - Feature requirements and success criteria
- [ ] Read [research.md](research.md) - Technical decisions (SSE, session storage, UI patterns)
- [ ] Read [data-model.md](data-model.md) - Database schema and entities
- [ ] Read [contracts/api-endpoints.md](contracts/api-endpoints.md) - API specifications
- [ ] Read [contracts/notifications.md](contracts/notifications.md) - SSE event specifications

**Estimated Implementation Time**: 3-5 days for MVP (1 developer)

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                     User Flow (Mobile)                       │
├─────────────────────────────────────────────────────────────┤
│ 1. Tap life counter icon in navbar                          │
│ 2. Life counter page loads (GET /life-counter)              │
│ 3. Track life totals with +/- buttons                       │
│    ├─ State saved in sessionStorage (client-side)           │
│    └─ No backend calls during tracking                      │
│ 4. Player reaches 0 life → "Report Match" button appears    │
│ 5. Submit match report (POST /api/life-counter/match-report)│
│    ├─ Creates match_confirmations record (status: pending)  │
│    └─ Triggers SSE notification to opponent                 │
│ 6. Opponent receives notification (SSE stream)              │
│ 7. Opponent confirms (POST /api/life-counter/confirm/{id})  │
│    ├─ Updates match_confirmations (status: confirmed)       │
│    ├─ Creates match_records entry                           │
│    └─ Updates ELO ratings via existing service              │
└─────────────────────────────────────────────────────────────┘
```

**Tech Stack**:
- **Backend**: Python 3.11+, Flask 3.0+, Flask-Login, SQLite3
- **Frontend**: Vanilla JavaScript (ES6+), CSS Grid/Flexbox, sessionStorage API
- **Real-time**: Server-Sent Events (SSE) via Flask `stream_with_context()`
- **Testing**: pytest with existing fixtures

---

## File Structure Roadmap

### Files to CREATE (New)

```text
web-app/
├── routes/
│   └── api/
│       ├── life_counter.py          # Match report submission, confirmation
│       └── notifications.py         # SSE stream endpoint
├── services/
│   ├── match_confirmation.py        # Confirmation business logic
│   └── notification.py              # SSE notification helpers
├── repositories/
│   └── match_confirmation.py        # Database access for confirmations
├── templates/
│   └── pages/
│       └── life_counter.html        # Main life counter page
├── static/
│   ├── css/pages/
│   │   └── life_counter.css        # Life counter styles
│   └── js/pages/
│       └── life_counter.js         # Counter logic, SSE client
└── tests/
    ├── test_life_counter_api.py    # API endpoint tests
    ├── test_match_confirmation.py  # Confirmation flow tests
    └── test_notification_service.py # SSE notification tests
```

### Files to MODIFY (Extend)

```text
web-app/
├── routes/
│   └── pages.py                     # Add /life-counter route
├── templates/
│   └── components/
│       └── navbar.html              # Add life counter icon (mobile only)
└── static/
    ├── css/components/
    │   └── navbar.css               # Icon styles
    └── images/
        └── icons/
            └── life-counter.svg     # Navbar icon asset

discord-bot/
└── match_records.db                 # Run migration to add match_confirmations table
```

---

## Implementation Checklist

### Phase 1: Database & Migrations (Day 1)

- [ ] Create migration script: `web-app/migrations/001_add_life_counter_support.sql`
- [ ] Run migration to create `match_confirmations` table
- [ ] Run migration to extend `match_records` table with life counter columns
- [ ] Verify schema with `sqlite3 discord-bot/match_records.db ".schema match_confirmations"`
- [ ] Create `match_confirmation.py` repository with CRUD functions

**Key Functions to Implement**:
```python
# web-app/repositories/match_confirmation.py
def create_confirmation(submitter_id, opponent_id, winner_id, loser_id, final_life_winner, final_life_loser, winner_deck_url=None, loser_deck_url=None) -> int
def get_pending_confirmations(user_id) -> list[dict]
def update_confirmation_status(confirmation_id, status, dispute_reason=None) -> bool
def get_expired_confirmations() -> list[dict]
```

### Phase 2: Backend Services (Day 1-2)

- [ ] Implement `match_confirmation.py` service with business logic
- [ ] Implement confirmation processing (confirm/dispute/auto-confirm)
- [ ] Integrate with existing ELO service (`discord-bot/services/elo_service.py`)
- [ ] Implement `notification.py` service for SSE helpers

**Key Functions to Implement**:
```python
# web-app/services/match_confirmation.py
def process_confirmation(confirmation_id, action, user_id) -> dict  # action: 'confirm' or 'dispute'
def create_match_report(submitter_id, opponent_id, match_result, decks) -> int
def auto_confirm_expired() -> int  # Returns count of auto-confirmed matches
```

### Phase 3: API Endpoints (Day 2)

- [ ] Implement `life_counter.py` API routes
  - [ ] POST `/api/life-counter/match-report` - Submit report
  - [ ] POST `/api/life-counter/confirm/{id}` - Confirm match
  - [ ] POST `/api/life-counter/dispute/{id}` - Dispute match
  - [ ] GET `/api/life-counter/pending-confirmations` - Get pending
  - [ ] GET `/api/life-counter/lfg-opponents` - Get recent opponents
- [ ] Implement `notifications.py` SSE route
  - [ ] GET `/api/notifications/stream` - SSE stream
- [ ] Add routes to Flask blueprint registration in `routes/__init__.py`

**Example Route Implementation**:
```python
# web-app/routes/api/life_counter.py
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.match_confirmation import create_match_report, process_confirmation

bp = Blueprint('life_counter', __name__, url_prefix='/api/life-counter')

@bp.route('/match-report', methods=['POST'])
@login_required
def submit_match_report():
    data = request.get_json()
    # Validate input
    # Create match confirmation
    # Return confirmation_id and expires_at
    pass
```

### Phase 4: Frontend Page (Day 2-3)

- [ ] Create `life_counter.html` template with base layout
- [ ] Implement life counter UI with element icons
- [ ] Add touch-optimized +/- buttons (48px tap targets)
- [ ] Implement session storage for state persistence
- [ ] Add match report form (appears when life → 0)
- [ ] Implement confirmation modal for opponent notifications

**HTML Structure**:
```html
<!-- web-app/templates/pages/life_counter.html -->
{% extends "base.html" %}
{% block content %}
<div class="life-counter-container">
  <header class="life-counter-header">
    <h1>Life Counter</h1>
    <button id="reset-btn">Reset</button>
  </header>

  <div class="element-selector">
    <!-- Element icons: fire, water, earth, air -->
  </div>

  <div class="player-section" data-player="1">
    <h2>Player 1: You</h2>
    <div class="life-display">
      <button class="decrement" data-player="1" data-amount="1">-1</button>
      <span class="life-value">20</span>
      <button class="increment" data-player="1" data-amount="1">+1</button>
    </div>
    <!-- Additional counters -->
  </div>

  <div class="player-section" data-player="2">
    <!-- Same structure for player 2 -->
  </div>

  <button id="report-match-btn" class="hidden">Report Match</button>
</div>

<!-- Match report modal -->
<div id="match-report-modal" class="modal hidden">
  <!-- Form for submitting match report -->
</div>

<!-- Confirmation request modal -->
<div id="confirmation-modal" class="modal hidden">
  <!-- Display pending confirmation for user to confirm/dispute -->
</div>
{% endblock %}
```

### Phase 5: Frontend JavaScript (Day 3-4)

- [ ] Implement state management (load/save sessionStorage)
- [ ] Implement counter increment/decrement logic
- [ ] Implement match report form submission
- [ ] Implement SSE client for notifications
- [ ] Implement confirmation modal interactions
- [ ] Add fallback polling if SSE fails

**JavaScript Modules**:
```javascript
// web-app/static/js/pages/life_counter.js

// 1. State Management
const LifeCounterState = {
  load: () => JSON.parse(sessionStorage.getItem('lifeCounterState')) || initDefaultState(),
  save: (state) => sessionStorage.setItem('lifeCounterState', JSON.stringify(state)),
  reset: () => sessionStorage.removeItem('lifeCounterState')
};

// 2. Counter Logic
function updateLife(player, amount) {
  const state = LifeCounterState.load();
  state.players[player].life += amount;
  state.lastModified = Date.now();
  LifeCounterState.save(state);
  renderUI(state);
  checkForGameEnd(state);
}

// 3. Match Report
async function submitMatchReport(data) {
  const response = await fetch('/api/life-counter/match-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  return response.json();
}

// 4. SSE Client
function connectSSE() {
  const eventSource = new EventSource('/api/notifications/stream');
  eventSource.addEventListener('pending_confirmation', (event) => {
    const confirmation = JSON.parse(event.data);
    showConfirmationModal(confirmation);
  });
  // Handle errors and reconnection
}
```

### Phase 6: Mobile Navbar Icon (Day 4)

- [ ] Add life counter icon to navbar (mobile only, hide on desktop)
- [ ] Create or source icon asset (`life-counter.svg`)
- [ ] Position icon in top-right corner of navbar
- [ ] Add active state when on life counter page

**Navbar Modification**:
```html
<!-- web-app/templates/components/navbar.html -->
<!-- In the "Right side" section, after line 180 -->
<div class="md:hidden flex items-center gap-2">
  <!-- Life Counter Icon (mobile only) -->
  <a
    href="/life-counter"
    class="flex items-center justify-center w-10 h-10 rounded hover:bg-white/10 transition-colors"
    aria-label="Life Counter"
    title="Life Counter">
    <img src="{{ url_for('static', filename='images/icons/life-counter.svg') }}" alt="" class="w-6 h-6">
  </a>
  {% if current_user %}
    <!-- User profile link -->
  {% endif %}
</div>
```

### Phase 7: Testing (Day 4-5)

- [ ] Write unit tests for repository functions
- [ ] Write unit tests for service functions
- [ ] Write integration tests for API endpoints
- [ ] Write end-to-end test for full match report flow
- [ ] Test SSE notification delivery
- [ ] Test on real mobile devices (iOS Safari, Android Chrome)

**Test Coverage Goals**:
- Repository layer: 90%+
- Service layer: 85%+
- API endpoints: 80%+
- Client-side JS: Manual testing (browser console)

**Example Test**:
```python
# tests/test_match_confirmation.py
def test_create_match_report(client, authenticated_user):
    """Test creating a match report creates pending confirmation."""
    payload = {
        "opponent_identification": {"method": "discord_id", "value": "123456789"},
        "match_result": {"winner": "self", "final_life": {"self": 15, "opponent": 0}},
        "decks": {"self_deck_url": "https://curiosa.io/decks/abc"}
    }
    response = client.post('/api/life-counter/match-report', json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data['success'] is True
    assert 'confirmation_id' in data
```

### Phase 8: Cron Job for Auto-Confirm (Day 5)

- [ ] Create cron script to auto-confirm expired matches
- [ ] Schedule to run every 15 minutes
- [ ] Add logging for auto-confirmed matches

**Cron Script**:
```python
# web-app/scripts/auto_confirm_matches.py
from services.match_confirmation import auto_confirm_expired

if __name__ == '__main__':
    count = auto_confirm_expired()
    print(f"Auto-confirmed {count} expired match(es)")
```

**Crontab Entry**:
```bash
*/15 * * * * cd /path/to/web-app && python scripts/auto_confirm_matches.py >> logs/auto_confirm.log 2>&1
```

---

## Local Development Setup

### 1. Install Dependencies

```bash
cd web-app
pip install -r requirements.txt
```

### 2. Run Database Migration

```bash
sqlite3 ../discord-bot/match_records.db < migrations/001_add_life_counter_support.sql
```

### 3. Start Development Server

```bash
python app.py
```

App runs at `http://localhost:5000`

### 4. Test on Mobile

- **Option A**: Use Chrome DevTools device emulation (F12 → Toggle device toolbar)
- **Option B**: Use ngrok for real device testing:
  ```bash
  ngrok http 5000
  # Access via https://xxx.ngrok.io on your phone
  ```

---

## Testing Workflow

### Manual Testing Checklist

- [ ] Load `/life-counter` on mobile device
- [ ] Adjust life totals for both players
- [ ] Verify session storage persistence (refresh page, state preserved)
- [ ] Reduce player 2 life to 0 → "Report Match" button appears
- [ ] Submit match report → Check confirmation created in database
- [ ] On different device/account, check SSE notification received
- [ ] Confirm match → Verify ELO ratings updated
- [ ] Test dispute flow → Verify no ELO change

### Automated Testing

```bash
# Run all tests
pytest web-app/tests/test_life_counter*.py -v

# Run with coverage
pytest web-app/tests/test_life_counter*.py --cov=web-app --cov-report=html
```

---

## Common Issues & Solutions

### Issue: SSE Connection Drops

**Symptom**: Notifications not received, browser console shows SSE error

**Solutions**:
1. Check Flask server logs for SSE exceptions
2. Verify user is authenticated (SSE requires login)
3. Check for proxy/firewall blocking event-stream MIME type
4. Fallback to polling should trigger automatically after 5 failed reconnects

### Issue: Session Storage Not Persisting

**Symptom**: Life totals reset on page refresh

**Solutions**:
1. Check browser console for JavaScript errors
2. Verify `sessionStorage.setItem()` is called after state changes
3. Check if user has disabled cookies/storage (sessionStorage requires it)
4. Ensure correct storage key (`'lifeCounterState'`)

### Issue: Match Report 400 Error

**Symptom**: Match report submission fails with "Opponent not found"

**Solutions**:
1. Check opponent identification method (discord_username vs discord_id)
2. Verify opponent exists in Discord user cache/database
3. Test with LFG lookup method instead of manual entry
4. Check server logs for specific error message

---

## Performance Optimization Tips

1. **Debounce sessionStorage writes**: Limit saves to max 1 per 500ms (not every keystroke)
2. **Lazy-load SSE**: Only connect SSE stream when user is on life counter page or has pending confirmations
3. **Index database queries**: Ensure indexes exist on `opponent_discord_id` and `expires_at` columns
4. **Minimize SSE payload**: Only send changed data, not full state

---

## Deployment Checklist

Before merging to production:

- [ ] All tests passing (pytest exit code 0)
- [ ] Database migration tested on staging database
- [ ] SSE endpoint tested with Nginx reverse proxy
- [ ] Mobile UI tested on real iOS and Android devices
- [ ] Icon assets optimized (SVG preferred, <5KB)
- [ ] Error handling covers all edge cases (network failures, timeouts)
- [ ] Logging configured for debugging (INFO level minimum)
- [ ] Cron job scheduled for auto-confirm on production server

---

## Resources & References

- **Flask SSE Guide**: [https://maxhalford.github.io/blog/flask-sse-no-deps/](https://maxhalford.github.io/blog/flask-sse-no-deps/)
- **EventSource API Docs**: [https://developer.mozilla.org/en-US/docs/Web/API/EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- **Touch-Friendly UI**: [https://material.io/design/usability/accessibility.html](https://material.io/design/usability/accessibility.html)
- **Existing ELO Service**: `discord-bot/services/elo_service.py`
- **Existing Match Repo**: `web-app/repositories/matches.py`

---

## Next Steps

1. ✅ Read this quickstart guide
2. ⬜ Generate implementation tasks: Run `/speckit.tasks` to create tasks.md
3. ⬜ Start implementation following Phase 1-8 checklist above
4. ⬜ Submit PR when all tests pass and manual testing complete

**Questions?** Reference spec.md, research.md, data-model.md, or API contracts for detailed information.

---

**Last Updated**: 2026-03-09
