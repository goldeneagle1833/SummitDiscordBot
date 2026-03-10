# Notification Contracts: Server-Sent Events (SSE)

**Feature**: Mobile Life Counter with Match Reporting
**Branch**: `001-mobile-life-counter`
**Date**: 2026-03-09

This document defines the Server-Sent Events (SSE) contract for real-time match confirmation notifications.

---

## Overview

**Technology**: Server-Sent Events (EventSource API)
**Endpoint**: `/api/notifications/stream`
**Protocol**: HTTP/1.1 with `text/event-stream` MIME type
**Authentication**: Required (Flask-Login session cookie)

**Why SSE?**:
- Native browser support (no library required)
- Works over HTTP/HTTPS
- Automatic reconnection on connection drop
- Simpler than WebSockets for one-way server→client messaging
- No permission prompts required

**Fallback Strategy**: If SSE fails (corporate firewall, proxy), client falls back to polling `/api/life-counter/pending-confirmations` every 30 seconds.

---

## SSE Stream Endpoint

### **GET** `/api/notifications/stream`

**Purpose**: Establish persistent connection for real-time match confirmation notifications.

**Authentication**: Required (Flask-Login session cookie)

**Request Headers**:
```http
Accept: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

**Response Headers**:
```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
Connection: keep-alive
```

**Response Body** (SSE format):

SSE messages follow the [EventSource specification](https://html.spec.whatwg.org/multipage/server-sent-events.html):

```text
event: pending_confirmation
data: {"confirmation_id": 42, "submitter": {...}, "match_details": {...}, "expires_at": 1710086400}

event: pending_confirmation
data: {"confirmation_id": 43, "submitter": {...}, "match_details": {...}, "expires_at": 1710086500}

event: heartbeat
data: {"timestamp": 1709999999}
```

Each message consists of:
- `event:` line - Event type (optional, defaults to "message")
- `data:` line - JSON payload
- Blank line separator

---

## Event Types

### 1. pending_confirmation

**Purpose**: Notify user of new match confirmation request from opponent.

**Event Name**: `pending_confirmation`

**Payload** (JSON):
```json
{
  "confirmation_id": 42,
  "submitter": {
    "discord_id": "123456789",
    "username": "OpponentName",
    "avatar_url": "https://cdn.discordapp.com/avatars/..."
  },
  "match_details": {
    "winner": "submitter" | "you",
    "final_life": {
      "submitter": 15,
      "you": 0
    },
    "decks": {
      "submitter_deck_url": "https://curiosa.io/decks/...",
      "your_deck_url": null
    }
  },
  "created_at": 1709999999,
  "expires_at": 1710086400,
  "time_remaining_seconds": 86400
}
```

**Payload Fields**:
- `confirmation_id` (integer): Unique ID for this confirmation request
- `submitter.discord_id` (string): Discord user ID of player who submitted report
- `submitter.username` (string): Discord username of submitter
- `submitter.avatar_url` (string, nullable): Discord avatar URL if available
- `match_details.winner` (string): "submitter" or "you" - who won the match
- `match_details.final_life` (object): Final life totals for both players
- `match_details.decks` (object): Deck URLs if provided
- `created_at` (integer): Unix timestamp when confirmation was created
- `expires_at` (integer): Unix timestamp when auto-confirm triggers
- `time_remaining_seconds` (integer): Seconds until expiration (for countdown display)

**When Sent**:
- Immediately when new match confirmation is created for this user
- On initial connection, all pending confirmations are sent as separate events

**Client Handling**:
```javascript
eventSource.addEventListener('pending_confirmation', (event) => {
  const confirmation = JSON.parse(event.data);
  displayConfirmationModal(confirmation);
  playNotificationSound();
  navigator.vibrate(200); // Haptic feedback on mobile
});
```

---

### 2. confirmation_update

**Purpose**: Notify user when a confirmation they submitted is processed (opponent confirmed/disputed).

**Event Name**: `confirmation_update`

**Payload** (JSON):
```json
{
  "confirmation_id": 42,
  "status": "confirmed" | "disputed",
  "opponent": {
    "discord_id": "987654321",
    "username": "OpponentName"
  },
  "elo_changes": {
    "your_old_elo": 1500,
    "your_new_elo": 1516,
    "your_change": +16,
    "opponent_old_elo": 1480,
    "opponent_new_elo": 1464,
    "opponent_change": -16
  } | null
}
```

**Payload Fields**:
- `confirmation_id` (integer): ID of the confirmation that was updated
- `status` (string): "confirmed" or "disputed"
- `opponent` (object): Opponent who confirmed/disputed
- `elo_changes` (object | null): ELO rating changes if confirmed, null if disputed

**When Sent**:
- When opponent confirms or disputes a match report you submitted
- Sent to the submitter, not the opponent

**Client Handling**:
```javascript
eventSource.addEventListener('confirmation_update', (event) => {
  const update = JSON.parse(event.data);
  if (update.status === 'confirmed') {
    showSuccessToast(`Match confirmed by ${update.opponent.username}! Your new ELO: ${update.elo_changes.your_new_elo}`);
  } else if (update.status === 'disputed') {
    showWarningToast(`Match disputed by ${update.opponent.username}. Flagged for admin review.`);
  }
});
```

---

### 3. heartbeat

**Purpose**: Keep connection alive and detect client disconnections.

**Event Name**: `heartbeat`

**Payload** (JSON):
```json
{
  "timestamp": 1709999999
}
```

**Payload Fields**:
- `timestamp` (integer): Current server Unix timestamp (seconds)

**When Sent**:
- Every 30 seconds while connection is open
- Helps prevent timeout from proxies/load balancers

**Client Handling**:
```javascript
eventSource.addEventListener('heartbeat', (event) => {
  const heartbeat = JSON.parse(event.data);
  lastHeartbeat = heartbeat.timestamp;
  // Update connection status indicator if needed
});
```

---

## Connection Management

### Client-Side Connection Code

```javascript
// Initialize SSE connection
let eventSource = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 5000; // 5 seconds

function connectSSE() {
  // Check if already connected
  if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
    return;
  }

  eventSource = new EventSource('/api/notifications/stream');

  // Connection opened
  eventSource.onopen = () => {
    console.log('SSE connection established');
    reconnectAttempts = 0;
    updateConnectionStatus('connected');
  };

  // Handle pending_confirmation events
  eventSource.addEventListener('pending_confirmation', (event) => {
    const confirmation = JSON.parse(event.data);
    displayConfirmationModal(confirmation);
  });

  // Handle confirmation_update events
  eventSource.addEventListener('confirmation_update', (event) => {
    const update = JSON.parse(event.data);
    handleConfirmationUpdate(update);
  });

  // Handle heartbeat events
  eventSource.addEventListener('heartbeat', (event) => {
    const heartbeat = JSON.parse(event.data);
    lastHeartbeat = heartbeat.timestamp;
  });

  // Connection error/closed
  eventSource.onerror = (error) => {
    console.error('SSE error:', error);
    eventSource.close();
    updateConnectionStatus('disconnected');

    // Attempt reconnection
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      console.log(`Reconnecting SSE... Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
      setTimeout(connectSSE, RECONNECT_DELAY);
    } else {
      console.warn('SSE reconnection failed. Falling back to polling.');
      fallbackToPolling();
    }
  };
}

// Fallback to polling if SSE fails
function fallbackToPolling() {
  updateConnectionStatus('polling');
  setInterval(async () => {
    const response = await fetch('/api/life-counter/pending-confirmations');
    const data = await response.json();
    if (data.count > 0) {
      data.confirmations.forEach(displayConfirmationModal);
    }
  }, 30000); // Poll every 30 seconds
}

// Disconnect SSE when user logs out or navigates away
function disconnectSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

// Auto-connect on page load (if user is logged in)
if (isUserLoggedIn()) {
  connectSSE();
}

// Clean up on page unload
window.addEventListener('beforeunload', disconnectSSE);
```

---

## Server-Side Implementation (Flask)

### SSE Stream Generator

```python
from flask import Response, stream_with_context, current_app
from flask_login import login_required, current_user
import json
import time

@app.route('/api/notifications/stream')
@login_required
def notification_stream():
    """
    Server-Sent Events stream for real-time notifications.
    """
    def generate():
        # Initial heartbeat
        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': int(time.time())})}\n\n"

        # Send all pending confirmations on initial connect
        pending = get_pending_confirmations(current_user.id)
        for confirmation in pending:
            payload = format_confirmation_payload(confirmation)
            yield f"event: pending_confirmation\ndata: {json.dumps(payload)}\n\n"

        # Keep connection alive and check for new confirmations
        last_check = time.time()
        while True:
            # Check for new confirmations every 5 seconds
            time.sleep(5)

            # Send heartbeat every 30 seconds
            if time.time() - last_check >= 30:
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': int(time.time())})}\n\n"
                last_check = time.time()

            # Check for new pending confirmations
            new_confirmations = get_new_confirmations_since(current_user.id, last_check)
            for confirmation in new_confirmations:
                payload = format_confirmation_payload(confirmation)
                yield f"event: pending_confirmation\ndata: {json.dumps(payload)}\n\n"

            # Check for confirmation updates (opponent confirmed/disputed)
            updates = get_confirmation_updates_since(current_user.id, last_check)
            for update in updates:
                payload = format_update_payload(update)
                yield f"event: confirmation_update\ndata: {json.dumps(payload)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )
```

---

## Security Considerations

1. **Authentication**: SSE endpoint requires Flask-Login session cookie. Unauthenticated requests return 401.
2. **Authorization**: Each user only receives notifications for their own pending confirmations.
3. **Rate Limiting**: Consider limiting concurrent SSE connections per user (max 3 connections).
4. **Timeout**: Close connections after 5 minutes of inactivity (client will auto-reconnect).
5. **Payload Validation**: Always sanitize user-provided data (usernames, deck URLs) before sending in SSE events.

---

## Browser Compatibility

| Browser | Version | Support | Notes |
|---------|---------|---------|-------|
| Chrome (Android) | 80+ | ✅ Full | Native EventSource support |
| Safari (iOS) | 12+ | ✅ Full | Native EventSource support |
| Firefox (Mobile) | 85+ | ✅ Full | Native EventSource support |
| Samsung Internet | 13+ | ✅ Full | Chromium-based |
| Opera (Mobile) | 60+ | ✅ Full | Chromium-based |

**No polyfill required** - All target browsers support EventSource API natively.

---

## Testing SSE

### Manual Testing with cURL

```bash
curl -N -H "Accept: text/event-stream" \
  -H "Cookie: session=your_session_cookie" \
  https://sorcererssummit.com/api/notifications/stream
```

Expected output:
```text
event: heartbeat
data: {"timestamp": 1709999999}

event: pending_confirmation
data: {"confirmation_id": 42, ...}
```

### Automated Testing

```python
# tests/test_notification_stream.py
def test_sse_stream_requires_auth(client):
    """Test that SSE endpoint requires authentication."""
    response = client.get('/api/notifications/stream')
    assert response.status_code == 401

def test_sse_stream_sends_pending_confirmations(client, authenticated_user):
    """Test that SSE stream sends pending confirmations on connect."""
    # Create pending confirmation for authenticated_user
    create_mock_confirmation(opponent_id=authenticated_user.id)

    # Connect to SSE stream
    response = client.get('/api/notifications/stream', stream=True)
    assert response.status_code == 200
    assert response.content_type == 'text/event-stream'

    # Read first event
    events = list(response.iter_lines())
    assert any(b'event: pending_confirmation' in line for line in events)
```

---

## Monitoring & Debugging

### Server-Side Logging

```python
import logging

logger = logging.getLogger('sse_notifications')

def generate():
    logger.info(f"SSE connection opened for user {current_user.id}")
    try:
        # ... stream logic ...
        yield ...
    except GeneratorExit:
        logger.info(f"SSE connection closed for user {current_user.id}")
    except Exception as e:
        logger.error(f"SSE error for user {current_user.id}: {e}")
        raise
```

### Client-Side Debugging

```javascript
eventSource.addEventListener('error', (event) => {
  if (event.target.readyState === EventSource.CONNECTING) {
    console.log('SSE reconnecting...');
  } else if (event.target.readyState === EventSource.CLOSED) {
    console.error('SSE connection closed');
  }
});
```

---

## Next Steps

- ✅ SSE notification contract defined
- ⬜ Create quickstart guide in `quickstart.md`
- ⬜ Update agent context with new technologies
