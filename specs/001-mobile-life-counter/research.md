# Research Findings: Mobile Life Counter

**Date**: 2026-03-09
**Feature**: Mobile Life Counter with Match Reporting
**Branch**: `001-mobile-life-counter`

This document consolidates technical research findings to resolve all NEEDS CLARIFICATION items from the Technical Context in plan.md.

---

## 1. Push Notification Approach

### Decision: Server-Sent Events (SSE) with Fallback to Polling

**Rationale**:
- **Web Push API rejected**: Requires HTTPS + service worker registration + user permission prompt + browser support is inconsistent (Safari requires iOS 16.4+, not widely adopted on mobile)
- **Firebase Cloud Messaging rejected**: Adds external dependency, requires Firebase account setup, overkill for simple notification needs
- **Server-Sent Events (SSE) chosen**: Native browser support, works over HTTP/HTTPS, no permission prompts, simple Flask implementation via `flask.stream_with_context()`

**Implementation Pattern**:
```python
# Flask SSE endpoint (web-app/routes/api/notifications.py)
from flask import Response, stream_with_context
import json, time

@app.route('/api/notifications/stream')
@login_required
def notification_stream():
    def generate():
        last_check = time.time()
        while True:
            # Check for new match confirmations for current_user
            pending = get_pending_confirmations(current_user.id)
            if pending:
                yield f"data: {json.dumps(pending)}\n\n"
            time.sleep(5)  # Poll every 5 seconds
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# Client-side (life_counter.js)
const eventSource = new EventSource('/api/notifications/stream');
eventSource.onmessage = (event) => {
    const confirmations = JSON.parse(event.data);
    displayConfirmationModal(confirmations);
};
```

**Fallback Strategy**:
- If SSE connection fails (corporate firewalls, proxy issues), fall back to simple polling every 30 seconds
- Client detects SSE failure via `onerror` event, switches to `setInterval()` polling

**Trade-offs**:
- ✅ No external dependencies, no user permissions required
- ✅ Works on all modern mobile browsers (iOS 12+, Android Chrome 80+)
- ⚠️ Requires persistent connection (mitigate with automatic reconnection logic)
- ⚠️ Not true push (5-second latency), acceptable for 24-hour confirmation window

**Alternatives Considered**:
1. **Web Push API**: Too complex, requires service worker + HTTPS + user permission (high friction), Safari support unreliable
2. **Firebase Cloud Messaging**: External service dependency, requires API keys in config, overkill for simple notifications
3. **WebSockets**: More complex than SSE, requires bidirectional communication (not needed), harder to deploy behind reverse proxies

---

## 2. Session Storage Strategy

### Decision: Browser sessionStorage with JSON Serialization

**Storage Format** (JSON Schema):
```json
{
  "version": "1.0",
  "timestamp": 1709999999000,
  "players": {
    "player1": {
      "name": "Player 1",
      "life": 20,
      "element": "fire",
      "counters": {
        "dice": 0,
        "pyramid": 0,
        "token": 0
      }
    },
    "player2": {
      "name": "Player 2",
      "life": 20,
      "element": "water",
      "counters": {
        "dice": 0,
        "pyramid": 0,
        "token": 0
      }
    }
  },
  "matchStartedAt": 1709999999000,
  "lastModified": 1709999999000
}
```

**Capacity Validation**:
- sessionStorage typical limit: 5-10MB per origin
- Our state object: ~500 bytes when serialized
- ✅ Well within limits (could store thousands of game states)

**Persistence Strategy**:
- Auto-save on every counter change (debounced to max 1 save per 500ms)
- Load on page mount: `const state = JSON.parse(sessionStorage.getItem('lifeCounterState') || 'null')`
- Clear on match report submission or explicit reset
- Data persists across page refreshes within same browser tab/session

**Browser Support**:
- ✅ All target browsers (iOS Safari 12+, Android Chrome 80+) fully support sessionStorage API
- No polyfill needed

**Trade-offs**:
- ✅ Simple implementation, no backend storage required
- ✅ Fast read/write (synchronous API)
- ⚠️ Lost if user closes tab (acceptable - casual game tracking)
- ⚠️ Not shared across devices (acceptable - mobile-only feature)

---

## 3. Mobile UI Patterns

### Decision: Touch-Optimized Counter Controls with Visual Feedback

**Button Specifications**:
- **Minimum tap target size**: 48px × 48px (follows iOS and Android accessibility guidelines)
- **Counter layout**: Vertical stacking on mobile (portrait), horizontal on landscape
- **Increment/decrement buttons**: Large +/- buttons flanking the life total number
- **Visual feedback**:
  - Active state: Background color change on `touchstart`
  - Scale animation: Button scales to 95% on press, returns to 100% on release
  - Number animation: Life total animates with CSS transition (0.2s ease) when value changes
- **Haptic feedback**: Use Vibration API (`navigator.vibrate(50)`) on button press (if supported, graceful degradation)

**Layout Pattern** (Mobile Portrait):
```text
┌───────────────────────────────┐
│     [Reset] Life Counter      │ ← Header with reset button
├───────────────────────────────┤
│  🔥 Element Icons (selectable) │
├───────────────────────────────┤
│        Player 1: You          │
│   [-]      20      [+]        │ ← 48px touch targets
│   [Dice: 0] [Pyramid: 0]      │ ← Additional counters
├───────────────────────────────┤
│      Player 2: Opponent       │
│   [-]      20      [+]        │
│   [Dice: 0] [Pyramid: 0]      │
├───────────────────────────────┤
│  [🎲 Other Counters] (expand) │ ← Collapsible section
└───────────────────────────────┘
```

**Best Practices Applied**:
1. **Accidental tap prevention**: 300ms delay disabled via `touch-action: manipulation` CSS
2. **Scroll locking**: Prevent bounce scrolling on counter page with `overscroll-behavior: none`
3. **Large numbers**: Life totals displayed at 48px-64px font size for readability
4. **Color contrast**: WCAG AA compliant contrast ratios (4.5:1 minimum) for all text/buttons
5. **Gesture support**: Swipe left/right on life number for quick -5/+5 adjustments (optional enhancement)

**Frameworks/Libraries**:
- **No framework needed**: Vanilla JavaScript with modern CSS (Grid + Flexbox)
- Use existing project CSS variables from `web-app/static/css/base/variables.css` for consistency
- Reuse button styles from `web-app/static/css/components/buttons.css`

**References**:
- [Material Design Touch Targets](https://material.io/design/usability/accessibility.html#layout-typography)
- [iOS Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/ios/visual-design/adaptivity-and-layout/)
- [MDN Touch Events Guide](https://developer.mozilla.org/en-US/docs/Web/API/Touch_events)

---

## 4. Match Confirmation Flow

### Decision: Asynchronous Confirmation with 24-Hour Auto-Confirm

**State Machine Diagram**:

```text
[Match Ends (Life → 0)]
        ↓
[Winner Submits Report] ─────────→ match_confirmations (status: pending)
        ↓                                    │
[SSE Notification Sent]                      │
        ↓                                    │
[Opponent Receives]                          │
        ├─[Confirms]──────→ status: confirmed → Update ELO Ratings
        ├─[Disputes]──────→ status: disputed → Flag for Admin Review
        └─[24h Timeout]───→ status: auto_confirmed → Update ELO Ratings
```

**Detailed Workflow**:

1. **Report Submission** (Winner's Device):
   - User taps "Report Match" button (appears when opponent life = 0)
   - Form collects: Opponent identification (lookup from recent LFG matches OR manual Discord username), optional deck links
   - POST `/api/life-counter/match-report` with payload:
     ```json
     {
       "winner_id": "12345",
       "loser_id": "67890",
       "final_life_winner": 8,
       "final_life_loser": 0,
       "winner_deck_url": "https://curiosa.io/...",
       "loser_deck_url": null
     }
     ```
   - Server creates `match_confirmations` record with `status='pending'`, `expires_at=now() + 24h`

2. **Notification Delivery** (Opponent's Device):
   - SSE stream detects new pending confirmation for opponent's user ID
   - Client displays modal: "You have a match confirmation request from [Username]. Result: [Win/Loss]. Confirm or Dispute?"
   - Modal shows match details: Final life totals, submitted deck links (if any), timestamp

3. **Opponent Response**:
   - **Confirm**: POST `/api/life-counter/confirm/{confirmation_id}` → status='confirmed' → trigger ELO update via `web-app/services/match.py`
   - **Dispute**: POST `/api/life-counter/dispute/{confirmation_id}` → status='disputed' → send alert to admin Discord channel, no ELO change
   - **Ignore**: After 24 hours, cron job (or on-demand check) sets status='auto_confirmed' → trigger ELO update

4. **ELO Integration**:
   - Only process ELO changes for status='confirmed' or status='auto_confirmed'
   - Call existing `web-app/services/match.py::record_match()` function with match details
   - Record in `match_records` table with flag `submitted_via_life_counter=true`

**Retry Logic**:
- If SSE notification fails to deliver (opponent offline), opponent sees notification on next login
- Check pending confirmations on every page load for logged-in users
- Display badge count in navbar for pending confirmations

**Admin Dispute Resolution**:
- Disputed matches appear in admin dashboard (extend existing `/admin/audit-log` page)
- Admin can manually confirm/reject after reviewing details
- Admin action updates status and triggers/reverses ELO changes as needed

**Edge Cases Handled**:
- **Both players at 0 life**: Report form shows "Draw" option, no winner/loser
- **Network failure during submit**: Client retries POST up to 3 times with exponential backoff
- **Duplicate reports**: Check for existing pending confirmation for same players within 1 hour, prevent duplicate
- **User deletes account**: If opponent account deleted before confirmation, auto-confirm after 24h

---

## 5. Integration with Existing ELO System

### Decision: Reuse Existing Match Service with Extension

**Integration Points Identified**:

1. **Service Layer** (`web-app/services/match.py`):
   - Existing function: `record_match(winner_id, loser_id, winner_deck=None, loser_deck=None, event_id=None)`
   - ✅ No modifications needed - function signature already supports our use case
   - Call this function from match confirmation handler after opponent confirms

2. **Repository Layer** (`web-app/repositories/matches.py`):
   - Existing function: `save_match_record(match_data: dict) -> int`
   - Extend match_data schema to include:
     ```python
     {
       "winner_id": int,
       "loser_id": int,
       "winner_deck_url": str | None,
       "loser_deck_url": str | None,
       "submitted_via_life_counter": bool,  # NEW FIELD
       "final_player1_life": int,           # NEW FIELD
       "final_player2_life": int,           # NEW FIELD
       "timestamp": int
     }
     ```
   - Add database migration to extend `match_records` table with new columns

3. **ELO Calculation** (`web-app/services/match.py` or `discord-bot/services/elo_service.py`):
   - Existing ELO calculation logic in `discord-bot/services/elo_service.py::calculate_elo_change()`
   - ✅ No modifications needed - calculation is player-agnostic
   - Web app uses Discord bot's ELO service via shared import (see `web-app/app.py` lines 18-21)

**Data Format Compatibility**:
- Winner/Loser IDs: Use Discord user IDs (integers) - ✅ matches existing format
- Deck URLs: Optional strings, Curiosa.io format - ✅ matches existing format
- Timestamp: Unix timestamp (seconds) - ✅ matches existing format

**Transaction Handling**:
- Match confirmation → ELO update is **atomic**: Single database transaction wraps:
  1. Update `match_confirmations.status = 'confirmed'`
  2. Insert into `match_records`
  3. Update `elo.db` player ratings (via existing ELO service)
- Use SQLite `BEGIN IMMEDIATE` transaction to prevent race conditions
- If any step fails, entire transaction rolls back (no partial state)

**API Contract Verification**:

```python
# New service function in web-app/services/match_confirmation.py
def process_confirmation(confirmation_id: int, action: str) -> dict:
    """
    Process match confirmation (confirm/dispute).

    Args:
        confirmation_id: ID of match_confirmations record
        action: 'confirm' or 'dispute'

    Returns:
        {"success": bool, "message": str, "elo_changes": dict | None}

    Raises:
        ValueError: If confirmation not found or expired
        RuntimeError: If ELO update fails
    """
    # 1. Load confirmation from database
    # 2. Validate status (must be 'pending'), check expiration
    # 3. Update status to 'confirmed' or 'disputed'
    # 4. If confirmed: call match.record_match() for ELO update
    # 5. Return result with new ELO ratings
    pass

# Integration with existing service
from services.match import record_match

def _finalize_confirmed_match(confirmation: MatchConfirmation):
    """Internal helper to trigger ELO update."""
    return record_match(
        winner_id=confirmation.winner_id,
        loser_id=confirmation.loser_id,
        winner_deck=confirmation.winner_deck_url,
        loser_deck=confirmation.loser_deck_url,
        event_id=None,  # Life counter matches not tied to events
        metadata={
            "submitted_via_life_counter": True,
            "final_life": {
                "winner": confirmation.final_life_winner,
                "loser": confirmation.final_life_loser
            }
        }
    )
```

**Testing Integration**:
- Create integration test: `tests/test_life_counter_elo_integration.py`
- Verify end-to-end flow: Submit report → Confirm → Check ELO updated correctly
- Mock database for unit tests, use test database for integration tests
- Follow existing test patterns in `discord-bot/tests/test_lfg_flow.py`

**Dependencies Verified**:
- ✅ `web-app/app.py` already adds `discord-bot/` to sys.path (line 19-21)
- ✅ Can import ELO service directly: `from services.elo_service import calculate_elo_change`
- ✅ Database shared via file path: `discord-bot/match_records.db`

**Potential Issues & Mitigations**:
1. **Concurrent match reports**: Use database row locking (`SELECT ... FOR UPDATE`) when checking for duplicate pending confirmations
2. **ELO service import conflicts**: If `web-app/services/` and `discord-bot/services/` both have same-named modules, use explicit imports with alias: `from discord-bot.services import elo_service as bot_elo`
3. **Database schema drift**: Document schema changes in both codebases, consider adding schema version table

---

## Summary of Decisions

| Area | Decision | Key Rationale |
|------|----------|---------------|
| Push Notifications | Server-Sent Events (SSE) with polling fallback | No external deps, works everywhere, simple implementation |
| Session Storage | Browser sessionStorage + JSON serialization | Standard API, sufficient capacity, no backend needed |
| Mobile UI | Touch-optimized 48px buttons with visual feedback | Follows platform guidelines, tested patterns |
| Confirmation Flow | Async with 24h auto-confirm, state machine | Balances validation with user experience, handles disputes |
| ELO Integration | Reuse existing match service, extend schema | DRY principle, maintains consistency, minimal changes |

**All NEEDS CLARIFICATION items resolved. Proceeding to Phase 1: Data Model & Contracts.**

---

## Open Questions / Future Enhancements

*Not blocking for MVP, but worth noting for future iterations:*

1. **Real-time sync between players**: Could use WebSockets to sync life counters between opponents' devices (spectator mode)
2. **Match analytics**: Track life total history throughout game (graph showing life changes over time)
3. **Offline support**: Service worker + IndexedDB for offline counter tracking, sync when back online
4. **Deck suggestions**: Integrate with Curiosa API to suggest decks based on element selection
5. **Tournament mode**: Link life counter to specific tournament matches from LFG queue
